"""Task-local numeric reserves keep the existing preservation and resume gates."""
import copy
import datetime as dt
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'))
import checkpoint as cp
import hook
import monitor
import reserve
import test_reserve_policy as fixtures
import test_reserve_integration as integration


class PercentReserveTests(unittest.TestCase):
    setUp = fixtures.ReserveTests.setUp
    signals = fixtures.ReserveTests.signals
    review = integration.ReserveIntegrationTests.review

    def grant(self, percent=7.5, signals=None, owner='fixture'):
        return reserve.grant(self.root, 'percent', signals or self.signals(),
                             'User explicitly chose a remaining percentage',
                             'Current isolated fixture user', owner=owner, percent=percent)

    def resume(self):
        cp.resume(self.root, self.review(), 'fixture', [])

    def test_fractional_choice_pending_review_and_exact_boundary(self):
        value = self.grant()
        self.assertEqual(value['percent'], 7.5)
        self.assertEqual(value['state'], 'pending_resume')
        self.assertFalse(value['automatic_resume'])
        self.assertTrue(cp.policy(self.signals(), self.root)['checkpoint_required'])
        self.resume()
        for remaining, stopped in [(7.5001, False), (7.5, True), (7.4999, True), (0, True)]:
            with self.subTest(remaining=remaining):
                summary = reserve.assess(self.root, self.signals(remaining))
                self.assertEqual(reserve.blocked(summary), stopped)
                self.assertEqual(summary['records'][0]['effective_guard'], 7.5)

    def test_zero_percentage_is_distinct_from_exhaustion(self):
        self.grant(0)
        self.resume()
        self.assertFalse(cp.policy(self.signals(0.001), self.root)['checkpoint_required'])
        self.assertTrue(cp.policy(self.signals(0), self.root)['checkpoint_required'])
        denied = self.signals(90)
        denied['records'][0]['blocked'] = True
        self.assertTrue(cp.policy(denied, self.root)['checkpoint_required'])

    def test_invalid_percentages_and_irrelevant_arguments_write_nothing(self):
        for value in (-0.01, 100.01, float('nan'), float('inf'), -float('inf'), True, '7.5', None):
            with self.subTest(value=value), self.assertRaises(cp.Fault):
                self.grant(value)
            self.assertFalse((self.store / reserve.NAME).exists())
        for mode in ('ten', 'exhaustion'):
            with self.assertRaises(cp.Fault):
                reserve.grant(self.root, mode, self.signals(), 'user', 'user', percent=5)
        self.assertEqual(reserve._threshold('percent', 100), 100)

    def test_equal_or_higher_reserve_cannot_resume_low_windows(self):
        for value in (14, 20, 100):
            with self.subTest(value=value), self.assertRaises(cp.Fault):
                self.grant(value)
        self.assertFalse((self.store / reserve.NAME).exists())

    def test_unpreserved_or_healthy_task_cannot_prearm_percentage(self):
        with self.assertRaises(cp.Fault):
            self.grant(7.5, self.signals(80))
        cp.checkpoint(self.root, self.source, 'milestone')
        with self.assertRaises(cp.Fault):
            self.grant()
        self.assertFalse((self.store / reserve.NAME).exists())

    def test_all_windows_provider_denial_and_unknown_are_enforced(self):
        signals = self.signals()
        signals['records'] += self.signals(40, window='secondary')['records']
        self.grant(signals=signals)
        self.resume()
        for mutation in ('low', 'missing', 'stale', 'provider-denied', 'foreign'):
            changed = copy.deepcopy(signals)
            if mutation == 'low':
                changed['records'][1]['remaining'] = 7.5
            elif mutation == 'missing':
                changed['records'].pop()
            elif mutation == 'stale':
                changed['records'][1]['observed_at'] = (self.base - dt.timedelta(minutes=3)).isoformat()
            elif mutation == 'provider-denied':
                changed['records'][1]['blocked'] = True
            else:
                changed['records'][1]['account_fingerprint'] = 'foreign'
            with self.subTest(mutation=mutation):
                self.assertTrue(reserve.blocked(reserve.assess(self.root, changed)))

    def test_other_resources_and_owner_still_block(self):
        cp.Ownership(self.root, self.binding, self.store).acquire('other')
        with self.assertRaises(cp.Fault):
            self.grant()
        cp.Ownership(self.root, self.binding, self.store).release()
        self.grant()
        self.resume()
        signals = self.signals()
        signals['records'].append({'kind': 'context', 'remaining': 0, 'source': 'fixture',
                                   'unit': 'tokens_remaining', 'observed_at': self.base.isoformat()})
        self.assertIn('context', reserve.kinds(reserve.assess(self.root, signals)))

    def test_collector_stop_then_explicit_lower_percentage_resume(self):
        self.grant(7.5)
        self.resume()
        result = monitor.stop_for_signals(self.root, self.signals(7.5))
        self.assertTrue((self.store / 'automatic-stop.json').exists(), result)
        self.grant(3, self.signals(7))
        self.assertTrue(cp.policy(self.signals(7), self.root)['checkpoint_required'])
        self.resume()
        self.assertFalse((self.store / 'automatic-stop.json').exists())
        self.assertFalse(cp.policy(self.signals(3.1), self.root)['checkpoint_required'])
        self.assertTrue(cp.policy(self.signals(3), self.root)['checkpoint_required'])

    def test_reset_and_revoke_restore_default_without_mutating_signals(self):
        self.grant()
        self.resume()
        signals = self.signals(8)
        before = copy.deepcopy(signals)
        self.assertFalse(reserve.blocked(reserve.assess(self.root, signals)))
        self.assertEqual(signals, before)
        later = self.base + dt.timedelta(hours=2)
        fresh = self.signals(14, at=later, reset=later + dt.timedelta(hours=1))
        self.assertTrue(reserve.blocked(reserve.assess(self.root, fresh, now=later)))
        reserve.revoke(self.root, 'User restored default', owner='fixture')
        self.assertTrue(reserve.blocked(reserve.assess(self.root, signals)))

    def test_tampered_saved_percentage_fails_closed(self):
        self.grant()
        value = cp.read(self.store / reserve.NAME)
        for changed in (None, '7.5', 101, True):
            invalid = dict(value, percent=changed)
            cp.atomic(self.store / reserve.NAME, cp.encoded(invalid))
            with self.subTest(changed=changed), self.assertRaises(cp.Fault):
                reserve.assess(self.root, self.signals())

    def test_cli_grant_and_stopped_maintenance_accept_percent_argument(self):
        scripts = Path(reserve.__file__).resolve().parent
        signal_path = self.store / 'signals.json'
        cp.atomic(signal_path, cp.encoded(self.signals()))
        args = ['python3', str(scripts / 'reserve.py'), '--root', str(self.root.resolve()),
                'grant', '--mode', 'percent', '--percent', '7.5', '--signals', str(signal_path.resolve()),
                '--reason', 'Explicit isolated user choice', '--source', 'Current fixture user', '--owner', 'fixture']
        event = {'tool_name': 'exec_command', 'tool_input': {'cmd': shlex.join(args)}}
        self.assertTrue(hook.maintenance(event, self.root.resolve()))
        args[0] = sys.executable
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cp.read(self.store / reserve.NAME)['percent'], 7.5)


