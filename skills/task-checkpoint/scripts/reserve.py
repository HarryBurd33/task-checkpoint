#!/usr/bin/env python3
"""Explicit local allowance-reserve grants; never account-limit or permission overrides."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys
import uuid
import checkpoint as cp
import telemetry

NAME = 'allowance-override.json'
POLICY_NAME = 'reserve-policy.json'
TERMINAL = {'completed', 'canceled', 'cancelled', 'transferred'}


def _threshold(mode, percent=None):
    if mode == 'percent':
        if not telemetry.number(percent) or not 0 <= percent <= 100:
            raise cp.Fault('Percent reserve requires a finite number from 0 through 100')
        return percent
    if percent is not None:
        raise cp.Fault('--percent is only valid with --mode percent')
    if mode == 'ten':
        return 10
    if mode == 'exhaustion':
        return None
    raise cp.Fault('Explicit reserve mode ten, percent or exhaustion is required')


def blocked(summary):
    return bool(summary['low']) or summary.get('override_blocked', False)


def kinds(summary):
    return sorted({r['kind'] for r in summary['low']} | ({'codex_plan'} if summary.get('override_blocked') else set()))


def _current(now=None):
    return telemetry.timestamp(now) if now is not None else telemetry.timestamp(cp.now())


def _key(record):
    account, window = record.get('account_fingerprint'), record.get('window')
    if not isinstance(account, str) or not account.strip() or not isinstance(window, str) or not window.strip():
        raise cp.Fault('Fresh account identity and named quota windows are required')
    return account, window


def _load(root):
    binding, store = cp.config(root)
    path = store / NAME
    value = cp.read(path) if path.exists() else None
    if value is not None:
        if (value.get('version') != 1 or value.get('project_id') != binding['project_id']
                or value.get('task_id') != binding['task_id'] or value.get('mode') not in ('ten', 'percent', 'exhaustion')
                or value.get('state') not in ('pending_resume', 'active', 'revoked')
                or not isinstance(value.get('windows'), list) or not value['windows']
                or not value.get('reason') or not value.get('source')):
            raise cp.Fault('Invalid or foreign allowance override; inspect before continuing')
        _threshold(value['mode'], value.get('percent'))
    return binding, store, value


def _lifecycle(store, binding):
    path = store / 'task-lifecycle.json'
    if not path.exists():
        return None
    value = cp.read(path)
    if value.get('project_id') != binding['project_id'] or value.get('task_id') != binding['task_id']:
        raise cp.Fault('Lifecycle belongs to a different task')
    return value.get('status')


def _lifecycle_hash(store):
    path = store / 'task-lifecycle.json'
    return cp.sha(cp.content(path)) if path.exists() else None


def _windows(summary):
    plan = [r for r in summary['records'] if r.get('kind') == 'codex_plan']
    if not plan:
        raise cp.Fault('Account telemetry missing; refresh before overriding the reserve')
    output = {}
    for r in plan:
        if r.get('blocked') is True:
            raise cp.Fault('Codex account has denied ordinary usage; reserve overrides cannot bypass it')
        key = _key(r)
        if r['status'] == 'unknown' or not r.get('resets_at'):
            raise cp.Fault('Fresh supported readings and observed reset times are required')
        reset = telemetry.timestamp(r['resets_at']).isoformat()
        if key in output and output[key] != reset:
            raise cp.Fault('Conflicting quota-window observations')
        output[key] = reset
    return output


def _record_windows(value):
    output = {}
    for item in value['windows']:
        key = _key(item)
        reset = telemetry.timestamp(item['resets_at']).isoformat()
        if key in output:
            raise cp.Fault('Duplicate recorded override window')
        output[key] = reset
    return output


def _workspace(root):
    root = Path(root).resolve()
    common = Path(cp.git_text(root, 'rev-parse', '--git-common-dir'))
    if not common.is_absolute():
        common = root / common
    return {'root': str(root), 'git_common_dir': str(common.resolve())}


def _scope(root, binding, store, value, check_receipt=True):
    if value.get('workspace') != _workspace(root):
        raise cp.Fault('Allowance grant belongs to another workspace; grant does not transfer')
    ownership = cp.Ownership(root, binding, store)
    current = ownership.value(ownership.tip())
    expected = value.get('active_owner')
    if current.get('owner'):
        current = ownership.check()
        if value.get('intended_owner') and current.get('owner') != value['intended_owner']:
            raise cp.Fault('Allowance grant belongs to another owner')
        if value.get('grant_owner_token') and current.get('token') != value['grant_owner_token']:
            raise cp.Fault('Ownership lease changed since the allowance grant')
    elif (store / 'owner.json').exists() or value.get('grant_owner_token') or value['state'] == 'active':
        raise cp.Fault('Allowance grant ownership is absent or changed')
    if value['state'] == 'active':
        if not expected or any(current.get(k) != expected.get(k) for k in ('owner', 'token')):
            raise cp.Fault('Active allowance grant requires its exact resumed owner lease')
        if check_receipt and (not (store / 'resume.json').exists() or
                cp.sha(cp.content(store / 'resume.json')) != value.get('resume_receipt_sha256')):
            raise cp.Fault('Active allowance grant resume receipt is absent or changed')
    return current if current.get('owner') else None



def _policy(root):
    """Validate a device/task/lease-local baseline; never import another owner's choice."""
    binding, store = cp.config(root)
    path = store / POLICY_NAME
    if not path.exists():
        return None
    value = cp.read(path)
    if (value.get('version') != 1 or value.get('project_id') != binding['project_id']
            or value.get('task_id') != binding['task_id'] or value.get('workspace') != _workspace(root)
            or not value.get('reason') or not value.get('source')
            or value.get('lifecycle_sha256') != _lifecycle_hash(store)
            or _lifecycle(store, binding) in TERMINAL):
        raise cp.Fault('Invalid or foreign task-local reserve policy; inspect and explicitly reconcile')
    _threshold('percent', value.get('percent'))
    owner = cp.Ownership(root, binding, store).check()
    expected = value.get('owner')
    if not isinstance(expected, dict) or any(owner.get(k) != expected.get(k) for k in ('owner', 'token')):
        raise cp.Fault('Task-local reserve policy belongs to another ownership lease')
    return value


