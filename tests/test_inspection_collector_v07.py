"""Isolated 0.7 regressions: inspect boundaries and collector fault containment."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'
sys.path.insert(0, str(SCRIPTS))
import account
import checkpoint as cp
import monitor


class InspectionCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        for args in [('init', '-b', 'main'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@example.invalid')]:
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        (self.root / '.gitignore').write_text('.checkpoint/\n')
        (self.root / 'work.txt').write_text('preserve this work\n')
        for args in [('add', '.'), ('commit', '-m', 'Fixture')]:
            subprocess.run(['git', *args], cwd=self.root, check=True, capture_output=True)
        self.store = self.root / '.checkpoint'
        self.binding = {'schema_version': 1, 'task_id': 'fixture', 'project_id': 'fixture/project',
                        'ownership': 'local'}
        cp.atomic(self.store / 'config.json', cp.encoded(self.binding))
        task = cp.read(cp.ASSETS / 'task-template.json')
        task['artifacts'] = [{'path': 'work.txt', 'required': True, 'preserve': True}]
        cp.atomic(self.store / 'input.json', cp.encoded(task))
        self.first = cp.checkpoint(self.root, self.store / 'input.json')
        self.state = Path(self.temp.name) / 'account'
        self.record = {'root': str(self.root), 'task_id': 'fixture', 'project_id': 'fixture/project'}
        self.config = {'version': 1, 'enabled': True, 'projects': [self.record]}
        cp.atomic(self.state / 'config.json', cp.encoded(self.config))

    def signals(self):
        return {'records': [{'kind': 'codex_plan', 'remaining': 10, 'unit': 'percent_remaining',
            'observed_at': cp.now(), 'source': 'isolated-fixture', 'window': 'weekly',
            'resets_at': '2099-01-01T00:00:00+00:00'}]}

    def observation(self):
        return {'source': 'isolated-test-double', 'observed_at': cp.now(),
                'account': {'account': {'type': 'chatgpt'}},
                'rate_limits': {'ordinaryUsageAllowed': True,
                    'rateLimits': {'primary': {'usedPercent': 4}}},
                'models': {'data': []}}

    def nested(self):
        nested = self.root / 'nested work'
        nested.mkdir()
        subprocess.run(['git', 'init', '-q', str(nested)], check=True, capture_output=True)
        (nested / 'file.txt').write_text('independent task\n')
        return nested

    def test_nested_repository_inspection_reports_unsaved_boundary(self):
        nested = self.nested()
        state, report = cp.inspect(self.root)
        self.assertEqual(state['id'], self.first['id'])
        self.assertIn('unsaved-artifact-boundary:nested work', report['issues'])
        self.assertFalse(report['implementation_allowed'])
        current = cp.repo(self.root)
        self.assertEqual(current['files']['nested work']['preserved'], False)
        self.assertNotIn('nested work/file.txt', current['files'])
        self.assertEqual(current, cp.repo(self.root))
        self.assertTrue((nested / 'file.txt').exists())

    def test_nested_repository_cannot_be_silently_dropped_from_checkpoint(self):
        self.nested()
        with self.assertRaisesRegex(cp.Fault, 'Unsaved directory or nested repository boundaries'):
            cp.checkpoint(self.root, self.store / 'input.json')
        self.assertEqual(cp.latest(self.store)[0]['id'], self.first['id'])
        self.assertFalse((self.store / 'writer.lock').exists())

    def test_explicit_git_exclusion_of_independent_repo_restores_checkpoint(self):
        self.nested()
        (self.root / '.gitignore').write_text('.checkpoint/\nnested work/\n')
        saved = cp.checkpoint(self.root, self.store / 'input.json')
        self.assertNotEqual(saved['id'], self.first['id'])
        state, _ = cp.latest(self.store)
        self.assertNotIn('nested work', state['repository']['files'])

    def test_nested_repository_stop_preserves_prior_generation(self):
        self.nested()
        result = monitor.evaluate_registered(self.state, self.signals())
        self.assertEqual(result['projects'][0]['status'], 'preservation-failed')
        self.assertEqual(cp.latest(self.store)[0]['id'], self.first['id'])
        self.assertEqual(cp.read(self.store / 'automatic-stop.json')['preservation_attempts'], 1)

    def test_source_failures_stop_after_three_preservation_attempts(self):
        with mock.patch.object(monitor, '_source', side_effect=cp.Fault('unavailable source')) as source:
            for _ in range(5):
                result = monitor.evaluate_registered(self.state, self.signals())
                self.assertEqual(result['projects'][0]['status'], 'preservation-failed')
            self.assertEqual(source.call_count, 3)
        marker = cp.read(self.store / 'automatic-stop.json')
        self.assertEqual(marker['preservation_attempts'], 3)
        self.assertEqual(marker['checkpoint_status'], 'failed')
        self.assertEqual(cp.latest(self.store)[0]['id'], self.first['id'])

    def test_collector_refreshes_quota_when_preservation_adapter_fails(self):
        with mock.patch('codex_probe.probe', return_value=self.observation()), \
             mock.patch.object(monitor, 'evaluate_registered', side_effect=PermissionError('private')):
            result = account.tick(self.state)
        self.assertEqual(result['telemetry']['statuses']['codex_plan'], 'ok')
        self.assertEqual(result['preservation']['status'], 'preservation-unavailable')
        self.assertEqual(result['scheduled'][0]['result'], 'project-blocked')
        self.assertEqual(cp.read(self.state / 'signals.json')['records'][0]['remaining'], 96)
        self.assertNotIn('private', json.dumps(result))

    def test_wrong_task_never_publishes_or_receives_another_tasks_bundle(self):
        self.record.update(task_id='different-task', private_transfer={'repository': 'fixture/project'},
                           private_receive={'repository': 'fixture/project'})
        cp.atomic(self.state / 'config.json', cp.encoded(self.config))
        with mock.patch('codex_probe.probe', return_value=self.observation()), \
             mock.patch('transfer.publish') as publish, mock.patch('transfer.receive_latest') as receive:
            result = account.tick(self.state)
        publish.assert_not_called()
        receive.assert_not_called()
        self.assertEqual(result['transfers'][0]['status'], 'pending-retry')
        self.assertEqual(result['receives'][0]['status'], 'pending-source-sync-or-review')
        self.assertEqual(cp.read(self.store / 'config.json'), self.binding)

    def test_transfer_dependency_failure_does_not_make_quota_stale(self):
        self.config['gh_executable'] = str(Path(self.temp.name) / 'missing-gh')
        self.record['private_transfer'] = {'repository': 'fixture/project'}
        cp.atomic(self.state / 'config.json', cp.encoded(self.config))
        with mock.patch('codex_probe.probe', return_value=self.observation()), \
             mock.patch('transfer.publish') as publish:
            result = account.tick(self.state)
        publish.assert_not_called()
        self.assertEqual(result['telemetry']['statuses']['codex_plan'], 'ok')
        self.assertIn('gh_executable', result['dependency_errors'])
        self.assertEqual(result['preservation']['projects'][0]['status'], 'no-low-signal')

    def test_failed_project_preservation_cannot_dispatch_without_marker(self):
        self.record['planned_dispatch'] = True
        cp.atomic(self.state / 'config.json', cp.encoded(self.config))
        cp.atomic(self.store / 'plan-approval.json', b'{}')
        with mock.patch('codex_probe.probe', return_value=self.observation()), \
             mock.patch.object(monitor, 'evaluate_registered', return_value={'projects': [
                 {'task_id': 'fixture', 'status': 'preservation-failed'}]}), \
             mock.patch('planner.boundary') as dispatch:
            result = account.tick(self.state)
        dispatch.assert_not_called()
        self.assertEqual(result['scheduled'][0]['result'], 'project-blocked')


if __name__ == '__main__':
    unittest.main()
