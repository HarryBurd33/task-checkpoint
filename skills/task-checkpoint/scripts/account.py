#!/usr/bin/env python3
"""User-wide local Codex activation and a launchd telemetry/scheduled-boundary adapter."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys

import checkpoint as cp
import telemetry

EVENTS = ('SessionStart', 'PreToolUse', 'PostToolUse', 'PreCompact', 'Stop', 'Interrupt', 'SessionEnd')
LABEL = 'com.checkpoint-handoff.codex'


def hook_definitions(script, state, python):
    args = [str(python), str(script), '--account-state', str(state)]
    command = subprocess.list2cmdline(args) if os.name == 'nt' else shlex.join(args)
    return {event: {'hooks': [{'type': 'command', 'command': command,
                             'timeout': 3 if event in ('Interrupt', 'SessionEnd') else 15}]}
            for event in EVENTS}


def install(state, codex_home, python, projects, platform=None):
    state.mkdir(parents=True, exist_ok=True)
    with cp.lock(state):
        return _install(state, codex_home, python, projects, platform)


def _install(state, codex_home, python, projects, platform=None):
    state.mkdir(parents=True, exist_ok=True)
    config_path = state / 'config.json'
    config = cp.read(config_path) if config_path.exists() else {'version': 1, 'enabled': True, 'guard_percent': 20, 'projects': []}
    if config.get('codex_home') and config['codex_home'] != str(codex_home.resolve()):
        raise cp.Fault('Account state is bound to another Codex profile; use a separate state directory')
    hooks = codex_home / 'hooks.json'
    receipt = state / 'hooks-receipt.json'
    definitions = hook_definitions(Path(__file__).with_name('hook.py').resolve(), state.resolve(), python.resolve())
    value = cp.read(hooks) if hooks.exists() else {'hooks': {}}
    if not isinstance(value.get('hooks'), dict):
        raise cp.Fault('Unsupported existing global hook file; preserve and reconcile it')
    if receipt.exists():
        prior = cp.read(receipt)
        for event, definition in prior['definitions'].items():
            if definition not in value['hooks'].get(event, []):
                raise cp.Fault('Managed global hook changed; preserve it for manual reconciliation')
            value['hooks'][event].remove(definition)
    else:
        cp.atomic(state / 'hooks-before.json', cp.encoded(value))
    for event, definition in definitions.items():
        value['hooks'].setdefault(event, []).append(definition)
    # Configuration and source installation never change native hook trust.
    cp.atomic(hooks, cp.encoded(value))
    cp.atomic(receipt, cp.encoded({'definitions': definitions, 'version': '0.4.0'}))
    config['codex_home'] = str(codex_home.resolve())
    known = {p['root']: p for p in config['projects']}
    for project in projects:
        binding, _ = cp.config(project)
        known[str(project.resolve())] = {**known.get(str(project.resolve()), {}), 'root': str(project.resolve()), 'project_id': binding['project_id'],
                                       'task_id': binding['task_id'], 'scheduled_dispatch': True}
    config['projects'] = list(known.values())
    cp.atomic(config_path, cp.encoded(config))
    git_path = shutil.which('git')
    if git_path and not config.get('git_executable'):
        config['git_executable'] = str(Path(git_path).resolve())
        cp.atomic(config_path, cp.encoded(config))
    gh_path = shutil.which('gh')
    if gh_path and not config.get('gh_executable'):
        config['gh_executable'] = str(Path(gh_path).resolve())
        cp.atomic(config_path, cp.encoded(config))
    codex_path = shutil.which('codex')
    if codex_path:
        config['codex_executable'] = str(Path(codex_path).resolve())
        cp.atomic(config_path, cp.encoded(config))
    service_path = str(Path(codex_path).parent) + ':/usr/bin:/bin:/usr/sbin:/sbin' if codex_path else '/usr/bin:/bin:/usr/sbin:/sbin'
    agent = {'Label': LABEL, 'EnvironmentVariables': {'PATH': service_path, 'CODEX_HOME': str(codex_home.resolve())}, 'ProgramArguments': [str(python.resolve()), str(Path(__file__).resolve()),
              '--state', str(state.resolve()), 'tick'], 'RunAtLoad': True, 'StartInterval': 60,
             'ProcessType': 'Background', 'WorkingDirectory': str(state.resolve()),
             'StandardOutPath': str(state / 'service.log'), 'StandardErrorPath': str(state / 'service-error.log')}
    selected_platform = sys.platform if platform is None else platform
    if selected_platform == 'darwin':
        cp.atomic(state / (LABEL + '.plist'), plistlib.dumps(agent))
    import monitor
    user = subprocess.check_output(['whoami'], text=True, timeout=10).strip() if selected_platform == 'win32' else None
    template = monitor.service_template(state.resolve(), python.resolve(), selected_platform, user)
    return {'installed': True, 'state': str(state), 'service_template': str(template),
            'native_trust': 'Review new definitions through Codex /hooks', 'interval_seconds': 60}


def tick(state):
    from codex_probe import probe
    config = cp.read(state / 'config.json')
    if config.get('version') != 1 or config.get('enabled') is not True:
        return {'enabled': False}
    # launchd normally serializes instances; this also fences explicit concurrent ticks.
    with cp.lock(state):
        signals_promoted = False
        original_path = os.environ.get('PATH')
        try:
            dependency_dirs = []
            dependency_errors = {}
            for label, key in (('Git', 'git_executable'), ('GitHub CLI', 'gh_executable')):
                executable = config.get(key)
                if executable:
                    if not Path(executable).is_absolute() or not Path(executable).is_file():
                        dependency_errors[key] = 'Configured ' + label + ' executable is unavailable; repair the user dependency'
                        continue
                    dependency_dirs.append(str(Path(executable).parent))
            if dependency_dirs:
                os.environ['PATH'] = os.pathsep.join(dependency_dirs + [original_path or ''])
            observed = probe(executable=config.get('codex_executable', 'codex'), timeout=25, codex_home=config.get('codex_home'))
            if (observed['account'].get('account') or {}).get('type') != 'chatgpt':
                raise cp.Fault('ChatGPT login required; no API fallback')
            signals = telemetry.normalize_codex(observed['rate_limits'], observed['observed_at'], observed['source'])
            guard = config.get('guard_percent', 20)
            if not telemetry.number(guard) or not 0 <= guard <= 100:
                raise cp.Fault('Invalid account usage reserve')
            for record in signals['records']:
                record['guard'] = guard
            profile_status = None
            if config.get('codex_profiles'):
                import profiles
                profile_status = profiles.collect(config, observed)
                signals['accounts'] = profile_status['accounts']
                primary_expected = next((p['account_fingerprint'] for p in config['codex_profiles'] if Path(p['codex_home']).resolve() == Path(config['codex_home']).resolve()), None)
                primary_id = profiles.inspect_profile(Path(config['codex_home']), observed, primary_expected)
                for record in signals['records']:
                    record['account_fingerprint'] = primary_id
                cp.atomic(state / 'account-profiles.json', cp.encoded(profile_status))
            if config.get('observe_local_resource') is True:
                signals['records'].extend(telemetry.disk_usage(state)['records'])
            cp.atomic(state / 'signals.json', cp.encoded(signals))
            signals_promoted = True
            import monitor
            # Quota collection must not become stale because an optional transfer
            # dependency or one project's preservation path failed. Do not dispatch
            # work when preservation could not be evaluated.
            preservation_error = None
            try:
                if 'git_executable' in dependency_errors:
                    raise cp.Fault(dependency_errors['git_executable'])
                preservation = monitor.evaluate_registered(state, signals)
            except Exception as exc:
                preservation_error = type(exc).__name__
                preservation = {'status': 'preservation-unavailable', 'failure_type': preservation_error,
                                'save_success_not_claimed': True}
            models = [{'model': m['model'], 'efforts': m.get('supportedReasoningEfforts', [])}
                      for m in observed['models'].get('data', [])]
            cp.atomic(state / 'models.json', cp.encoded({'observed_at': observed['observed_at'], 'models': models}))
            status = {'last_success': cp.now(), 'source': observed['source'], 'auth_type': 'chatgpt',
                      'telemetry': telemetry.assess(signals), 'preservation': preservation, 'scheduled': [],
                      'dependency_errors': dependency_errors}
            dispatch_projects = config['projects']
            if config.get('observation_only') is True:
                status['observation_only'] = True
                dispatch_projects = []
            failed_tasks = {item.get('task_id') for item in preservation.get('projects', [])
                            if item.get('status') == 'preservation-failed'}
            for project in dispatch_projects:
                try:
                    if preservation_error or project.get('task_id') in failed_tasks:
                        raise cp.Fault('Preservation could not be evaluated; no work dispatched')
                    root = Path(project['root'])
                    binding, store = monitor._binding(root, project)
                    if (store / 'automatic-stop.json').exists():
                        status['scheduled'].append({'task_id': binding['task_id'], 'result': 'automatic-stop-persists'})
                        continue
                    if project.get('planned_dispatch') and (store / 'plan-approval.json').exists():
                        import planner
                        result = planner.boundary(root, store/'input.json', store/'router-config.json', signals, True)
                        status['scheduled'].append({'task_id': binding['task_id'], 'result': result.get('status', result.get('action'))})
                        continue
                    ticket = store / 'router-schedule.json'
                    if not project.get('scheduled_dispatch') or not ticket.exists():
                        continue
                    value = cp.read(ticket)
                    if value.get('status') != 'pending' or cp.age(value['at']) < 0:
                        continue
                    # Existing wake rechecks the reviewed contract, task lease,
                    # fresh telemetry, budgets and authorization expiry.
                    import router
                    result = router.wake(root, store / 'input.json', store / 'router-config.json', 'codex', None, True)
                    status['scheduled'].append({'task_id': binding['task_id'], 'result': result.get('status', result.get('action'))})
                except Exception as exc:
                    status['scheduled'].append({'task_id': project.get('task_id', 'unknown'), 'result': 'project-blocked', 'error_type': type(exc).__name__})
            if profile_status is not None:
                status['account_profiles'] = profile_status['profiles']
            status['transfers'] = []
            for project in dispatch_projects:
                if not project.get('private_transfer'):
                    continue
                try:
                    import transfer
                    if dependency_errors:
                        raise cp.Fault('Transfer dependency unavailable')
                    root = Path(project['root'])
                    monitor._binding(root, project)
                    result = transfer.publish(root, project['private_transfer']['repository'])
                    status['transfers'].append({'task_id': project['task_id'], **result})
                except Exception as exc:
                    status['transfers'].append({'task_id': project['task_id'], 'status': 'pending-retry', 'error_type': type(exc).__name__})
            status['receives'] = []
            for project in dispatch_projects:
                if not project.get('private_receive'):
                    continue
                try:
                    import transfer
                    if dependency_errors:
                        raise cp.Fault('Transfer dependency unavailable')
                    root = Path(project['root'])
                    monitor._binding(root, project)
                    result = transfer.receive_latest(root, project['private_receive']['repository'])
                    status['receives'].append({'task_id': project['task_id'], **result})
                except Exception as exc:
                    status['receives'].append({'task_id': project['task_id'], 'status': 'pending-source-sync-or-review', 'error_type': type(exc).__name__})
            cp.atomic(state / 'status.json', cp.encoded(status))
            return status
        except Exception as exc:
            cp.atomic(state / 'last-error.json', cp.encoded({'observed_at': cp.now(), 'error_type': type(exc).__name__,
                      'message': str(exc) if isinstance(exc, cp.Fault) else 'Collector or scheduled-boundary adapter failed',
                      'operation_path': getattr(exc, 'filename', None),
                      'old_signals_not_refreshed': not signals_promoted}))
            raise
        finally:
            if original_path is None:
                os.environ.pop('PATH', None)
            else:
                os.environ['PATH'] = original_path


def uninstall(state, codex_home):
    receipt = cp.read(state / 'hooks-receipt.json')
    hooks = codex_home / 'hooks.json'
    value = cp.read(hooks)
    for event, definition in receipt['definitions'].items():
        if definition not in value.get('hooks', {}).get(event, []):
            raise cp.Fault('Managed hook was customized; preserve and reconcile it before removal')
    for event, definition in receipt['definitions'].items():
        value['hooks'][event].remove(definition)
        if not value['hooks'][event]:
            del value['hooks'][event]
    cp.atomic(hooks, cp.encoded(value))
    config = cp.read(state / 'config.json')
    config['enabled'] = False
    cp.atomic(state / 'config.json', cp.encoded(config))
    (state / 'hooks-receipt.json').unlink()
    return {'hooks_removed': True, 'private_state_retained': True,
            'service': 'Boot out the launchd agent before removing its plist; native trust records are untouched'}


def registration_status(state):
    """Configured definitions and delivery are separate from collector health."""
    config = cp.read(state/'config.json')
    path = Path(config['codex_home'])/'hooks.json'
    current = cp.read(path) if path.exists() else {'hooks': {}}
    receipt_path = state/'hooks-receipt.json'
    receipt = cp.read(receipt_path) if receipt_path.exists() else None
    definitions = receipt.get('definitions', {}) if receipt else {}
    counts = {event: current.get('hooks', {}).get(event, []).count(definition)
              for event, definition in definitions.items()}
    delivery = state/'hook-delivery.json'
    return {'receipt_present': receipt is not None, 'managed_definition_counts': counts,
            'configuration_complete': bool(definitions) and all(n == 1 for n in counts.values()),
            'last_delivery': cp.read(delivery) if delivery.exists() else None,
            'native_delivery_verified_by_configuration': False,
            'next': 'Verify a fresh native event for the intended chat; old receipts and collector success do not prove current delivery'}


def _recover_definitions(state, codex_home, original, python):
    config = cp.read(state/'config.json')
    if Path(config['codex_home']).resolve() != codex_home:
        raise cp.Fault('Account state belongs to another Codex home')
    if python is None or not python.is_absolute() or not python.is_file():
        raise cp.Fault('Receipt recovery requires an explicit installed Python executable')
    trusted = {Path(sys.executable).resolve(), Path('/usr/bin/python3').resolve()}
    trusted.update(Path(p).resolve() for p in (shutil.which('python3'), shutil.which('python')) if p)
    if python.resolve() not in trusted:
        raise cp.Fault('Unrecognized Python interpreter; preserve and reconcile the receipt')
    script = Path(__file__).with_name('hook.py').resolve()
    definitions = hook_definitions(script, state, python.resolve())
    for event, expected in definitions.items():
        entries = original.get('hooks', {}).get(event, [])
        if entries.count(expected) != 1:
            raise cp.Fault('Backup lacks one exact installed definition for every managed event')
    for event, entries in original.get('hooks', {}).items():
        for entry in entries:
            if any(str(script) in h.get('command', '') for h in entry.get('hooks', [])) and entry != definitions.get(event):
                raise cp.Fault('Customized checkpoint definition in backup; preserve and reconcile')
    return definitions


def restore_hooks(state, codex_home, backup, recover_receipt=False, python=None):
    """Restore only exact owned definitions removed for maintenance; retain other edits."""
    state, codex_home, backup = state.resolve(), codex_home.resolve(), backup.resolve()
    if backup.parent != state or not backup.name.startswith('hooks-temporary-backup-'):
        raise cp.Fault('Explicit temporary hook backup in the existing account state is required')
    with cp.lock(state):
        original = cp.read(backup)
        receipt_path = state/'hooks-receipt.json'
        recovered = not receipt_path.exists()
        if recovered:
            if not recover_receipt:
                raise cp.Fault('Managed hook receipt missing; explicitly reconcile exact installed definitions before recovery')
            receipt = {'version': '0.4.0', 'definitions': _recover_definitions(state, codex_home, original, python),
                       'recovered_from_sha256': cp.sha(cp.content(backup)), 'recovered_at': cp.now()}
        else:
            receipt = cp.read(receipt_path)
        path = codex_home/'hooks.json'
        current = cp.read(path)
        if not isinstance(current.get('hooks'),dict):
            raise cp.Fault('Unsupported hook configuration; preserve and reconcile')
        if recovered:
            script = str(Path(__file__).with_name('hook.py').resolve())
            for event, entries in current['hooks'].items():
                for entry in entries:
                    if any(script in h.get('command', '') for h in entry.get('hooks', [])) and entry != receipt['definitions'].get(event):
                        raise cp.Fault('Customized current checkpoint hook; preserve and reconcile')
        restored = []
        for event, definition in receipt['definitions'].items():
            if definition not in original.get('hooks',{}).get(event,[]):
                raise cp.Fault('Backup does not contain the exact owned definitions')
            entries = current['hooks'].setdefault(event,[])
            if not isinstance(entries,list):
                raise cp.Fault('Unsupported hook event; no changes written')
            if entries.count(definition) > 1:
                raise cp.Fault('Duplicate managed definition; preserve and reconcile before restoration')
            if recovered and any(entry != definition and any(
                    str(Path(__file__).with_name('hook.py').resolve()) in h.get('command', '')
                    for h in entry.get('hooks', [])) for entry in entries):
                raise cp.Fault('Customized current checkpoint hook; preserve and reconcile')
            if definition not in entries:
                entries.append(definition);restored.append(event)
        before = cp.sha(cp.content(path))
        if recovered:
            # Validate all files first. If the following hook write fails, the exact
            # receipt permits an ordinary retry; no false restoration is reported.
            cp.atomic(receipt_path, cp.encoded(receipt))
        cp.atomic(path, cp.encoded(current))
        result = {'restored':restored,'owned_definitions':len(receipt['definitions']), 'receipt_recovered':recovered, 'unrelated_entries_preserved':True,'native_trust_changed':False,'before_sha256':before,'after_sha256':cp.sha(cp.content(path))}
        cp.atomic(state/'hooks-restoration.json',cp.encoded(result))
        return result

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state', type=Path, required=True)
    sub = p.add_subparsers(dest='command', required=True)
    install_parser = sub.add_parser('install')
    install_parser.add_argument('--codex-home', type=Path, required=True)
    install_parser.add_argument('--python', type=Path, default=Path(sys.executable))
    install_parser.add_argument('--project', type=Path, action='append', default=[])
    sub.add_parser('tick')
    sub.add_parser('status')
    restore_parser = sub.add_parser('restore-hooks')
    restore_parser.add_argument('--codex-home',type=Path,required=True)
    restore_parser.add_argument('--backup',type=Path,required=True)
    restore_parser.add_argument('--recover-receipt',action='store_true')
    restore_parser.add_argument('--python',type=Path)
    remove_parser = sub.add_parser('uninstall')
    remove_parser.add_argument('--codex-home', type=Path, required=True)
    a = p.parse_args()
    if a.command == 'install':
        result = install(a.state, a.codex_home, a.python, a.project)
    elif a.command == 'restore-hooks':
        if a.python is not None and not a.recover_receipt:
            raise cp.Fault('--python is only used for explicit receipt recovery')
        result = restore_hooks(a.state,a.codex_home,a.backup,a.recover_receipt,a.python)
    elif a.command == 'tick':
        result = tick(a.state)
    elif a.command == 'uninstall':
        result = uninstall(a.state, a.codex_home)
    else:
        result = cp.read(a.state / 'status.json')
        result['hook_registration'] = registration_status(a.state)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (cp.Fault, OSError, subprocess.SubprocessError, KeyError, ValueError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc) if isinstance(exc, cp.Fault) else type(exc).__name__}), file=sys.stderr)
        sys.exit(2)