def _baseline(root, signals, now=None, max_age_seconds=120):
    value = _policy(root)
    normalized = telemetry.from_checkpoint_signals(signals)
    if value is not None:
        for record in normalized['records']:
            if record.get('kind') == 'codex_plan':
                record['guard'] = value['percent']
    summary = telemetry.assess(normalized, now, max_age_seconds)
    summary['reserve_policy'] = value
    return summary


def configure(root, percent, owner, reason, source):
    """Set the initial task-local numeric stop; cannot clear a stop or resume work."""
    percent = _threshold('percent', percent)
    if any(not isinstance(v, str) or not v.strip() for v in (owner, reason, source)):
        raise cp.Fault('Explicit current owner, user reason and authorization source are required')
    binding, store = cp.config(root)
    with cp.lock(store):
        claim = _owner_gate(root, binding, store, owner)
        if claim is None:
            raise cp.Fault('Configure requires the current verified exclusive owner lease')
        if (store / 'automatic-stop.json').exists():
            raise cp.Fault('An existing stop cannot be changed by configuration; use the reviewed grant/resume procedure')
        if _lifecycle(store, binding) in TERMINAL:
            raise cp.Fault('Task is completed/canceled/transferred; configuration cannot restore authority')
        _, _, override = _load(root)
        if override is not None and override['state'] != 'revoked':
            raise cp.Fault('Reconcile the existing pending or active allowance grant before changing the baseline')
        saved, _ = cp.latest(store)
        if saved['project_id'] != binding['project_id'] or saved['task_id'] != binding['task_id']:
            raise cp.Fault('Checkpoint belongs to another task')
        if any(j['status'] not in ('completed', 'failed', 'cancelled') for j in saved['task']['jobs']):
            raise cp.Fault('Active or uncertain task jobs must be reconciled first')
        # Semantic input can contain newer jobs than the latest saved generation.
        if (store / 'input.json').exists():
            task = cp.read(store / 'input.json')
            if any(j.get('status') not in ('completed', 'failed', 'cancelled') for j in task.get('jobs', [])):
                raise cp.Fault('Active or uncertain input jobs must be reconciled first')
        cp.verify_root(root, saved)
        previous = store / POLICY_NAME
        if previous.exists():
            history = store / 'reserve-policy-history'
            history.mkdir(exist_ok=True)
            cp.atomic(history / (uuid.uuid4().hex + '.json'), cp.content(previous))
        value = {'version': 1, 'project_id': binding['project_id'], 'task_id': binding['task_id'],
                 'workspace': _workspace(root), 'percent': percent,
                 'owner': {k: claim[k] for k in ('owner', 'token')},
                 'lifecycle_sha256': _lifecycle_hash(store), 'created_at': cp.now(),
                 'reason': reason.strip(), 'source': source.strip(),
                 'automatic_resume': False, 'permissions_restored': False}
        cp.atomic(previous, cp.encoded(value))
        return value


