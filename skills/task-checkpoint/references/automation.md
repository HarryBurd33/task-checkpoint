> Historical compatibility reference inherited from v0.5.0. For this candidate, current SKILL.md, README.md, readiness.md and capabilities.md control activation, delivery and validation claims. No publishing, installing services, changing accounts or resuming after recovery is implied.

# Automatic usage checkpoints on macOS and Windows

The system has one account/profile collector, one project registry, and the existing per-project checkpoint store. `account.py tick` reads supported Codex allowance signals without starting a model turn, then calls `monitor.evaluate_registered` **before** checking any separately authorized routing schedules. It polls every 60 seconds through launchd on macOS or Task Scheduler on Windows. This is a real OS trigger, not an instruction to remember to run a command.

## What happens automatically

For each explicitly registered project, fresh readings at or below its configured remaining-allowance reserve cause a durable `.checkpoint/automatic-stop.json` request, then a schema-validated checkpoint, human-readable HANDOFF.md, artifact backups and manifest readback. The atomic latest pointer retains its prior valid generation. Only a verified save is reported as verified; failed saves keep the stop request and preserve the previous checkpoint. A failing project does not prevent other registered projects from saving.

Repeated low readings and percentage decreases do not duplicate an unchanged snapshot. Changed input, repository contents or active-worker identity can cause a new preservation save. Active workers are recorded as needing verification; the monitor does not kill them, release ownership, restart work, switch models or push private state to GitHub.

Covered trusted hooks deny/stop ordinary work when the persistent stop request exists. Explicit resume requires fresh recovery of every affected resource kind, current artifact/Git checks, a fresh authorization/review, and the existing task lease. Resource recovery never resumes the task automatically. Stop requests are archived only after the successful explicit resume gate and a final serialized recovery recheck.

The handoff uses the last agent-maintained `.checkpoint/input.json`. If missing, the last valid checkpoint's task is used with an explicit stale-semantic-source label. If neither is available, preservation fails visibly; no objective or next action is invented. Keep semantic input current at meaningful milestones. Files and logs created after the last maintained semantic state can be preserved, but new conversation-only decisions cannot be reconstructed by a background script.

New account setups default to **20% remaining**, equivalent to 80% used, checked once per minute. Existing configured thresholds are retained; the current Mac activation uses the explicitly authorized **20% remaining** reserve. Change `guard_percent` in the private account config when you want a different reserve. Each account window keeps its own reset. Context tokens, API dollars and account allowance remain distinct; unsupported/stale/future/reset readings are unknown and do not fabricate a low or recovered balance. Every affected resource must have fresh adequate evidence before explicit resume.

## Register a project

First initialize or resume the project's existing checkpoint binding using the ordinary operator procedure. Do not reinitialize a transferred binding or create another task database. Confirm it has valid task input and at least one verified generation. From an installed skill, use the actual Python executable:

```sh
python3 SKILL/scripts/account.py --state ACCOUNT-STATE install --codex-home CODEX-HOME --project PROJECT
```

The registry entry binds the absolute device-local root to the exact existing project/task IDs. Changed or unavailable bindings fail rather than create a replacement task. On another laptop, register the new local root independently. Source Git and the entire private checkpoint bundle still need deliberate transfer; automatic local preservation is not automatic cross-device synchronization. A transferred stop request is rebound to the new device's account state when its exact registered binding is successfully evaluated.

The collector must use the same independently authenticated Codex profile as the local session. Do not copy credentials between devices, combine different accounts' allowance readings, or reuse Mac absolute paths on Windows. Inspect existing hooks and scheduler registrations; customized entries require reconciliation.

## macOS activation and status

The account installer prepares the owned `com.checkpoint-handoff.codex` LaunchAgent. Installation preserves the prior Herdr/global hooks and requires normal native `/hooks` review for new definitions. The threshold writer itself runs from the OS collector even if a model is idle; stopping model/tool work additionally depends on the actual trusted covered hook/wrapper path.

```sh
python3 SKILL/scripts/monitor.py --state ACCOUNT-STATE install-service
python3 SKILL/scripts/monitor.py --state ACCOUNT-STATE status
```

