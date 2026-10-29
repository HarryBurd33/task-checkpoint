# Task checkpoint 0.7.6

Version 0.7.6 routes same-owner stopped checkpoint saves through the existing fenced preservation path, keeping the stop and saved generation aligned. Raw snapshots and rewinding away from a pinned stop fail closed. Saving never resumes work or replaces ownership.

Version 0.7.5 keeps context compaction reachable during a pause, diagnoses a missing first checkpoint through read-only maintenance, and reminds existing bindings to maintain semantic input. Ordinary tools still require explicit reviewed recovery.
Use `maintenance.py --root PROJECT handoff` for the verified canonical handoff
while paused. Clarification tools remain available. After a prior stop was
acknowledged, normal `prepare-review --signals ACCOUNT-STATE/signals.json` selects
only an existing enabled collector registered to this task; quota windows and
reserves are rechecked at resume. See the [reserve procedure](references/reserve.md).

Version 0.7.4 adds explicit recovery of missing managed hook receipts from exact
installed definitions, separates hook registration from collector health, and
records delivery before task enrollment. Account maintenance leaves unbound repair
contexts unbound. Native hook trust and OS notification permissions are unchanged.

Version 0.7.3 supports normal recovery with fresh collector readings and explicit
reviewed resume, observation-only collection without dispatch or transfer, and
owner-aware bounded preservation retry. Stops, ownership and native permissions
remain in force. See the [0.7.3 verification report](https://github.com/HarryBurd33/task-checkpoint/blob/main/docs/RELEASE-0.7.3.md).

Preserve unfinished work before account allowance runs low. Verify the saved work in a new context, account or device, then continue only after an explicit resume instruction. Install this directory per-user to make the workflow available in local Codex chats. Background collection and notifications require separate opt-in configuration. Installing the skill never switches accounts.

Python 3.9+ and Git are required. No third-party Python packages or model/API calls are required for save/verify/readiness logic. Manual save/resume remains useful without automatic collection or scheduling. Start with [SKILL.md](SKILL.md), [capabilities](references/capabilities.md), and [validation](VALIDATION.md).

## Install the skill, without background activation

From this delivered directory, inspect the source and use the managed installer:

```sh
python3 install.py --skills-dir "$HOME/.agents/skills" --status
python3 install.py --skills-dir "$HOME/.agents/skills" --repair
```

`--repair` is an idempotent install/upgrade and refuses customized/unmanaged copies. It backs up an unchanged prior managed version under `.task-checkpoint-rollback/` beside the skills directory. Installation alone does not install a service or trust hooks. Do not add `--project` if an existing global hook integration already covers the project. The installer does not change native hook trust.

Set the following command variables to reviewed absolute paths (examples use placeholders):

```sh
skill_dir="$HOME/.agents/skills/task-checkpoint"
project_dir="/absolute/path/to/project"
```

## Automatic enrollment and chat scope

Automatic enrollment is a separate opt-in in the existing account registry.
Use `scripts/enrollment.py --state ACCOUNT-STATE configure --enabled true`, with
repeated `--exclude-root PATH` and `--exclude-session CHAT-ID` options as needed.
Delivered `SessionStart`/`PreToolUse` hooks enroll eligible committed Git roots
only when a stable host thread identity is available. An unborn Git repository or busy collector defers enrollment without a task
pause. Eligible roots receive an ignored `.checkpoint` binding and collector registration; they do not schedule execution,
acquire ownership, invent semantic input or install another service.

Existing task bindings remain unchanged. A reviewed `bind-chat` mapping records owning and explicitly unrelated chats.
Only recorded unrelated chats avoid inheriting an existing task stop. Native hook
`session_id` identifies the current root chat, including subagent hooks; explicit
event `thread_id` is accepted when no session ID is supplied. Conflicting host
fields fail closed, and inherited `CODEX_THREAD_ID` is ignored. Unknown IDs and
legacy mappings retain conservative behavior. A recorded
unrelated chat needs a separate checkout for its own checkpoint; a new same-task
continuation cannot bypass its existing stop. Exclusions affect new enrollment, not existing stops.
[Exact setup and repair procedure](references/enrollment.md).

## Bind and save

Inspect project instructions, Git status, existing `.checkpoint/config.json`, queues, hooks and ownership first. Do not initialize over an existing binding. Ensure `.checkpoint/` is ignored by Git and an initial commit exists. For a new task binding:

```sh
python3 "$skill_dir/scripts/checkpoint.py" --root "$project_dir" init --task YOUR-TASK --project-id YOUR-PROJECT
```

The default ownership uses an existing remote Git authority and never force-pushes. If no remote coordination exists, explicitly choose `--ownership local` for a single-machine task; this cannot coordinate another laptop. Do not change ownership mode to bypass a claim.

Copy `assets/task-template.json` into the existing store's `input.json` and fill the semantic fields from observed work. Record actual test commands/results and checks not run in `observations`, failures in `failures`, and ordered continuation outcomes in `decisions`/`next_action`; do not invent passes. Include required ignored artifacts explicitly.

```sh
python3 "$skill_dir/scripts/checkpoint.py" --root "$project_dir" checkpoint --input "$project_dir/.checkpoint/input.json" --trigger save-and-stop
python3 "$skill_dir/scripts/checkpoint.py" --root "$project_dir" verify
python3 "$skill_dir/scripts/checkpoint.py" --root "$project_dir" inspect
```

New bindings enable detailed root `HANDOFF.md`. For an existing 0.5.0 binding, first verify its current generation, then explicitly migrate the root output:

```sh
python3 "$skill_dir/scripts/checkpoint.py" --root "$project_dir" enable-root-handoff
python3 "$skill_dir/scripts/checkpoint.py" --root "$project_dir" verify
```

Existing unrelated handoff text survives. Managed sections carry identity/digests; manual changes fail closed. Following a verified incoming adoption or a detected stale projection, preserve the old root version and run `refresh-handoff` explicitly. Do not discard a tampered section or conflicting user text blindly. Root and canonical pointer are separate atomic files: a crash between them can leave a detectable stale projection. Ordinary publication failure rolls back the prior root and preserves the valid pointer.

## Automatic threshold and readiness

Reuse an existing configured quota collector; this release adds no second watcher. Default reserve is <=20% remaining in any applicable window; preserve existing thresholds unless the user explicitly chooses a task-local percentage. Ordinary work stops at the reserve. Account quota, context and API spending remain separate; unknown readings never imply recovery.

Opt in `readiness: {"enabled": true, "notifier": "macos"}` only on the intended existing registered project record after reviewing [readiness setup](references/readiness.md). Preserve all other settings. Verify the actual service, host access, fresh readings and hook delivery using [account setup](references/account.md) and [automatic preservation](references/automation.md) before claiming automatic support. The already-installed collector must execute this candidate version after an authorized upgrade; an old service may point at a different runtime. Do not install or redirect it merely to demonstrate this build.

A ticket in the existing store targets the latest blocking reset plus 60 seconds. The existing minute poll may execute later. Re-read every window before notification. Native macOS command acceptance does not prove visible notification; Windows/Linux delivery currently needs a reviewed adapter. Missing reset, scheduler, native permission or local-file access => use manual fallback: inspect `HANDOFF.md`, check fresh allowance, then say `Resume from HANDOFF.md`.

Notifications never implement task steps, clear stops, acquire continuation authority or switch accounts. Set lifecycle `completed`, `canceled` or `transferred` when that action is verified, so obsolete tickets retire. Automatic failed saves stop after three attempts; repair the cause before explicitly resetting that bounded retry sequence. See readiness procedure.

## Choose a task-local reserve

The default is 20% remaining. Before work, the user may choose any finite
remaining percentage from 0 through 100, including fractions. Offer a choice
when it would help; do not require users to know the commands. Execute a clear
current choice without asking for the same permission again.

`reserve.py ... configure --percent N --owner OWNER --reason REASON --source SOURCE`
sets the initial task baseline using its exact verified owner lease. It rejects
existing automatic stops, uncertain jobs/workers and pending or active grants.
The shared collector reserve and existing resume authority remain unchanged.

After a verified stop, use a pending `--mode percent --percent N` grant followed
by the usual fresh review and explicit resume. `ten` remains shorthand for 10%.
Numeric 0% stops at measured zero; only separately explicit `exhaustion` waives
the numeric reserve. Actual provider refusal, other resources, unknown readings,
ownership and uncertain jobs always remain enforced. Hard exhaustion can prevent
a final save, so maintain semantic milestones.

[Exact CLI, expiry, revocation and maintenance commands](references/reserve.md).
Initial policies and grants stay out of portable bundles. After a normal owner
release, explicit `retire-policy` archives the prior policy under verified vacant
ownership before fresh reviewed resume. It cannot clear stops or uncertain work.
While stopped, quota
reads, named instructions, help and exact maintenance commands remain available.
Native `Bash` and `exec_command` names use the same strict argument checks;
ordinary work and chained shell commands remain blocked for the stopped task.

## Inspection and collector behavior

Untracked nested repositories appear as unsaved artifact boundaries in inspection.
Checkpoint creation refuses to represent them as preserved files; preserve them
separately or explicitly exclude them. Collector quota refresh survives optional
transfer dependency failures and reports project preservation errors separately.
Affected dispatch remains blocked. Python 3.9 is supported; see the versioned
validation report for actual interpreter and native-host evidence.

## Resume and transfer

Natural invocations: `Checkpoint now`, `Save and stop`, `Prepare a handoff for another laptop`, and `Resume from HANDOFF.md`.

A conceptual question such as “What do Codex usage limits mean?” does not start a checkpoint or activate background monitoring. A scheduled recovery event allows only readiness verification/notification.

For explicit resume, read and verify the handoff, current instructions/files, exact source revision and artifacts, prerequisites, current authorization, fresh resources, jobs/external outcomes and exclusive ownership. State the first unfinished action and verification before writing. Create a fresh review following [operator procedure](references/operator.md), then run `resume`, `owner-check`, bounded work, validation, and `release` at a verified boundary. Saved text grants no permissions.

[Cross-device instructions](references/cross-device.md) cover source Git/history, dirty snapshots, binary/untracked/ignored files, external exports, integrity, independent credentials, path mappings and conflicts. HANDOFF.md alone is insufficient. No live schedule, PID, source account permission or owner token transfers.

## Disable, rollback and uninstall

Disable readiness by setting only the intended registered project's `readiness.enabled` to false. It retires its ticket on the next collector tick and leaves preservation/other projects intact. To disable automatic preservation separately, follow the existing collector guide; retain current stop/state and reconcile any active worker first. Manual checkpointing still works.

To roll back, retain private state, preserve root HANDOFF.md and any customizations, and inspect the installer-produced prior ZIP. Uninstall the unchanged managed candidate, extract the prior version into the skills directory (retaining its receipt), and verify metadata/hashes. If a new binding has `root_handoff:true`, remove that flag only after preserving the root output and verifying the old runtime's compatibility; old runtimes do not validate the new projection. Never delete private checkpoints or change ownership to make rollback appear successful. An existing native service/hook must point to the restored reviewed runtime before reuse; reconcile active/uncertain workers first.

```sh
python3 install.py --skills-dir "$HOME/.agents/skills" --uninstall
```

This removes only the unchanged managed skill and retains checkpoints. If automatic activation was separately authorized, first remove the unchanged managed native service with `scripts/monitor.py --state ACCOUNT-STATE uninstall-service`, then remove owned account hooks with `scripts/account.py --state ACCOUNT-STATE uninstall --codex-home CODEX-DIRECTORY`. Preserve unrelated hooks and trust records. Do not run these commands on an unrelated installation merely to remove this staged folder. A staged folder may simply be retained or deleted after review.

MIT license and [source attribution](ATTRIBUTION.md) are included. Validation distinguishes static, deterministic, fresh-model and native evidence; prior release claims are historical.