def assess(root, signals, now=None, max_age_seconds=120, allow_pending=False, require_account=False):
    """Assess measured data under a validated local grant, without changing inputs.

    Expired/revoked/terminal grants use the normal configured reserve. Unknown or
    foreign observations while relying on a grant block work without inventing a
    numeric low reading. A pending grant only informs an explicit resume review.
    """
    current = _current(now)
    summary = _baseline(root, signals, current, max_age_seconds)
    require_account = require_account or summary['reserve_policy'] is not None
    summary.update(override=None, override_blocked=False)
    if require_account and summary['statuses']['codex_plan'] == 'unknown':
        summary['override_blocked'] = True
        summary['account_reason'] = 'Fresh supported account observations are required before work'
    binding, store, value = _load(root)
    if value is None:
        return summary
    summary['override'] = {'mode': value['mode'], 'state': value['state'], 'id': value['id']}
    threshold = _threshold(value['mode'], value.get('percent'))
    summary['override']['percent'] = threshold
    if value['state'] == 'pending_resume' and not allow_pending:
        summary['override_blocked'] = True
        summary['override']['reason'] = 'Override granted; fresh explicit reviewed resume is still required'
        return summary
    if value['state'] == 'revoked' or _lifecycle(store, binding) in TERMINAL:
        summary['override']['effective'] = 'default'
        return summary
    if value.get('lifecycle_sha256') != _lifecycle_hash(store):
        summary['override']['effective'] = 'lifecycle-changed-default'
        return summary
    try:
        _scope(root, binding, store, value)
        expected = _record_windows(value)
        if current < telemetry.timestamp(value['created_at']):
            raise cp.Fault('Override creation time is in the future')
        if current >= min(telemetry.timestamp(v) for v in expected.values()):
            summary['override']['effective'] = 'expired-default'
            return summary
        if value['state'] == 'pending_resume' and not allow_pending:
            raise cp.Fault('Override granted; fresh explicit reviewed resume is still required')
        observed = _windows(summary)
        if observed != expected:
            raise cp.Fault('Account/window/reset changed or missing; grant does not transfer')
    except (cp.Fault, ValueError, KeyError, TypeError) as exc:
        summary['override_blocked'] = True
        summary['override']['reason'] = str(exc)
        return summary
    for r in summary['records']:
        if r.get('kind') != 'codex_plan':
            continue
        # _windows already verified freshness, source, identity and no hard denial.
        r['status'] = 'low' if threshold is not None and r['remaining'] <= threshold else 'ok'
        r['effective_guard'] = threshold
    states = [r['status'] for r in summary['records'] if r.get('kind') == 'codex_plan']
    summary['statuses']['codex_plan'] = 'low' if 'low' in states else 'ok'
    summary['low'] = [r for r in summary['records'] if r['status'] == 'low']
    summary['override']['effective'] = value['mode']
    return summary


