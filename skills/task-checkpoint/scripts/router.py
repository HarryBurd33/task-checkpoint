#!/usr/bin/env python3
"""One bounded worker at a time, using the existing checkpoint and ownership authority."""
import argparse
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid

import checkpoint as cp
import router_policy as policy
import telemetry
import reserve

ACTIVE = {'prepared', 'launching', 'running', 'validating', 'uncertain', 'review_required'}


def digest(value):
    return cp.sha(cp.encoded(value))


def paths(root):
    binding, store = cp.config(root)
    # Coordination lives beside the existing store; no second task queue is created.
    return binding, store, store / 'router.json'


def state(root):
    binding, store, path = paths(root)
    value = cp.read(path) if path.exists() else {'version': 1, 'task_id': binding['task_id'], 'history': [], 'active': None}
    if value.get('version') != 1 or value.get('task_id') != binding['task_id']:
        raise cp.Fault('Router state belongs to another task or version')
    return value


def save(root, value):
    cp.atomic(paths(root)[2], cp.encoded(value))


@contextlib.contextmanager
def exclusive_store(root):
    common = Path(cp.git_text(root, 'rev-parse', '--git-common-dir'))
    if not common.is_absolute():
        common = root / common
    folder = common / 'checkpoint-router'
    folder.mkdir(exist_ok=True)
    with cp.lock(folder):
        yield


@contextlib.contextmanager
def exclusive(root):
    with exclusive_store(root):
        binding, store, _ = paths(root)
        cp.Ownership(root, binding, store).check()
        yield


def load_inputs(root, source, config_path):
    task = cp.read(source)
    if cp.redact(task) != task:
        raise cp.Fault('Secret-like task prose must be removed before worker dispatch; handoff and prompt must agree')
    policy.validate_task(task)
    config = cp.read(config_path)
    policy.validate_config(config)
    binding, _, _ = paths(root)
    expected = 'checkpoint:' + binding['project_id'] + ':' + binding['task_id']
    if config.get('queue_authority') != expected:
        raise cp.Fault('Use the existing checkpoint authority; external queues need a reviewed lease adapter')
    if config.get('version') != 1:
        raise cp.Fault('Unsupported router configuration')
    return task, config


def prerequisites(root, task):
    if (paths(root)[1] / 'automatic-stop.json').exists():
        raise cp.Fault('Automatic stop persists; explicitly resume after fresh resource recovery before dispatch')
    for name in task['tools']:
        if not shutil.which(name):
            raise cp.Fault('Original task tool unavailable: ' + name)
    receipt = cp.read(paths(root)[1] / 'resume.json')
    if set(task['capabilities']) - set(receipt.get('capabilities', [])):
        raise cp.Fault('Original task capability requires a new verified resume')
    if any(d['status'] != 'verified-ready' and d['status'] != 'completed' for d in task['dependencies']):
        raise cp.Fault('Original task dependencies are unresolved')


def authorize(root, source, config_path, scope, evidence, seconds=300, _held=False, expected_fingerprint=None):
    if not scope or not evidence or not 0 < seconds <= 86400:
        raise cp.Fault('Explicit scope/source and authorization lifetime up to 24 hours required')
    with contextlib.nullcontext() if _held else exclusive(root):
        task, config = load_inputs(root, source, config_path)
        prerequisites(root, task)
        _, inspected = cp.inspect(root)
        if inspected['issues']:
            raise cp.Fault('Inspect/reconcile checkpoint issues before authorizing dispatch')
        if any(j['status'] not in ('completed', 'failed', 'cancelled') for j in task['jobs']):
            raise cp.Fault('Reconcile active jobs before authorizing a worker')
        fingerprint = cp.repo(root)['fingerprint']
        if expected_fingerprint is not None and fingerprint != expected_fingerprint:
            raise cp.Fault('Source changed after plan approval; fresh review required')
        record = {'task_digest': digest(task), 'config_digest': digest(config),
                  'scope': scope, 'source': evidence, 'observed_at': cp.now(),
                  'lifetime_seconds': seconds, 'repository_fingerprint': fingerprint}
        cp.atomic(paths(root)[1] / 'router-authorization.json', cp.encoded(record))
        return {'authorized': True, 'expires_in_seconds': seconds}


