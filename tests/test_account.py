import copy
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'
sys.path.insert(0, str(SCRIPTS))
import account
import checkpoint as cp


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'codex'
        self.home.mkdir()
        self.state = self.home / 'checkpoint-handoff'
        self.original = {'hooks': {'SessionStart': [{'hooks': [{'type': 'command', 'command': 'existing-handler', 'timeout': 10}]}]}}
        cp.atomic(self.home / 'hooks.json', cp.encoded(self.original))
        account.install(self.state, self.home, Path(sys.executable), [], platform="darwin")

    def test_install_preserves_hooks_and_native_trust(self):
        result = cp.read(self.home / 'hooks.json')
        self.assertIn(self.original['hooks']['SessionStart'][0], result['hooks']['SessionStart'])
        self.assertFalse((self.home / 'config.toml').exists())
        self.assertEqual(len(result['hooks']['SessionStart']), 2)
        account.install(self.state, self.home, Path(sys.executable), [], platform="darwin")
        self.assertEqual(cp.read(self.home / 'hooks.json'), result)
        value = plistlib.loads((self.state / (account.LABEL + '.plist')).read_bytes())
        self.assertEqual(value['StartInterval'], 60)
        self.assertTrue(value['RunAtLoad'])
        self.assertEqual(value['ProgramArguments'][-1], 'tick')
        self.assertIn('/usr/bin', value['EnvironmentVariables']['PATH'])

    def test_uninstall_retains_other_hooks_and_private_state(self):
        value = cp.read(self.home / 'hooks.json')
        other = {'hooks': [{'type': 'command', 'command': 'added-later'}]}
        value['hooks']['Stop'].append(other)
        cp.atomic(self.home / 'hooks.json', cp.encoded(value))
        account.uninstall(self.state, self.home)
        result = cp.read(self.home / 'hooks.json')
        self.assertEqual(result['hooks']['Stop'], [other])
        self.assertEqual(result['hooks']['SessionStart'], self.original['hooks']['SessionStart'])
        self.assertFalse(cp.read(self.state / 'config.json')['enabled'])
        self.assertTrue((self.state / 'hooks-before.json').exists())

    def test_changed_managed_hook_preserved(self):
        value = cp.read(self.home / 'hooks.json')
        value['hooks']['Stop'][0]['hooks'][0]['command'] = 'customized'
        cp.atomic(self.home / 'hooks.json', cp.encoded(value))
        with self.assertRaises(cp.Fault):
            account.install(self.state, self.home, Path(sys.executable), [], platform="darwin")
        self.assertEqual(cp.read(self.home / 'hooks.json'), value)

    def test_account_profile_cannot_be_silently_rebound(self):
        before = (self.home / 'hooks.json').read_bytes()
        with self.assertRaisesRegex(cp.Fault, 'another Codex profile'):
            account.install(self.state, self.root / 'different-profile', Path(sys.executable), [], platform='darwin')
        self.assertEqual((self.home / 'hooks.json').read_bytes(), before)

    def reading(self):
        return {'source': 'codex-app-server', 'observed_at': cp.now(), 'account': {'account': {'type': 'chatgpt'}},
                'rate_limits': {'ordinaryUsageAllowed': True, 'rateLimits': {'primary': {'usedPercent': 86}}},
                'models': {'data': [{'model': 'gpt-6-luna'}]}}

    def test_tick_collects_supported_account_data_without_model_turn(self):
        with mock.patch('codex_probe.probe', return_value=self.reading()) as probe:
            result = account.tick(self.state)
            configured = cp.read(self.state / 'config.json')
            probe.assert_called_once_with(executable=configured.get('codex_executable', 'codex'), timeout=25, codex_home=str(self.home.resolve()))
        self.assertEqual(result['auth_type'], 'chatgpt')
        self.assertEqual(cp.read(self.state / 'signals.json')['records'][0]['remaining'], 14)
        self.assertEqual(cp.read(self.state / 'signals.json')['records'][0]['guard'], 20)
        self.assertEqual(result['scheduled'], [])

    def test_collection_only_keeps_monitoring_and_preserves_dispatch_configuration(self):
        config = cp.read(self.state/'config.json')
        config['observation_only'] = True
        config['projects'] = [{'root': str(self.root), 'task_id': 'fixture',
            'project_id': 'fixture/project', 'planned_dispatch': True,
            'scheduled_dispatch': True, 'private_transfer': {'repository': 'fixture/project'},
            'private_receive': {'repository': 'fixture/project'}}]
        cp.atomic(self.root/'.checkpoint/config.json', cp.encoded({'schema_version': 1,
            'task_id': 'fixture', 'project_id': 'fixture/project', 'ownership': 'local'}))
        cp.atomic(self.root/'.checkpoint/plan-approval.json', b'{}')
        cp.atomic(self.state/'config.json', cp.encoded(config))
        before = (self.state/'config.json').read_bytes()
        with mock.patch('codex_probe.probe', return_value=self.reading()), \
             mock.patch('monitor.evaluate_registered', return_value={'projects': []}) as preserve, \
             mock.patch('planner.boundary', return_value={'status': 'unexpected-dispatch'}) as planned, \
             mock.patch('router.wake') as scheduled, \
             mock.patch('transfer.publish', return_value={'status': 'unexpected-publish'}) as publish, \
             mock.patch('transfer.receive_latest', return_value={'status': 'unexpected-receive'}) as receive:
            result = account.tick(self.state)
        preserve.assert_called_once()
        for action in (planned, scheduled, publish, receive):
            action.assert_not_called()
        self.assertTrue(result['observation_only'])
        self.assertEqual(result['scheduled'], [])
        self.assertEqual(result['transfers'], [])
        self.assertEqual(result['receives'], [])
        self.assertEqual((self.state/'config.json').read_bytes(), before)
        self.assertEqual(cp.read(self.state/'signals.json')['records'][0]['remaining'], 14)

    def test_tick_resolves_git_without_scheduler_path_and_restores_environment(self):
        config = cp.read(self.state / 'config.json')
        config['git_executable'] = str(Path(sys.executable).resolve())
        cp.atomic(self.state / 'config.json', cp.encoded(config))
        observed = []
        def preserve(*args):
            observed.append(os.environ['PATH'])
            return {'projects': []}
        with mock.patch.dict(os.environ, {'PATH': 'scheduler-without-git'}):
            with mock.patch('codex_probe.probe', return_value=self.reading()), mock.patch('monitor.evaluate_registered', side_effect=preserve):
                account.tick(self.state)
            self.assertEqual(os.environ['PATH'], 'scheduler-without-git')
        self.assertEqual(observed[0].split(os.pathsep)[0], str(Path(sys.executable).resolve().parent))

    def test_private_exchange_resolves_gh_without_scheduler_path(self):
        config = cp.read(self.state / 'config.json')
        config['gh_executable'] = str(Path(sys.executable).resolve())
        config['projects'] = [{'root': str(self.root), 'task_id': 'fixture',
                               'project_id': 'owner/private',
                               'private_transfer': {'repository': 'owner/private'}}]
        cp.atomic(self.root/'.checkpoint/config.json', cp.encoded({'schema_version': 1,
            'task_id': 'fixture', 'project_id': 'owner/private', 'ownership': 'local'}))
        cp.atomic(self.state / 'config.json', cp.encoded(config))
        observed = []
        def publish(*args):
            observed.append(os.environ['PATH'].split(os.pathsep))
            return {'status': 'verified-test-double'}
        with mock.patch.dict(os.environ, {'PATH': 'scheduler-without-gh'}):
            with mock.patch('codex_probe.probe', return_value=self.reading()), mock.patch('monitor.evaluate_registered', return_value={'projects': []}), mock.patch('transfer.publish', side_effect=publish):
                result = account.tick(self.state)
            self.assertEqual(os.environ['PATH'], 'scheduler-without-gh')
        self.assertIn(str(Path(sys.executable).resolve().parent), observed[0][:-1])
        self.assertEqual(result['transfers'][0]['status'], 'verified-test-double')

    def test_unavailable_configured_gh_does_not_prevent_quota_refresh(self):
        with mock.patch('codex_probe.probe', return_value=self.reading()):
            account.tick(self.state)
        original = (self.state / 'signals.json').read_bytes()
        config = cp.read(self.state / 'config.json')
        config['gh_executable'] = str(self.root / 'missing-gh.exe')
        cp.atomic(self.state / 'config.json', cp.encoded(config))
        with mock.patch('codex_probe.probe', return_value=self.reading()):
            result = account.tick(self.state)
        self.assertNotEqual((self.state / 'signals.json').read_bytes(), original)
        self.assertIn('gh_executable', result['dependency_errors'])

    def test_unavailable_configured_git_refreshes_quota_but_blocks_preservation(self):
        with mock.patch('codex_probe.probe', return_value=self.reading()):
            account.tick(self.state)
        original = (self.state / 'signals.json').read_bytes()
        config = cp.read(self.state / 'config.json')
        config['git_executable'] = str(self.root / 'missing-git.exe')
        cp.atomic(self.state / 'config.json', cp.encoded(config))
        with mock.patch('codex_probe.probe', return_value=self.reading()):
            result = account.tick(self.state)
        self.assertNotEqual((self.state / 'signals.json').read_bytes(), original)
        self.assertIn('git_executable', result['dependency_errors'])
        self.assertEqual(result['preservation']['status'], 'preservation-unavailable')

    def test_failed_collection_never_refreshes_old_reading_or_buys_fallback(self):
        with mock.patch('codex_probe.probe', return_value=self.reading()):
            account.tick(self.state)
        old = (self.state / 'signals.json').read_bytes()
        observation = self.reading(); observation['account']['account']['type'] = 'apiKey'
        with mock.patch('codex_probe.probe', return_value=observation):
            with self.assertRaises(cp.Fault):
                account.tick(self.state)
        self.assertEqual((self.state / 'signals.json').read_bytes(), old)
        self.assertTrue(cp.read(self.state / 'last-error.json')['old_signals_not_refreshed'])

    def test_unbound_git_project_receives_global_instruction(self):
        repo = self.root / 'repo'; repo.mkdir()
        subprocess.run(['git', 'init', str(repo)], capture_output=True, check=True)
        result = subprocess.run([sys.executable, str(SCRIPTS / 'hook.py'), '--account-state', str(self.state)],
            input=json.dumps({'cwd': str(repo), 'hook_event_name': 'SessionStart'}), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('enabled for this local Codex user', json.loads(result.stdout)['hookSpecificOutput']['additionalContext'])
        self.assertFalse((repo / '.checkpoint').exists())

    def test_global_hook_is_harmless_outside_git(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'hook.py'), '--account-state', str(self.state)],
            input=json.dumps({'cwd': str(self.root), 'hook_event_name': 'PreToolUse'}), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {})
