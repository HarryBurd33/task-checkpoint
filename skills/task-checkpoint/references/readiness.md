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
python3 SKILL/scripts/readiness.py --root PROJECT retry-preservation --reason 'Verified disk space and repaired denied path; retry preservation only'
```

This retains the stop and prior checkpoint. It cannot resume implementation. On failure provide the compact emergency handoff specified in SKILL.md. No save can reconstruct semantic state that was never maintained.