def _owner_gate(root, binding, store, intended_owner=None):
    if intended_owner is not None and (not isinstance(intended_owner, str) or not intended_owner.strip()):
        raise cp.Fault('Explicit current owner identity is required')
    journal = cp.read(store / 'router.json') if (store / 'router.json').exists() else {}
    if journal.get('active') is not None:
        raise cp.Fault('Active or uncertain worker must be reconciled first')
    owner = cp.Ownership(root, binding, store)
    if owner.value(owner.tip()).get('owner'):
        current = owner.check()
        if intended_owner is not None and current.get('owner') != intended_owner:
            raise cp.Fault('Task already owned by another agent; never use its lease')
        return current
    if (store / 'owner.json').exists():
        raise cp.Fault('Stale ownership receipt; reconcile before changing the allowance grant')
    return None


def grant(root, mode, signals, reason, source, now=None, signals_path=None, owner=None, percent=None):
    threshold = _threshold(mode, percent)
    if not isinstance(reason, str) or not reason.strip() or not isinstance(source, str) or not source.strip():
        raise cp.Fault('Explicit mode, current user reason and authorization source are required')
    current = _current(now)
    binding, store = cp.config(root)
    with cp.lock(store):
        claim = _owner_gate(root, binding, store, owner)
        if _lifecycle(store, binding) in TERMINAL:
            raise cp.Fault('Task is completed/canceled/transferred; new current authorization is required')
        saved, _ = cp.latest(store)
        if saved['project_id'] != binding['project_id'] or saved['task_id'] != binding['task_id']:
            raise cp.Fault('Checkpoint belongs to another task')
        if any(j['status'] not in ('completed', 'failed', 'cancelled') for j in saved['task']['jobs']):
            raise cp.Fault('Active or uncertain task jobs must be reconciled first')
        marker = cp.read(store / 'automatic-stop.json') if (store / 'automatic-stop.json').exists() else None
        if marker and (marker.get('project_id') != binding['project_id'] or marker.get('task_id') != binding['task_id']):
            raise cp.Fault('Stop belongs to another task')
        verified_stop = marker and marker.get('checkpoint_status') == 'verified' and marker.get('checkpoint_id') == saved['id']
        if marker and not verified_stop:
            raise cp.Fault('Existing preservation is incomplete or checkpoint changed; repair and verify before override')
        if saved['trigger'] != 'low-resource' and not verified_stop:
            raise cp.Fault('First save and verify the automatic reserve stop; a grant cannot pre-arm bypass')
        cp.verify_root(root, saved)
        # Native account files omit per-project context/API/disk observations.
        # Merge those existing observations; never use them as account readings.
        combined = {'records': list(telemetry.from_checkpoint_signals(signals)['records'])}
        local_signals = store / 'signals.json'
        if local_signals.exists():
            combined['records'] += [r for r in telemetry.from_checkpoint_signals(cp.read(local_signals))['records'] if r.get('kind') != 'codex_plan']
        summary = _baseline(root, combined, current)
        windows = _windows(summary)
        if marker and set(marker.get('resource_accounts', [])) - {a for a, _ in windows}:
            raise cp.Fault('Readings do not include every stopped account')
        if marker and any(summary['statuses'].get(k) != 'ok' for k in marker.get('low_kinds', []) if k != 'codex_plan'):
            raise cp.Fault('Every other stopped resource needs a fresh adequate reading; missing/unknown cannot be waived')
        if any(r['kind'] != 'codex_plan' for r in summary['low']):
            raise cp.Fault('Other resource stops cannot be overridden')
        if not any(r['kind'] == 'codex_plan' for r in summary['low']):
            raise cp.Fault('The normal account reserve is not reached; do not pre-arm an override')
        if threshold is not None and any(r['remaining'] <= threshold for r in summary['records'] if r['kind'] == 'codex_plan'):
            raise cp.Fault(str(threshold) + '% reserve already reached; choose an explicitly authorized lower reserve or exhaustion')
        previous = cp.read(store / NAME) if (store / NAME).exists() else None
        if previous:
            history = store / 'allowance-override-history'; history.mkdir(exist_ok=True)
            cp.atomic(history / (uuid.uuid4().hex + '.json'), cp.encoded(previous))
        value = {'version': 1, 'id': uuid.uuid4().hex, 'project_id': binding['project_id'], 'task_id': binding['task_id'],
                 'checkpoint_id': saved['id'], 'stop_pointer': {k:v for k,v in cp.read(store/'latest.json').items() if k in ('id','hashes')},
                 'lifecycle_sha256': _lifecycle_hash(store), 'mode': mode, 'state': 'pending_resume',
                 'workspace': _workspace(root), 'intended_owner': owner or (claim['owner'] if claim else None),
                 'grant_owner_token': claim['token'] if claim else None,
                 'reason': reason.strip(), 'source': source.strip(), 'created_at': current.isoformat(),
                 'windows': [{'account_fingerprint': a, 'window': w, 'resets_at': reset} for (a, w), reset in sorted(windows.items())],
                 'automatic_resume': False, 'permissions_restored': False}
        if mode == 'percent':
            value['percent'] = threshold
        if signals_path is not None:
            value['signals_path'] = str(Path(signals_path).resolve())
        cp.atomic(store / 'allowance-override-signals.json', cp.encoded(combined))
        cp.atomic(store / NAME, cp.encoded(value))
        return value



