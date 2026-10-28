"""Owner, workspace and freshness regressions at the allowance boundary."""
import contextlib
import datetime as dt
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'))
import checkpoint as cp
import reserve
import test_reserve_policy as fixtures
import test_reserve_integration as integration


class ReserveHardeningTests(unittest.TestCase):
    setUp = fixtures.ReserveTests.setUp
    signals = fixtures.ReserveTests.signals
    activate = fixtures.ReserveTests.activate
    review = integration.ReserveIntegrationTests.review

    def grant(self, owner='fixture'):
        return reserve.grant(self.root, 'ten', self.signals(), 'Explicit user reserve bypass',
                             'Current user instruction', now=self.base, owner=owner)

    def assessment(self, **kwargs):
        return reserve.assess(self.root, self.signals(11), **kwargs)

    def test_pending_without_lease_requires_same_intended_owner_at_activation(self):
        self.grant()
        self.assertFalse(reserve.blocked(self.assessment(allow_pending=True)))
        self.assertTrue(reserve.blocked(self.assessment()))
        owner = cp.Ownership(self.root, self.binding, self.store).acquire('other')
        cp.atomic(self.store/'resume.json', cp.encoded({'checkpoint_id': self.saved['id'],
                  'owner': owner, 'resumed_at': cp.now()}))
        with self.assertRaises(cp.Fault):
            reserve.activate(self.root)
        self.assertEqual(cp.read(self.store/reserve.NAME)['state'], 'pending_resume')

    def test_pending_without_lease_activates_after_matching_reviewed_owner(self):
        self.grant(); self.activate()
        self.assertFalse(reserve.blocked(self.assessment()))

    def test_pending_and_active_reject_other_workspace_or_git_directory(self):
        self.grant()
        workspace = reserve._workspace(self.root)
        for active in (False, True):
            if active:
                self.activate()
            for key in ('root', 'git_common_dir'):
                with mock.patch.object(reserve, '_workspace', return_value=dict(workspace, **{key: '/another/workspace'})):
                    result = self.assessment(allow_pending=True)
                    self.assertTrue(reserve.blocked(result))
                    self.assertIn('workspace', result['override']['reason'])

    def test_existing_owner_must_match_explicit_mutation_owner(self):
        cp.Ownership(self.root, self.binding, self.store).acquire('unrelated')
        with self.assertRaises(cp.Fault):
            self.grant()
        self.assertFalse((self.store/reserve.NAME).exists())
        self.assertEqual(cp.Ownership(self.root, self.binding, self.store).check()['owner'], 'unrelated')

    def test_pending_grant_pins_existing_lease(self):
        ownership = cp.Ownership(self.root, self.binding, self.store)
        ownership.acquire('fixture'); self.grant(); ownership.release(); ownership.acquire('fixture')
        self.assertTrue(reserve.blocked(self.assessment(allow_pending=True)))

    def test_active_grant_rejects_release_and_reacquisition(self):
        self.grant(); self.activate()
        ownership = cp.Ownership(self.root, self.binding, self.store)
        ownership.release()
        self.assertTrue(reserve.blocked(self.assessment()))
        ownership.acquire('fixture')
        self.assertTrue(reserve.blocked(self.assessment()))

    def test_active_grant_requires_unchanged_current_resume_receipt(self):
        self.grant(); self.activate()
        path = self.store/'resume.json'
        receipt = cp.read(path)
        cp.atomic(path, cp.encoded(dict(receipt, checkpoint_id='unrelated')))
        self.assertTrue(reserve.blocked(self.assessment()))
        cp.atomic(path, cp.encoded(receipt))
        self.assertFalse(reserve.blocked(self.assessment()))
        path.unlink()
        self.assertTrue(reserve.blocked(self.assessment()))

    def test_repeat_explicit_reviewed_resume_refreshes_receipt_binding(self):
        self.grant()
        cp.resume(self.root, self.review(), 'fixture', [])
        first = cp.read(self.store/reserve.NAME)['resume_receipt_sha256']
        cp.resume(self.root, self.review(), 'fixture', [])
        current = cp.read(self.store/reserve.NAME)['resume_receipt_sha256']
        self.assertNotEqual(first, current)
        self.assertEqual(current, cp.sha(cp.content(self.store/'resume.json')))
        self.assertFalse(reserve.blocked(self.assessment()))

    def test_explicit_mutations_reject_wrong_intended_owner_before_writes(self):
        self.grant()
        previous = cp.content(self.store/reserve.NAME)
        with self.assertRaises(cp.Fault):
            reserve.prepare_review(self.root, 'Continue task', 'Current user', 'Fresh quota', owner='other')
        self.assertFalse((self.store/'allowance-resume-review.json').exists())
        with self.assertRaises(cp.Fault):
            reserve.revoke(self.root, 'Current user', owner='other')
        self.assertEqual(cp.content(self.store/reserve.NAME), previous)

    def test_opt_in_account_gate_blocks_unknown_without_inventing_low(self):
        cases = [{'records': []}, self.signals(at=self.base-dt.timedelta(minutes=3))]
        unsupported = self.signals(); unsupported['records'][0]['supported'] = False
        cases.append(unsupported)
        for signals in cases:
            self.assertFalse(reserve.blocked(reserve.assess(self.root, signals)))
            result = reserve.assess(self.root, signals, require_account=True)
            self.assertTrue(reserve.blocked(result)); self.assertEqual(result['low'], [])
        self.assertFalse(reserve.blocked(reserve.assess(self.root, self.signals(80), require_account=True)))

    def test_cli_requires_owner_for_every_mutating_command(self):
        commands = [['grant', '--mode', 'ten', '--signals', '/tmp/signals.json', '--reason', 'user', '--source', 'user'],
                    ['prepare-review', '--scope', 'same', '--source', 'user', '--resources-evidence', 'fresh'],
                    ['revoke', '--reason', 'user']]
        for command in commands:
            args = ['--root', str(self.root)] + command
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                reserve.build_parser().parse_args(args)
            self.assertEqual(reserve.build_parser().parse_args(args + ['--owner', 'fixture']).owner, 'fixture')
        self.assertEqual(reserve.build_parser().parse_args(['--root', str(self.root), 'status']).command, 'status')


if __name__ == '__main__':
    unittest.main()
