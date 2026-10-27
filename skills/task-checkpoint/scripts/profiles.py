#!/usr/bin/env python3
"""Separate locally authenticated Codex profiles; never copies credentials or changes logins."""
import hashlib
from pathlib import Path

import checkpoint as cp
import telemetry


def fingerprint(account_id):
    if not isinstance(account_id, str) or not account_id:
        raise cp.Fault('Supported account identity unavailable')
    return hashlib.sha256(account_id.encode()).hexdigest()


def inspect_profile(home, observed, expected=None):
    home = Path(home)
    if not home.is_absolute() or not home.is_dir():
        raise cp.Fault('Codex profile directory must be explicit and available')
    local = cp.read(home / 'auth.json')
    if local.get('auth_mode') != 'chatgpt':
        raise cp.Fault('Profile is not signed in with ChatGPT; no API fallback')
    local_id = fingerprint((local.get('tokens') or {}).get('account_id'))
    remote_id = fingerprint(observed['rate_limits'].get('accountId'))
    account = observed.get('account', {}).get('account') or {}
    if account.get('type') != 'chatgpt' or remote_id != local_id or (expected and expected != remote_id):
        raise cp.Fault('Codex account identity changed; review profile before dispatch')
    return remote_id


def signals_for(observed, ident, guard=20):
    signals = telemetry.normalize_codex(observed['rate_limits'], observed['observed_at'], observed['source'])
    for record in signals['records']:
        record.update(account_fingerprint=ident, guard=guard)
    return signals


def collect(config, primary_observation):
    """One native collector, distinct account windows, isolated per-profile failures."""
    from codex_probe import probe
    accounts, statuses = {}, []
    primary = str(Path(config['codex_home']).resolve())
    guard = config.get('guard_percent', 20)
    seen = set()
    for item in config.get('codex_profiles', []):
        expected = item['account_fingerprint']
        if expected in seen:
            raise cp.Fault('Duplicate account aliases must not count as separate capacity')
        seen.add(expected)
        try:
            home = str(Path(item['codex_home']).resolve())
            observed = primary_observation if home == primary else probe(
                config.get('codex_executable', 'codex'), codex_home=home)
            actual = inspect_profile(Path(home), observed, expected)
            accounts[actual] = signals_for(observed, actual, guard)
            statuses.append({'profile_id': item['id'], 'account_fingerprint': actual,
                             'observed_at': observed['observed_at'], 'status': 'observed',
                             'windows': [{k: r.get(k) for k in ('window','remaining','guard','resets_at','observed_at')} for r in accounts[actual]['records']]})
        except Exception as exc:
            accounts[expected] = {'records': []}
            statuses.append({'profile_id': item.get('id'), 'account_fingerprint': expected,
                             'status': 'unknown', 'failure_type': type(exc).__name__})
    return {'accounts': accounts, 'profiles': statuses}


def worker_observation(worker, config):
    from codex_probe import probe
    home = worker.get('codex_home')
    expected = worker.get('account_fingerprint')
    if not home or not expected:
        raise cp.Fault('Pinned plan worker requires both profile and account identity')
    observed = probe(worker.get('executable', 'codex'), codex_home=str(Path(home).resolve()))
    ident = inspect_profile(Path(home), observed, expected)
    return observed, signals_for(observed, ident, config.get('plan_reserve_percent', 20))


def worker_environment(worker, environment):
    result = dict(environment)
    if worker.get('codex_home'):
        result['CODEX_HOME'] = str(Path(worker['codex_home']).resolve())
        for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_BASE_URL', 'CODEX_BASE_URL'):
            result.pop(key, None)
    return result
