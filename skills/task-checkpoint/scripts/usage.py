#!/usr/bin/env python3
"""Direct task limits. No pause latches, grants, timers or resume authority."""
import argparse
from pathlib import Path
import json
import sys
import tempfile

import checkpoint as cp
import telemetry


def setting(root):
    binding, store = cp.config(root)
    path = store / 'usage-policy.json'
    if not path.exists():
        return {'mode': 'percent', 'percent': 20}
    value = cp.read(path)
    if value.get('task_id') != binding['task_id'] or value.get('project_id') != binding['project_id']:
        raise cp.Fault('Usage setting belongs to a different task')
    validate(value.get('mode'), value.get('percent'))
    return value


def validate(mode, percent):
    if mode not in ('percent', 'exhaustion'):
        raise cp.Fault('Choose percent or exhaustion')
    if mode == 'percent' and (not telemetry.number(percent) or not 0 <= percent <= 100):
        raise cp.Fault('Remaining percentage must be finite and between 0 and 100')


def configure(root, percent=None, exhaustion=False, owner=None):
    mode = 'exhaustion' if exhaustion else 'percent'
    validate(mode, percent)
    binding, store = cp.config(root)
    with cp.lock(store):
        cp.mutation_owner(root, binding, store, owner)
        value = {'mode': mode, 'percent': None if exhaustion else percent,
                 'task_id': binding['task_id'], 'project_id': binding['project_id'], 'updated_at': cp.now()}
        cp.atomic(store / 'usage-policy.json', cp.encoded(value))
    return value


def assess(signals, root=None):
    choice = setting(root) if root else {'mode': 'percent', 'percent': 20}
    normalized = telemetry.from_checkpoint_signals(signals)
    for record in normalized['records']:
        if record.get('kind') == 'codex_plan':
            # Exhaustion ignores a numeric reserve, including measured zero. A
            # current provider denial still stops. Never invent additional quota.
            record['guard'] = choice['percent'] if choice['mode'] == 'percent' else 0
    result = telemetry.assess(normalized)
    low = [r for r in result['low'] if r.get('kind') != 'codex_plan'
           or choice['mode'] == 'percent' or r.get('blocked') is True]
    unknown = result['statuses']['codex_plan'] == 'unknown'
    return {'action': 'handoff' if low else 'continue', 'policy': choice,
            'quota_status': 'unknown' if unknown else ('limit-reached' if low else 'available'),
            'observations': result['records'], 'reasons': low,
            'note': 'Usage is unknown; collect a fresh reading. No quota stop is inferred.' if unknown else None}


def signals_for(root, state=None):
    _, store = cp.config(root)
    if state is not None:
        path = state / 'signals.json'
    else:
        path = store / 'signals.json'
        if not path.exists():
            path = Path.home() / '.codex/checkpoint-handoff/signals.json'
    return cp.read(path) if path.exists() else {'records': []}


def check(root, state=None, source=None, owner=None):
    result = assess(signals_for(root, state), root)
    if result['action'] == 'handoff':
        _, store = cp.config(root)
        source = source or store / 'input.json'
        # A failure is visible to the caller; no persistent stop is written.
        task = cp.read(source)
        task['metrics']['usage_policy'] = result['policy']
        task['metrics']['usage_observations'] = result['observations']
        with tempfile.TemporaryDirectory(prefix='.usage-save-', dir=store) as temporary:
            prepared = Path(temporary) / 'input.json'
            cp.atomic(prepared, cp.encoded(task))
            result['checkpoint'] = cp.checkpoint(root, prepared, 'low-resource', owner=owner)
        cp.latest(store)
    return result


def migrate(root, owner=None):
    """Archive only obsolete policy files; retain every snapshot and owner claim."""
    binding, store = cp.config(root)
    with cp.lock(store):
        cp.mutation_owner(root, binding, store, owner)
        names = ('automatic-stop.json', 'allowance-override.json', 'reserve-policy.json', 'readiness.json')
        found = [store / n for n in names if (store / n).exists()]
        archive = store / 'legacy-policy' / cp.uuid.uuid4().hex
        if found:
            archive.mkdir(parents=True)
            for path in found:
                if path.is_symlink():
                    raise cp.Fault('Linked legacy state preserved; reconcile explicitly')
            for path in found:
                path.rename(archive / path.name)
    return {'archived': [p.name for p in found], 'snapshots_and_ownership_retained': True}


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--root', type=Path, default=Path.cwd())
    p.add_argument('--owner')
    sub = p.add_subparsers(dest='command', required=True)
    config = sub.add_parser('set')
    choice = config.add_mutually_exclusive_group(required=True)
    choice.add_argument('--percent', type=float)
    choice.add_argument('--exhaustion', action='store_true')
    check_parser = sub.add_parser('check')
    check_parser.add_argument('--state', type=Path)
    check_parser.add_argument('--input', type=Path)
    sub.add_parser('status')
    sub.add_parser('migrate')
    a = p.parse_args()
    root = a.root.resolve()
    if a.command == 'set':
        out = configure(root, a.percent, a.exhaustion, a.owner)
    elif a.command == 'migrate':
        out = migrate(root, a.owner)
    elif a.command == 'status':
        out = assess(signals_for(root), root)
    else:
        out = check(root, a.state, a.input, a.owner)
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (cp.Fault, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc) if isinstance(exc, cp.Fault) else type(exc).__name__}), file=sys.stderr)
        sys.exit(2)
