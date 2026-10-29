#!/usr/bin/env python3
"""Collect fresh signed-in Codex allowance. Never dispatch tasks or impose stops."""
import argparse
import json
from pathlib import Path
import sys
import shutil

import checkpoint as cp
import telemetry
from codex_probe import probe


def tick(state):
    state.mkdir(parents=True, exist_ok=True)
    with cp.lock(state):
        config_path = state / 'config.json'
        config = cp.read(config_path) if config_path.exists() else {}
        try:
            executable = config.get('codex_executable', 'codex')
            if Path(executable).is_absolute() and not Path(executable).is_file():
                executable = shutil.which('codex')
                if executable is None:
                    raise cp.Fault('Configured Codex CLI is missing; install Codex CLI or update its path')
            observed = probe(executable=executable,
                             codex_home=config.get('codex_home'), timeout=25)
            if (observed['account'].get('account') or {}).get('type') != 'chatgpt':
                raise cp.Fault('Sign in with ChatGPT; no paid API fallback')
            signals = telemetry.normalize_codex(observed['rate_limits'], observed['observed_at'], observed['source'])
            cp.atomic(state / 'signals.json', cp.encoded(signals))
            status = {'last_success': observed['observed_at'], 'source': observed['source'],
                      'telemetry': telemetry.assess(signals), 'mode': 'observation-only'}
            cp.atomic(state / 'status.json', cp.encoded(status))
            return status
        except Exception as exc:
            # Retain the last observation's true timestamp; a failed poll never
            # makes stale numbers fresh or creates a task stop.
            cp.atomic(state / 'status.json', cp.encoded({'last_success': None, 'mode': 'observation-only',
                       'collection_error': type(exc).__name__, 'attempted_at': cp.now()}))
            raise


def uninstall(state, codex_home):
    """Remove exact receipt-owned global definitions, preserving unrelated hooks."""
    receipt_path = state / 'hooks-receipt.json'
    if not receipt_path.exists():
        return {'hooks_removed': 0, 'private_state_retained': True}
    with cp.lock(state):
        receipt = cp.read(receipt_path)
        path = codex_home / 'hooks.json'
        current = cp.read(path)
        for event, definition in receipt['definitions'].items():
            if current.get('hooks', {}).get(event, []).count(definition) != 1:
                raise cp.Fault('Managed hook changed; preserve and reconcile before removal')
        for event, definition in receipt['definitions'].items():
            current['hooks'][event].remove(definition)
            if not current['hooks'][event]:
                del current['hooks'][event]
        cp.atomic(path, cp.encoded(current))
        receipt_path.rename(state / ('hooks-retired-' + cp.uuid.uuid4().hex + '.json'))
    return {'hooks_removed': len(receipt['definitions']), 'private_state_retained': True,
            'native_trust_changed': False}


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--state', type=Path, default=Path.home() / '.codex/checkpoint-handoff')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('tick')
    sub.add_parser('status')
    remove = sub.add_parser('uninstall')
    remove.add_argument('--codex-home', type=Path, required=True)
    a = p.parse_args()
    if a.command == 'tick':
        result = tick(a.state)
    elif a.command == 'uninstall':
        result = uninstall(a.state, a.codex_home)
    else:
        result = cp.read(a.state / 'status.json') if (a.state / 'status.json').exists() else {'last_success': None}
        stamp = result.get('last_success')
        result['fresh'] = stamp is not None and 0 <= cp.age(stamp) <= 120
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (cp.Fault, OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc) if isinstance(exc, cp.Fault) else type(exc).__name__}), file=sys.stderr)
        sys.exit(2)