def check_authorization(root, task, config):
    record = cp.read(paths(root)[1] / 'router-authorization.json')
    if record['task_digest'] != digest(task) or record['config_digest'] != digest(config):
        raise cp.Fault('Task or router config changed; fresh authorization required')
    if not 0 <= cp.age(record['observed_at']) <= record['lifetime_seconds']:
        raise cp.Fault('Router authorization expired')
    if record['repository_fingerprint'] != cp.repo(root)['fingerprint']:
        raise cp.Fault('Worktree changed since authorization; review the changes before another dispatch')


def argv_for(worker, root, output):
    interface = worker['interface']
    if interface == 'local_text':
        import local_text
        return local_text.command(worker, output.parent)[0]
    if interface == 'fixture':
        if worker.get('test_only') is not True or worker['provider'] != 'fixture' or worker['billing'] != 'local':
            raise cp.Fault('Fixture adapter cannot run a model or a provider')
        return [sys.executable, str(Path(__file__).with_name('fixture_worker.py')), worker.get('fixture_result', '42')]
    if interface == 'codex_exec':
        # Never inherit a parent's high effort or attempt a custom-agent provider override.
        command = [worker.get('executable', 'codex'), 'exec', '--json', '--ephemeral',
                   '-m', worker['model'], '-c', 'model_reasoning_effort=' + json.dumps(worker['effort']),
                   '-s', worker.get('sandbox', 'read-only'), '-C', str(root), '-o', str(output)]
        if worker.get('sandbox', 'read-only') not in ('read-only', 'workspace-write'):
            raise cp.Fault('Unsupported worker sandbox; permissions cannot be bypassed')
        if worker['provider'] in ('ollama', 'lmstudio'):
            if worker['billing'] != 'local':
                raise cp.Fault('Local provider requires a separately configured local worker')
            command += ['--oss', '--local-provider', worker['provider']]
        elif worker['provider'] == 'openai':
            command += ['-c', 'model_provider="openai"']
        else:
            raise cp.Fault('Provider requires a separately configured command worker')
        if worker.get('codex_home'):
            command += ['-c', 'forced_login_method="chatgpt"']
        command += ['-']
        return command
    command = worker.get('argv', [])
    if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
        raise cp.Fault('Worker requires a configured argument vector, never a shell command')
    return command


def collect(kind, signal_path):
    if kind == 'codex':
        from codex_probe import probe
        observed = probe()
        return telemetry.normalize_codex(observed['rate_limits'], observed['observed_at'], observed['source'])
    return cp.read(signal_path) if signal_path else {'records': []}


def _run(command, root, environment, prompt, log, timeout, on_start):
    # File output avoids pipe deadlocks and keeps private worker text out of source Git.
    # A regular input file avoids a blocking stdin pipe before timeout polling begins.
    with contextlib.ExitStack() as stack:
        out = stack.enter_context(log.open('wb'))
        stdin = subprocess.DEVNULL
        if prompt is not None:
            prompt_path = log.with_suffix('.prompt.txt')
            cp.atomic(prompt_path, prompt.encode())
            stdin = stack.enter_context(prompt_path.open('rb'))
        child = subprocess.Popen(command, cwd=str(root), env=environment,
                                 stdin=stdin,
                                 stdout=out, stderr=subprocess.STDOUT)
        on_start(child.pid)
        interrupted = []
        prior = {}
        def stop(signum, frame):
            interrupted.append(signum)
        for name in ('SIGINT', 'SIGTERM'):
            sig = getattr(signal, name, None)
            if sig is not None:
                prior[sig] = signal.signal(sig, stop)
        start = time.monotonic()
        try:
            while child.poll() is None:
                if interrupted or time.monotonic() - start >= timeout:
                    # Descendant side effects cannot be disproved by killing the direct child.
                    return {'status': 'uncertain', 'pid': child.pid, 'exit_code': None,
                            'reason': 'Interrupted or timed out; inspect process and external outcomes before recovery'}
                time.sleep(.05)
            return {'status': 'exited', 'pid': child.pid, 'exit_code': child.returncode}
        finally:
            for sig, handler in prior.items():
                signal.signal(sig, handler)