class InitialReservePolicyTests(unittest.TestCase):
    setUp = fixtures.ReserveTests.setUp
    signals = fixtures.ReserveTests.signals
    review = integration.ReserveIntegrationTests.review

    def configure(self, percent=35, owner='fixture'):
        return reserve.configure(self.root, percent, owner, 'User chose initial task threshold', 'Current fixture user')

    def own(self):
        return cp.Ownership(self.root, self.binding, self.store).acquire('fixture')

    def test_initial_percent_before_work_keeps_resume_and_global_signals(self):
        self.own()
        receipt = self.store / 'resume.json'
        receipt.write_text('{"existing": "receipt"}\n')
        old = receipt.read_bytes()
        value = self.configure(35.5)
        self.assertEqual(value['percent'], 35.5)
        self.assertFalse(value['automatic_resume'])
        self.assertEqual(receipt.read_bytes(), old)
        self.assertFalse((self.store / reserve.NAME).exists())
        for remaining, stopped in [(36, False), (35.5, True), (35, True)]:
            signals = self.signals(remaining)
            signals['records'][0]['guard'] = 20
            before = copy.deepcopy(signals)
            self.assertEqual(cp.policy(signals, self.root)['checkpoint_required'], stopped)
            self.assertEqual(signals, before)
        self.assertEqual(reserve.status(self.root)['reserve_policy']['percent'], 35.5)

    def test_initial_low_percent_and_zero_are_numeric_stops(self):
        self.own()
        for threshold in (7.5, 0):
            self.configure(threshold)
            self.assertFalse(cp.policy(self.signals(threshold + 0.1), self.root)['checkpoint_required'])
            self.assertTrue(cp.policy(self.signals(threshold), self.root)['checkpoint_required'])
        self.configure(100)
        self.assertTrue(cp.policy(self.signals(100), self.root)['checkpoint_required'])

    def test_no_owner_wrong_owner_invalid_percent_and_empty_authority_rejected(self):
        with self.assertRaises(cp.Fault):
            self.configure()
        self.own()
        with self.assertRaises(cp.Fault):
            self.configure(owner='another')
        for value in (-1, 101, float('nan'), float('inf'), True, None):
            with self.subTest(value=value), self.assertRaises(cp.Fault):
                self.configure(value)
        for reason, source in [('', 'user'), ('user', '')]:
            with self.assertRaises(cp.Fault):
                reserve.configure(self.root, 35, 'fixture', reason, source)
        self.assertFalse((self.store / reserve.POLICY_NAME).exists())

    def test_existing_stop_blocks_configure_without_changing_either_file(self):
        self.own()
        self.configure()
        monitor.stop_for_signals(self.root, self.signals(35))
        before = {p.name: p.read_bytes() for p in (self.store / reserve.POLICY_NAME, self.store / 'automatic-stop.json')}
        with self.assertRaises(cp.Fault):
            self.configure(0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.store / reserve.POLICY_NAME, self.store / 'automatic-stop.json')})

    def test_current_uncertain_jobs_and_active_workers_block_configuration(self):
        self.own()
        cp.atomic(self.store / 'router.json', cp.encoded({'active': {'id': 'fixture-uncertain'}}))
        with self.assertRaises(cp.Fault):
            self.configure()
        (self.store / 'router.json').unlink()
        task = cp.read(self.source)
        task['jobs'] = [{'id': 'new-job', 'kind': 'owned-child', 'status': 'unknown', 'source': 'fixture', 'observed_at': cp.now()}]
        cp.atomic(self.source, cp.encoded(task))
        with self.assertRaises(cp.Fault):
            self.configure()
        cp.checkpoint(self.root, self.source, 'milestone')
        task['jobs'] = []
        cp.atomic(self.source, cp.encoded(task))
        with self.assertRaises(cp.Fault):
            self.configure()

    def test_pending_or_active_grant_cannot_be_overwritten_by_configuration(self):
        self.own()
        reserve.grant(self.root, 'ten', self.signals(), 'Explicit fixture user', 'Current user', owner='fixture')
        with self.assertRaises(cp.Fault):
            self.configure(0)
        cp.resume(self.root, self.review(), 'fixture', [])
        with self.assertRaises(cp.Fault):
            self.configure(0)

    def test_foreign_binding_workspace_or_lease_policy_fails_closed(self):
        self.own()
        self.configure()
        original = cp.read(self.store / reserve.POLICY_NAME)
        variants = [dict(original, task_id='foreign'), dict(original, project_id='foreign'),
                    dict(original, workspace={'root': '/foreign', 'git_common_dir': '/foreign/.git'}),
                    dict(original, owner={'owner': 'fixture', 'token': 'foreign'}), dict(original, percent=101)]
        for invalid in variants:
            cp.atomic(self.store / reserve.POLICY_NAME, cp.encoded(invalid))
            with self.assertRaises(cp.Fault):
                reserve.assess(self.root, self.signals(99))
            self.assertFalse(reserve.status(self.root)['implementation_allowed'])
        cp.atomic(self.store / reserve.POLICY_NAME, cp.encoded(original))
        cp.Ownership(self.root, self.binding, self.store).release()
        self.own()
        with self.assertRaises(cp.Fault):
            reserve.assess(self.root, self.signals(99))

    def test_unknown_provider_denial_other_resource_and_secondary_not_waived(self):
        self.own()
        self.configure(0)
        self.assertTrue(reserve.blocked(reserve.assess(self.root, {'records': []})))
        denied = self.signals(99)
        denied['records'][0]['blocked'] = True
        self.assertTrue(reserve.blocked(reserve.assess(self.root, denied)))
        secondary = self.signals(90)
        secondary['records'] += self.signals(0, window='secondary')['records']
        self.assertTrue(reserve.blocked(reserve.assess(self.root, secondary)))
        context = self.signals(90)
        context['records'].append({'kind': 'context', 'remaining': 0, 'unit': 'tokens_remaining',
                                   'source': 'fixture', 'observed_at': self.base.isoformat()})
        self.assertIn('context', reserve.kinds(reserve.assess(self.root, context)))
        stale = self.signals(90, at=self.base - dt.timedelta(minutes=3))
        self.assertTrue(reserve.blocked(reserve.assess(self.root, stale)))

    def test_configured_stop_grant_resume_and_revoke_return_to_task_baseline(self):
        self.own()
        self.configure(35)
        monitor.stop_for_signals(self.root, self.signals(35))
        reserve.grant(self.root, 'percent', self.signals(34), 'Explicit continuation', 'Current user', owner='fixture', percent=25)
        cp.resume(self.root, self.review(), 'fixture', [])
        self.assertFalse(cp.policy(self.signals(30), self.root)['checkpoint_required'])
        reserve.revoke(self.root, 'Restore baseline', owner='fixture')
        self.assertTrue(cp.policy(self.signals(30), self.root)['checkpoint_required'])

    def test_task_policy_is_not_exported_in_portable_bundle(self):
        import transfer
        import zipfile
        self.own()
        self.configure()
        archive = self.store / 'bundle.zip'
        transfer.package(self.root, archive)
        with zipfile.ZipFile(archive) as bundle:
            self.assertFalse(any('reserve-policy' in name for name in bundle.namelist()))

    def test_cli_configuration_does_not_write_grant_or_resume(self):
        self.own()
        args = [sys.executable, str(Path(reserve.__file__).resolve()), '--root', str(self.root.resolve()),
                'configure', '--percent', '33.3', '--owner', 'fixture', '--reason', 'Explicit fixture choice', '--source', 'Current fixture user']
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cp.read(self.store / reserve.POLICY_NAME)['percent'], 33.3)
        self.assertFalse((self.store / reserve.NAME).exists())
        self.assertFalse((self.store / 'resume.json').exists())


