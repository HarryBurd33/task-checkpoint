import copy
import datetime as dt
import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'
sys.path.insert(0, str(SCRIPTS))
import checkpoint as cp
import router_policy as policy
import telemetry

NOW = '2026-10-25T12:00:00+00:00'


class RouterPolicyTests(unittest.TestCase):
    def test_explicit_account_denial_does_not_invent_remaining(self):
        normalized = telemetry.normalize_codex({'ordinaryUsageAllowed': False}, NOW)
        self.assertIsNone(normalized['records'][0]['remaining'])
        self.assertEqual(telemetry.assess(normalized, NOW)['statuses']['codex_plan'], 'low')

    def setUp(self):
        self.task = cp.read(cp.ASSETS / 'task-template.json')
        self.task['routing'] = {'id': 'bounded', 'task_class': 'edit', 'complexity': 'routine',
            'risk': 'low', 'required_tools': ['git'], 'privacy': 'private',
            'allowed_providers': ['fixture'], 'budget': {'max_attempts': 3,
            'max_wall_seconds': 600, 'max_api_usd': None}, 'dependencies': [],
            'estimated_work_seconds': 60, 'acceptance': [{'id': 'unit', 'argv': ['python3', '-m', 'unittest']}],
            'escalation_reason': None}
        def worker(name, rank):
            return {'id': name, 'model': 'test-only-model', 'test_only': True,
                'provider': 'fixture', 'billing': 'plan', 'available': True, 'enabled': True,
                'availability': {'source': 'test fixture', 'observed_at': NOW},
                'tools': ['git'], 'privacy': ['private'], 'max_complexity': 'complex',
                'rank': rank, 'effort': 'medium', 'interface': 'command', 'argv': ['true'],
                'qualification': {'model': 'test-only-model', 'effort': 'medium', 'task_classes': ['edit'], 'passed': True, 'source': 'test fixture',
                    'samples': 2, 'acceptance_rate': 1, 'mean_total_seconds': 30 + rank * 40, 'observed_at': NOW}}
        self.config = {'workers': [worker('small', 0), worker('large', 1)],
            'allowed_providers': ['fixture'], 'allow_paid': False, 'max_retries': 1}
        self.signals = {'records': [self.record('codex_plan', 50)]}
        self.history = []

    def record(self, kind, remaining, **kw):
        return dict({'kind': kind, 'source': 'test fixture', 'observed_at': NOW,
            'unit': telemetry.UNITS[kind], 'remaining': remaining, 'uncertainty': None}, **kw)

    def decide(self, **kw):
        return policy.decide(self.task, self.config, self.signals, self.history, now=NOW, **kw)

    def test_selects_observed_useful_completion_cost(self):
        self.config['workers'][0]['qualification']['acceptance_rate'] = .2
        self.assertEqual(self.decide()['worker_id'], 'large')
        self.config['workers'][0]['qualification']['acceptance_rate'] = 1
        self.assertEqual(self.decide()['worker_id'], 'small')

    def test_qualification_is_bound_to_model_and_effort(self):
        self.config['workers'][0]['effort']='low'
        self.assertEqual(self.decide()['worker_id'],'large')
        self.config['workers'][1]['model']='untested-model'
        self.assertEqual(self.decide()['action'],'manual')

    def test_duplicate_worker_ids_fail_before_selection(self):
        first = copy.deepcopy(self.config['workers'][0])
        first['enabled'] = False
        first['provider'] = 'forbidden'
        self.config['workers'].insert(0, first)
        with self.assertRaises(cp.Fault):
            self.decide()
        with self.assertRaises(cp.Fault):
            policy.validate_config(self.config)

    def test_malformed_configuration_fails_closed(self):
        cases = [None, [], {'workers': [None], 'allowed_providers': []},
                 dict(self.config, allowed_providers='fixture'),
                 dict(self.config, cooldown_seconds='300'),
                 dict(self.config, max_retries=True)]
        for config in cases:
            with self.subTest(config=config):
                with self.assertRaises(cp.Fault):
                    policy.decide(self.task, config, self.signals, [], now=NOW)
        for field in ('qualification', 'tools', 'privacy', 'availability', 'billing', 'effort', 'available', 'interface', 'rank'):
            config = copy.deepcopy(self.config)
            config['workers'][0][field] = 'invalid' if field == 'rank' else 42
            with self.assertRaises(cp.Fault):
                policy.decide(self.task, config, self.signals, [], now=NOW)

    def test_qualification_optional_tool_and_privacy_coverage(self):
        for worker in self.config['workers']:
            worker['qualification']['required_tools'] = []
        self.assertEqual(self.decide()['action'], 'manual')
        self.config['workers'][0]['qualification']['required_tools'] = ['git']
        self.assertEqual(self.decide()['worker_id'], 'small')
        self.config['workers'][0]['qualification']['privacy'] = ['public']
        self.assertEqual(self.decide()['action'], 'manual')

    def test_direct_observation_uncertainty_note_preserved(self):
        signals = telemetry.normalize_direct('codex_plan', 5, 'percent_remaining', NOW,
            'test fixture', uncertainty='rounded display')
        result = telemetry.assess(signals, NOW)
        self.assertEqual(result['statuses']['codex_plan'], 'low')
        self.assertEqual(result['low'][0]['uncertainty'], 'rounded display')
        signals['records'][0]['supported'] = False
        self.assertEqual(telemetry.assess(signals, NOW)['statuses']['codex_plan'], 'unknown')
        for kind in ('api_balance', 'context', 'local_resource'):
            normalized = telemetry.normalize_direct(kind, 42, telemetry.UNITS[kind], NOW, 'test fixture')
            self.assertEqual(telemetry.assess(normalized, NOW)['statuses'][kind], 'ok')

    def test_checkpoint_bridges_preserve_source_units_and_guards(self):
        record = self.record('codex_plan', 15, uncertainty='rounded display')
        record.pop('kind')
        original = {'account_quota': [record]}
        normalized = telemetry.from_checkpoint_signals(original)
        self.assertEqual(normalized['records'][0]['guard'], 20)
        result = telemetry.assess(original, NOW)
        self.assertEqual(result['statuses']['codex_plan'], 'low')
        roundtrip = telemetry.to_checkpoint_signals(normalized)['account_quota'][0]
        for field in ('source', 'unit', 'observed_at', 'remaining', 'uncertainty'):
            self.assertEqual(roundtrip[field], record[field])
        direct = telemetry.normalize_direct('codex_plan', 15, 'percent_remaining', NOW, 'fixture')
        self.assertEqual(telemetry.to_checkpoint_signals(direct)['account_quota'][0]['guard'], 20)

    def test_disk_collector_is_disk_bytes_only(self):
        normalized = telemetry.disk_usage(SCRIPTS)
        record = normalized['records'][0]
        self.assertEqual(record['unit'], 'bytes_available')
        self.assertEqual(record['source'], 'python.shutil.disk_usage')
        self.assertGreaterEqual(record['remaining'], 0)
        bad = telemetry.disk_usage(SCRIPTS / 'no-such-directory')
        self.assertEqual(telemetry.assess(bad)['statuses']['local_resource'], 'unknown')

    def test_valid_optional_contract(self):
        self.assertIs(policy.validate_task(self.task), self.task)
        del self.task['routing']
        policy.validate_task(self.task)
        self.assertEqual(self.decide()['action'], 'manual')

    def test_invalid_task_contract(self):
        for field, value in [('complexity', 'huge'), ('privacy', 'secret'), ('acceptance', []), ('estimated_work_seconds', True)]:
            with self.subTest(field=field):
                bad = copy.deepcopy(self.task); bad['routing'][field] = value
                with self.assertRaises(cp.Fault): policy.validate_task(bad)

    def test_selects_smallest_qualified_worker(self):
        self.assertEqual(self.decide()['worker_id'], 'small')
        self.config['workers'][0]['qualification']['passed'] = False
        self.assertEqual(self.decide()['worker_id'], 'large')

    def test_low_account_stops_all_ordinary_work(self):
        self.signals['records'][0]['remaining'] = 0
        self.assertEqual(self.decide()['action'], 'pause')
        self.config['workers'][0]['billing'] = 'local'
        self.signals['records'].append(self.record('local_resource', 1000))
        self.assertEqual(self.decide()['action'], 'pause')

    def test_missing_stale_future_wrong_unit_and_null_unknown(self):
        for update in ({'remaining': None}, {'observed_at': '2026-10-24T12:00:00Z'},
                       {'observed_at': '2026-10-26T12:00:00Z'}, {'unit': 'usd_remaining'}, {'supported': False, 'uncertainty': 'estimate'}):
            with self.subTest(update=update):
                self.signals = {'records': [dict(self.record('codex_plan', 0), **update)]}
                decision = self.decide()
                self.assertEqual(decision['telemetry']['statuses']['codex_plan'], 'unknown')
                self.assertEqual(decision['telemetry']['low'], [])
                self.assertEqual(decision['action'], 'manual')
        self.signals = {'records': []}
        self.assertEqual(self.decide()['action'], 'manual')

    def test_permissions_cannot_be_overridden(self):
        for key, value in [('allowed_providers', []), ('required_tools', ['missing']), ('privacy', 'local_only')]:
            with self.subTest(key=key):
                original = self.task['routing'][key]
                self.task['routing'][key] = value
                self.assertEqual(self.decide(override='small')['action'], 'manual')
                self.task['routing'][key] = original

    def test_failure_escalates_once_and_uncertainty_pauses(self):
        self.history = [{'worker_id': 'small', 'status': 'rejected', 'wall_seconds': 40,
            'api_cost_usd': None, 'finished_at': NOW}]
        self.assertEqual(self.decide()['worker_id'], 'large')
        self.history.append(dict(self.history[0], worker_id='large'))
        self.assertEqual(self.decide()['action'], 'pause')
        self.history[0]['status'] = 'uncertain'
        self.assertIn('uncertain', self.decide()['reasons'][0])

    def test_budget_caps(self):
        self.task['routing']['budget']['max_attempts'] = 1
        self.history = [{'worker_id': 'small', 'status': 'accepted', 'wall_seconds': 10}]
        self.assertEqual(self.decide()['action'], 'pause')
        self.history = []
        self.task['routing']['budget']['max_wall_seconds'] = 10
        self.assertEqual(self.decide()['action'], 'pause')

    def test_no_paid_fallback_or_unknown_cost(self):
        for w in self.config['workers']: w['billing'] = 'api'
        self.signals = {'records': [self.record('api_balance', 50)]}
        self.assertEqual(self.decide()['action'], 'manual')
        self.config['allow_paid'] = True
        self.assertEqual(self.decide()['action'], 'manual')
        self.task['routing']['budget']['max_api_usd'] = 1
        self.assertEqual(self.decide()['action'], 'launch')
        self.history = [{'worker_id': 'small', 'status': 'accepted', 'wall_seconds': 10, 'api_cost_usd': None}]
        self.assertEqual(self.decide()['action'], 'manual')

    def test_cooldown_avoids_switch(self):
        self.history = [{'worker_id': 'large', 'status': 'accepted', 'wall_seconds': 10,
                         'finished_at': NOW}]
        self.assertEqual(self.decide(current_worker='large')['worker_id'], 'large')
        self.history[0]['finished_at'] = '2026-10-25T11:00:00Z'
        self.assertEqual(self.decide(current_worker='large')['worker_id'], 'small')

    def test_context_low_and_dependencies_pause(self):
        self.signals['records'].append(self.record('context', 0))
        self.assertEqual(self.decide()['action'], 'pause')
        self.signals['records'].pop()
        self.task['routing']['dependencies'] = [{'id': 'before', 'status': 'pending'}]
        self.assertEqual(self.decide()['action'], 'pause')

    def test_availability_and_qualification_evidence_required(self):
        for w in self.config['workers']: w['availability']['observed_at'] = '2026-10-20T12:00:00Z'
        self.assertEqual(self.decide()['action'], 'manual')

    def test_codex_adapter_preserves_window_and_never_infers_api(self):
        payload = {'rateLimitsByLimitId': {'codex': {'primary': {'usedPercent': 95,
            'resetsAt': 1792933200}, 'credits': {'balance': '20'}}}}
        normalized = telemetry.normalize_codex(payload, NOW)
        self.assertEqual(normalized['records'][0]['remaining'], 5)
        self.assertEqual(normalized['records'][0]['window'], 'codex:primary')
        assessed = telemetry.assess(normalized, NOW)
        self.assertEqual(assessed['statuses']['api_balance'], 'unknown')
        self.assertEqual(assessed['statuses']['codex_plan'], 'low')

    def test_reset_stale_and_malformed_values_unknown(self):
        values = [None, True, '0', float('nan'), -1, 101]
        for value in values:
            normalized = telemetry.normalize_codex({'rateLimits': {'primary': {'usedPercent': value}}}, NOW)
            self.assertEqual(telemetry.assess(normalized, NOW)['statuses']['codex_plan'], 'unknown')
        signals = {'records': [self.record('codex_plan', 0, resets_at='2026-10-25T11:00:00Z')]}
        self.assertEqual(telemetry.assess(signals, NOW)['statuses']['codex_plan'], 'unknown')


if __name__ == '__main__':
    unittest.main()
