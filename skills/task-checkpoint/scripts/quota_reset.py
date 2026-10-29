#!/usr/bin/env python3
"""Read-only evidence of a real quota-window transition. Never resumes a task."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

import telemetry


def capture(signals, now=None):
    current = telemetry.timestamp(now) if now is not None else dt.datetime.now(dt.timezone.utc)
    assessed = telemetry.assess(signals, now=current)
    records = [r for r in assessed['records'] if r.get('kind') == 'codex_plan']
    if not records:
        raise ValueError('No account quota windows')
    keys = set()
    for r in records:
        key = (r.get('account_fingerprint'), r.get('window'))
        if r['status'] == 'unknown' or r.get('blocked') is True or not all(isinstance(x, str) and x.strip() for x in key):
            raise ValueError('Fresh, identified account windows are required')
        if key in keys:
            raise ValueError('Duplicate account/window')
        keys.add(key)
        telemetry.timestamp(r.get('resets_at'))
    return {'schema_version': 1, 'captured_at': current.isoformat(), 'records': records}


def verify(baseline, signals, now=None):
    current = telemetry.timestamp(now) if now is not None else dt.datetime.now(dt.timezone.utc)
    result = {'verified': False, 'action': 'report-only', 'checked_at': current.isoformat(), 'windows': []}
    try:
        if baseline.get('schema_version') != 1 or telemetry.timestamp(baseline['captured_at']) > current:
            raise ValueError('Invalid baseline')
        prior = capture(baseline, now=baseline['captured_at'])
        fresh = capture(signals, now=current)
        before = {(r['account_fingerprint'], r['window']): r for r in prior['records']}
        after = {(r['account_fingerprint'], r['window']): r for r in fresh['records']}
        if set(before) != set(after):
            raise ValueError('Account/window set changed; no substitution is allowed')
        for key, old in before.items():
            new = after[key]
            due = telemetry.timestamp(old['resets_at'])
            observed = telemetry.timestamp(new['observed_at'])
            advanced = telemetry.timestamp(new['resets_at']) > due
            status = 'not-due' if current < due else ('observed' if observed >= due and advanced else 'unverified')
            result['windows'].append({'account_fingerprint': key[0], 'window': key[1],
                                      'previous_reset': old['resets_at'], 'current_reset': new['resets_at'],
                                      'observed_at': new['observed_at'], 'remaining': new['remaining'], 'status': status})
        result['verified'] = all(w['status'] == 'observed' for w in result['windows'])
        result['status'] = 'verified' if result['verified'] else ('not-due' if any(w['status'] == 'not-due' for w in result['windows']) else 'unverified')
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        result.update(status='unverified', reason=str(exc))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = p.add_subparsers(dest='command', required=True)
    first = sub.add_parser('baseline'); first.add_argument('--signals', type=Path, required=True)
    check = sub.add_parser('verify'); check.add_argument('--signals', type=Path, required=True); check.add_argument('--baseline', type=Path, required=True)
    a = p.parse_args()
    signals = json.loads(a.signals.read_text())
    result = capture(signals) if a.command == 'baseline' else verify(json.loads(a.baseline.read_text()), signals)
    print(json.dumps(result, indent=2))
    return 0 if a.command == 'baseline' or result['verified'] or result.get('status') == 'not-due' else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'verified': False, 'action': 'report-only', 'error': type(exc).__name__}), file=sys.stderr)
        sys.exit(2)