def validate_resume(root):
    """Prospective resource gate for an explicit resume, including hook-only stops."""
    _, store, value = _load(root)
    if value is None or value['state'] == 'revoked':
        return
    signals = cp.read(Path(value.get('signals_path', str(store / 'allowance-override-signals.json'))))
    summary = assess(root, signals, allow_pending=True)
    if blocked(summary) or summary['statuses'].get('codex_plan') != 'ok':
        raise cp.Fault('Fresh adequate readings under the selected reserve are required before explicit resume')


def activate(root):
    """Called inside the normal resume gate after its receipt and lease exist."""
    binding, store, value = _load(root)
    if value is None or value['state'] not in ('pending_resume', 'active'):
        return
    _scope(root, binding, store, value, check_receipt=False)
    owner = cp.Ownership(root, binding, store).check()
    receipt = cp.read(store / 'resume.json')
    original, _ = cp.check_generation(store, value.get('stop_pointer', {}))
    current, _ = cp.latest(store)
    if any(s['project_id'] != binding['project_id'] or s['task_id'] != binding['task_id'] for s in (original, current)):
        raise cp.Fault('Original stop or current resume generation belongs to another task')
    if original['id'] != value['checkpoint_id'] or receipt.get('checkpoint_id') != current['id'] or receipt.get('owner', {}).get('token') != owner['token']:
        raise cp.Fault('Matching fresh reviewed current resume and exclusive owner required to activate override')
    if not 0 <= cp.age(receipt.get('resumed_at')) <= 300:
        raise cp.Fault('Resume receipt stale; grant never authorizes ordinary work by itself')
    signals = cp.read(Path(value.get('signals_path', str(store / 'allowance-override-signals.json'))))
    summary = _baseline(root, signals)
    expected = _record_windows(value)
    if _current() < telemetry.timestamp(value['created_at']):
        raise cp.Fault('Override creation time is in the future')
    expired = _current() >= min(telemetry.timestamp(v) for v in expected.values())
    invalidated = _lifecycle(store, binding) in TERMINAL or value.get('lifecycle_sha256') != _lifecycle_hash(store)
    if expired or invalidated:
        if summary['statuses']['codex_plan'] != 'ok' or summary['low']:
            raise cp.Fault('Grant expired or lifecycle changed; fresh adequate default resources are required')
        value.update(state='revoked', revoked_at=cp.now(), revocation_reason='Expired or lifecycle changed at explicit resume')
        cp.atomic(store / NAME, cp.encoded(value))
        return
    if _windows(summary) != expected:
        raise cp.Fault('Account/window/reset changed; a fresh grant is required')
    threshold = _threshold(value['mode'], value.get('percent'))
    if any(r['kind'] != 'codex_plan' for r in summary['low']) or (threshold is not None and
            any(r['remaining'] <= threshold for r in summary['records'] if r['kind'] == 'codex_plan')):
        raise cp.Fault('Fresh adequate resources under the chosen override are required for resume')
    value.update(state='active', activated_at=cp.now(), resume_checkpoint_id=receipt['checkpoint_id'],
                 active_owner={k: owner[k] for k in ('owner', 'token')},
                 resume_receipt_sha256=cp.sha(cp.content(store / 'resume.json')))
    cp.atomic(store / NAME, cp.encoded(value))


