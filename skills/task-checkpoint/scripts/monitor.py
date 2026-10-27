#!/usr/bin/env python3
"""Usage-triggered preservation using the existing account registry and checkpoint store.

No model calls, task takeover, worktree restoration, queue, or automatic resumption.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

import checkpoint as cp
import telemetry

LABEL = 'com.checkpoint-handoff.codex'
TASK_NAME = 'Checkpoint-Handoff-Usage'
NS = 'http://schemas.microsoft.com/windows/2004/02/mit/task'
PREFIXES = ('Automatic usage checkpoint:', 'Automatic source provenance:')


def _binding(root, record):
    if not root.is_absolute() or not root.is_dir():
        raise cp.Fault('Registered project is unavailable; no replacement task created')
    binding, store = cp.config(root)
    if binding['task_id'] != record['task_id'] or binding['project_id'] != record['project_id']:
        raise cp.Fault('Registered project binding changed; no state overwritten')
    return binding, store


def _marker(store, binding):
    path = store / 'automatic-stop.json'
    if not path.exists():
        return None
    value = cp.read(path)
    if value.get('schema_version') != 1 or value.get('task_id') != binding['task_id'] or value.get('project_id') != binding['project_id']:
        raise cp.Fault('Automatic stop belongs to a different task')
    return value


def _incident(low):
    # Do not hash remaining values or collection times: one depletion incident
    # must not produce a new snapshot at every percentage/poll.
    return cp.sha(cp.encoded(sorted([{
        'kind': x['kind'], 'account_fingerprint': x.get('account_fingerprint'), 'window': x.get('window'), 'reset': x.get('resets_at'),
        'guard': x.get('guard', 20 if x['kind'] == 'codex_plan' else 0)
    } for x in low], key=lambda x: cp.encoded(x))))


def _source(root, store, marker):
    source = store / 'input.json'
    if source.exists():
        task = cp.read(source)
        evidence = {'kind': 'agent-maintained-input', 'mtime_ns': source.stat().st_mtime_ns,
                    'sha256': cp.sha(cp.content(source)), 'semantic_freshness': 'not inferred from filesystem time'}
    else:
        state, _ = cp.latest(store)
        task = state['task']
        original = marker.get('source', {}) if marker and marker.get('checkpoint_id') == state['id'] else {}
        evidence = original or {'kind': 'last-valid-checkpoint-fallback', 'checkpoint_id': state['id'],
                                'checkpoint_created_at': state['created_at'], 'semantic_freshness': 'potentially stale; no conversation reconstruction'}
    task = cp.redact(task)
    task['observations'] = [v for v in task['observations'] if not v.startswith(PREFIXES)]
    return task, evidence


def _preserve(root, store, binding, marker, signals, assessment):
    task, source = _source(root, store, marker)
    fingerprint = cp.repo(root)['fingerprint']
    journal = store / 'router.json'
    active = cp.read(journal).get('active') if journal.exists() else None
    worker = {key: active.get(key) for key in ('id', 'pid', 'status')} if active else None
    digest = cp.sha(cp.encoded({'task': task, 'worker': worker}))
    if marker.get('checkpoint_status') == 'verified' and marker.get('source_digest') == digest and marker.get('repository_fingerprint') == fingerprint:
        saved, _ = cp.latest(store)
        if saved['id'] == marker.get('checkpoint_id'):
            return {'task_id': binding['task_id'], 'status': 'already-preserved', 'checkpoint_id': saved['id']}
    attempts = marker.get('preservation_attempts', 0)
    if attempts >= 3:
        raise cp.Fault('Preservation retry limit reached; retain prior generation, repair the cause, and explicitly reset retries')
    marker.update(checkpoint_status='pending', attempted_at=cp.now(), preservation_attempts=attempts + 1)
    cp.atomic(store / 'automatic-stop.json', cp.encoded(marker))
    task['observations'].append('Automatic usage checkpoint: fresh observed resource threshold reached; stop ordinary work. No job cancellation, model switch, release or automatic resume was performed.')
    task['observations'].append('Automatic source provenance: ' + json.dumps(source, sort_keys=True) + '. This captures the last maintained semantic state; later conversation details may be absent.')
    if active:
        ident = str(active.get('id', 'unidentified-router-run'))
        if not any(j['id'] == ident for j in task['jobs']):
            task['jobs'].append({'id': ident, 'kind': 'router-worker', 'status': 'unknown',
                                 'source': 'Existing router journal; observed PID ' + str(active.get('pid', 'unknown')) + '; verify process identity and external outcomes before retry or release', 'observed_at': cp.now()})
    temporary = store / ('monitor-input-' + uuid.uuid4().hex + '.json')
    try:
        cp.atomic(temporary, cp.encoded(task))
        saved = cp.checkpoint(root, temporary, 'low-resource')
        verified, _ = cp.latest(store)
        if verified['id'] != saved['id']:
            raise cp.Fault('Checkpoint changed during monitor verification; inspect concurrent boundary')
        marker.update(checkpoint_status='verified', checkpoint_id=saved['id'], verified_at=cp.now(),
                      source_digest=digest, repository_fingerprint=fingerprint, source=source)
        marker.pop('failure_type', None)
        marker['preservation_attempts'] = 0
        cp.atomic(store / 'automatic-stop.json', cp.encoded(marker))
        return {'task_id': binding['task_id'], 'status': 'checkpoint-verified', 'checkpoint_id': saved['id'],
                'handoff': saved['handoff'], 'semantic_source': source['kind']}
    finally:
        temporary.unlink(missing_ok=True)


def account_scope(signals, marker):
    wanted = set(marker.get('resource_accounts', [])) if marker else set()
    if not wanted:
        return signals
    result = {'records': [r for r in signals.get('records', []) if r.get('kind') != 'codex_plan']}
    seen = set()
    candidates = list(signals.get('records', []))
    for ident in wanted:
        candidates += signals.get('accounts', {}).get(ident, {}).get('records', [])
    for record in candidates:
        ident = record.get('account_fingerprint')
        if record.get('kind') == 'codex_plan' and ident in wanted:
            result['records'].append(record); seen.add(ident)
    for ident in wanted - seen:
        result['records'].append({'kind':'codex_plan', 'account_fingerprint':ident, 'unit':'percent_remaining',
            'remaining':None, 'supported':False, 'source':'missing-account-observation', 'observed_at':cp.now()})
    return result


def affected_accounts(marker, assessment):
    marker['resource_accounts'] = sorted(set(marker.get('resource_accounts', [])) |
        {r['account_fingerprint'] for r in assessment['low'] if r.get('account_fingerprint')})


def evaluate_registered(state, signals):
    """Preserve each registered task on fresh low signals; never acquire its lease.

    Called by account.tick after collection, before any scheduled dispatch.
    Also accepts explicitly sourced context/API signals in their existing units.
    """
    config = cp.read(state / 'config.json')
    if config.get('enabled') is not True or config.get('automatic_checkpoints_enabled', True) is not True:
        return {'enabled': False, 'projects': []}
    normalized = telemetry.from_checkpoint_signals(signals)
    guard = config.get('guard_percent', 20)
    if not telemetry.number(guard) or not 0 <= guard <= 100:
        raise cp.Fault('Invalid usage reserve')
    for r in normalized['records']:
        if r.get('kind') == 'codex_plan':
            r['guard'] = guard
    account_assessment = telemetry.assess(normalized)
    results = []
    guard_dir = state / 'preservation'
    guard_dir.mkdir(parents=True, exist_ok=True)
    with cp.lock(guard_dir):
        for record in config.get('projects', []):
            marker, store = None, None
            try:
                root = Path(record['root'])
                binding, store = _binding(root, record)
                # Respect local context/API observations, but account plan readings
                # always come from this collector rather than an older local copy.
                combined = {'records': list(normalized['records']), 'accounts': signals.get('accounts', {})}
                if (store / 'signals.json').exists():
                    combined['records'] += [r for r in telemetry.from_checkpoint_signals(cp.read(store / 'signals.json'))['records'] if r.get('kind') != 'codex_plan']
                marker = _marker(store, binding)
                assessment = telemetry.assess(account_scope(combined, marker))
                if assessment['low']:
                    incident = _incident(assessment['low'])
                    if marker is None:
                        marker = {'schema_version': 1, 'task_id': binding['task_id'], 'project_id': binding['project_id'],
                                  'requested_at': cp.now(), 'incident_id': incident, 'checkpoint_status': 'pending'}
                    marker.update(incident_id=incident, low_kinds=sorted(set(marker.get('low_kinds', [])) | {x['kind'] for x in assessment['low']}),
                                  account_state=str(state.resolve()), automatic_resume=False)
                    affected_accounts(marker, assessment)
                    marker.pop('resources_recovered_at', None)
                    # Stop first, then preserve. A failed save must not permit work.
                    cp.atomic(store / 'automatic-stop.json', cp.encoded(marker))
                    results.append(_preserve(root, store, binding, marker, combined, assessment))
                elif marker is not None:
                    marker['account_state'] = str(state.resolve())
                    kinds = marker.get('low_kinds', [])
                    recovered = bool(kinds) and all(assessment['statuses'].get(k) == 'ok' for k in kinds)
                    if recovered:
                        marker['resources_recovered_at'] = cp.now()
                        # If an earlier save failed, retry preservation with the
                        # now recovered resources before permitting explicit resume.
                        if marker.get('checkpoint_status') != 'verified':
                            results.append(_preserve(root, store, binding, marker, combined, assessment))
                        cp.atomic(store / 'automatic-stop.json', cp.encoded(marker))
                    results.append({'task_id': binding['task_id'], 'status': 'explicit-resume-required' if recovered else 'stopped-resource-status-unknown'})
                else:
                    results.append({'task_id': binding['task_id'], 'status': 'no-low-signal'})
                if record.get('readiness', {}).get('enabled') is True or (store / 'readiness.json').exists():
                    import readiness
                    settings = dict(record.get('readiness', {}))
                    settings.setdefault('scheduler_id', config.get('readiness_scheduler_id'))
                    try:
                        notice = readiness.update(root, account_scope(combined, marker), settings)
                    except Exception as notification_error:
                        notice = {'status':'user-action-required','reason':type(notification_error).__name__, 'automatic_resume':False}
                    results.append({'task_id': binding['task_id'], 'status': 'readiness-' + notice['status'], 'readiness': notice})
            except Exception as exc:
                if marker is not None and store is not None:
                    marker.update(checkpoint_status='failed', failure_type=type(exc).__name__, failed_at=cp.now())
                    try:
                        cp.atomic(store / 'automatic-stop.json', cp.encoded(marker))
                    except Exception:
                        pass  # A full/denied device must not prevent other projects from saving.
                results.append({'task_id': record.get('task_id', 'unknown'), 'status': 'preservation-failed',
                                'failure_type': type(exc).__name__, 'save_success_not_claimed': True})
    status = {'observed_at': cp.now(), 'threshold_percent_remaining': guard,
              'account_status': account_assessment['statuses']['codex_plan'], 'projects': results}
    cp.atomic(state / 'monitor-status.json', cp.encoded(status))
    return status


def stop_for_signals(root, signals):
    binding, store = cp.config(root)
    assessment = telemetry.assess(signals)
    if not assessment['low']:
        return None
    cp.atomic(store / 'signals.json', cp.encoded(signals))
    marker = _marker(store, binding) or {'schema_version': 1, 'task_id': binding['task_id'],
        'project_id': binding['project_id'], 'requested_at': cp.now(), 'checkpoint_status': 'pending'}
    marker.update(incident_id=_incident(assessment['low']),
        low_kinds=sorted(set(marker.get('low_kinds', [])) | {r['kind'] for r in assessment['low']}), automatic_resume=False)
    affected_accounts(marker, assessment)
    cp.atomic(store / 'automatic-stop.json', cp.encoded(marker))
    return _preserve(root, store, binding, marker, signals, assessment)


def validate_resume(root, store):
    """Use before acquiring ownership; unknown/recovered usage never resumes itself."""
    binding, _ = cp.config(root)
    marker = _marker(store, binding)
    if marker is None:
        return
    if marker.get('checkpoint_status') != 'verified':
        raise cp.Fault('Automatic preservation is incomplete; repair saving and retry monitor before resume')
    state = Path(marker['account_state']) if marker.get('account_state') else store
    config = cp.read(state / 'config.json') if marker.get('account_state') else {'guard_percent': 20}
    raw_signals = cp.read(state / 'signals.json')
    signals = telemetry.from_checkpoint_signals(raw_signals)
    signals['accounts'] = raw_signals.get('accounts', {})
    for r in signals['records']:
        if r.get('kind') == 'codex_plan':
            r['guard'] = config.get('guard_percent', 20)
    if (store / 'signals.json').exists():
        signals['records'] += [r for r in telemetry.from_checkpoint_signals(cp.read(store / 'signals.json'))['records'] if r.get('kind') != 'codex_plan']
    assessment = telemetry.assess(account_scope(signals, marker))
    if assessment['low'] or not marker.get('low_kinds') or any(assessment['statuses'].get(k) != 'ok' for k in marker['low_kinds']):
        raise cp.Fault('Automatic stop persists: refresh all affected resource readings and explicitly resume after recovery')


def acknowledge_resume(root, store):
    """Call only after the normal fresh-review/authorization/ownership gate passed."""
    binding, _ = cp.config(root)
    marker = _marker(store, binding)
    if marker is None:
        return
    guard = (Path(marker['account_state']) if marker.get('account_state') else store) / 'preservation'
    guard.mkdir(parents=True, exist_ok=True)
    with cp.lock(guard):
        validate_resume(root, store)
        marker = _marker(store, binding)
        history = store / 'automatic-stop-history'
        history.mkdir(exist_ok=True)
        cp.atomic(history / (uuid.uuid4().hex + '.json'), cp.encoded(dict(marker, explicitly_resumed_at=cp.now())))
        (store / 'automatic-stop.json').unlink()


def windows_task_xml(python, script, state, user):
    """Current-user, interactive-token task: no stored password or elevation."""
    if not user or any(c in user for c in '\r\n\x00'):
        raise cp.Fault('Current Windows user is required')
    ET.register_namespace('', NS)
    task = ET.Element('{' + NS + '}Task', {'version': '1.2'})
    def element(parent, name, text=None):
        e = ET.SubElement(parent, '{' + NS + '}' + name)
        e.text = text
        return e
    registration = element(task, 'RegistrationInfo')
    element(registration, 'Description', 'Checkpoint and Handoff: read usage and preserve registered projects; routing needs separate authorization')
    triggers = element(task, 'Triggers')
    trigger = element(triggers, 'TimeTrigger')
    repetition = element(trigger, 'Repetition')
    element(repetition, 'Interval', 'PT1M')
    element(repetition, 'StopAtDurationEnd', 'false')
    element(trigger, 'StartBoundary', dt.datetime.now().replace(microsecond=0).isoformat())
    element(trigger, 'Enabled', 'true')
    principals = element(task, 'Principals')
    principal = ET.SubElement(principals, '{' + NS + '}Principal', {'id': 'CurrentUser'})
    element(principal, 'UserId', user)
    element(principal, 'LogonType', 'InteractiveToken')
    element(principal, 'RunLevel', 'LeastPrivilege')
    settings = element(task, 'Settings')
    for name, text in [('MultipleInstancesPolicy','IgnoreNew'),('DisallowStartIfOnBatteries','false'),
                       ('StopIfGoingOnBatteries','false'),('StartWhenAvailable','true'),('Enabled','true'),
                       ('ExecutionTimeLimit','PT0S')]:
        element(settings, name, text)
    actions = ET.SubElement(task, '{' + NS + '}' + 'Actions', {'Context':'CurrentUser'})
    action = element(actions, 'Exec')
    element(action, 'Command', str(python))
    element(action, 'Arguments', subprocess.list2cmdline([str(script), '--state', str(state), 'tick']))
    element(action, 'WorkingDirectory', str(state))
    return ET.tostring(task, encoding='utf-16', xml_declaration=True)


def service_template(state, python, platform=None, user=None):
    """Reuse the one account collector rather than installing a second watcher."""
    platform = sys.platform if platform is None else platform
    script = Path(__file__).with_name('account.py').resolve()
    if platform == 'darwin':
        value = {'Label':LABEL,'ProgramArguments':[str(python),str(script),'--state',str(state),'tick'],
                 'RunAtLoad':True,'StartInterval':60,'ProcessType':'Background','WorkingDirectory':str(state),
                 'StandardOutPath':str(state/'service.log'),'StandardErrorPath':str(state/'service-error.log')}
        path = state / (LABEL + '.plist')
        prior = plistlib.loads(cp.content(path)) if path.exists() else {}
        environment = prior.get('EnvironmentVariables', {})
        if not environment:
            binary = shutil.which('codex')
            environment = {'PATH': (str(Path(binary).parent) + os.pathsep if binary else '') + os.environ.get('PATH', '/usr/bin:/bin')}
        value['EnvironmentVariables'] = environment
        cp.atomic(path, plistlib.dumps(value))
    elif platform == 'win32':
        path = state / 'checkpoint-handoff-task.xml'
        cp.atomic(path, windows_task_xml(python, script, state, user))
    else:
        raise cp.Fault('Automatic service supports macOS launchd and Windows Task Scheduler; use account.py tick manually on this host')
    return path


def _collector_idle(state):
    for project in cp.read(state / 'config.json').get('projects', []):
        _, store = _binding(Path(project['root']), project)
        if (store / 'router.json').exists() and cp.read(store / 'router.json').get('active') is not None:
            raise cp.Fault('Routed work is active or uncertain; do not restart its service')


def _run(args, check=True):
    return subprocess.run(args, check=check, capture_output=True, timeout=20)


def install_service(state, python, platform=None):
    platform = sys.platform if platform is None else platform
    receipt = state / 'monitor-service.json'
    transaction = state / 'monitor-service-transaction.json'
    # Serialize the entire scheduler mutation against collection and dispatch.
    with cp.lock(state):
        _collector_idle(state)
        old_receipt = cp.content(receipt) if receipt.exists() else None
        old_config = cp.content(state / 'config.json')
        user = _run(['whoami']).stdout.decode().strip() if platform == 'win32' else None
        template = service_template(state, python, platform, user)
        if platform == 'darwin':
            destination = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
            prior = cp.content(destination) if destination.exists() else None
            if prior is not None:
                value = plistlib.loads(prior)
                if value.get('Label') != LABEL or 'account.py' not in ' '.join(value.get('ProgramArguments', [])) or str(state) not in value.get('ProgramArguments', []):
                    raise cp.Fault('Existing service differs; preserve and review before replacing')
                if old_receipt and cp.read(receipt).get('sha256') != cp.sha(prior):
                    raise cp.Fault('Managed service changed; preserve and review it')
            domain = 'gui/' + str(os.getuid())
            was_running = _run(['launchctl','print',domain+'/'+LABEL],check=False).returncode == 0
        else:
            query = _run(['schtasks','/Query','/TN',TASK_NAME,'/XML'],check=False)
            prior = query.stdout if query.returncode == 0 else None
            if prior is not None and (old_receipt is None or cp.read(receipt).get('scheduler_definition_sha256') != _xml_hash(prior)):
                raise cp.Fault('Existing Windows task differs from managed receipt; preserve and review it')
        if prior is not None:
            cp.atomic(state / ('monitor-service-transaction-before.plist' if platform == 'darwin' else 'monitor-service-transaction-before.xml'), prior)
            if platform == 'darwin' and old_receipt is None:
                cp.atomic(state / 'monitor-service-before.plist', prior)
        cp.atomic(transaction, cp.encoded({'platform':platform,'status':'installing','started_at':cp.now(),
                                          'previous_service_present':prior is not None,'previous_receipt_present':old_receipt is not None}))
        mutated = False
        try:
            if platform == 'darwin':
                if was_running:
                    _run(['launchctl','bootout',domain,str(destination)])
                mutated = True
                cp.atomic(destination, cp.content(template))
                _run(['launchctl','bootstrap',domain,str(destination)])
                info = {'platform':platform,'label':LABEL,'path':str(destination),'sha256':cp.sha(cp.content(destination))}
            else:
                mutated = True
                _run(['schtasks','/Create','/TN',TASK_NAME,'/XML',str(template),'/F'])
                query = _run(['schtasks','/Query','/TN',TASK_NAME,'/XML'])
                info = {'platform':platform,'task_name':TASK_NAME,'path':str(template),'sha256':cp.sha(cp.content(template)),
                        'scheduler_definition_sha256':_xml_hash(query.stdout)}
            config = cp.read(state / 'config.json')
            config['automatic_checkpoints_enabled'] = True
            cp.atomic(state / 'config.json', cp.encoded(config))
            cp.atomic(receipt, cp.encoded(info))
            cp.atomic(transaction, cp.encoded({'platform':platform,'status':'installed','at':cp.now()}))
        except Exception as original:
            rollback = 'not-needed'
            if mutated:
                try:
                    if platform == 'darwin':
                        _run(['launchctl','bootout',domain,str(destination)],check=False)
                        if prior is not None:
                            cp.atomic(destination, prior)
                            if was_running:
                                _run(['launchctl','bootstrap',domain,str(destination)])
                        else:
                            destination.unlink(missing_ok=True)
                    elif prior is not None:
                        _run(['schtasks','/Create','/TN',TASK_NAME,'/XML',str(state/'monitor-service-transaction-before.xml'),'/F'])
                    else:
                        _run(['schtasks','/Delete','/TN',TASK_NAME,'/F'])
                    cp.atomic(state / 'config.json', old_config)
                    if old_receipt is not None:
                        cp.atomic(receipt, old_receipt)
                    else:
                        receipt.unlink(missing_ok=True)
                    rollback = 'restored'
                except Exception:
                    rollback = 'failed-manual-reconciliation-required'
            cp.atomic(transaction, cp.encoded({'platform':platform,'status':'failed','failure_type':type(original).__name__,
                                              'rollback':rollback,'at':cp.now()}))
            raise cp.Fault('Service setup failed; rollback ' + rollback + '; inspect private transaction record')
    return dict(info, installed=True, execution_verified=False,
                note='Check account and monitor-status timestamps after the next minute; registration alone is not successful collection or preservation')


def _xml_hash(raw):
    # schtasks /Query writes console-codepage bytes to a redirected pipe even
    # though its XML declaration says UTF-16. Genuine UTF-16 remains bytes so
    # ElementTree can detect its BOM; decode console output before parsing.
    if isinstance(raw, bytes) and b'\x00' not in raw[:80] and not raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        raw = raw.decode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') or os.name != 'nt' else 'oem')
    tree = ET.fromstring(raw)
    def value(node):
        return [node.tag, sorted(node.attrib.items()), (node.text or '').strip(), [value(child) for child in node]]
    return cp.sha(cp.encoded(value(tree)))


def _uninstall_service_locked(state):
    receipt = cp.read(state / 'monitor-service.json')
    for project in cp.read(state / 'config.json').get('projects', []):
        _, store = _binding(Path(project['root']), project)
        if (store / 'router.json').exists() and cp.read(store / 'router.json').get('active') is not None:
            raise cp.Fault('Routed work is active or uncertain; do not stop its service')
    if receipt['platform'] == 'darwin':
        path = Path(receipt['path'])
        if cp.sha(cp.content(path)) != receipt['sha256']:
            raise cp.Fault('Managed service changed; preserve it for manual reconciliation')
        _run(['launchctl','bootout','gui/'+str(os.getuid()),str(path)])
        backup = state / 'monitor-service-before.plist'
        if backup.exists():
            cp.atomic(path, cp.content(backup))
            _run(['launchctl','bootstrap','gui/'+str(os.getuid()),str(path)])
        else:
            path.unlink()
    elif receipt['platform'] == 'win32':
        query = _run(['schtasks','/Query','/TN',TASK_NAME,'/XML'])
        if _xml_hash(query.stdout) != receipt['scheduler_definition_sha256']:
            raise cp.Fault('Managed Windows task changed; preserve it for manual reconciliation')
        _run(['schtasks','/Delete','/TN',TASK_NAME,'/F'])
    else:
        raise cp.Fault('Unsupported service receipt')
    config = cp.read(state / 'config.json')
    config['automatic_checkpoints_enabled'] = False
    cp.atomic(state / 'config.json', cp.encoded(config))
    cp.atomic(state / ('monitor-service-removed-' + uuid.uuid4().hex + '.json'), cp.encoded(dict(receipt, removed_at=cp.now())))
    (state / 'monitor-service.json').unlink()
    return {'uninstalled': True, 'private_checkpoints_retained': True, 'running_workers_cancelled': False}


def uninstall_service(state):
    with cp.lock(state):
        _collector_idle(state)
        return _uninstall_service_locked(state)


def service_status(state):
    result = {'service':cp.read(state/'monitor-service.json') if (state/'monitor-service.json').exists() else None,
              'monitor':cp.read(state/'monitor-status.json') if (state/'monitor-status.json').exists() else None,
              'account':cp.read(state/'status.json') if (state/'status.json').exists() else None}
    if result['monitor']:
        result['monitor']['fresh'] = 0 <= cp.age(result['monitor']['observed_at']) <= 120
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status')
    sub.add_parser('uninstall-service')
    p = sub.add_parser('install-service')
    p.add_argument('--python',type=Path,default=Path(sys.executable))
    args = parser.parse_args()
    if args.command == 'install-service':
        result = install_service(args.state.resolve(),args.python.resolve())
    elif args.command == 'uninstall-service':
        result = uninstall_service(args.state.resolve())
    else:
        result = service_status(args.state.resolve())
    print(json.dumps(cp.redact(result),indent=2))

if __name__ == '__main__':
    try:
        main()
    except (cp.Fault,OSError,subprocess.SubprocessError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc) if isinstance(exc,cp.Fault) else type(exc).__name__}),file=sys.stderr)
        sys.exit(2)
