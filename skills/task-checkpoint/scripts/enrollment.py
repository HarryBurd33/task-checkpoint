#!/usr/bin/env python3
"""Opt-in automatic enrollment and explicit chat scopes in the existing account registry.

Scopes are routing metadata, never ownership, permission, resume receipts or new queues.
"""
import argparse
import json
from pathlib import Path
import re

import checkpoint as cp


def session_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,191}', value):
        raise cp.Fault('A verified host session/chat ID is required')
    return value


def host_identity(event):
    """Use the native root session ID, shared with its subagents.

    CODEX_THREAD_ID in a parent shell may leak into a newly spawned app-server;
    it is not an authority for hook routing. The host event is authoritative.
    """
    session = event.get('session_id')
    explicit = event.get('thread_id')
    if session and explicit and session != explicit:
        raise cp.Fault('Conflicting host chat identities; no isolation inferred')
    value = session or explicit
    if value:
        return session_id(value), 'session_id' if session else 'thread_id'
    return None, 'unknown'


def excluded(config, root, session):
    policy = config.get('auto_enrollment', {})
    if session in policy.get('exclude_sessions', []):
        return True
    for name in policy.get('exclude_roots', []):
        path = Path(name)
        if not path.is_absolute():
            raise cp.Fault('Enrollment exclusions require absolute roots')
        if root == path.resolve() or path.resolve() in root.parents:
            return True
    return False


def scope(config, root, binding, session):
    """Legacy/unknown identities stay conservative; only exact reviewed maps isolate."""
    record = config.get('chat_scopes', {}).get(str(root))
    if record is None and binding.get('enrolled_session_id'):
        record = {k: binding[k] for k in ('task_id', 'project_id')}
        record['session_ids'] = [binding['enrolled_session_id']]
    if record is None or not session:
        return 'legacy'
    session_id(session)
    if record.get('task_id') != binding['task_id'] or record.get('project_id') != binding['project_id']:
        raise cp.Fault('Chat scope no longer matches task binding; reconcile explicitly')
    ids = record.get('session_ids')
    if not isinstance(ids, list) or not ids:
        raise cp.Fault('Chat scope has no verified identities')
    for ident in ids:
        session_id(ident)
    unrelated = record.get('unrelated_session_ids', [])
    if not isinstance(unrelated, list) or set(ids) & set(unrelated):
        raise cp.Fault('Invalid or overlapping chat scope identities')
    for ident in unrelated:
        session_id(ident)
    return 'matched' if session in ids else ('foreign' if session in unrelated else 'legacy')


def bind(state, root, task, sessions, unrelated=None):
    """Operator-reviewed routing repair; never edit a task's checkpoint or owner."""
    root = root.resolve()
    binding, _ = cp.config(root)
    if task != binding['task_id']:
        raise cp.Fault('Wrong task for chat scope; no changes made')
    ids = sorted(set(session_id(s) for s in sessions))
    if not ids:
        raise cp.Fault('At least one verified owning chat is required')
    foreign = sorted(set(session_id(s) for s in (unrelated or [])))
    if set(ids) & set(foreign):
        raise cp.Fault('A chat cannot be both owning and unrelated')
    with cp.lock(state):
        config = cp.read(state/'config.json')
        scopes = config.setdefault('chat_scopes', {})
        previous = scopes.get(str(root))
        value = {'task_id': binding['task_id'], 'project_id': binding['project_id'], 'session_ids': ids, 'unrelated_session_ids': foreign}
        # Rebinding a known map can weaken a stop; require an explicit separate repair.
        if previous and previous != value:
            raise cp.Fault('Existing chat scope differs; preserve and review before changing it')
        scopes[str(root)] = value
        cp.atomic(state/'config.json', cp.encoded(config))
    return {'chat_scope': value, 'root': str(root), 'task_state_changed': False, 'resumed': False}


def configure(state, enabled, roots=None, sessions=None):
    with cp.lock(state):
        config = cp.read(state/'config.json')
        prior = config.get('auto_enrollment', {})
        policy = {'enabled': enabled,
                  'exclude_roots': sorted(set(str(Path(p).resolve()) for p in (roots if roots is not None else prior.get('exclude_roots', [])))),
                  'exclude_sessions': sorted(set(session_id(s) for s in (sessions if sessions is not None else prior.get('exclude_sessions', []))))}
        config['auto_enrollment'] = policy
        cp.atomic(state/'config.json', cp.encoded(config))
    return {'auto_enrollment': policy, 'existing_stops_changed': False}


