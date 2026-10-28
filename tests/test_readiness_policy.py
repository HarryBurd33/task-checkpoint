"""Readiness shares effective task reserve gates; notifications remain simulated."""
import datetime as dt
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'skills/task-checkpoint/scripts'))
import checkpoint as cp
import monitor
import readiness
import reserve


class ReadinessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for args in [('init', '-b', 'main'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@example.invalid')]:
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        (self.root / '.gitignore').write_text('.checkpoint/\n')
        (self.root / 'work.txt').write_text('isolated audit fixture\n')
        for args in [('add', '.'), ('commit', '-m', 'fixture')]:
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        self.store = self.root / '.checkpoint'
        self.store.mkdir()
        self.binding = {'schema_version': 1, 'task_id': 'readiness-audit', 'project_id': 'fixture/readiness-audit',
                        'store': None, 'ownership': 'local'}
        cp.atomic(self.store / 'config.json', cp.encoded(self.binding))
        source = self.store / 'input.json'
        cp.atomic(source, cp.encoded(cp.read(cp.ASSETS / 'task-template.json')))
        cp.checkpoint(self.root, source, 'milestone')
        cp.Ownership(self.root, self.binding, self.store).acquire('fixture-owner')
        reserve.configure(self.root, 35, 'fixture-owner', 'Current isolated user threshold', 'Current fixture user')
        self.base = readiness.stamp(cp.now())
        self.settings = {'enabled': True, 'notifier': 'unsupported', 'scheduler_id': 'fixture-only'}
        self.deliver = mock.Mock(return_value={'adapter': 'isolated-spy', 'display_observed': False})

    def signals(self, remaining, elapsed=0, reset=60):
        return {'records': [{'kind': 'codex_plan', 'remaining': remaining, 'unit': 'percent_remaining',
                             'guard': 20, 'source': 'isolated-audit-fixture',
                             'observed_at': (self.base + dt.timedelta(seconds=elapsed)).isoformat(),
                             'resets_at': (self.base + dt.timedelta(seconds=reset)).isoformat(),
                             'account_fingerprint': 'fixture-account', 'window': 'weekly'}]}

    def update(self, signals, elapsed=0):
        return readiness.update(self.root, signals, self.settings,
                                now=self.base + dt.timedelta(seconds=elapsed), deliver=self.deliver)

    def stop(self, remaining):
        result = monitor.stop_for_signals(self.root, self.signals(remaining))
        self.assertEqual(result['status'], 'checkpoint-verified')

    def test_custom_baseline35_stop30_arms_reset_ticket(self):
        self.stop(30)
        signals = self.signals(30)
        self.assertTrue(reserve.blocked(reserve.assess(self.root, signals, now=self.base)))
        result = self.update(signals)
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(result['not_before'], (self.base + dt.timedelta(seconds=120)).isoformat())
        self.deliver.assert_not_called()

    def test_after_reset30_is_still_low_for35_and_must_not_notify(self):
        self.stop(10)
        self.assertEqual(self.update(self.signals(10))['status'], 'pending')
        signals = self.signals(30, elapsed=121, reset=600)
        self.assertTrue(reserve.blocked(reserve.assess(self.root, signals, now=self.base + dt.timedelta(seconds=121))))
        before = (self.store / 'automatic-stop.json').read_bytes()
        result = self.update(signals, elapsed=121)
        self.assertEqual((self.store / 'automatic-stop.json').read_bytes(), before)
        self.assertNotEqual(result['status'], 'notified')
        self.deliver.assert_not_called()

    def test_active_ten_grant_does_not_delay_for_nonblocking_window(self):
        def dual(primary, secondary, elapsed=0, primary_reset=60):
            signals = self.signals(primary, elapsed=elapsed, reset=primary_reset)
            extra = dict(signals['records'][0], remaining=secondary, window='secondary',
                         resets_at=(self.base + dt.timedelta(seconds=3600)).isoformat())
            signals['records'].append(extra)
            return signals
        initial = dual(30, 18)
        self.assertEqual(monitor.stop_for_signals(self.root, initial)['status'], 'checkpoint-verified')
        reserve.grant(self.root, 'ten', initial, 'Explicit isolated user continuation',
                      'Current fixture user', owner='fixture-owner')
        review = reserve.prepare_review(self.root, 'Same isolated fixture', 'Current fixture user',
                                        'Fresh fixture quota and no uncertain jobs', owner='fixture-owner')
        cp.resume(self.root, Path(review['review']), 'fixture-owner', [])
        stopped = dual(8, 18)
        self.assertEqual(monitor.stop_for_signals(self.root, stopped)['status'], 'checkpoint-verified')
        assessment = reserve.assess(self.root, stopped)
        self.assertEqual([(r['window'], r['status']) for r in assessment['records']],
                         [('weekly', 'low'), ('secondary', 'ok')])
        # The grant was created after setUp; assess at a later clock value.
        observed_elapsed = (readiness.stamp(cp.now()) - self.base).total_seconds() + 1
        ticket = self.update(stopped, elapsed=observed_elapsed)
        recovered = dual(90, 90, elapsed=121, primary_reset=600)
        self.assertFalse(reserve.blocked(reserve.assess(self.root, recovered,
                         now=self.base + dt.timedelta(seconds=121))))
        result = self.update(recovered, elapsed=121)
        self.assertEqual(ticket['not_before'], (self.base + dt.timedelta(seconds=120)).isoformat())
        self.assertEqual(result['status'], 'notified')
        self.deliver.assert_called_once()

    def test_pending_grant_never_establishes_notification_readiness(self):
        self.stop(30)
        self.update(self.signals(30))
        reserve.grant(self.root, 'ten', self.signals(30), 'Explicit isolated continuation',
                      'Current fixture user', owner='fixture-owner')
        before = cp.content(self.store / reserve.NAME)
        result = self.update(self.signals(90, elapsed=121, reset=600), elapsed=121)
        self.assertEqual(result['status'], 'pending')
        self.assertIn('reviewed resume', result['reason'])
        self.assertEqual(cp.content(self.store / reserve.NAME), before)
        self.deliver.assert_not_called()

    def test_foreign_or_malformed_policy_requires_action_without_notification(self):
        self.stop(10)
        self.update(self.signals(10))
        path = self.store / reserve.POLICY_NAME
        original = cp.read(path)
        variants = [dict(original, task_id='foreign-task'), dict(original, percent=101)]
        for policy in variants:
            with self.subTest(policy=policy):
                cp.atomic(path, cp.encoded(policy))
                result = self.update(self.signals(90, elapsed=121, reset=600), elapsed=121)
                self.assertEqual(result['status'], 'user-action-required')
                self.assertIn('policy unverified', result['reason'])
                self.deliver.assert_not_called()
        path.write_text('{malformed-json')
        self.assertEqual(self.update(self.signals(90, elapsed=121, reset=600), 121)['status'], 'user-action-required')
        self.deliver.assert_not_called()

    def test_lower_local_baseline_notifies_when_recovered_below_shared_reserve(self):
        reserve.configure(self.root, 7.5, 'fixture-owner', 'Current isolated user threshold', 'Current fixture user')
        self.stop(5)
        self.update(self.signals(5))
        result = self.update(self.signals(10, elapsed=121, reset=600), 121)
        self.assertEqual(result['status'], 'notified')
        self.deliver.assert_called_once()
        self.assertTrue((self.store / 'automatic-stop.json').exists())

    def test_custom_baseline_healthy_reset_notifies_once_without_resuming(self):
        self.stop(30)
        self.update(self.signals(30))
        protected = {name: cp.content(self.store / name) for name in
                     ('automatic-stop.json', 'latest.json', 'owner.json', 'input.json', reserve.POLICY_NAME)}
        signals = self.signals(90, elapsed=121, reset=600)
        self.assertEqual(self.update(signals, 121)['status'], 'notified')
        self.assertEqual(self.update(signals, 121)['status'], 'notified')
        self.deliver.assert_called_once()
        self.assertEqual(protected, {name: cp.content(self.store / name) for name in protected})
        self.assertFalse((self.store / 'resume.json').exists())

    def test_unknown_or_denied_account_stays_unready(self):
        self.stop(30)
        self.update(self.signals(30))
        for variant in ('stale', 'unsupported', 'denied'):
            signals = self.signals(90, elapsed=121, reset=600)
            if variant == 'stale':
                signals['records'][0]['observed_at'] = self.base.isoformat()
            elif variant == 'unsupported':
                signals['records'][0]['supported'] = False
            else:
                signals['records'][0]['blocked'] = True
            with self.subTest(variant=variant):
                self.assertEqual(self.update(signals, 121)['status'], 'pending')
                self.deliver.assert_not_called()

    def test_changed_policy_lease_does_not_emit_ready(self):
        self.stop(10)
        self.assertEqual(self.update(self.signals(10))['status'], 'pending')
        cp.Ownership(self.root, self.binding, self.store).release()
        signals = self.signals(90, elapsed=121, reset=600)
        with self.assertRaises(cp.Fault):
            reserve.assess(self.root, signals, now=self.base + dt.timedelta(seconds=121))
        result = self.update(signals, elapsed=121)
        self.assertNotEqual(result['status'], 'notified')
        self.deliver.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
