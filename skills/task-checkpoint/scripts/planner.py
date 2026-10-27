#!/usr/bin/env python3
"""DAG planning in the existing task object; no secondary queue or model polling.

An agent supplies semantic work packages at the beginning of substantial work.
This module validates bounds, selects ready work and qualified assignments, and
uses the existing dispatcher. It cannot invent conversation-only requirements.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import checkpoint as cp
import router
import router_policy as policy


def validate(plan):
    policy.require(isinstance(plan, list) and bool(plan), 'nonempty work_packages required')
    ids = []
    required = {'objective', 'permitted_files', 'permitted_actions', 'capabilities',
                'assignment', 'checkpoint_boundary', 'contract'}
    for item in plan:
        policy.require(isinstance(item, dict) and set(item) == required, 'invalid work package fields')
        for key in ('objective', 'checkpoint_boundary'):
            policy.require(isinstance(item[key], str) and bool(item[key].strip()), key + ' required')
        for key in ('permitted_files', 'permitted_actions', 'capabilities'):
            policy.require(policy.strings(item[key]), key + ' must be strings')
        for path in item['permitted_files']:
            cp.file_at(Path('/bounded-contract'), path)
        assignment = item['assignment']
        policy.require(isinstance(assignment, dict) and set(assignment) == {'model', 'effort', 'reason'}, 'assignment required')
        policy.require(all(isinstance(x, str) and x.strip() for x in assignment.values()), 'assignment must be explicit')
        policy.require(assignment['effort'] in ('low', 'medium', 'high'), 'bounded assignment effort required')
        task = cp.read(cp.ASSETS / 'task-template.json')
        task['routing'] = item['contract']
        policy.require('work_packages' not in task['routing'], 'nested plans forbidden')
        policy.validate_task(task)
        policy.require(bool(item['contract'].get('escalation_reason')), 'escalation condition required')
        ids.append(item['contract']['id'])
    policy.require(len(ids) == len(set(ids)), 'duplicate bounded IDs')
    graph = {p['contract']['id']: [d['id'] for d in p['contract']['dependencies']] for p in plan}
    visited, active = set(), set()
    def visit(ident):
        policy.require(ident in graph, 'unknown dependency: ' + ident)
        policy.require(ident not in active, 'cyclic bounded plan')
        if ident in visited:
            return
        active.add(ident)
        for dep in graph[ident]:
            visit(dep)
        active.remove(ident)
        visited.add(ident)
    for ident in ids:
        visit(ident)
    return plan


def select(task, config, signals, journal):
    """Return one immutable contract; accepted journal records are authoritative."""
    packages = validate(task['routing']['work_packages'])
    if journal.get('active') is not None:
        return {'action': 'pause', 'reason': 'worker outcome active or uncertain'}
    history = journal.get('history', [])
    accepted = {h['bounded_task_id'] for h in history if h['status'] == 'accepted'}
    for item in packages:
        r = item['contract']
        if any(d['id'] not in accepted for d in r['dependencies']):
            continue
        candidate = copy.deepcopy(task)
        candidate['routing'] = copy.deepcopy(r)
        candidate['routing']['work_packages'] = copy.deepcopy(packages)
        candidate['routing']['bounds'] = {k: copy.deepcopy(item[k]) for k in ('permitted_files', 'permitted_actions', 'checkpoint_boundary', 'assignment')}
        candidate['routing']['dependencies'] = [dict(d, status='completed') for d in r['dependencies']]
        candidate['objective'] = item['objective']
        candidate['capabilities'] = sorted(set(task['capabilities']) | set(item['capabilities']))
        candidate['next_action'] = {'description': item['objective'], 'verification': item['checkpoint_boundary']}
        attempts = [h for h in history if h['bounded_task_id'] == r['id']]
        if any(h.get('task_digest') != router.digest(candidate) for h in attempts):
            raise cp.Fault('Bounded ID changed after execution; use a new ID and review')
        if r['id'] in accepted:
            continue
        decision = policy.decide(candidate, config, signals, attempts, journal.get('current_worker'))
        worker = next((w for w in config['workers'] if w['id'] == decision.get('worker_id')), None)
        return dict(decision, task=candidate, assignment={'model': worker['model'], 'effort': worker['effort'],
                    'reason': decision['reasons'], 'usage_savings': None} if worker else None)
    return {'action': 'complete' if len(accepted & {p['contract']['id'] for p in packages}) == len(packages) else 'pause',
            'reason': 'all packages validated' if all(p['contract']['id'] in accepted for p in packages) else 'dependencies need reconciliation'}


def approve(root, source, config_path, scope, evidence, seconds=3600):
    """Explicit operator approval; never invoked merely by a scheduler/import."""
    policy.require(bool(scope) and bool(evidence) and 0 < seconds <= 86400, 'bounded approval required')
    with router.exclusive(root):
        task, config = router.load_inputs(root, source, config_path)
        validate(task['routing']['work_packages'])
        router.prerequisites(root, task)
        if router.state(root)['active'] is not None:
            raise cp.Fault('Reconcile active worker first')
        _, report = cp.inspect(root)
        if report['issues']:
            raise cp.Fault('Review checkpoint issues before approving a plan')
        record = {'task_digest': router.digest(task), 'config_digest': router.digest(config),
                  'repository_fingerprint': cp.repo(root)['fingerprint'], 'observed_at': cp.now(),
                  'lifetime_seconds': seconds, 'scope': scope, 'source': evidence}
        cp.atomic(router.paths(root)[1] / 'plan-approval.json', cp.encoded(record))
        return {'approved': True, 'expires_in_seconds': seconds}


def boundary(root, source, config_path, signals, execute=False):
    # Serializes plan selection/approval across collector ticks and foreground calls.
    _, store = cp.config(root)
    guard = store / 'planner'; guard.mkdir(exist_ok=True)
    with cp.lock(guard), router.exclusive(root):
        task, config = router.load_inputs(root, source, config_path)
        journal = router.state(root)
        choice = select(task, config, signals, journal)
        if choice['action'] in ('complete', 'pause') and 'task' not in choice:
            return choice
        candidate = choice['task']
        path = store / 'planned-input.json'
        if not execute:
            return choice
        approval = cp.read(store / 'plan-approval.json')
        if (approval['task_digest'] != router.digest(task) or approval['config_digest'] != router.digest(config)
            or not 0 <= cp.age(approval['observed_at']) <= approval['lifetime_seconds']
            or approval['repository_fingerprint'] != cp.repo(root)['fingerprint']):
            raise cp.Fault('Plan changed, expired or repository changed; fresh review required')
        cp.atomic(path, cp.encoded(candidate))
        # Explicit approval covers the immutable package and its acceptance commands.
        # Repository changes after a worker always require fresh operator review;
        # output-only tasks can progress automatically within the approved lifetime.
        cp.checkpoint(root, path, 'pre-switch')
        if cp.read(source) != task or cp.read(config_path) != config:
            raise cp.Fault('Plan input changed after approval check; fresh review required')
        router.authorize(root, path, config_path, approval['scope'], approval['source'],
                         max(.01, approval['lifetime_seconds'] - cp.age(approval['observed_at'])), _held=True, expected_fingerprint=approval['repository_fingerprint'])
        return router.dispatch(root, path, config_path, signals, trigger='planned-boundary', execute=True, _held=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('command', choices=['status', 'approve', 'boundary'])
    p.add_argument('--scope'); p.add_argument('--source')
    p.add_argument('--signals', type=Path, help='Telemetry override; otherwise use configured signals_path or project signals.json')
    p.add_argument('--seconds', type=int, default=3600)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args(); root = a.root.resolve(); _, store = cp.config(root)
    source, config_path = store/'input.json', store/'router-config.json'
    if a.command == 'approve':
        result = approve(root, source, config_path, a.scope, a.source, a.seconds)
    else:
        configured = cp.read(config_path).get('signals_path')
        signal_path = a.signals or (Path(configured).expanduser() if configured else store/'signals.json')
        if not signal_path.is_absolute():
            signal_path = root/signal_path
        result = boundary(root, source, config_path, cp.read(signal_path), a.execute)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try: main()
    except (cp.Fault, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr); sys.exit(2)
