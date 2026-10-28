#!/usr/bin/env python3
"""Notification-only reset tickets in the existing task store. Never invokes work."""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import uuid
import checkpoint as cp
import telemetry
import reserve

TERMINAL = {'completed', 'canceled', 'cancelled', 'transferred', 'resumed'}

def stamp(value):
    return telemetry.timestamp(value)

def key(record):
    return (record.get('account_fingerprint', ''), record.get('window', ''))

def lifecycle(root, status, reason):
    binding, store = cp.config(root)
    if status not in TERMINAL | {'active'} or not reason.strip():
        raise cp.Fault('Explicit lifecycle status and reason required')
    value = dict(project_id=binding['project_id'], task_id=binding['task_id'], status=status,
                 observed_at=cp.now(), reason=reason)
    cp.atomic(store/'task-lifecycle.json', cp.encoded(value))
    return value

def notify(message, adapter):
    if adapter != 'macos' or sys.platform != 'darwin':
        raise cp.Fault('Native notification unsupported; read HANDOFF.md and explicitly resume after a fresh allowance check')
    # Text travels as argv, never executable AppleScript or shell source.
    script = 'on run argv\n display notification (item 1 of argv) with title "Checkpoint ready"\nend run'
    result = subprocess.run(['/usr/bin/osascript', '-e', script, message], capture_output=True, timeout=15)
    if result.returncode:
        raise cp.Fault('Native notification failed; verify macOS notification permissions and use manual resume')
    return {'adapter': 'macos', 'accepted_by_command': True, 'display_observed': False}

