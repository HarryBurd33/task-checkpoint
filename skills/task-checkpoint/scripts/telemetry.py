"""Conservative, unit-preserving telemetry. No network access or usage inference."""
import datetime as dt
import hashlib
import math
import shutil

UNITS = {'codex_plan': 'percent_remaining', 'api_balance': 'usd_remaining',
         'context': 'tokens_remaining', 'local_resource': 'bytes_available'}


def timestamp(value):
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    else:
        raise ValueError('timestamp required')
    if parsed.tzinfo is None:
        raise ValueError('timezone required')
    return parsed.astimezone(dt.timezone.utc)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize_codex(payload, observed_at, source='codex-account-rate-limits'):
    """Adapt the account limits tool's windows; credits never become API dollars."""
    records = []
    if not isinstance(payload, dict):
        payload = {}
    if payload.get('ordinaryUsageAllowed') is False:
        records.append({'kind': 'codex_plan', 'unit': UNITS['codex_plan'],
                        'source': source, 'observed_at': observed_at, 'remaining': None,
                        'blocked': True, 'uncertainty': 'Explicit ordinaryUsageAllowed=false; no numeric balance inferred'})
    buckets = payload.get('rateLimitsByLimitId')
    if not isinstance(buckets, dict) or not buckets:
        buckets = {'default': payload.get('rateLimits')}
    for bucket, limits in buckets.items():
        if not isinstance(limits, dict):
            continue
        for name in ('primary', 'secondary'):
            window = limits.get(name)
            if not isinstance(window, dict):
                continue
            used = window.get('usedPercent')
            valid = number(used) and 0 <= used <= 100
            record = {'kind': 'codex_plan', 'unit': UNITS['codex_plan'],
                      'source': source, 'observed_at': observed_at,
                      'remaining': 100 - used if valid else None,
                      'uncertainty': None if valid else 'missing or invalid usedPercent',
                      'window': str(bucket) + ':' + name}
            reset = window.get('resetsAt')
            if number(reset):
                try:
                    record['resets_at'] = dt.datetime.fromtimestamp(reset, dt.timezone.utc).isoformat()
                except (OverflowError, OSError, ValueError):
                    record['uncertainty'] = 'invalid reset timestamp'
                    record['supported'] = False
            elif reset is not None:
                record['uncertainty'] = 'invalid reset timestamp'
                record['supported'] = False
            records.append(record)
    # Preserve the signed-in account identity even without optional multi-profile
    # routing. Store a one-way identifier, never raw account state or credentials.
    account_id = payload.get('accountId')
    if isinstance(account_id, str) and account_id.strip():
        ident = hashlib.sha256(account_id.encode()).hexdigest()
        for record in records:
            record['account_fingerprint'] = ident
    return {'records': records}


def assess(signals, now=None, max_age_seconds=120):
    """Only fresh, well-formed observations can establish headroom or a low limit."""
    current = timestamp(now) if now is not None else dt.datetime.now(dt.timezone.utc)
    raw = from_checkpoint_signals(signals)['records'] if isinstance(signals, dict) else signals
    if not isinstance(raw, list):
        raw = []
    records, low = [], []
    statuses = {kind: 'unknown' for kind in UNITS}
    grouped = {kind: [] for kind in UNITS}
    for item in raw:
        if not isinstance(item, dict):
            continue
        record = dict(item)
        kind = record.get('kind')
        reason = None
        try:
            age = (current - timestamp(record.get('observed_at'))).total_seconds()
            value = record.get('remaining')
            threshold = record.get('guard', 20 if kind == 'codex_plan' else 0)
            if kind not in UNITS or record.get('unit') != UNITS[kind]:
                reason = 'unsupported kind or unit'
            elif not isinstance(record.get('source'), str) or not record['source'].strip():
                reason = 'missing source'
            elif record.get('supported', True) is not True:
                reason = 'unsupported observation'
            elif record.get('blocked') is not True and (not number(value) or value < 0 or kind == 'codex_plan' and value > 100):
                reason = 'invalid value'
            elif not number(threshold) or threshold < 0:
                reason = 'invalid threshold'
            elif age < 0 or not number(max_age_seconds) or age > max_age_seconds:
                reason = 'future or stale observation'
            elif record.get('resets_at') is not None and timestamp(record['resets_at']) <= current:
                reason = 'observation predates reset'
        except (ValueError, TypeError, OverflowError):
            reason = 'invalid timestamp'
        record['status'] = 'unknown' if reason else ('low' if record.get('blocked') is True or value <= threshold else 'ok')
        if reason:
            record['assessment_reason'] = reason
        records.append(record)
        if kind in grouped:
            grouped[kind].append(record['status'])
        if record['status'] == 'low':
            low.append(record)
    for kind, values in grouped.items():
        if values:
            statuses[kind] = 'low' if 'low' in values else ('unknown' if 'unknown' in values else 'ok')
    return {'statuses': statuses, 'records': records, 'low': low}


ALIASES = {'account_quota': 'codex_plan', 'context': 'context', 'api_budget': 'api_balance'}
LEGACY_GUARDS = {'account_quota': 20, 'context': 8000, 'api_budget': 1}


def normalize_direct(kind, remaining, unit, observed_at, source, uncertainty=None,
                     guard=None, resets_at=None, supported=True):
    """Wrap an observed value without inferring balance, context, or units.

    Uncertainty is a retained note, e.g. a rounded account display. Callers must
    set supported=False for an estimate or an unsupported collection method.
    Missing/malformed remaining values are always assessed as unknown.
    """
    record = {'kind': kind, 'remaining': remaining, 'unit': unit,
              'observed_at': observed_at, 'source': source,
              'uncertainty': uncertainty, 'supported': supported}
    if guard is not None:
        record['guard'] = guard
    if resets_at is not None:
        record['resets_at'] = resets_at
    return {'records': [record]}


def disk_usage(path):
    """Observe free disk bytes only; this says nothing about RAM or model fit."""
    observed_at = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        free = shutil.disk_usage(path).free
        return normalize_direct('local_resource', free, 'bytes_available', observed_at,
                                'python.shutil.disk_usage')
    except (OSError, ValueError, TypeError) as exc:
        return normalize_direct('local_resource', None, 'bytes_available', observed_at,
                                'python.shutil.disk_usage', type(exc).__name__, supported=False)


def from_checkpoint_signals(signals):
    """Bridge checkpoint policy signals, retaining their original reserve guards."""
    if not isinstance(signals, dict):
        return {'records': []}
    raw = signals.get('records', [])
    records = [dict(r) for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
    for old, kind in ALIASES.items():
        entries = signals.get(old, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                record = dict(entry, kind=kind)
                record.setdefault('guard', LEGACY_GUARDS[old])
                records.append(record)
    return {'records': records}


def to_checkpoint_signals(signals):
    """Return the three kinds understood by the existing checkpoint policy."""
    result = {old: [] for old in ALIASES}
    reverse = {kind: old for old, kind in ALIASES.items()}
    for entry in from_checkpoint_signals(signals)['records']:
        old = reverse.get(entry.get('kind'))
        if old:
            record = dict(entry)
            kind = record.pop('kind', None)
            record.setdefault('guard', 20 if kind == 'codex_plan' else 0)
            # A bridge must not turn an explicitly unsupported estimate into fact.
            if record.get('supported', True) is not True:
                record['remaining'] = None
            result[old].append(record)
    return result