def prepare_review(root, scope, source, evidence, owner=None):
    """Write only a fresh, issue-free operator review; never execute task work."""
    if any(not isinstance(v,str) or not v.strip() for v in (scope,source,evidence)):
        raise cp.Fault('Current authorization scope/source and truthful resource evidence are required')
    binding,store,value = _load(root)
    if value is None or value['state'] != 'pending_resume':
        raise cp.Fault('A pending explicit allowance grant is required')
    validate_resume(root)
    _owner_gate(root,binding,store,owner)
    if owner is not None and value.get('intended_owner') and owner != value['intended_owner']:
        raise cp.Fault('Allowance grant belongs to another intended owner')
    saved,report = cp.inspect(root)
    if report['issues']:
        raise cp.Fault('Reconcile these checkpoint issues before preparing a review: '+', '.join(report['issues']))
    if any(j['status'] not in ('completed','failed','cancelled') for j in saved['task']['jobs']):
        raise cp.Fault('Resolve uncertain jobs before preparing a review')
    review = {'checkpoint_id':saved['id'],'task_id':saved['task_id'],
        'next_action':saved['task']['next_action']['description'],'verification':saved['task']['next_action']['verification'],
        'current_fingerprint':report['current_fingerprint'],'observed_at':cp.now(),
        'authorization':{'confirmed':True,'scope':scope.strip(),'source':source.strip()},
        'resources':{'adequate_for_bounded_action':True,'evidence':evidence.strip(),'observed_at':cp.now()},'resolutions':{}}
    path=store/'allowance-resume-review.json'
    cp.atomic(path,cp.encoded(review))
    return {'review':str(path),'next_action':saved['task']['next_action'],'implementation_allowed':False,
        'requires':'Explicit checkpoint.py resume with current owner and required capabilities'}



def retire_policy(root, reason, source, owner=None):
    """Explicitly archive a local baseline; preserve all stops and resume authority."""
    if any(not isinstance(v, str) or not v.strip() for v in (reason, source)):
        raise cp.Fault('Current user retirement reason and authorization source are required')
    binding, store = cp.config(root)
    with cp.lock(store):
        authority = cp.Ownership(root, binding, store)
        tip = authority.tip()
        current = authority.value(tip)
        if current.get('owner') and (not owner or owner != current['owner']):
            raise cp.Fault('Policy retirement requires the explicit current owner; never use another lease')
        _owner_gate(root, binding, store, owner)
        saved, _ = cp.latest(store)
        if saved['project_id'] != binding['project_id'] or saved['task_id'] != binding['task_id']:
            raise cp.Fault('Checkpoint belongs to another task')
        if any(j['status'] not in ('completed', 'failed', 'cancelled') for j in saved['task']['jobs']):
            raise cp.Fault('Active or uncertain task jobs must be reconciled before policy retirement')
        if (store / 'input.json').exists():
            task = cp.read(store / 'input.json')
            if any(j.get('status') not in ('completed', 'failed', 'cancelled') for j in task.get('jobs', [])):
                raise cp.Fault('Active or uncertain input jobs must be reconciled before policy retirement')
        path = store / POLICY_NAME
        if not path.exists():
            return {'retired': False, 'reason': 'No task-local reserve policy exists', 'automatic_resume': False}
        raw = cp.content(path)
        history = store / 'reserve-policy-history'
        history.mkdir(exist_ok=True)
        ident = uuid.uuid4().hex
        archived = history / (ident + '.json')
        cp.atomic(archived, raw)
        if authority.tip() != tip:
            raise cp.Fault('Ownership changed during policy retirement; policy preserved')
        cp.atomic(history / (ident + '-retirement.json'), cp.encoded({
            'retired_at': cp.now(), 'project_id': binding['project_id'], 'task_id': binding['task_id'],
            'reason': reason.strip(), 'source': source.strip(), 'owner': current.get('owner'),
            'policy_sha256': cp.sha(raw), 'automatic_resume': False, 'permissions_restored': False}))
        path.unlink()
        return {'retired': True, 'archive': str(archived), 'automatic_resume': False,
                'stops_preserved': True, 'permissions_restored': False}


