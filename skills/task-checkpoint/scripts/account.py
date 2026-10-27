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
            for label, key in (('Git', 'git_executable'), ('GitHub CLI', 'gh_executable')):
                executable = config.get(key)
                if executable:
                    if not Path(executable).is_absolute() or not Path(executable).is_file():
                        raise cp.Fault('Configured ' + label + ' executable is unavailable; repair the user dependency')
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
            preservation = monitor.evaluate_registered(state, signals)
            models = [{'model': m['model'], 'efforts': m.get('supportedReasoningEfforts', [])}
                      for m in observed['models'].get('data', [])]
            cp.atomic(state / 'models.json', cp.encoded({'observed_at': observed['observed_at'], 'models': models}))
            status = {'last_success': cp.now(), 'source': observed['source'], 'auth_type': 'chatgpt',
                      'telemetry': telemetry.assess(signals), 'preservation': preservation, 'scheduled': []}
            for project in config['projects']:
                try:
                    root = Path(project['root'])
                    binding, store = cp.config(root)
                    if binding['task_id'] != project['task_id'] or binding['project_id'] != project['project_id']:
                        raise cp.Fault('Registered project binding changed; no work dispatched')
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
            for project in config['projects']:
                if not project.get('private_transfer'):
                    continue
                try:
                    import transfer
                    result = transfer.publish(Path(project['root']), project['private_transfer']['repository'])
                    status['transfers'].append({'task_id': project['task_id'], **result})
                except Exception as exc:
                    status['transfers'].append({'task_id': project['task_id'], 'status': 'pending-retry', 'error_type': type(exc).__name__})
            status['receives'] = []
            for project in config['projects']:
                if not project.get('private_receive'):
                    continue
                try:
                    import transfer
                    result = transfer.receive_latest(Path(project['root']), project['private_receive']['repository'])
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
    remove_parser = sub.add_parser('uninstall')
    remove_parser.add_argument('--codex-home', type=Path, required=True)
    a = p.parse_args()
    if a.command == 'install':
        result = install(a.state, a.codex_home, a.python, a.project)
    elif a.command == 'tick':
        result = tick(a.state)
    elif a.command == 'uninstall':
        result = uninstall(a.state, a.codex_home)
    else:
        result = cp.read(a.state / 'status.json')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (cp.Fault, OSError, subprocess.SubprocessError, KeyError, ValueError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc) if isinstance(exc, cp.Fault) else type(exc).__name__}), file=sys.stderr)
        sys.exit(2)