def dispatch(root, source, config_path, signals, override=None, trigger='boundary', execute=False, _held=False):
    with contextlib.nullcontext() if _held else exclusive(root):
        task, config = load_inputs(root, source, config_path)
        if reserve.blocked(reserve.assess(root, signals)):
            import monitor
            saved = monitor.stop_for_signals(root, signals)
            return {'action': 'pause', 'executed': False, 'normal_work_must_stop': True, 'checkpoint': saved, 'checkpoint_id': saved.get('checkpoint_id')}
        prerequisites(root, task)
        check_authorization(root, task, config)
        current = state(root)
        if current['active'] is not None:
            raise cp.Fault('An active/uncertain transition exists; verify it before dispatch, never retry on restart')
        _, inspection = cp.inspect(root)
        if inspection['issues']:
            raise cp.Fault('Checkpoint has unresolved artifact, repository, freshness or job issues')
        history = [h for h in current['history'] if h['bounded_task_id'] == task['routing']['id']]
        if any(h['task_digest'] != digest(task) for h in history):
            raise cp.Fault('Bounded task ID was reused for a changed contract; review and assign a new task ID')
        if any(h['status'] == 'accepted' for h in history):
            return {'action': 'complete', 'reason': 'This bounded task already passed acceptance'}
        decision = policy.decide(task, config, signals, history, current.get('current_worker'), override, trigger, assessment=reserve.assess(root, signals), worker_assessor=lambda value: reserve.assess(root, value))
        if any(j['status'] not in ('completed', 'failed', 'cancelled') for j in task['jobs']):
            raise cp.Fault('Active jobs must finish or be reconciled before dispatch')
        if decision['action'] != 'launch' or not execute:
            saved = cp.checkpoint(root, source, 'low-resource' if decision['telemetry'].get('low') else 'pre-switch')
            current['last_decision'] = decision
            save(root, current)
            return dict(decision, checkpoint_id=saved['id'], executed=False,
                        resume_command=resume_command(root, source, config_path, override))
        worker = next(w for w in config['workers'] if w['id'] == decision['worker_id'])
        if worker['interface'] == 'local_text':
            import local_text
            adapter = Path(local_text.__file__).with_name('local_text_worker.py')
            if worker['qualification'].get('adapter_sha256') != cp.sha(cp.content(adapter)):
                raise cp.Fault('Local adapter source differs from qualification; review and requalify')
        if worker['interface'] == 'command':
            saved = cp.checkpoint(root, source, 'pre-switch')
            return dict(decision, action='manual', executed=False, checkpoint_id=saved['id'],
                        worker_argv=worker.get('argv', []),
                        reason='Generic command providers require a reviewed execution adapter; automatic execution is disabled')
        # Only an explicit billing channel may be launched. API-funded workers require
        # real cost telemetry supplied by their adapter; this version provides no API adapter.
        if worker['billing'] == 'api':
            saved = cp.checkpoint(root, source, 'pre-switch')
            return dict(decision, action='manual', executed=False, checkpoint_id=saved['id'],
                        reason='Paid API execution adapter unavailable; configure a cost-capped worker before dispatch')
        if worker['interface'] == 'codex_exec' and worker['billing'] == 'local':
            saved = cp.checkpoint(root, source, 'pre-switch')
            return dict(decision, action='manual', executed=False, checkpoint_id=saved['id'],
                        reason='Local endpoint isolation must be verified in a separately configured command worker')
        if worker['interface'] == 'codex_exec' and not shutil.which(worker.get('executable', 'codex')):
            saved = cp.checkpoint(root, source, 'pre-switch')
            return dict(decision, action='manual', executed=False, checkpoint_id=saved['id'],
                        resume_command=resume_command(root, source, config_path, worker['id']),
                        reason='Codex executable unavailable on this host')
        if worker['interface'] == 'codex_exec' and worker['billing'] == 'plan':
            from codex_probe import probe
            if worker.get('codex_home'):
                import profiles
                observed, profile_signals = profiles.worker_observation(worker, config)
                if reserve.blocked(reserve.assess(root, profile_signals)):
                    import monitor
                    saved = monitor.stop_for_signals(root, profile_signals)
                    return dict(decision, action='pause', executed=False, normal_work_must_stop=True, checkpoint_id=saved['checkpoint_id'], reason='Selected account reserve reached; explicit reviewed handoff required')
                if reserve.assess(root, profile_signals)['statuses']['codex_plan'] != 'ok':
                    raise cp.Fault('Selected account allowance unknown; no plan worker launched')
            else:
                observed = probe(worker.get('executable', 'codex'))
            account = observed.get('account', {}).get('account') or {}
            if account.get('type') != 'chatgpt':
                raise cp.Fault('Plan worker requires verified ChatGPT login; API credentials are not a fallback')
            available = {m.get('model', m.get('id')): m for m in observed['models'].get('data', [])}
            if worker['model'] not in available:
                raise cp.Fault('Selected model absent from live model/list')
            efforts = {e.get('reasoningEffort') for e in available[worker['model']].get('supportedReasoningEfforts', [])}
            if worker['effort'] not in efforts:
                raise cp.Fault('Selected effort absent from live model/list')
            fresh = profile_signals if worker.get('codex_home') else telemetry.normalize_codex(observed['rate_limits'], observed['observed_at'], observed['source'])
            if worker.get('codex_home'):
                fresh['accounts'] = dict(signals.get('accounts', {}))
                fresh['accounts'][worker['account_fingerprint']] = {'records': list(fresh['records'])}
            guard = max([20] + [r.get('guard', 20) for r in signals.get('records', []) if r.get('kind') == 'codex_plan' and telemetry.number(r.get('guard', 20))])
            for r in fresh['records']:
                r['guard'] = guard
            fresh['records'].extend(r for r in signals.get('records', []) if r.get('kind') != 'codex_plan')
            fresh_decision = policy.decide(task, config, fresh, history, current.get('current_worker'), worker['id'], trigger, assessment=reserve.assess(root, fresh), worker_assessor=lambda value: reserve.assess(root, value))
            if fresh_decision['action'] != 'launch':
                if reserve.blocked(fresh_decision['telemetry']):
                    import monitor
                    monitor.stop_for_signals(root, fresh)
                return dict(fresh_decision, executed=False, normal_work_must_stop=True)
        run_id = uuid.uuid4().hex
        folder = paths(root)[1] / 'router-runs' / run_id
        folder.mkdir(parents=True)
        output = folder / 'result.txt'
        command = argv_for(worker, root, output)
        if worker['interface'] == 'manual' or not shutil.which(command[0]):
            saved = cp.checkpoint(root, source, 'pre-switch')
            return dict(decision, action='manual', executed=False, checkpoint_id=saved['id'],
                        worker_argv=command, resume_command=resume_command(root, source, config_path, worker['id']),
                        reason='Target worker interface unavailable here; configure it on the destination and run the resume command')
        for check in task['routing']['acceptance']:
            if not isinstance(check.get('argv'), list) or not check['argv'] or not shutil.which(check['argv'][0]):
                raise cp.Fault('Acceptance command unavailable; no worker was launched')
        record = {'id': run_id, 'bounded_task_id': task['routing']['id'], 'worker_id': worker['id'],
                  'model': worker['model'], 'effort': decision['effort'], 'status': 'prepared',
                  'task_digest': digest(task), 'config_digest': digest(config), 'started_at': cp.now(),
                  'api_cost_usd': None, 'plan_usage': None, 'token_usage': None, 'wall_seconds': 0,
                  'evaluator_seconds': 0, 'checks': [], 'pre_repository': cp.repo(root)['fingerprint']}
        if worker.get('codex_home'):
            record['account_fingerprint'] = worker['account_fingerprint']
            record['execution_profile'] = worker['codex_home']
        current['active'] = record
        save(root, current)  # Durable intent precedes checkpoint and process creation.
        pending = dict(task, jobs=task['jobs'] + [{'id': run_id, 'kind': 'router-worker', 'status': 'pending',
                       'source': 'router-runs/' + run_id, 'observed_at': cp.now()}])
        pending_source = folder / 'input.json'
        cp.atomic(pending_source, cp.encoded(pending))
        saved = cp.checkpoint(root, pending_source, 'pre-switch')
        cp.latest(paths(root)[1])
        record.update(checkpoint_id=saved['id'], status='launching')
        save(root, current)
        binding, store, _ = paths(root)
        cp.Ownership(root, binding, store).check()
        environment = dict(os.environ, CHECKPOINT_RESULT=str(output), CHECKPOINT_RUN_ID=run_id,
                           CHECKPOINT_HANDOFF=saved['handoff'])
        if worker.get('codex_home'):
            import profiles
            environment = profiles.worker_environment(worker, environment)
        prompt = ('Perform only the bounded task below. The coordinator retains the exclusive task lease. '
                  'Do not launch other workers, change providers/permissions, or acquire/release ownership. '
                  'Verify the next action and supplied artifacts before work. Return the requested result.\n'
                  + json.dumps(task))
        def started(pid):
            record.update(status='running', pid=pid)
            save(root, current)
        check_authorization(root, task, config)
        before_files = cp.repo(root)['files']
        begin = time.monotonic()
        remaining = task['routing']['budget']['max_wall_seconds'] - sum(h.get('wall_seconds', 0) for h in history)
        worker_environment = environment
        worker_prompt = prompt if worker['interface'] == 'codex_exec' else None
        if worker['interface'] == 'local_text':
            import local_text
            command, worker_environment = local_text.command(worker, folder)
            worker_prompt = local_text.request(worker, task)
        result = _run(command, root, worker_environment, worker_prompt,
                      folder / 'worker.log', remaining, started)
        record.update(result)
        if result['status'] == 'uncertain':
            record['wall_seconds'] = time.monotonic() - begin
            save(root, current)
            return dict(record, normal_work_must_stop=True)
        record['status'] = 'validating'
        save(root, current)
        valid = result['exit_code'] == 0
        if valid and worker['interface'] == 'local_text':
            try:
                record['local_usage'] = local_text.result(folder / 'worker.log', output)
            except (ValueError, OSError, KeyError, TypeError):
                valid = False
        bounds = task['routing'].get('bounds')
        if bounds is not None:
            after_files = cp.repo(root)['files']
            changed = {p for p in set(before_files) | set(after_files) if before_files.get(p) != after_files.get(p)}
            forbidden = sorted(p for p in changed if not any(p == allowed or p.startswith(allowed.rstrip('/') + '/') for allowed in bounds['permitted_files']))
            record['out_of_scope_files'] = forbidden
            valid = valid and not forbidden
        if valid:
            for index, check in enumerate(task['routing']['acceptance']):
                evaluation_start = time.monotonic()
                timeout = max(.01, remaining - (evaluation_start - begin))
                outcome = _run(check['argv'], root, environment, None, folder / ('check-%d.log' % index),
                               timeout, lambda pid: _validation_started(root, current, pid))
                record['evaluator_seconds'] += time.monotonic() - evaluation_start
                record['checks'].append({'id': check['id'], **outcome})
                if outcome['status'] == 'uncertain':
                    record.update(status='uncertain', wall_seconds=time.monotonic() - begin)
                    save(root, current)
                    return dict(record, normal_work_must_stop=True)
                valid = valid and outcome['exit_code'] == 0
        record.update(status=('review_required' if valid and task['routing']['risk'] == 'high' else 'accepted' if valid else 'rejected'),
                      finished_at=cp.now(), wall_seconds=time.monotonic() - begin,
                      post_repository=cp.repo(root)['fingerprint'])
        cp.Ownership(root, binding, store).check()
        if worker['interface'] == 'codex_exec':
            record['token_usage'] = read_usage(folder / 'worker.log')
        save(root, current)
        completed = dict(task, observations=task['observations'] + ['Router attempt ' + run_id + ': ' + record['status']],
                         jobs=task['jobs'] + [{'id': run_id, 'kind': 'router-worker', 'status': 'completed' if valid else 'failed',
                                               'source': 'router-runs/' + run_id, 'observed_at': cp.now()}])
        cp.atomic(folder / 'completed-input.json', cp.encoded(completed))
        cp.checkpoint(root, folder / 'completed-input.json', 'milestone' if valid else 'error')
        if record['status'] != 'review_required':
            current['history'].append(dict(record))
            current['active'] = None
        current['current_worker'] = worker['id']
        save(root, current)
        # Changes need fresh operator review before another attempt; unchanged output-only
        # work may retry within the same explicit authorization and bounded budget.
        return dict(record, normal_work_must_stop=record['status'] != 'accepted')


