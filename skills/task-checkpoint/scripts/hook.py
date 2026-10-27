#!/usr/bin/env python3
"""Trusted project hook: bounded snapshots of agent-maintained input, never a watcher."""
import json
import argparse
import os
from pathlib import Path
import sys
import checkpoint as cp

def halt(name, message):
    if name == 'PreToolUse':
        return {'systemMessage': message, 'hookSpecificOutput': {'hookEventName': name, 'permissionDecision': 'deny', 'permissionDecisionReason': message}}
    if name in ('Interrupt', 'SessionEnd'):
        return {'systemMessage': message}
    return {'continue': False, 'stopReason': message}

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
    if not binding.exists():
        if account_enabled and name == 'SessionStart':
            return {'hookSpecificOutput': {'hookEventName': name, 'additionalContext': 'Checkpoint and Handoff is enabled for this local Codex user. Use task-checkpoint for meaningful work boundaries and usage-aware assignment. This repository has no task binding yet: inspect its policies and existing queues before initializing one. No work or permission is restored by this message.'}}
        return {}
    c, store = cp.config(root)
    source = store / 'input.json'
    if account_enabled:
        cp.atomic(account_state / 'hook-delivery.json', cp.encoded({'event': name, 'observed_at': cp.now(), 'task_id': c['task_id'], 'root': str(root), 'project_id': c['project_id']}))
    if account_enabled:
        cp.atomic(store / 'native-hook-delivery.json', cp.encoded({'event': name, 'observed_at': cp.now(), 'root': str(root), 'project_id': c['project_id'], 'task_id': c['task_id'], 'session_id': event.get('session_id'), 'pid': os.getpid()}))
    stop = store / 'automatic-stop.json'
    if name in ('PreToolUse', 'PostToolUse', 'PreCompact', 'Stop') and stop.exists():
        marker = cp.read(stop)
        status = marker.get('checkpoint_status', 'unknown')
        return halt(name, 'Automatic usage stop persists. Preservation status: ' + str(status) +
                    '; checkpoint: ' + str(marker.get('checkpoint_id', 'not verified')) +
                    '. Stop ordinary work. Inspect/repair and explicitly resume through the manual runtime after fresh resource recovery; no job cancellation is claimed.')
    if name == 'SessionStart':
        return {'hookSpecificOutput': {'hookEventName': name, 'additionalContext': 'Checkpoint integration is present. Read the task-checkpoint skill. Inspect and verify current authorization, artifacts, jobs and exclusive task ownership before implementation. This hook does not resume work.' + (' User-wide usage collection is configured. Use the approved router configuration for qualified bounded tasks and check fresh shared signals before dispatch.' if account_enabled else '')}}
    low = False
    signal_path = account_state / 'signals.json' if account_enabled else store / 'signals.json'
    if name in ('PreToolUse', 'PostToolUse', 'PreCompact', 'Stop') and signal_path.exists():
        signals = cp.read(signal_path)
        if account_enabled and (store / 'signals.json').exists():
            import telemetry
            local = cp.read(store / 'signals.json')
            if 'records' not in local:
                local = telemetry.from_checkpoint_signals(local)
            signals['records'].extend(r for r in local['records'] if r.get('kind') != 'codex_plan')
        low = cp.policy(signals)['checkpoint_required']
    journal = store / 'router.json'
    if account_enabled and name == 'PreToolUse' and journal.exists():
        active = cp.read(journal).get('active')
        if active and os.environ.get('CHECKPOINT_RUN_ID') != active.get('id'):
            return halt(name, 'A routed worker is active or uncertain. Stop ordinary writes and inspect/reconcile that worker before continuing.')
    if name in ('PreToolUse', 'PostToolUse') and not low:
        return {}
    if name not in ('PreToolUse', 'PostToolUse', 'PreCompact', 'Stop', 'Interrupt', 'SessionEnd'):
        return {}
    if not source.exists():
        return halt(name, 'Checkpoint input missing. Save a manual semantic checkpoint before normal work.') if low else {}
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
        return halt(name, 'Low-resource guard: checkpoint verified. Stop normal work. Recheck signals and explicitly resume later; no automatic resumption.')
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