def enroll(state, root, session):
    """Register one eligible Git workspace. Never replace a binding or invent semantics."""
    root = root.resolve()
    session_id(session)
    config = cp.read(state/'config.json')
    if config.get('enabled') is not True or config.get('auto_enrollment', {}).get('enabled') is not True:
        return {'status': 'disabled'}
    if excluded(config, root, session):
        return {'status': 'excluded'}
    try:
        with cp.lock(state):
            return _enroll_locked(state, root, session)
    except cp.Fault as exc:
        if str(exc).startswith('Writer lock exists'):
            return {'status': 'deferred-collector-busy'}
        raise


def _enroll_locked(state, root, session):
    config = cp.read(state/'config.json')
    if config.get('enabled') is not True or config.get('auto_enrollment', {}).get('enabled') is not True:
        return {'status': 'disabled'}
    if excluded(config, root, session):
        return {'status': 'excluded'}
    if Path(cp.git_text(root, 'rev-parse', '--show-toplevel')).resolve() != root:
        raise cp.Fault('Enrollment requires the exact Git workspace root')
    if not cp.git_text(root, 'rev-parse', '--verify', 'HEAD', check=False):
        return {'status': 'not-eligible-no-commit'}
    local = root/'.checkpoint'
    if local.is_symlink():
        raise cp.Fault('Linked checkpoint directory cannot be enrolled')
    if local.exists():
        if not (local/'config.json').exists():
            return {'status': 'existing-store-needs-review'}
        binding, _ = cp.config(root)
        if binding.get('enrolled_session_id') != session:
            return {'status': 'existing-binding', 'task_id': binding['task_id']}
    else:
        if any(p.get('root') == str(root) for p in config.get('projects', [])) or str(root) in config.get('chat_scopes', {}):
            return {'status': 'registry-conflict-needs-review'}
        # Private state must be ignored before any state is created. Preserve all
        # existing ignore bytes; no global excludes or Git configuration changes.
        ignored = cp.git_text(root, 'check-ignore', '.checkpoint/config.json', check=False)
        if not ignored:
            ignore = root/'.gitignore'
            before = cp.content(ignore) if ignore.exists() else b''
            suffix = b'' if not before or before.endswith(b'\n') else b'\n'
            cp.atomic(ignore, before + suffix + b'.checkpoint/\n')
        local.mkdir(mode=0o700)
        binding = {'schema_version': 1, 'task_id': 'chat-'+cp.sha(session.encode())[:24],
                   'project_id': 'local-'+cp.sha(str(root).encode())[:24], 'store': None,
                   'ownership': 'local', 'root_handoff': True, 'enrolled_session_id': session}
        cp.atomic(local/'config.json', cp.encoded(binding))
    key = str(root)
    record = {'root': key, 'task_id': binding['task_id'], 'project_id': binding['project_id'], 'scheduled_dispatch': False}
    projects = config.setdefault('projects', [])
    prior = next((p for p in projects if p.get('root') == key), None)
    if prior and (prior.get('task_id'), prior.get('project_id')) != (binding['task_id'], binding['project_id']):
        raise cp.Fault('Registry identity conflicts with enrollment; preserve and reconcile')
    if prior is None:
        projects.append(record)
    expected = {'task_id': binding['task_id'], 'project_id': binding['project_id'], 'session_ids': [session]}
    scopes = config.setdefault('chat_scopes', {})
    if key in scopes and scopes[key] != expected:
        raise cp.Fault('Existing chat scope conflicts with enrollment')
    scopes[key] = expected
    cp.atomic(state/'config.json', cp.encoded(config))
    return {'status': 'enrolled', 'task_id': binding['task_id'], 'semantic_input_required': not (local/'input.json').exists(),
            'ownership_acquired': False, 'execution_scheduled': False}


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--state', type=Path, required=True)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    settings = sub.add_parser('configure')
    settings.add_argument('--enabled', choices=['true', 'false'], required=True)
    settings.add_argument('--exclude-root', type=Path, action='append')
    settings.add_argument('--exclude-session', action='append')
    attach = sub.add_parser('bind-chat')
    attach.add_argument('--root', type=Path, required=True)
    attach.add_argument('--task', required=True)
    attach.add_argument('--session', action='append', required=True)
    attach.add_argument('--unrelated-session', action='append', default=[])
    a = p.parse_args()
    if a.command == 'configure':
        result = configure(a.state, a.enabled == 'true', a.exclude_root, a.exclude_session)
    elif a.command == 'bind-chat':
        result = bind(a.state, a.root, a.task, a.session, a.unrelated_session)
    else:
        config = cp.read(a.state/'config.json')
        result = {k: config.get(k, {}) for k in ('auto_enrollment', 'chat_scopes')}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (cp.Fault, OSError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        raise SystemExit(2)