class RetireReservePolicyTests(unittest.TestCase):
    setUp = fixtures.ReserveTests.setUp
    signals = fixtures.ReserveTests.signals
    review = integration.ReserveIntegrationTests.review
    own = InitialReservePolicyTests.own
    configure = InitialReservePolicyTests.configure

    def retire(self, owner=None):
        return reserve.retire_policy(self.root, 'Current user retires prior local policy',
                                     'Current fixture user message', owner=owner)

    def test_normal_release_retirement_then_fresh_reviewed_resume(self):
        self.own()
        self.configure(35)
        monitor.stop_for_signals(self.root, self.signals(35))
        cp.atomic(self.store / 'signals.json', cp.encoded(self.signals(90)))
        old_policy = cp.content(self.store / reserve.POLICY_NAME)
        old_stop = cp.content(self.store / 'automatic-stop.json')
        cp.Ownership(self.root, self.binding, self.store).release()
        with self.assertRaises(cp.Fault):
            cp.resume(self.root, self.review(), 'next-owner', [])
        result = self.retire()
        self.assertTrue(result['retired'])
        self.assertEqual(cp.content(Path(result['archive'])), old_policy)
        self.assertEqual(cp.content(self.store / 'automatic-stop.json'), old_stop)
        self.assertFalse((self.store / 'owner.json').exists())
        self.assertFalse((self.store / 'resume.json').exists())
        self.assertFalse(result['automatic_resume'])
        cp.resume(self.root, self.review(), 'next-owner', [])
        self.assertEqual(cp.Ownership(self.root, self.binding, self.store).check()['owner'], 'next-owner')
        self.assertFalse((self.store / 'automatic-stop.json').exists())

    def test_active_lease_requires_explicit_matching_owner(self):
        self.own()
        self.configure()
        before = cp.content(self.store / reserve.POLICY_NAME)
        for owner in (None, '', 'foreign'):
            with self.subTest(owner=owner), self.assertRaises(cp.Fault):
                self.retire(owner)
            self.assertEqual(cp.content(self.store / reserve.POLICY_NAME), before)
        self.assertTrue(self.retire('fixture')['retired'])
        self.assertEqual(cp.Ownership(self.root, self.binding, self.store).check()['owner'], 'fixture')

    def test_uncertain_router_and_new_input_jobs_deny_retirement(self):
        self.own()
        self.configure()
        cp.atomic(self.store / 'router.json', cp.encoded({'active': {'status': 'unknown'}}))
        with self.assertRaises(cp.Fault):
            self.retire('fixture')
        (self.store / 'router.json').unlink()
        task = cp.read(self.source)
        task['jobs'] = [{'id': 'job', 'kind': 'owned-child', 'status': 'unknown', 'source': 'fixture', 'observed_at': cp.now()}]
        cp.atomic(self.source, cp.encoded(task))
        with self.assertRaises(cp.Fault):
            self.retire('fixture')
        cp.checkpoint(self.root, self.source, 'milestone')
        task['jobs'] = []
        cp.atomic(self.source, cp.encoded(task))
        with self.assertRaises(cp.Fault):
            self.retire('fixture')
        self.assertTrue((self.store / reserve.POLICY_NAME).exists())

    def test_retirement_preserves_grant_stop_resume_and_owner(self):
        self.own()
        self.configure()
        monitor.stop_for_signals(self.root, self.signals(35))
        reserve.grant(self.root, 'percent', self.signals(34), 'Explicit continuation', 'Current user', owner='fixture', percent=25)
        (self.store / 'resume.json').write_text('{"historical": true}\n')
        names = ('automatic-stop.json', 'resume.json', 'owner.json', reserve.NAME)
        before = {name: cp.content(self.store / name) for name in names}
        self.retire('fixture')
        self.assertEqual(before, {name: cp.content(self.store / name) for name in names})
        self.assertTrue(cp.policy(self.signals(34), self.root)['checkpoint_required'])

    def test_retirement_needs_current_reason_source_and_rejects_stale_receipt(self):
        self.own()
        self.configure()
        for reason, source in [('', 'user'), ('user', '')]:
            with self.assertRaises(cp.Fault):
                reserve.retire_policy(self.root, reason, source, owner='fixture')
        receipt = cp.content(self.store / 'owner.json')
        cp.Ownership(self.root, self.binding, self.store).release()
        cp.atomic(self.store / 'owner.json', receipt)
        with self.assertRaises(cp.Fault):
            self.retire()
