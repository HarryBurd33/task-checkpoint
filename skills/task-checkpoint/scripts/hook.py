#!/usr/bin/env python3
"""Trusted project hook: bounded snapshots of agent-maintained input, never a watcher."""
import json
import argparse
import os
import re
import shlex
import shutil
from pathlib import Path
import sys
import checkpoint as cp

def halt(name, message):
    if name == 'PreToolUse':
        return {'systemMessage': message, 'hookSpecificOutput': {'hookEventName': name, 'permissionDecision': 'deny', 'permissionDecisionReason': message}}
    if name in ('Interrupt', 'SessionEnd'):
        return {'systemMessage': message}
    return {'continue': False, 'stopReason': message}

def maintenance(event, root, account_state=None):
    from maintenance import classify
    return classify(event, root, account_state)[0]


def recovery_message(event, root, account_state, message):
    from maintenance import classify, next_command
    allowed, reason = classify(event, root, account_state)
    return message + ' Maintenance classification: ' + reason + '. Exact next command: ' + next_command(root, account_state) + '. Read-only inspection never resumes a task; confirm task and owner before a grant.'

def record_delivery(state, event, root, chat, identity_source, binding=None, scope="unvalidated"):
    value = {'event': event.get('hook_event_name'), 'observed_at': cp.now(),
             'root': str(root), 'session_id': event.get('session_id'), 'chat_id': chat,
             'identity_source': identity_source, 'pid': os.getpid(), 'parent_pid': os.getppid(),
             'tool_name': event.get('tool_name'), 'scope': scope,
             'task_id': binding.get('task_id') if binding else None,
             'project_id': binding.get('project_id') if binding else None}
    cp.atomic(state/'hook-delivery.json', cp.encoded(value))
    if chat:
        cp.atomic(state/'chat-delivery'/(cp.sha(chat.encode())+'.json'), cp.encoded(value))

