"""Recovered-quota bootstrap, using isolated Git and callback fixtures only."""
import datetime as dt
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'
sys.path.insert(0, str(SCRIPTS))
import checkpoint as cp
import maintenance
import monitor
import reserve
import test_reserve_policy as fixtures


class NormalRecoveryTests(unittest.TestCase):
    setUp = fixtures.ReserveTests.setUp
    signals = fixtures.ReserveTests.signals

    def stopped(self, secondary=False, owned=False):
        if owned:
            cp.Ownership(self.root, self.binding, self.store).acquire('fixture')
        self.account = self.root.parent / ('normal-recovery-' + self.root.name)
        self.account.mkdir()
        self.addCleanup(lambda: shutil.rmtree(self.account))
        cp.atomic(self.account/'config.json', cp.encoded({'enabled': True, 'guard_percent': 20}))
        low = self.signals(20)
        if secondary:
            low['records'] += self.signals(60, window='daily')['records']
        cp.atomic(self.account/'signals.json', cp.encoded(low))
        monitor.stop_for_signals(self.root, low, self.account, require_account=True)
        healthy = self.signals(80)
        if secondary:
            healthy['records'] += self.signals(90, window='daily')['records']
        cp.atomic(self.account/'signals.json', cp.encoded(healthy))
        return healthy

    def state(self):
        names = ('automatic-stop.json', 'owner.json', 'resume.json', 'allowance-override.json',
                 'latest.json', 'review.json', 'allowance-resume-review.json')
        return {n: (self.store/n).read_bytes() if (self.store/n).exists() else None for n in names}

    def prepare(self):
        return reserve.prepare_review(self.root, 'Explicit same-task bounded continuation',
                                      'Current isolated fixture user', 'Fresh fixture observations', 'fixture')

    def invoke(self, command='echo ordinary'):
        event = {'cwd': str(self.root), 'session_id': 'fixture-chat',
                 'hook_event_name': 'PreToolUse', 'tool_name': 'exec_command',
                 'tool_input': {'cmd': command}}
        result = subprocess.run([sys.executable, str(SCRIPTS/'hook.py'), '--account-state', str(self.account)],
                                input=json.dumps(event), text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def test_supported_cli_normal_review_then_explicit_resume_uses_live_collector(self):
        self.stopped(secondary=True)
        self.assertEqual(cp.read(self.store/'signals.json')['records'][0]['remaining'], 20)
        before = self.state()
        argv = ['python3', str(SCRIPTS/'reserve.py'), '--root', str(self.root.resolve()),
                'prepare-review', '--owner', 'fixture', '--scope', 'Same task continuation',
                '--source', 'Current fixture user', '--resources-evidence', 'Fresh fixture readings']
        command = shlex.join(argv)
        self.assertTrue(maintenance.classify({'tool_name': 'exec_command',
                        'tool_input': {'cmd': command}}, self.root.resolve(), self.account)[0])
        self.assertEqual(self.invoke(command), {})
        result = subprocess.run(argv, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        prepared = json.loads(result.stdout)
        self.assertEqual(Path(prepared['review']), (self.store/'review.json').resolve())
        after = self.state()
        for name in before:
            if name != 'review.json':
                self.assertEqual(before[name], after[name], name)
        self.assertFalse(prepared['implementation_allowed'])
        self.assertEqual(self.invoke()['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertFalse(cp.Ownership(self.root, self.binding, self.store).tip())
        resumed = cp.resume(self.root, Path(prepared['review']), 'fixture', [])
        self.assertTrue(resumed['implementation_allowed'])
        self.assertFalse((self.store/'automatic-stop.json').exists())
        self.assertFalse((self.store/'allowance-override.json').exists())
        self.assertEqual(self.invoke(), {})

    def test_normal_review_preserves_existing_owner_and_old_review(self):
        self.stopped(owned=True)
        owner = (self.store/'owner.json').read_bytes()
        (self.store/'review.json').write_text('{"historical":"keep"}\n')
        self.prepare()
        self.assertEqual((self.store/'owner.json').read_bytes(), owner)
        self.assertTrue((self.store/'automatic-stop.json').exists())
        backups = list((self.store/'review-history').glob('*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), '{"historical":"keep"}\n')

    def test_unhealthy_or_unidentified_readings_do_not_prepare(self):
        self.stopped(secondary=True)
        healthy = self.signals(80)
        healthy['records'] += self.signals(90, window='daily')['records']
        cases = {'low': self.signals(10), 'missing': {'records': []},
                 'stale': self.signals(80, at=self.base-dt.timedelta(minutes=3)),
                 'future': self.signals(80, at=self.base+dt.timedelta(minutes=1)),
                 'wrong-account': self.signals(80, account='other'),
                 'missing-window': self.signals(80)}
        for field, value in [('supported', False), ('blocked', True)]:
            data = json.loads(json.dumps(healthy)); data['records'][0][field] = value
            cases[field] = data
        for name, readings in cases.items():
            with self.subTest(name=name):
                cp.atomic(self.account/'signals.json', cp.encoded(readings))
                before = self.state()
                with self.assertRaises(cp.Fault):
                    self.prepare()
                self.assertEqual(before, self.state())

    def test_lost_window_cannot_resume_even_after_a_good_review(self):
        self.stopped(secondary=True)
        review = self.prepare()
        cp.atomic(self.account/'signals.json', cp.encoded(self.signals(80)))
        before = self.state()
        with self.assertRaises(cp.Fault):
            cp.resume(self.root, Path(review['review']), 'fixture', [])
        self.assertEqual(before, self.state())

    def test_wrong_owner_worker_and_new_input_job_block_before_review(self):
        self.stopped(owned=True)
        before = self.state()
        with self.assertRaises(cp.Fault):
            reserve.prepare_review(self.root, 'Same task', 'Current fixture user', 'Fresh readings', 'other')
        self.assertEqual(before, self.state())
        cp.atomic(self.store/'router.json', cp.encoded({'active': {'status': 'unknown'}}))
        with self.assertRaises(cp.Fault):
            self.prepare()
        self.assertEqual(before, self.state())
        (self.store/'router.json').unlink()
        task = cp.read(self.source)
        task['jobs'] = [{'id': 'unresolved', 'status': 'unknown', 'kind': 'fixture',
                         'source': 'Current fixture', 'observed_at': cp.now()}]
        cp.atomic(self.source, cp.encoded(task))
        with self.assertRaises(cp.Fault):
            self.prepare()
        self.assertEqual(before, self.state())

    def test_incomplete_foreign_and_moved_stop_generation_block(self):
        self.stopped()
        original = cp.read(self.store/'automatic-stop.json')
        for changes in ({'checkpoint_status': 'pending'}, {'task_id': 'foreign'},
                        {'checkpoint_id': 'old-generation'}):
            with self.subTest(changes=changes):
                cp.atomic(self.store/'automatic-stop.json', cp.encoded(dict(original, **changes)))
                before = self.state()
                with self.assertRaises(cp.Fault):
                    self.prepare()
                self.assertEqual(before, self.state())

    def test_expired_review_stays_blocked_and_changed_repository_needs_reconciliation(self):
        self.stopped()
        prepared = self.prepare()
        path = Path(prepared['review']); review = cp.read(path)
        review['observed_at'] = (self.base-dt.timedelta(minutes=6)).isoformat()
        cp.atomic(path, cp.encoded(review)); before = self.state()
        with self.assertRaises(cp.Fault):
            cp.resume(self.root, path, 'fixture', [])
        self.assertEqual(before, self.state())
        (self.root/'work.txt').write_text('new user work\n')
        with self.assertRaises(cp.Fault):
            self.prepare()
        self.assertEqual(before, self.state())


if __name__ == '__main__':
    unittest.main()