def update(root, signals, settings, now=None, deliver=None):
    """Called after collection/preservation by the existing minute collector.

    At-most-one delivery attempt, not exactly-once OS display. A crash during
    delivery stays uncertain and is never redelivered automatically.
    """
    binding, store = cp.config(root)
    current = stamp(now) if now is not None else stamp(cp.now())
    path = store/'readiness.json'
    gate = store/'readiness-fence'; gate.mkdir(exist_ok=True)
    with cp.lock(gate):
        ticket = cp.read(path) if path.exists() else None
        if ticket and (ticket.get('project_id') != binding['project_id'] or ticket.get('task_id') != binding['task_id']):
            raise cp.Fault('Readiness identity mismatch; preserve existing ticket')
        def persist(status, **fields):
            ticket.update(status=status, checked_at=current.isoformat(), **fields)
            cp.atomic(path, cp.encoded(ticket))
            return dict(ticket)
        if settings.get('enabled') is not True:
            return persist('retired', reason='disabled') if ticket else {'status':'disabled'}
        life = cp.read(store/'task-lifecycle.json') if (store/'task-lifecycle.json').exists() else None
        if life and (life.get('project_id') != binding['project_id'] or life.get('task_id') != binding['task_id']):
            raise cp.Fault('Lifecycle identity mismatch')
        stop = cp.read(store/'automatic-stop.json') if (store/'automatic-stop.json').exists() else None
        if (life and life.get('status') in TERMINAL) or stop is None:
            return persist('retired', reason=life['status'] if life else 'stop-cleared-or-explicitly-resumed') if ticket else {'status':'inactive'}
        if stop.get('task_id') != binding['task_id'] or stop.get('project_id') != binding['project_id']:
            raise cp.Fault('Stop identity mismatch')
        incident = stop.get('requested_at')
        if not incident:
            return {'status':'user-action-required','reason':'Stop lacks stable incident identity; inspect manually'}
        if ticket and ticket.get('incident') != incident:
            history = store/'readiness-history';history.mkdir(exist_ok=True)
            cp.atomic(history/(ticket['id']+'.json'), cp.encoded(ticket)); ticket = None
        if ticket and ticket['status'] in {'notified','delivery-uncertain','delivery-failed','retired'}:
            return ticket
        if ticket is None:
            ticket = {'version':1,'id':uuid.uuid4().hex,'project_id':binding['project_id'],'task_id':binding['task_id'],
                      'incident':incident,'created_at':current.isoformat(),'status':'pending',
                      'automatic_resume':False,'execution_authorized':False,'scheduler_id':settings.get('scheduler_id'),
                      'scheduler_kind':'existing-collector','schedule_status':'pending',
                      'required_windows':[], 'not_before':None}
        # Readiness must use the same task baseline, grant and identity gates as
        # preservation. Shared raw guards can disagree with an explicit local choice.
        try:
            assessment = reserve.assess(root, signals, now=current, require_account=True)
        except (cp.Fault, OSError, ValueError, KeyError, TypeError) as exc:
            return persist('user-action-required', reason='Task reserve policy unverified: ' + str(exc))
        plan = [r for r in assessment['records'] if r.get('kind') == 'codex_plan']
        if not plan or any(not isinstance(r.get('account_fingerprint'),str) or not r['account_fingerprint'].strip()
                           or not isinstance(r.get('window'),str) or not r['window'].strip() for r in plan):
            return persist('user-action-required', schedule_status='unsupported', reason='Account/profile identity and named quota windows required; manually verify readiness')
        # Remember every observed applicable window, including nonblocking windows.
        required = {tuple(x) for x in ticket['required_windows']}
        required.update(key(r) for r in plan)
        ticket['required_windows'] = [list(x) for x in sorted(required)]
        if assessment.get('override_blocked'):
            reason = (assessment.get('override') or {}).get('reason') or assessment.get('account_reason')
            return persist('pending', reason=reason or 'Task reserve policy does not establish readiness')
        low = [r for r in plan if r['status'] == 'low']
        if low:
            if any(not r.get('resets_at') for r in low):
                return persist('user-action-required',schedule_status='unsupported',reason='Blocking reset unknown; manually recheck allowance and HANDOFF.md')
            target = max(stamp(r['resets_at']) for r in low) + dt.timedelta(seconds=60)
            if ticket['not_before']:
                target = max(target,stamp(ticket['not_before']))
            ticket.update(not_before=target.isoformat(),schedule_status='registered-local-ticket')
            return persist('pending',reason='Waiting for all blocking resets plus 60 seconds; execution time is a target')
        if ticket['not_before'] is None:
            return persist('user-action-required',schedule_status='unsupported',reason='No verified blocking reset; manual fresh allowance check required')
        if current < stamp(ticket['not_before']):
            return persist('pending')
        by_key = {}
        for r in plan:
            by_key.setdefault(key(r), []).append(r)
        if (not required or any(k not in by_key or any(r['status'] != 'ok' for r in by_key[k]) for k in required)
            or assessment['statuses']['codex_plan'] != 'ok'
            or assessment['low'] or any(assessment['statuses'].get(k) != 'ok' for k in stop.get('low_kinds', ['codex_plan']))):
            return persist('pending',reason='Fresh recovery of every required account/window/resource is unestablished')
        try:
            saved,_ = cp.latest(store)
            cp.verify_root(root, saved)
            if stop.get('checkpoint_status') != 'verified' or saved['id'] != stop.get('checkpoint_id'):
                raise cp.Fault('Checkpoint incomplete or changed; verify current handoff')
            if any(j['status'] not in {'completed','failed','cancelled'} for j in saved['task']['jobs']):
                raise cp.Fault('Active or uncertain job requires verification before readiness')
            journal = cp.read(store/'router.json') if (store/'router.json').exists() else {}
            if journal.get('active'):
                raise cp.Fault('Active or uncertain worker requires verification')
            resume = cp.read(store/'resume.json') if (store/'resume.json').exists() else {}
            if resume.get('resumed_at') and stamp(resume['resumed_at']) > stamp(incident):
                return persist('retired', reason='Task already explicitly resumed')
            owner = cp.Ownership(root,binding,store)
            claim = owner.value(owner.tip())
            if claim.get('owner') and (not claim.get('created_at') or stamp(claim['created_at']) > stamp(incident)):
                raise cp.Fault('A newer task owner exists; verify transfer/resumption')
        except (cp.Fault, OSError, ValueError, KeyError) as exc:
            return persist('user-action-required',reason=str(exc))
        message = ('Ready to review ' + binding['project_id'] + '. Read ' + str(root/'HANDOFF.md')
                   + '. Say: Resume from HANDOFF.md. Verify authorization, ownership and fresh resources before continuing.')
        # Persist intent first: uncertain delivery must not become duplicate delivery.
        persist('delivery-uncertain', message=message, delivery_started_at=current.isoformat())
        try:
            receipt = (deliver or notify)(message, settings.get('notifier','unsupported'))
        except Exception as exc:
            return persist('delivery-failed',reason=type(exc).__name__ + ': ' + str(exc),manual_fallback='Read HANDOFF.md, recheck allowance, then explicitly request resume')
        return persist('notified',receipt=receipt,notified_at=current.isoformat())

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    subs=parser.add_subparsers(dest='command',required=True)
    check=subs.add_parser('check');check.add_argument('--signals',type=Path,required=True);check.add_argument('--notifier',choices=['macos','unsupported'],default='unsupported')
    life=subs.add_parser('lifecycle');life.add_argument('--status',required=True,choices=sorted(TERMINAL|{'active'}));life.add_argument('--reason',required=True)
    reset=subs.add_parser('retry-preservation');reset.add_argument('--reason',required=True)
    args=parser.parse_args();root=args.root.resolve()
    if args.command=='lifecycle':result=lifecycle(root,args.status,args.reason)
    elif args.command=='retry-preservation':
        _,store=cp.config(root)
        with cp.lock(store):
            marker=cp.read(store/'automatic-stop.json');marker['preservation_attempts']=0
            marker['retry_authorization']={'reason':args.reason,'at':cp.now()}
            cp.atomic(store/'automatic-stop.json',cp.encoded(marker))
        result={'status':'retry-enabled','automatic_resume':False}
    else:result=update(root,cp.read(args.signals),{'enabled':True,'notifier':args.notifier})
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (cp.Fault,OSError,ValueError) as exc:
        print(str(exc),file=sys.stderr);sys.exit(2)
