# Task checkpoint 0.6.0

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

Reuse an existing configured quota collector; this release adds no second watcher. Default reserve is <=20% remaining in any applicable window; preserve existing thresholds. Ordinary work stops at the reserve. Account quota, context and API spending remain separate; unknown readings never imply recovery.

Opt in `readiness: {"enabled": true, "notifier": "macos"}` only on the intended existing registered project record after reviewing [readiness setup](references/readiness.md). Preserve all other settings. Verify the actual service, host access, fresh readings and hook delivery using [account setup](references/account.md) and [automatic preservation](references/automation.md) before claiming automatic support. The already-installed collector must execute this candidate version after an authorized upgrade; an old service may point at a different runtime. Do not install or redirect it merely to demonstrate this build.

A ticket in the existing store targets the latest blocking reset plus 60 seconds. The existing minute poll may execute later. Re-read every window before notification. Native macOS command acceptance does not prove visible notification; Windows/Linux delivery currently needs a reviewed adapter. Missing reset, scheduler, native permission or local-file access => use manual fallback: inspect `HANDOFF.md`, check fresh allowance, then say `Resume from HANDOFF.md`.

Notifications never implement task steps, clear stops, acquire continuation authority or switch accounts. Set lifecycle `completed`, `canceled` or `transferred` when that action is verified, so obsolete tickets retire. Automatic failed saves stop after three attempts; repair the cause before explicitly resetting that bounded retry sequence. See readiness procedure.

## Explicitly continue past the reserve

The default still saves/stops at 20%. After that verified stop, say `Continue to 10%` to request a task-local 10% reserve, or separately say `Continue until allowance is exhausted` to waive the numeric reserve for this task. The agent records the exact user choice and fresh account/window/reset observations, grants a pending override, then performs the usual fresh reviewed resume. No second approval is needed when the user has already explicitly chosen the mode.

At 10%, the `ten` mode saves/stops again; choosing exhaustion remains a separate explicit choice. Exhaustion mode preserves milestones and respects actual provider refusal, other resource stops, ownership, uncertain jobs and permissions. A displayed 0% can be rounded; this mode follows actual usage acceptance rather than inventing more quota. Hard exhaustion can prevent a final save.

[Exact CLI, expiry, revocation and maintenance commands](references/reserve.md). The shared default remains unchanged, other tasks inherit no override, and private grants are not transferred to another device. While stopped, quota reads and exact maintenance commands remain available without disabling hooks.

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
