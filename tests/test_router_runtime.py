import copy
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'
sys.path.insert(0, str(SCRIPTS))
import checkpoint as cp
import router


class RouterRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.g('init', '-b', 'main')
        self.g('config', 'user.name', 'Router Fixture')
        self.g('config', 'user.email', 'fixture@example.invalid')
        (self.root / '.gitignore').write_text('.checkpoint/\n')
        (self.root / 'work.txt').write_text('preserved\n')
        self.g('add', '.')
        self.g('commit', '-m', 'Fixture')
        subprocess.run([sys.executable, str(SCRIPTS / 'checkpoint.py'), '--root', str(self.root),
                        'init', '--task', 'fixture', '--project-id', 'fixture', '--ownership', 'local'],
                       check=True, capture_output=True)
        self.source = self.root / '.checkpoint/input.json'
        self.config_path = self.root / '.checkpoint/router-config.json'
        self.task = cp.read(cp.ASSETS / 'task-template.json')
        self.task['routing'] = {'id': 'one', 'task_class': 'fixture', 'complexity': 'routine', 'risk': 'low',
            'required_tools': ['python'], 'privacy': 'private', 'allowed_providers': ['fixture'],
            'budget': {'max_attempts': 2, 'max_wall_seconds': 30, 'max_api_usd': None},
            'dependencies': [], 'estimated_work_seconds': 1,
            'acceptance': [{'id': 'result', 'argv': [sys.executable, '-c',
                "import os;from pathlib import Path;assert Path(os.environ['CHECKPOINT_RESULT']).read_text()=='42'"]}]}
        def worker(name, rank, result):
            return {'id': name, 'model': 'deterministic-fixture', 'test_only': True, 'provider': 'fixture',
                'billing': 'local', 'available': True, 'enabled': True,
                'availability': {'source': 'test subprocess', 'observed_at': cp.now()},
                'tools': ['python'], 'privacy': ['private'], 'max_complexity': 'complex',
                'rank': rank, 'effort': 'medium', 'interface': 'fixture', 'fixture_result': result,
                'argv': [sys.executable, '-c', "import os;from pathlib import Path;Path(os.environ['CHECKPOINT_RESULT']).write_text(" + repr(result) + ")"],
                'qualification': {'model': 'deterministic-fixture', 'effort': 'medium', 'task_classes': ['fixture'], 'passed': True, 'source': 'deterministic fixture',
                    'samples': 1, 'acceptance_rate': 1, 'mean_total_seconds': 1 + rank, 'observed_at': cp.now()}}
        self.config = {'version': 1, 'queue_authority': 'checkpoint:fixture:fixture',
            'workers': [worker('small', 0, '42'), worker('large', 1, '42')], 'allowed_providers': ['fixture'],
            'allow_paid': False, 'max_retries': 1, 'unknown_telemetry': 'explicit_budget'}
        self.signals = {'records': []}
        self.prepare()

    def g(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.DEVNULL).decode().strip()

    def prepare(self):
        cp.atomic(self.source, cp.encoded(self.task))
        cp.atomic(self.config_path, cp.encoded(self.config))
        cp.checkpoint(self.root, self.source)
        binding, store = cp.config(self.root)
        if not (store / 'owner.json').exists():
            s, report = cp.inspect(self.root)
            review = {'checkpoint_id': s['id'], 'task_id': s['task_id'],
                'next_action': s['task']['next_action']['description'], 'verification': s['task']['next_action']['verification'],
                'current_fingerprint': report['current_fingerprint'], 'observed_at': cp.now(),
                'authorization': {'confirmed': True, 'scope': 'fixture', 'source': 'unit test'},
                'resources': {'adequate_for_bounded_action': True, 'evidence': 'bounded subprocess', 'observed_at': cp.now()},
                'resolutions': {}}
            cp.atomic(store / 'review.json', cp.encoded(review))
            cp.resume(self.root, store / 'review.json', 'fixture-coordinator', [])
        router.authorize(self.root, self.source, self.config_path, 'fixture execution', 'unit test')

    def dispatch(self, **kwargs):
        return router.dispatch(self.root, self.source, self.config_path, self.signals, execute=True, **kwargs)

    def test_real_trigger_launch_acceptance_and_duplicate_completion(self):
        result = self.dispatch(trigger='new-task')
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(self.dispatch()['action'], 'complete')
        self.assertEqual(router.report(self.root)['useful_completed_tasks'], 1)
        self.assertEqual((self.root / 'work.txt').read_text(), 'preserved\n')
        self.assertEqual(cp.latest(self.root / '.checkpoint')[0]['task']['routing'], self.task['routing'])

    def test_failed_cheaper_worker_recovers_to_capable(self):
        self.config['workers'][0]['fixture_result'] = 'wrong'
        self.prepare()
        first = self.dispatch()
        self.assertEqual(first['status'], 'rejected')
        second = self.dispatch()
        self.assertEqual(second['worker_id'], 'large')
        self.assertEqual(second['status'], 'accepted')
        self.assertEqual(router.report(self.root)['retries'], 1)

    def test_final_checkpoint_failure_never_repeats_launch(self):
        original = cp.checkpoint
        def checkpoint(root, source, trigger='manual', **kw):
            if trigger == 'milestone':
                raise cp.Fault('Injected final snapshot failure')
            return original(root, source, trigger, **kw)
        with mock.patch.object(cp, 'checkpoint', side_effect=checkpoint):
            with self.assertRaises(cp.Fault):
                self.dispatch()
        self.assertEqual(router.state(self.root)['active']['status'], 'accepted')
        with self.assertRaisesRegex(cp.Fault, 'transition'):
            self.dispatch()

    def test_interrupted_prelaunch_and_duplicate_dispatch_block(self):
        with mock.patch.object(router, '_run', side_effect=cp.Fault('Injected launch boundary crash')):
            with self.assertRaises(cp.Fault):
                self.dispatch()
        current = router.state(self.root)
        self.assertEqual(current['active']['status'], 'launching')
        with self.assertRaisesRegex(cp.Fault, 'transition'):
            self.dispatch()
        router.reconcile(self.root, current['active']['id'], 'rejected', 'Confirmed fixture never started')
        self.assertIsNone(router.report(self.root)['latency_seconds'])
        with self.assertRaisesRegex(cp.Fault, 'unresolved'):
            self.dispatch()

    def test_same_worktree_dispatch_lock_blocks_duplicates(self):
        common = self.root / '.git/checkpoint-router'
        common.mkdir(exist_ok=True)
        with cp.lock(common):
            with self.assertRaisesRegex(cp.Fault, 'lock'):
                self.dispatch()

    def test_high_risk_requires_independent_review(self):
        self.task['routing']['risk'] = 'high'
        self.prepare()
        result = self.dispatch()
        self.assertEqual(result['status'], 'review_required')
        with self.assertRaises(cp.Fault):
            router.reconcile(self.root, result['id'], 'accepted', 'self review', 'small')
        router.reconcile(self.root, result['id'], 'accepted', 'independent fixture checks inspected', 'reviewer')
        self.assertEqual(self.dispatch()['action'], 'complete')

    def test_forbidden_override_and_changed_authorization(self):
        self.config['allowed_providers'] = []
        self.prepare()
        self.assertEqual(self.dispatch(override='small')['action'], 'manual')
        self.config['allowed_providers'] = ['fixture']
        cp.atomic(self.config_path, cp.encoded(self.config))
        with self.assertRaisesRegex(cp.Fault, 'authorization'):
            self.dispatch()

    def test_resume_command_when_worker_missing(self):
        self.config['workers'][0].update(interface='codex_exec', billing='plan', provider='openai', executable='fixture-no-such-worker-executable')
        self.config['allowed_providers'].append('openai'); self.task['routing']['allowed_providers'].append('openai')
        self.prepare()
        result = self.dispatch()
        self.assertEqual(result['action'], 'manual')
        self.assertIn('--execute', result['resume_command'])
        self.assertIsNone(router.state(self.root)['active'])

    def test_scheduler_restart_once_and_fresh_budget(self):
        at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=10)).isoformat()
        router.schedule(self.root, self.source, self.config_path, at, 'explicit_user_schedule', self.signals)
        ticket_path = self.root / '.checkpoint/router-schedule.json'
        ticket = cp.read(ticket_path)
        ticket['at'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)).isoformat()
        cp.atomic(ticket_path, cp.encoded(ticket))
        with mock.patch.object(router, 'collect', return_value={'records': [{'kind': 'local_resource',
                'remaining': 0, 'unit': 'bytes_available', 'source': 'fresh test observation',
                'observed_at': cp.now(), 'uncertainty': None}]}) as collector:
            result = router.wake(self.root, self.source, self.config_path, 'file', None, True)
            self.assertEqual(result['action'], 'pause')
            self.assertEqual(cp.read(self.root / '.checkpoint/automatic-stop.json')['checkpoint_status'], 'verified')
            collector.assert_called_once()
        self.assertEqual(router.wake(self.root, self.source, self.config_path, 'file', None, True)['action'], 'pause')
        self.assertEqual(router.report(self.root)['attempts'], 0)

    def test_scheduler_crash_does_not_redeliver(self):
        at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=10)).isoformat()
        router.schedule(self.root, self.source, self.config_path, at, 'explicit_user_schedule', self.signals)
        target = self.root / '.checkpoint/router-schedule.json'
        ticket = cp.read(target); ticket['status'] = 'checking'; cp.atomic(target, cp.encoded(ticket))
        self.assertEqual(router.wake(self.root, self.source, self.config_path, 'file', None, True)['action'], 'pause')

    def test_reset_schedule_cannot_be_invented(self):
        at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=10)).isoformat()
        with self.assertRaisesRegex(cp.Fault, 'exact reset'):
            router.schedule(self.root, self.source, self.config_path, at, 'verified_reset', self.signals)

    def test_worker_cannot_claim_paid_api_as_plan(self):
        self.config['workers'][0].update(interface='codex_exec', billing='plan', provider='openai')
        self.config['allowed_providers'].append('openai'); self.task['routing']['allowed_providers'].append('openai')
        self.prepare()
        with mock.patch('codex_probe.probe', return_value={'account': {'account': {'type': 'apiKey'}}}):
            with self.assertRaisesRegex(cp.Fault, 'ChatGPT login'):
                self.dispatch(override='small')

    def test_generic_command_never_bypasses_verified_adapter(self):
        self.config['workers'][0].update(interface='command', argv=[sys.executable, '-c', "raise AssertionError('must not run')"])
        self.prepare()
        self.assertEqual(self.dispatch()['action'], 'manual')
        self.assertEqual(router.report(self.root)['attempts'], 0)

    def test_release_blocked_during_dispatch_and_uncertain_work(self):
        binding, store = cp.config(self.root)
        with router.exclusive(self.root):
            with self.assertRaises(cp.Fault):
                cp.Ownership(self.root, binding, store).release()
        current = router.state(self.root)
        current['active'] = {'id': 'uncertain', 'status': 'uncertain'}
        router.save(self.root, current)
        with self.assertRaisesRegex(cp.Fault, 'active or uncertain'):
            cp.Ownership(self.root, binding, store).release()
        cp.Ownership(self.root, binding, store).check()

    def test_changed_contract_never_reuses_accepted_result(self):
        self.dispatch()
        self.task['completion_criteria'] = ['A new requirement']
        self.prepare()
        with self.assertRaisesRegex(cp.Fault, 'changed contract'):
            self.dispatch()

    def test_original_prerequisites_not_weakened(self):
        self.task['tools'] = ['nonexistent-fixture-tool']
        with self.assertRaisesRegex(cp.Fault, 'Original task tool'):
            self.prepare()
        self.task['tools'] = []
        self.task['capabilities'] = ['another-device']
        with self.assertRaisesRegex(cp.Fault, 'Original task capability'):
            self.prepare()

    def test_large_unread_prompt_still_obeys_timeout(self):
        import os
        import time
        log = self.root / '.checkpoint/large-input.log'
        begin = time.monotonic()
        result = router._run([sys.executable, '-c', 'import time; time.sleep(.4)'],
            self.root, dict(os.environ), 'x' * 200000, log, .1, lambda pid: None)
        self.assertEqual(result['status'], 'uncertain')
        self.assertLess(time.monotonic() - begin, 1)
        # The short fixture child has no side effects; wait for its known end.
        time.sleep(.5)

    def test_routing_contract_roundtrip_and_malformed_save(self):
        self.assertIn('routing', cp.latest(self.root / '.checkpoint')[0]['task'])
        self.task['routing']['budget']['max_attempts'] = 0
        cp.atomic(self.source, cp.encoded(self.task))
        with self.assertRaises(cp.Fault):
            cp.checkpoint(self.root, self.source)

    def test_existing_hook_accepts_router_telemetry_format(self):
        cp.atomic(self.root / '.checkpoint/signals.json', cp.encoded({'records': [{
            'kind': 'codex_plan', 'source': 'supported test reading', 'remaining': 1,
            'unit': 'percent_remaining', 'observed_at': cp.now(), 'uncertainty': None}]}))
        result = subprocess.run([sys.executable, str(SCRIPTS / 'hook.py')],
            input=json.dumps({'cwd': str(self.root), 'hook_event_name': 'PreToolUse'}), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(cp.latest(self.root / '.checkpoint')[0]['trigger'], 'low-resource')

    def test_redacted_handoff_cannot_hide_secret_in_raw_prompt(self):
        self.task['observations'] = ['password=' + 'synthetic-test-value']
        with self.assertRaisesRegex(cp.Fault, 'Secret-like task prose'):
            self.prepare()


if __name__ == '__main__':
    unittest.main()
