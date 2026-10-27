#!/usr/bin/env python3
"""Synthetic deterministic routing demonstration, not model performance evidence.

Runs temporary local Git repositories through actual checkpoint/resume/authorize/
dispatch operations. No model, paid API, external queue or network is used.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY / 'skills/task-checkpoint/scripts'
sys.path.insert(0, str(SCRIPTS))
import checkpoint as cp
import router
import telemetry


def git(root, *args):
    subprocess.run(['git', *args], cwd=str(root), check=True, capture_output=True)


def worker(name, rank, result='42'):
    return {'id': name, 'model': 'deterministic-fixture', 'test_only': True,
        'provider': 'fixture', 'billing': 'local', 'available': True, 'enabled': True,
        'availability': {'source': 'owned deterministic fixture adapter', 'observed_at': cp.now()},
        'tools': ['python'], 'privacy': ['private'], 'max_complexity': 'complex',
        'rank': rank, 'effort': 'medium', 'interface': 'fixture', 'fixture_result': result,
        'qualification': {'model': 'deterministic-fixture', 'effort': 'medium', 'task_classes': ['fixture'], 'passed': True,
            'source': 'synthetic fixture contract: output 42; not a model qualification',
            'samples': 1, 'acceptance_rate': 1, 'mean_total_seconds': 1 + rank,
            'observed_at': cp.now()}}


class Fixture:
    def __init__(self, root, workers):
        self.root = root
        root.mkdir()
        git(root, 'init', '-b', 'main')
        git(root, 'config', 'user.name', 'Router Demo Fixture')
        git(root, 'config', 'user.email', 'fixture@example.invalid')
        (root / '.gitignore').write_text('.checkpoint/\n', encoding='utf-8')
        (root / 'preserved.txt').write_text('preserved original work\n', encoding='utf-8')
        git(root, 'add', '.')
        git(root, 'commit', '-m', 'Synthetic demonstration fixture')
        subprocess.run([sys.executable, str(SCRIPTS / 'checkpoint.py'), '--root', str(root),
            'init', '--task', 'demo', '--project-id', 'demo', '--ownership', 'local'],
            check=True, capture_output=True)
        self.source = root / '.checkpoint/input.json'
        self.config_path = root / '.checkpoint/router-config.json'
        self.config = {'version': 1, 'queue_authority': 'checkpoint:demo:demo',
            'workers': workers, 'allowed_providers': ['fixture'], 'allow_paid': False,
            'max_retries': 1, 'unknown_telemetry': 'explicit_budget'}
        self.elapsed = 0
        self.outcomes = []

    def prepare(self, task_id):
        task = cp.read(cp.ASSETS / 'task-template.json')
        task.update(objective='Synthetic fixture produces 42', tools=[], capabilities=[],
            next_action={'description': 'Produce the deterministic fixture result',
                         'verification': 'Preserved original work must still be present'})
        task['routing'] = {'id': task_id, 'task_class': 'fixture', 'complexity': 'routine',
            'risk': 'low', 'required_tools': ['python'], 'privacy': 'private',
            'allowed_providers': ['fixture'], 'budget': {'max_attempts': 2,
                'max_wall_seconds': 30, 'max_api_usd': None},
            'dependencies': [], 'estimated_work_seconds': 1,
            'acceptance': [{'id': 'exact-output', 'argv': [sys.executable, '-c',
                "import os;from pathlib import Path;assert Path(os.environ['CHECKPOINT_RESULT']).read_text()=='42'"]}]}
        cp.atomic(self.source, cp.encoded(task))
        cp.atomic(self.config_path, cp.encoded(self.config))
        cp.checkpoint(self.root, self.source)
        _, store = cp.config(self.root)
        if not (store / 'owner.json').exists():
            saved, inspected = cp.inspect(self.root)
            review = {'checkpoint_id': saved['id'], 'task_id': saved['task_id'],
                'next_action': saved['task']['next_action']['description'],
                'verification': saved['task']['next_action']['verification'],
                'current_fingerprint': inspected['current_fingerprint'], 'observed_at': cp.now(),
                'authorization': {'confirmed': True, 'scope': 'temporary deterministic fixtures only',
                                  'source': 'explicit router demo invocation'},
                'resources': {'adequate_for_bounded_action': True,
                    'evidence': 'bounded deterministic local subprocess', 'observed_at': cp.now()},
                'resolutions': {}}
            cp.atomic(store / 'review.json', cp.encoded(review))
            cp.resume(self.root, store / 'review.json', 'demo-coordinator', [])
        router.authorize(self.root, self.source, self.config_path,
                         'temporary deterministic fixtures only', 'explicit demo invocation')

    def dispatch(self, signals=None, trigger='new-task'):
        started = time.monotonic()
        result = router.dispatch(self.root, self.source, self.config_path,
            signals if signals is not None else {'records': []}, execute=True, trigger=trigger)
        duration = time.monotonic() - started
        self.elapsed += duration
        if result.get('status'):
            self.outcomes.append({'task_id': result['bounded_task_id'],
                'worker_id': result['worker_id'], 'status': result['status'],
                'dispatch_seconds': duration, 'attempt_wall_seconds': result['wall_seconds'],
                'evaluator_seconds': result['evaluator_seconds'],
                'token_usage': result.get('token_usage'), 'api_cost_usd': result.get('api_cost_usd'),
                'plan_usage': result.get('plan_usage')})
        assert (self.root / 'preserved.txt').read_text() == 'preserved original work\n'
        return result

    def summary(self):
        observed = router.report(self.root)
        return {key: observed[key] for key in ('attempts', 'accepted_attempts',
            'useful_completed_tasks', 'acceptance_rate', 'retries', 'latency_seconds',
            'evaluator_seconds', 'observed_api_cost_usd', 'observed_plan_usage')} | {
            'dispatch_total_seconds': self.elapsed, 'attempts_detail': self.outcomes,
            'observed_token_usage': None, 'worker_only_subprocess_seconds': None,
            'orchestration_overhead_seconds': None,
            'timing_note': 'latency_seconds measures worker plus evaluation and internal bookkeeping; '
                'dispatch_total_seconds includes checkpoint/lease/preflight overhead; worker-only and '
                'overhead splits were not instrumented and remain unknown'}


def run():
    with tempfile.TemporaryDirectory(prefix='checkpoint-router-demo-') as directory:
        base = Path(directory)
        baseline = Fixture(base / 'baseline', [worker('capable', 1)])
        routed = Fixture(base / 'routed', [worker('small', 0), worker('capable', 1)])
        for task_id in ('task-one', 'task-two'):
            baseline.prepare(task_id)
            assert baseline.dispatch()['status'] == 'accepted'
            if task_id == 'task-two':
                routed.config['workers'][0]['fixture_result'] = 'wrong'
            routed.prepare(task_id)
            result = routed.dispatch()
            if task_id == 'task-two':
                assert result['status'] == 'rejected' and result['worker_id'] == 'small'
                result = routed.dispatch(trigger='boundary')
                assert result['worker_id'] == 'capable'
            assert result['status'] == 'accepted'
        baseline_summary, routed_summary = baseline.summary(), routed.summary()
        assert baseline_summary['useful_completed_tasks'] == routed_summary['useful_completed_tasks'] == 2
        assert baseline_summary['attempts'] == 2 and routed_summary['attempts'] == 3
        assert routed_summary['retries'] == 1

        boundary = Fixture(base / 'telemetry', [worker('small', 0)])
        boundary.prepare('low-resource')
        low_signals = {'records': [{'kind': 'local_resource', 'remaining': 0,
            'unit': 'bytes_available', 'source': 'synthetic boundary observation',
            'observed_at': cp.now(), 'uncertainty': None}]}
        low = boundary.dispatch(low_signals, trigger='telemetry')
        assert low['executed'] is False and low['checkpoint_id']
        assert router.report(boundary.root)['attempts'] == 0
        stale_signals = json.loads(json.dumps(low_signals))
        stale_signals['records'][0]['observed_at'] = (dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(minutes=10)).isoformat()
        try:
            boundary.dispatch(stale_signals, trigger='telemetry')
        except cp.Fault:
            stale = {'status': 'blocked-persistent-stop'}
        else:
            raise AssertionError('Stale readings must not bypass the durable stop')
        binding, store = cp.config(boundary.root)
        cp.atomic(store/'signals.json', cp.encoded({'records': [{'kind': 'local_resource',
            'remaining': 1000000, 'unit': 'bytes_available', 'source': 'fresh synthetic recovery',
            'observed_at': cp.now()}]}))
        cp.Ownership(boundary.root, binding, store).release()
        saved, inspected = cp.inspect(boundary.root)
        review = {'checkpoint_id': saved['id'], 'task_id': saved['task_id'],
            'next_action': saved['task']['next_action']['description'],
            'verification': saved['task']['next_action']['verification'],
            'current_fingerprint': inspected['current_fingerprint'], 'observed_at': cp.now(),
            'authorization': {'confirmed': True, 'scope': 'temporary fixture after fresh recovery', 'source': 'explicit demo invocation'},
            'resources': {'adequate_for_bounded_action': True, 'observed_at': cp.now(), 'evidence': 'Fresh synthetic local resource recovery, unchanged artifacts, no jobs'}, 'resolutions': {}}
        cp.atomic(store/'recovery-review.json', cp.encoded(review))
        cp.resume(boundary.root, store/'recovery-review.json', 'demo-coordinator', [])
        boundary.prepare('missing-resource')
        missing = boundary.dispatch()
        assert missing['status'] == 'accepted'
        clock = Fixture(base / 'clock', [worker('small', 0)])
        clock.prepare('scheduled-clock')
        delay = 1
        requested_at = dt.datetime.now(dt.timezone.utc)
        scheduled_at = (requested_at + dt.timedelta(seconds=delay)).isoformat()
        router.schedule(clock.root, clock.source, clock.config_path, scheduled_at,
                        'explicit_user_schedule', {'records': []})
        signal_path = clock.root / '.checkpoint/direct-disk-reading.json'
        clock_start = time.monotonic()
        clock_result = None
        polls = 0
        while time.monotonic() - clock_start < 5:
            # Refresh at the actual wake boundary; no ticket/timestamp mutation.
            fresh_disk = telemetry.disk_usage(clock.root)
            cp.atomic(signal_path, cp.encoded(fresh_disk))
            triggered_at = cp.now()
            clock_result = router.wake(clock.root, clock.source, clock.config_path,
                                       'file', signal_path, True)
            polls += 1
            if clock_result.get('action') != 'waiting':
                break
            time.sleep(.1)
        assert clock_result is not None and clock_result.get('status') == 'accepted'
        second_wake = router.wake(clock.root, clock.source, clock.config_path,
                                  'file', signal_path, True)
        assert second_wake['action'] == 'pause'
        assert router.report(clock.root)['attempts'] == 1
        clock_evidence = {'trigger': 'actual UTC clock crossing scheduled deadline',
            'basis': 'explicit_user_schedule', 'requested_at': requested_at.isoformat(),
            'scheduled_at': scheduled_at, 'trigger_observed_at': triggered_at,
            'requested_delay_seconds': delay, 'observed_delay_to_trigger_seconds':
                (dt.datetime.fromisoformat(triggered_at) - requested_at).total_seconds(),
            'bounded_poll_limit_seconds': 5, 'poll_count': polls,
            'outcome': clock_result['status'], 'worker_id': clock_result['worker_id'],
            'fresh_local_reading': fresh_disk['records'][0],
            'second_wake_action': second_wake['action'],
            'second_wake_reason': second_wake['reason'], 'attempts': 1,
            'ticket_timestamps_modified': False}
        return {'schema_version': 1, 'observed_at': cp.now(),
            'demonstration': 'synthetic deterministic demonstration; no model performance or savings claims',
            'scope': 'temporary local Git fixtures; actual checkpoint/resume/authorize/dispatch and evaluator subprocesses',
            'task_contracts': ['task-one: small and capable output 42',
                               'task-two: small injected wrong output, capable outputs 42'],
            'qualification_note': 'fixture scheduling estimates are synthetic inputs, not measured model qualifications',
            'baseline_fixed_capable': baseline_summary, 'routed': routed_summary,
            'actual_clock_trigger': clock_evidence,
            'telemetry_boundaries': {
                'fresh_low_local_resource': {'action': low['action'], 'executed': low['executed'],
                    'checkpoint_created': bool(low['checkpoint_id']), 'attempts': 0},
                'stale_low_explicit_budget': {'outcome': stale['status'], 'attempt_started': False,
                    'note': 'stale is unknown and cannot clear a persistent stop; subsequent fresh recovery required explicit reviewed resume'},
                'missing_explicit_budget': {'outcome': missing['status'], 'attempt_started': True,
                    'note': 'missing telemetry is unknown, never zero; explicit bounded budget permits fixture'}},
            'usage_limitations': 'token usage, paid API cost, and plan usage are unobserved and null; no conversion or quota attribution'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='write aggregate evidence only after all assertions pass')
    args = parser.parse_args()
    result = run()
    if args.output:
        cp.atomic(args.output, cp.encoded(result))
    else:
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
