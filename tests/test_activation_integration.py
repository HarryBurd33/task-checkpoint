import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import test_router_runtime as rt
SCRIPTS = rt.SCRIPTS
import account
import checkpoint as cp


class ActivationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = rt.RouterRuntimeTests('test_real_trigger_launch_acceptance_and_duplicate_completion')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.store = self.root / '.checkpoint'
        self.state = self.root / '.account'
        self.state.mkdir()
        # Keep account telemetry/private state outside the repo fingerprint.
        (self.root / '.gitignore').write_text('.checkpoint/\n.account/\n')
        self.fixture.prepare()
        cp.atomic(self.state / 'config.json', cp.encoded({'version': 1, 'enabled': True,
            'guard_percent': 20, 'projects': [{'root': str(self.root), 'task_id': 'fixture',
            'project_id': 'fixture', 'scheduled_dispatch': True}]}))

    def reading(self, remaining=5):
        return {'source': 'codex-app-server', 'observed_at': cp.now(),
            'account': {'account': {'type': 'chatgpt'}}, 'models': {'data': []},
            'rate_limits': {'ordinaryUsageAllowed': True, 'rateLimits': {'primary': {'usedPercent': 100-remaining}}}}

    def tick(self, remaining=5):
        with mock.patch('codex_probe.probe', return_value=self.reading(remaining)):
            return account.tick(self.state)

    def test_background_tick_preserves_without_hook_and_without_taking_lease(self):
        owner = cp.read(self.store / 'owner.json')
        source = (self.store / 'input.json').read_bytes()
        result = self.tick()
        marker = cp.read(self.store / 'automatic-stop.json')
        self.assertEqual(marker['checkpoint_status'], 'verified')
        self.assertEqual(result['preservation']['projects'][0]['status'], 'checkpoint-verified')
        self.assertEqual(cp.latest(self.store)[0]['trigger'], 'low-resource')
        self.assertEqual(cp.read(self.store / 'owner.json'), owner)
        self.assertEqual((self.store / 'input.json').read_bytes(), source)
        self.tick()
        self.assertEqual(cp.latest(self.store)[0]['id'], marker['checkpoint_id'])

    def test_marker_blocks_hook_after_recovery_until_fresh_resume(self):
        self.tick()
        self.tick(80)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'hook.py'), '--account-state', str(self.state)],
            input=json.dumps({'cwd': str(self.root), 'hook_event_name': 'PreToolUse'}), text=True, capture_output=True)
        self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')
        binding, store = cp.config(self.root)
        cp.Ownership(self.root, binding, store).release()
        state, inspected = cp.inspect(self.root)
        task = state['task']
        review = {'checkpoint_id': state['id'], 'task_id': state['task_id'],
            'next_action': task['next_action']['description'], 'verification': task['next_action']['verification'],
            'current_fingerprint': inspected['current_fingerprint'], 'observed_at': cp.now(),
            'authorization': {'confirmed': True, 'scope': 'fixture', 'source': 'test user'}, 'resolutions': {},
            'resources': {'adequate_for_bounded_action': True, 'evidence': 'fresh80percentreading', 'observed_at': cp.now()}}
        cp.atomic(store / 'review.json', cp.encoded(review))
        cp.resume(self.root, store / 'review.json', 'explicit-resumer', [])
        self.assertFalse((store / 'automatic-stop.json').exists())
        self.assertTrue(list((store / 'automatic-stop-history').glob('*.json')))

    def test_project_permission_failure_does_not_hide_successful_collection(self):
        with mock.patch('account.cp.config', side_effect=PermissionError('Documents access denied')):
            result = self.tick()
        self.assertEqual(result['auth_type'], 'chatgpt')
        self.assertEqual(result['preservation']['projects'][0]['status'], 'preservation-failed')
        self.assertEqual(result['scheduled'][0]['result'], 'project-blocked')
        self.assertTrue((self.state / 'status.json').exists())

    def test_preservation_precedes_and_blocks_scheduled_dispatch(self):
        cp.atomic(self.store / 'router-schedule.json', cp.encoded({'status': 'pending', 'at': '2000-01-01T00:00:00+00:00'}))
        with mock.patch('router.wake') as wake:
            result = self.tick()
        wake.assert_not_called()
        self.assertEqual(result['scheduled'][0]['result'], 'automatic-stop-persists')

    def test_retained_lease_cannot_bypass_stop_through_direct_execution(self):
        self.tick()
        self.tick(80)
        with self.assertRaisesRegex(cp.Fault, 'Automatic stop persists'):
            self.fixture.dispatch()
        with self.assertRaisesRegex(cp.Fault, 'Automatic stop persists'):
            cp.run_boundary(self.root, self.fixture.source, [sys.executable, '-c', 'raise AssertionError("must not start")'], [])
