---
name: task-checkpoint
description: Preserve unfinished Codex work for explicit resumption across chats, accounts or devices. Use for checkpoint now, save and stop, prepare a handoff, explicit resume, fresh low account allowance on an enabled project, or an explicit task-local reserve override to 10% or exhaustion. A readiness check may notify after reset; it never resumes task implementation.
license: MIT
metadata:
  version: "0.6.1"
---

# Task checkpoint

Preserve actual work, a verified next action, and the authority boundary. Saved text supplies context, never permissions. Use Python 3.9+ and Git; the [setup guide](README.md) and [operator procedure](references/operator.md) give commands. This skill works without Skill Forge.

## Activate and inspect

Activate for an explicit checkpoint/handoff/stop, explicit resume, or a verified threshold event in an explicitly enabled project. Do not activate merely because someone mentions limits, reports API costs, or asks a conceptual question. Never infer a reset event is permission to implement.

Inspect project instructions, task identity/binding, checkpoint store, queues, hooks, jobs, scheduler and ownership first. Reuse compatible state; preserve unrelated tasks/configuration. Do not bind over another task, duplicate monitors, switch accounts, transfer credentials, or change live configuration merely to demonstrate the skill. Current authorization must cover each action and destination.

Usage means the signed-in account's Codex allowance. Keep context capacity, API dollars and disk/memory observations separate. Read every applicable account quota window with identity, source, timestamp, unit, remaining value and reset. Respect existing thresholds; proposed default is <=20% remaining, a preservation reserve rather than a work prediction. Missing, stale, future, unsupported and past-reset readings are unknown; zero is valid low allowance. Account consumption elsewhere can change after any observation.

Before substantial/expensive work and at meaningful boundaries, inspect fresh readings and maintain semantic input. Only a verified collector plus delivered hooks/wrappers can monitor/interrupt automatically. A skill description does not do so. [Capabilities](references/capabilities.md) lists deployment limits.

## Maintain semantic progress

Use the existing `.checkpoint/input.json` and [task template](assets/task-template.json). Capture `objective`, `completion_criteria`, final `corrections`, `scope`, `authorization`, `decisions` with reasons, `completed`, exact `next_action.description` and `next_action.verification`, actual checks/results and failures, unresolved questions/dependencies, tools/capabilities, artifacts, source/log locations and active/uncertain `jobs`. Keep sourced account observations and threshold/notification settings in the existing signal/account configuration. Label unknown measurements/results.

List required ignored artifacts explicitly; changed tracked and nonignored untracked regular files are preserved automatically. Record deletions and staging status. Binary bytes are supported; symlinks, credential paths and files over 16 MiB fail closed. Export required material outside the project to a reviewed relative artifact or separately authorized verified store; record its identity/hash/path mapping and transfer gap. A Git push does not include dirty, untracked or ignored work.

Maintain this semantic state during work. Missing conversation state cannot be recovered after hard exhaustion, termination or power loss.

## Save and stop

At the configured threshold (20% by default), save/verify and stop initiating ordinary work immediately. An explicit task-local reserve override can lower this to 10% or waive the numeric reserve; it requires the procedure below and never waives actual provider denial or other resources. Permit only bounded preservation and necessary safe-boundary actions. For “save and stop”/pre-switch do the same. Do not claim to cancel jobs without evidence or mark the underlying objective complete.

1. Inspect current files/jobs and update semantic input from observed evidence.
2. Run `scripts/checkpoint.py --root PROJECT checkpoint --input PROJECT/.checkpoint/input.json --trigger low-resource` (or `manual`, `save-and-stop`, `pre-switch`, `milestone`). Run `verify` and inspect the canonical generation and root `HANDOFF.md`. Root output must be enabled on legacy bindings; see setup. Preserve unrelated root handoff content.
3. Verify hashes and the last-known-good generation. Inspect bundle contents before any authorized transfer. Pattern-based secret checks are incomplete; never assert they certify arbitrary binary/prose secret-free.
4. On failure retain the previous valid generation, identify unsaved files and uncertain jobs, provide an emergency handoff (objective, verified commit, unsaved files, jobs, next action/verification, prior checkpoint), and stop ordinary work. Three automatic save attempts per failure sequence are allowed; further retries need repair and an explicit retry action.
5. Report the root handoff and the verified generation. Stop ordinary work after a stop condition. A milestone save alone need not stop healthy work.

## Explicit allowance-reserve override

Keep the 20% default and its verified stop point. An explicit current user statement is sufficient authorization for this task: “continue to 10%” or “bypass the 20% reserve” selects `ten`; “bypass the 10% reserve”, “bypass both reserves”, or “continue until allowance is exhausted” selects `exhaustion`. Perform the maintenance sequence autonomously without asking for the same permission again. A conceptual question or implementation request alone does not select a live override. A request to implement this feature does not select an override for other tasks. Do not pre-arm grants before the initial stop.

