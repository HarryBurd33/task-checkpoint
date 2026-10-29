# Notification-only readiness

This extension adds no watcher or task queue. The existing `account.py tick` collector calls `monitor.evaluate_registered`, which processes notification tickets before its stopped-project dispatch skip. A readiness check never calls the router or task implementation.

In the existing private account configuration, opt in only the intended registered project:

```json
"readiness": {"enabled": true, "notifier": "macos"}
```

Do not replace the entire account configuration. Preserve all existing project settings and thresholds. Optionally record `readiness_scheduler_id` at account level only after verifying the actual existing native service ID. A local ticket records `registered-local-ticket`; this alone does not claim native scheduling succeeded. `macos` uses `/usr/bin/osascript` with message as argv and a 15-second timeout. Native command acceptance is not proof the user saw an OS notification. Windows/Linux notification delivery currently requires a separately reviewed adapter; use the manual fallback.

The existing collector normally polls every minute, while the computer is awake, the account is available and the service has permissions to read each project. The ticket targets max(all fresh blocking reset timestamps)+60 seconds. Polling/sleep/offline operation can delay execution; recovery must always be re-read. Missing reset => unsupported scheduling plus manual user action. Missing or blank account/profile/window identity, stale readings or changed resources cannot establish recovery.

The supported account-limit adapter hashes the observed account ID into a private fingerprint for both single-profile and multi-profile configurations. Missing identity may still trigger conservative preservation but cannot establish readiness.

Ticket fields include project/task identity, stable stop incident, required account/window keys, `not_before`, schedule status, scheduler kind/ID, lifecycle status and notification receipt. The file is private task state and is not copied as a live schedule to another device. It is notification state, not an implementation queue.

Record completion/cancellation/transfer before leaving the source device:

```sh
python3 SKILL/scripts/readiness.py --root PROJECT lifecycle --status transferred --reason 'Verified explicit transfer to destination; source writer stopped'
```

Other statuses: `completed`, `canceled`, `resumed`, `active`. These are records of actual reviewed actions, not a way to claim they happened. New work requires its own current lifecycle review; never reactivate a canceled task implicitly. A cleared stop or newer resume retires an obsolete ticket. Unknown jobs or a newer owner block a ready claim.

For a manual check using already collected fresh sourced signals:

```sh
python3 SKILL/scripts/readiness.py --root PROJECT check --signals SIGNALS --notifier unsupported
```

Using `--notifier macos` authorizes that invocation to try a native notification after all gates pass. Automatic notification needs the opt-in configuration and an actual collector. On an unsupported host: read `HANDOFF.md`, check the account allowance again, then tell the agent `Resume from HANDOFF.md`. Never infer readiness solely from wall-clock time.

At most one notification attempt is made per incident. The runtime records delivery intent before calling the adapter. A crash stays `delivery-uncertain`; a failed command stays `delivery-failed`. Inspect these states and notify manually if needed; do not delete the ticket to retry blindly. An accepted command does not prove native display.

Automatic preservation is bounded to three failed attempts. After repairing the underlying storage/content problem, explicitly permit a new bounded attempt sequence:

```sh
python3 SKILL/scripts/readiness.py --root PROJECT retry-preservation --owner OWNER --reason 'Verified disk space and repaired denied path for preservation retry only' --source 'Current user authorized preservation retry'
```

Use the exact current owner with a matching local lease receipt. If the ownership
ledger and receipt are both vacant, replace `--owner OWNER` with the explicit
`--vacant-owner` option. Retry never acquires, releases or replaces a lease.
An active/uncertain worker, foreign task/lifecycle/journal, corrupt prior
checkpoint, occupied collector/writer fence, or missing authorization blocks it.
Only an incomplete stop with one to three recorded attempts may reset; an unused
retry grant and a verified checkpoint cannot be renewed this way.

The command resets only the failed preservation counter and appends its repair
authorization to the stop. The existing collector may make up to three further
save attempts; this command neither installs a collector nor performs a save.
It retains the stop, prior checkpoint, permissions, reserve and resume state.
Uncertain jobs may be captured as uncertain for preservation, but retry never
resumes or duplicates them. Explicit reviewed resume still requires reconciliation.
On failure provide the compact emergency handoff specified in SKILL.md. No save
can reconstruct semantic state that was never maintained.

## Verify visible display separately

An explicit native display test may invoke the same macOS adapter with a clearly
labeled test message that claims no task recovery or resume. Record command
acceptance and actual visual/user confirmation separately. Do not fabricate a
healthy account reading, alter reset times, clear a ticket, grant OS permission or
disable Focus just to obtain a notification. A user-confirmed display test verifies
that observation, not future scheduler delivery or timing. This host's adapter was
visibly confirmed by the user during 0.7.4 verification; no permission was changed.

## Recovery must remain reachable

A persistent stop blocks ordinary tools, not context compaction. PreCompact emits
an informational stop reminder without continue:false and never advances the
pinned checkpoint or grants resume authority. This lets the owning chat read
maintenance instructions after compaction. PreToolUse still denies ordinary work.

Before the first verified checkpoint, maintenance status reports a missing
generation and semantic input explicitly; it does not invent progress or acquire
a lease. An authorized repair workspace can reconstruct factual input from
current evidence, verify jobs and existing ownership, then request bounded
preservation retry. Missing input is highlighted on every SessionStart, including
existing auto-enrolled bindings. Resume still requires a verified generation,
fresh resources, current authorization and the normal ownership gate.