Scheduler registration alone is not verification. After the next minute, check that both `status.json` and `monitor-status.json` have recent timestamps, the intended profile was used, and the registered project list is correct. Inspect each project result too: a healthy collector or recent timestamp alone does not prove project preservation. macOS may deny a LaunchAgent access to Documents until the corresponding native permission is granted; report that block and use the trusted in-session boundary/manual fallback meanwhile. Do not bypass TCC or silently grant broader access. If macOS only offers Full Disk Access for the responsible process, explain its broader scope and let the user decide through native settings. A required app restart may be deferred while other tasks run; keep background project access unverified until a successful retry. A real low threshold can then preserve registered tasks without a model request. Do not deliberately exhaust real allowance just to test it; use isolated simulated readings for threshold tests.

## Windows setup

Install Git, Python 3.9+ and supported Codex CLI; authenticate on Windows. Clone/update the existing checkpoint-handoff repository and install the current managed skill. Preserve customized managed copies and follow the documented uninstall/upgrade path before replacement.

In PowerShell, replace `C:\Projects\MY-PROJECT` with the actual transferred project. The default state belongs to the default `.codex` profile; use the correct profile directory when different.

```powershell
$checkpointScripts = "$HOME\.agents\skills\task-checkpoint\scripts"
$checkpointState = "$HOME\.codex\checkpoint-handoff"
py -3 "$checkpointScripts\account.py" --state $checkpointState install --codex-home "$HOME\.codex" --project "C:\Projects\MY-PROJECT"
py -3 "$checkpointScripts\monitor.py" --state $checkpointState install-service
py -3 "$checkpointScripts\monitor.py" --state $checkpointState status
```

The Windows installer uses the actual Python executable, current-user `InteractiveToken`, least privilege, a one-minute repeating trigger, non-overlapping instances and battery-compatible settings. It stores no password and does not elevate or run as SYSTEM. It runs while that user is logged in and the laptop is awake; it does not monitor a powered-off/asleep laptop. Source template/argument and scheduler failure-injection tests on Mac are **simulated Windows checks**. Only a fresh Windows scheduler tick plus an isolated save/readback demonstration establishes native deployment success. Native deployment was observed on 2026-10-26: real one-minute ticks collected account readings, saved a synthetic-context fixture, deduplicated unchanged state and retained the stop after recovery until an explicit reviewed resume. The fixture lease and registration were removed. All seven native hook definitions were trusted and native Stop delivery was observed. This required the redirected scheduler XML encoding fix and collector-local Git discovery. The intended Mac bundle was not transferred, so production project resumption remains unverified.

If native hooks are used, review Windows-compatible handler commands and trust the exact definitions through Codex `/hooks`. A skill installation or scheduler registration does not grant that trust. Hosted tools and some specialized paths bypass lifecycle hooks; arbitrary editors are outside this cooperative enforcement. No implementation can save conversation state after hard exhaustion or power loss, so retain the reserve and milestone saves.

## Failures, recovery and uninstall

Unknown telemetry produces an unknown status, never a made-up percentage. A previous stop persists until fresh recovery and explicit resume. Check private `last-error.json`, `monitor-status.json`, `automatic-stop.json` and the scheduler's own status. If saving is denied/full/corrupt, stop ordinary work, preserve the prior generation, repair the underlying cause and let the next tick retry. Do not delete stop/ownership/lock files merely to continue. A stale writer lock requires verification that the originating process has ended, just as in the main operator procedure.

Service installation holds the collector fence, checks active router work, records a durable transaction and rolls back failed registration to the prior owned service. It refuses unmanaged/customized scheduler definitions. A failed rollback is reported for manual reconciliation; it is not labeled successful removal. Do not restart a service with active or uncertain routed work.

```sh
python3 SKILL/scripts/monitor.py --state ACCOUNT-STATE uninstall-service
```

This removes the unchanged managed scheduler, restores a prior owned macOS service where recorded, disables the background threshold writer, and retains all private checkpoints and stop history. Existing native hooks remain under native trust controls. It does not cancel workers, remove credentials, delete queue databases or delete the repository. For a complete uninstall, also follow the account/skill uninstall procedure and preserve private state first.

References: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Codex app server](https://learn.chatgpt.com/docs/app-server), [Windows scheduler creation](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks-create), [Task Scheduler schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema). Documentation checked 2026-10-25; the native Windows fixture was verified on 2026-10-26. This does not verify any untransferred production bundle or every lifecycle event.