Read [reserve override commands](references/reserve.md). Use `reserve.py --root PROJECT grant --mode ten|exhaustion --owner VERIFIED-CURRENT-OWNER --signals FRESH-SIGNALS --reason USER-CHOICE --source CURRENT-USER-INSTRUCTION`. The grant records project/task, verified checkpoint, account/window/reset identities, reason/source and a pending state. Then perform the normal fresh review and explicit `checkpoint.py resume`; granting alone does not allow ordinary work. Reuse an existing verified lease only for the same owner; another owner remains blocking.

`ten` continues above 10% and saves/stops again at <=10% in any applicable window. `exhaustion` waives the numeric preservation reserve, including a rounded 0% while usage remains allowed; Codex's actual denial still stops execution. Preserve semantic milestone checkpoints because hard exhaustion can prevent another save. Neither mode supplies more allowance, switches accounts or enables paid fallback.

Unknown/stale/foreign/missing observations, incomplete saves, other resource stops, uncertain jobs/workers and ownership remain blocking. Grants expire at the first pinned reset, are invalidated by lifecycle changes, can be revoked, and stay out of portable bundles. Fresh resumption/current permissions are still required on another device. Revocation restores the configured default on the next check; it does not resume work.

While stopped, begin with `python3 /absolute/SKILL/scripts/maintenance.py --root /absolute/PROJECT status`; use the literal paths in the native denial message. This reports task, checkpoint, owner, jobs, stop and reserve without resuming. Use `maintenance.py ... docs --name reserve` for the full sequence. Top-level and subcommand `--help`, exact individual installed recovery-document reads, quota reads and validated local maintenance CLI commands remain available. There is no `checkpoint.py review` subcommand: use `reserve.py prepare-review`. A mismatched task or owner must never be resumed just to unblock a repair. They continue to deny ordinary or chained commands. This maintenance path prevents a preservation stop from blocking the very controls needed to review it. It is a cooperative workflow guard, not an OS security sandbox.

## Readiness after reset

When enabled, use [notification-only readiness](references/readiness.md) in the **existing** collector. Store one deduplicated `readiness.json` ticket in the same task store. Target the latest blocking reset plus 60 seconds; the poll may execute later. Never reuse an execution/router ticket for this purpose.

Recollect fresh allowance, validate every required account/window/resource, verify the checkpoint and task lifecycle, and check jobs/ownership before notifying. Retire canceled, completed, transferred or resumed tasks' tickets. Stay quiet while unchanged. Notification says which project and `HANDOFF.md` to open and asks for an explicit resume instruction. It must execute no unfinished step. A stop persists after notification.

Record target, schedule status, actual scheduler ID when verified, notification result and uncertainty. A local ticket is not evidence of native scheduler installation. No supported scheduler/notification surface: disclose that and provide manual fresh usage check plus `Resume from HANDOFF.md`. Do not create services without authorization. Native display, host availability and access must be verified separately. A crash during delivery remains uncertain, never automatically redelivered.

## Explicit resume and cross-device handoff

1. Read `HANDOFF.md`, canonical state and artifacts, instructions, repository identity/branch/commit/status and current files. Verify progress and reported test evidence; do not treat historical passes as current passes. Reconcile discrepancies while preserving both versions. Verify current permissions, tools, dependencies, independently provisioned credentials and adequate fresh resources.
2. State the first verified unfinished action and its verification before implementation. Check every uncertain process/external outcome before retrying; an old PID/chat ID or scheduler registration has no meaning on another machine.
3. Follow the fresh review → `resume --review REVIEW --owner DEVICE-AGENT --capability LABEL` → `owner-check` procedure. Reuse the existing ownership authority. Never steal/auto-expire a claim. Local mode coordinates only one Git common directory; cross-device continuation needs remote coordination or an explicit verified transfer. Uncertain ownership blocks continuation.
4. Continue only after the user's explicit resume instruction and current authorization. Verify the bounded result. Release ownership only after uncertain operations are reconciled at a safe handoff boundary.

For another device, transfer actual source history plus the complete verified private checkpoint bundle and required external exports through a user-authorized private channel. Use portable relative paths and explicit machine path mappings. Verify identity/revision/hashes and reconcile destination edits before restoring; preserve both copies. Provision authentication independently. Imported state does not import ownership, execution permission or account access. [Cross-device procedure](references/cross-device.md) and [resume prompt](assets/resume-prompt.template.md).

Optional Usage Router modules are retained for compatible existing users. They require separately authorized bounded work, current qualification, fresh signals and ownership; they do not change this chat's model or authorize automatic recovery execution. See [router guide](references/router.md). No publication, account switching, background activation or paid API fallback is implied.