def status(root):
    binding, store, value = _load(root)
    result = {'project_id': binding['project_id'], 'task_id': binding['task_id'], 'override': value,
              'default_percent_if_unconfigured': 20, 'automatic_resume': False}
    try:
        result['reserve_policy'] = _policy(root)
    except (cp.Fault, OSError, ValueError, KeyError, TypeError) as exc:
        result['reserve_policy_error'] = str(exc)
        result['implementation_allowed'] = False
    return result


def revoke(root, reason, owner=None):
    if not isinstance(reason, str) or not reason.strip():
        raise cp.Fault('Revocation reason required')
    binding, store = cp.config(root)
    with cp.lock(store):
        _owner_gate(root, binding, store, owner)
        _, _, value = _load(root)
        if value is None:
            return {'revoked': False, 'reason': 'No override exists'}
        if owner is not None and value.get('intended_owner') and owner != value['intended_owner']:
            raise cp.Fault('Allowance grant belongs to another intended owner')
        if value.get('workspace') != _workspace(root):
            raise cp.Fault('Allowance grant belongs to another workspace')
        value.update(state='revoked', revoked_at=cp.now(), revocation_reason=reason.strip())
        cp.atomic(store / NAME, cp.encoded(value))
    return {'revoked': True, 'automatic_resume': False}


def build_parser():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--root', type=Path, required=True)
    sub = p.add_subparsers(dest='command', required=True)
    config = sub.add_parser('configure')
    config.add_argument('--percent', type=float, required=True)
    config.add_argument('--owner', required=True)
    config.add_argument('--reason', required=True)
    config.add_argument('--source', required=True)
    retire = sub.add_parser('retire-policy')
    retire.add_argument('--owner')
    retire.add_argument('--reason', required=True)
    retire.add_argument('--source', required=True)
    g = sub.add_parser('grant'); g.add_argument('--mode', choices=['ten', 'percent', 'exhaustion'], required=True)
    g.add_argument('--percent', type=float, help='Task-local remaining allowance percentage (0..100); requires --mode percent')
    g.add_argument('--signals', type=Path, required=True); g.add_argument('--reason', required=True); g.add_argument('--source', required=True)
    review = sub.add_parser('prepare-review'); review.add_argument('--scope',required=True); review.add_argument('--source',required=True); review.add_argument('--resources-evidence',required=True)
    sub.add_parser('status'); r = sub.add_parser('revoke'); r.add_argument('--reason', required=True)
    for command in (g, review, r):
        command.add_argument('--owner', required=True)
    return p


def main():
    a = build_parser().parse_args(); root = a.root.resolve()
    if a.command == 'configure': value = configure(root, a.percent, a.owner, a.reason, a.source)
    elif a.command == 'retire-policy': value = retire_policy(root, a.reason, a.source, owner=a.owner)
    elif a.command == 'grant': value = grant(root, a.mode, cp.read(a.signals), a.reason, a.source, signals_path=a.signals, owner=a.owner, percent=a.percent)
    elif a.command == 'prepare-review': value = prepare_review(root,a.scope,a.source,a.resources_evidence,owner=a.owner)
    elif a.command == 'revoke': value = revoke(root, a.reason, owner=a.owner)
    else: value = status(root)
    print(json.dumps(value, indent=2))

if __name__ == '__main__':
    try:
        main()
    except (cp.Fault, OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr); sys.exit(2)