def main(account_state=None):
    event = json.load(sys.stdin)
    root = Path(event.get('cwd', '.')).resolve()
    try:
        root = Path(cp.git_text(root, 'rev-parse', '--show-toplevel')).resolve()
    except cp.Fault:
        return {}
    binding = root / '.checkpoint' / 'config.json'
    name = event.get('hook_event_name', '')
    account_enabled = account_state is not None and (account_state / 'config.json').exists() and cp.read(account_state / 'config.json').get('enabled') is True
    import enrollment
    chat, identity_source = enrollment.host_identity(event)
    account_config = cp.read(account_state / 'config.json') if account_enabled else {}
    if account_enabled:
        record_delivery(account_state, event, root, chat, identity_source)
    # Recovery inspection is not a new domain task. Keep unbound repair contexts
    # unbound; ordinary covered tools still follow configured enrollment below.
    if not binding.exists() and name in ('PreToolUse', 'PostToolUse') and maintenance(event, root, account_state):
        return {}
    enrolled = None
    if not binding.exists() and account_enabled and chat and name in ('SessionStart', 'PreToolUse'):
        enrolled = enrollment.enroll(account_state, root, chat)
        account_config = cp.read(account_state / 'config.json')
    if binding.exists():
        current, _ = cp.config(root)
        selected_scope = enrollment.scope(account_config, root, current, chat)
        if account_enabled and chat:
            cp.atomic(account_state / 'chat-delivery' / (cp.sha(chat.encode()) + '.json'), cp.encoded({
                'event': name, 'observed_at': cp.now(), 'root': str(root), 'task_id': current['task_id'],
                'chat_id': chat, 'identity_source': identity_source, 'session_id': event.get('session_id'),
                'scope': selected_scope, 'tool_name': event.get('tool_name')}))
        if selected_scope == 'foreign':
            # The stopped task and all of its state remain intact. This chat may
            # work independently, but cannot inherit its checkpoint or ownership.
            if name == 'SessionStart':
                return {'hookSpecificOutput': {'hookEventName': name, 'additionalContext':
                    'This workspace checkpoint belongs to another chat/task (' + current['task_id'] +
                    '). Its ownership and stops are unchanged. Use a separate checkout for this chat checkpoint; never resume or replace that binding to unblock unrelated work.'}}
            return {}
    if not binding.exists():
        if account_enabled and name == 'SessionStart':
            return {'hookSpecificOutput': {'hookEventName': name, 'additionalContext': 'Checkpoint and Handoff is enabled for this local Codex user. Use task-checkpoint for meaningful work boundaries and usage-aware assignment. This repository has no task binding yet: inspect its policies and existing queues before initializing one. No work or permission is restored by this message.'}}
        return {}
    c, store = cp.config(root)
    source = store / 'input.json'
    if account_enabled:
        record_delivery(account_state, event, root, chat, identity_source, c, selected_scope)
    if account_enabled:
        cp.atomic(store / 'native-hook-delivery.json', cp.encoded({'event': name, 'observed_at': cp.now(), 'root': str(root), 'project_id': c['project_id'], 'task_id': c['task_id'], 'session_id': event.get('session_id'), 'chat_id': chat, 'identity_source': identity_source, 'pid': os.getpid()}))
    if name in ('PreToolUse', 'PostToolUse') and maintenance(event, root, account_state):
        return {}
    stop = store / 'automatic-stop.json'
    # A persistent stop pins its verified generation until reviewed resume.
    # Terminal boundary saves must not advance latest/HANDOFF behind that marker.
    if name in ('PreToolUse', 'PostToolUse', 'PreCompact', 'Stop', 'Interrupt', 'SessionEnd') and stop.exists():
        marker = cp.read(stop)
        status = marker.get('checkpoint_status', 'unknown')
        return halt(name, recovery_message(event, root, account_state,
                    'Policy denial: automatic usage stop persists. Preservation status: ' + str(status) +
                    '; checkpoint: ' + str(marker.get('checkpoint_id', 'not verified')) +
                    '. Ordinary work remains blocked until current authorization, fresh readings and reviewed resume succeed.'))
    if name == 'SessionStart':
        return {'hookSpecificOutput': {'hookEventName': name, 'additionalContext': ('Automatic enrollment created a task binding. Maintain .checkpoint/input.json with real semantic progress before preservation. ' if enrolled and enrolled.get('status') == 'enrolled' else '') + 'Checkpoint integration is present. Read the task-checkpoint skill. Inspect and verify current authorization, artifacts, jobs and exclusive task ownership before implementation. This hook does not resume work.' + (' User-wide usage collection is configured. Use the approved router configuration for qualified bounded tasks and check fresh shared signals before dispatch.' if account_enabled else '')}}
    low = False
    signal_path = account_state / 'signals.json' if account_enabled else store / 'signals.json'
    if name in ('PreToolUse', 'PostToolUse', 'PreCompact', 'Stop'):
        signals = cp.read(signal_path) if signal_path.exists() else {'records': []}
        if account_enabled and (store / 'signals.json').exists():
            import telemetry
            local = cp.read(store / 'signals.json')
            if 'records' not in local:
                local = telemetry.from_checkpoint_signals(local)
            signals['records'].extend(r for r in local['records'] if r.get('kind') != 'codex_plan')
        import telemetry
        required_account = account_enabled or (store / 'allowance-override.json').exists() or any(r.get('kind') == 'codex_plan' for r in telemetry.from_checkpoint_signals(signals)['records'])
        observation = cp.policy(signals, root, require_account=required_account)
        low = observation['checkpoint_required']
    journal = store / 'router.json'
    if account_enabled and name == 'PreToolUse' and journal.exists():
        active = cp.read(journal).get('active')
        if active and os.environ.get('CHECKPOINT_RUN_ID') != active.get('id'):
            return halt(name, 'A routed worker is active or uncertain. Stop ordinary writes and inspect/reconcile that worker before continuing.')
    if name in ('PreToolUse', 'PostToolUse') and not low:
        return {}
    if name not in ('PreToolUse', 'PostToolUse', 'PreCompact', 'Stop', 'Interrupt', 'SessionEnd'):
        return {}
    if low:
        import monitor
        # The hook-only path must also create a durable stop. A healthy/stale
        # next reading cannot resume work without the explicit review gate.
        normalized = {'records': observation['observations'], 'accounts': signals.get('accounts', {})}
        preserved = monitor.stop_for_signals(root, normalized, account_state if account_enabled else None, require_account=required_account)
        return halt(name, recovery_message(event, root, account_state,
                    'Resource policy denial. Preservation result: ' + str(preserved) + '. No automatic resumption.'))
    if not source.exists():
        return {}
    # Deduplicate unchanged boundary saves. Never turn unknown readings into zero.
    fingerprint = cp.repo(root)['fingerprint']
    key = cp.sha(cp.content(source)) + ':' + fingerprint
    marker = store / 'boundary.json'
    last = cp.read(marker) if marker.exists() else {}
    if key != last.get('key'):
        task = cp.read(source)
        task['observations'].append('Hook boundary ' + name + '; semantic input source last modified at ' + str(source.stat().st_mtime_ns) + ' ns. Hook does not reconstruct conversation state.')
        temporary = store / 'hook-input.json'
        cp.atomic(temporary, cp.encoded(cp.redact(task)))
        try:
            saved = cp.checkpoint(root, temporary, 'low-resource' if low else {'PreCompact':'pre-switch','Stop':'milestone','Interrupt':'shutdown','SessionEnd':'shutdown'}[name])
        finally:
            temporary.unlink(missing_ok=True)
        cp.atomic(marker, cp.encoded({'key': key, 'checkpoint_id': saved['id'], 'at': cp.now()}))
    if low:
        return halt(name, 'Low-resource guard: checkpoint verified. Stop normal work. Quota reads and exact checkpoint/reserve maintenance commands are allowed. Explicitly grant ten/exhaustion and perform reviewed resume, or wait for fresh recovery; no automatic resumption.')
    return {}

if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument('--account-state', type=Path)
        args = parser.parse_args()
        print(json.dumps(main(args.account_state)))
    except Exception:
        print(json.dumps({'systemMessage': 'Checkpoint hook failed. Stop normal work; inspect private state and use the manual emergency handoff.'}))
        sys.exit(2)