def _validation_started(root, current, pid):
    current['active']['validator_pid'] = pid
    save(root, current)


def read_usage(log):
    usage = []
    for line in log.read_text(errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'turn.completed' and isinstance(event.get('usage'), dict):
            usage.append(event['usage'])
    return usage or None


def resume_command(root, source, config_path, override=None):
    command = [sys.executable, str(Path(__file__).resolve()), '--root', str(root), 'dispatch',
               '--input', str(source.resolve()), '--config', str(config_path.resolve()), '--collector', 'codex', '--execute']
    configured_signals = cp.read(config_path).get('signals_path')
    if configured_signals:
        index = command.index('--collector')
        command[index + 1] = 'signals'
        command += ['--signals', str(Path(configured_signals).resolve())]
    if override:
        command += ['--worker', str(override)]
    return shlex.join(command)


def reconcile(root, run_id, outcome, evidence, reviewer=None):
    """Operator evidence, never an automatic lock steal or PID-only liveness guess."""
    with exclusive(root):
        current = state(root)
        active = current['active']
        if not active or active['id'] != run_id or not evidence:
            raise cp.Fault('Matching active transition and current outcome evidence required')
        if outcome == 'accepted':
            if active['status'] not in ('review_required', 'accepted') or not reviewer or reviewer == active['worker_id']:
                raise cp.Fault('Acceptance requires completed checks plus an independent reviewer identity')
            if cp.repo(root)['fingerprint'] != active['post_repository']:
                raise cp.Fault('Worktree changed since validation; acceptance must be repeated')
        elif outcome != 'rejected':
            raise cp.Fault('Uncertain work may only be rejected after verifying the process and side effects')
        if active['status'] in ('prepared', 'launching', 'running', 'validating', 'uncertain'):
            active['wall_seconds'] = None  # A child may have continued after the coordinator stopped.
        active.update(status=outcome, reconciliation={'evidence': evidence, 'reviewer': reviewer, 'observed_at': cp.now()},
                      finished_at=cp.now())
        current['history'].append(dict(active))
        current['active'] = None
        save(root, current)
        return {'reconciled': run_id, 'outcome': outcome, 'next': 'Inspect checkpoint, reconcile jobs, and refresh authorization before dispatch'}


def schedule(root, source, config_path, at, basis, signals):
    with exclusive(root):
        task, config = load_inputs(root, source, config_path)
        check_authorization(root, task, config)
        if cp.age(at) >= 0:
            raise cp.Fault('Schedule must be in the future')
        if basis == 'verified_reset':
            assessment = telemetry.assess(signals)
            resets = [r.get('resets_at') for r in assessment['low'] if r.get('kind') == 'codex_plan']
            if at not in resets:
                raise cp.Fault('Reset schedule needs an exact reset from fresh supported low telemetry')
        target = paths(root)[1] / 'router-schedule.json'
        if target.exists() and cp.read(target)['status'] in ('pending', 'checking'):
            raise cp.Fault('An existing schedule needs reconciliation; no duplicate scheduler')
        value = {'id': uuid.uuid4().hex, 'at': at, 'basis': basis, 'status': 'pending',
                 'task_digest': digest(task), 'config_digest': digest(config)}
        cp.atomic(target, cp.encoded(value))
        return dict(value, note='Only a running watch process or explicit wake executes this ticket; fresh budget and authorization checks remain required')


def wake(root, source, config_path, collector, signal_path, execute):
    target = paths(root)[1] / 'router-schedule.json'
    with exclusive(root):
        ticket = cp.read(target)
        if ticket['status'] != 'pending':
            return {'action': 'pause', 'reason': 'Schedule already consumed or interrupted; no automatic redelivery'}
        if cp.age(ticket['at']) < 0:
            return {'action': 'waiting', 'at': ticket['at']}
        task, config = load_inputs(root, source, config_path)
        if ticket['task_digest'] != digest(task) or ticket['config_digest'] != digest(config):
            raise cp.Fault('Scheduled task/config changed')
        ticket['status'] = 'checking'
        cp.atomic(target, cp.encoded(ticket))
    # No old low reading is recycled as a fresh reading after a reset.
    signals = collect(collector, signal_path)
    result = dispatch(root, source, config_path, signals, trigger='scheduled', execute=execute)
    ticket['status'] = 'consumed'
    ticket['result'] = result.get('status', result.get('action'))
    cp.atomic(target, cp.encoded(ticket))
    return result


def report(root):
    history = state(root)['history']
    accepted = [r for r in history if r['status'] == 'accepted']
    costs = [r.get('api_cost_usd') for r in history]
    wall = [r.get('wall_seconds') for r in history]
    return {'attempts': len(history), 'accepted_attempts': len(accepted),
            'useful_completed_tasks': len({r['bounded_task_id'] for r in accepted}),
            'acceptance_rate': len(accepted) / len(history) if history else None,
            'retries': len(history) - len({r['bounded_task_id'] for r in history}),
            'latency_seconds': sum(wall) if all(v is not None for v in wall) else None,
            'evaluator_seconds': sum(r.get('evaluator_seconds', 0) for r in history),
            'observed_api_cost_usd': sum(costs) if costs and all(c is not None for c in costs) else None,
            'observed_plan_usage': None, 'active': state(root)['active'],
            'note': 'Attempt acceptance differs from task completion; plan usage is account-wide, not attributed from token counts'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('authorize', 'dispatch', 'schedule', 'wake', 'watch'):
        p = subs.add_parser(name)
        p.add_argument('--input', type=Path, required=True)
        p.add_argument('--config', type=Path, required=True)
        if name == 'authorize':
            p.add_argument('--scope', required=True)
            p.add_argument('--source', required=True)
            p.add_argument('--seconds', type=int, default=300)
        else:
            p.add_argument('--signals', type=Path)
            p.add_argument('--collector', choices=['file', 'codex'], default='file')
            p.add_argument('--execute', action='store_true')
        if name == 'dispatch':
            p.add_argument('--worker')
            p.add_argument('--trigger', choices=['boundary', 'manual', 'telemetry', 'new-task'], default='boundary')
        if name == 'schedule':
            p.add_argument('--at', required=True)
            p.add_argument('--basis', choices=['explicit_user_schedule', 'verified_reset'], required=True)
        if name == 'watch':
            p.add_argument('--interval', type=float, default=15)
            p.add_argument('--max-polls', type=int, default=20)
    p = subs.add_parser('reconcile')
    p.add_argument('--run-id', required=True)
    p.add_argument('--outcome', choices=['accepted', 'rejected'], required=True)
    p.add_argument('--evidence', required=True)
    p.add_argument('--reviewer')
    subs.add_parser('report')
    p = subs.add_parser('collect-codex')
    p.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    root = a.root.resolve()
    if a.command == 'authorize':
        result = authorize(root, a.input, a.config, a.scope, a.source, a.seconds)
    elif a.command == 'dispatch':
        result = dispatch(root, a.input, a.config, collect(a.collector, a.signals), a.worker, a.trigger, a.execute)
    elif a.command == 'reconcile':
        result = reconcile(root, a.run_id, a.outcome, a.evidence, a.reviewer)
    elif a.command == 'schedule':
        result = schedule(root, a.input, a.config, a.at, a.basis, collect(a.collector, a.signals))
    elif a.command in ('wake', 'watch'):
        if a.command == 'watch' and not (1 <= a.interval <= 60 and 1 <= a.max_polls <= 10000):
            raise cp.Fault('Use bounded polling: interval 1..60 seconds, max-polls 1..10000')
        for index in range(a.max_polls if a.command == 'watch' else 1):
            result = wake(root, a.input, a.config, a.collector, a.signals, a.execute)
            if result.get('action') != 'waiting':
                break
            if a.command == 'watch' and index < a.max_polls - 1:
                time.sleep(a.interval)
    elif a.command == 'collect-codex':
        result = collect('codex', None)
        cp.atomic(a.output, cp.encoded(result))
    else:
        result = report(root)
    print(json.dumps(cp.redact(result), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (cp.Fault, OSError, subprocess.SubprocessError, KeyError, ValueError, TypeError) as exc:
        print(json.dumps({'ok': False, 'normal_work_must_stop': True,
                          'error': str(exc) if isinstance(exc, cp.Fault) else type(exc).__name__}), file=sys.stderr)
        sys.exit(2)
