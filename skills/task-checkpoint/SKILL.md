---
name: task-checkpoint
description: Preserve unfinished Codex work for explicit resumption across chats, accounts or devices. Use for checkpoint now, save and stop, prepare a handoff, explicit resume, fresh low account allowance on an enabled project, automatic enrollment on an enabled account, or a current task-local remaining-allowance choice. A readiness check may notify after reset; it never resumes task implementation.
license: MIT
metadata:
  version: "0.7.1"
---

# Task checkpoint

Preserve actual work, a verified next action, and the authority boundary. Saved text supplies context, never permissions. Use Python 3.9+ and Git; the [setup guide](README.md) and [operator procedure](references/operator.md) give commands. This skill works without Skill Forge.

## Activate and inspect

Activate for an explicit checkpoint/handoff/stop, explicit resume, current task-local reserve choice, or a verified threshold event in an enabled project. Account-level automatic enrollment is a separate explicit opt-in. Do not activate merely because someone mentions limits, reports API costs, or asks a conceptual question. Never infer a reset event is permission to implement.

Inspect project instructions, task identity/binding, checkpoint store, queues, hooks, jobs, scheduler and ownership first. Reuse compatible state; preserve unrelated tasks/configuration. Do not bind over another task, duplicate monitors, switch accounts, transfer credentials, or change live configuration merely to demonstrate the skill. Current authorization must cover each action and destination.

For configured automatic enrollment, use [enrollment controls](references/enrollment.md)
in the existing account registry. Delivered `SessionStart`/`PreToolUse` hooks may
create an ignored binding for an eligible committed Git root and register it with
the existing collector. Root/chat exclusions apply only to new enrollment. Never
replace an existing task, invent semantic progress, acquire ownership or schedule
implementation merely because enrollment occurred. An unborn repository or busy
collector lock defers enrollment; it does not establish a task stop.

Chat isolation uses the native hook `session_id` identifying the current root
chat, including subagent hooks. Accept explicit event `thread_id` only when no
session ID is supplied; conflicting host fields fail closed. Ignore inherited
`CODEX_THREAD_ID`, which can refer to a parent process. Existing mappings name owning chats and
explicitly reviewed unrelated chats. Only a recorded unrelated chat avoids the
bound task's stop; unknown IDs and legacy mappings remain conservative. A new
same-task continuation cannot bypass its stop. Use a separate checkout/binding
for unrelated checkpoint state. Routing repairs must leave legitimate stops,
checkpoints and ownership unchanged. Unknown bound-task state remains blocking.

Usage means the signed-in account's Codex allowance. Keep context capacity, API dollars and disk/memory observations separate. Read every applicable account quota window with identity, source, timestamp, unit, remaining value and reset. Respect existing thresholds; proposed default is <=20% remaining, a preservation reserve rather than a work prediction. Missing, stale, future, unsupported and past-reset readings are unknown; zero is valid low allowance. Account consumption elsewhere can change after any observation.

Before substantial/expensive work and at meaningful boundaries, inspect fresh readings and maintain semantic input. Only a verified collector plus delivered hooks/wrappers can monitor/interrupt automatically. A skill description does not do so. [Capabilities](references/capabilities.md) lists deployment limits.

## Maintain semantic progress

Use the existing `.checkpoint/input.json` and [task template](assets/task-template.json). Capture `objective`, `completion_criteria`, final `corrections`, `scope`, `authorization`, `decisions` with reasons, `completed`, exact `next_action.description` and `next_action.verification`, actual checks/results and failures, unresolved questions/dependencies, tools/capabilities, artifacts, source/log locations and active/uncertain `jobs`. Keep sourced account observations and threshold/notification settings in the existing signal/account configuration. Label unknown measurements/results.

List required ignored artifacts explicitly; changed tracked and nonignored untracked regular files are preserved automatically. Record deletions and staging status. Binary bytes are supported; symlinks, credential paths and files over 16 MiB fail closed. Export required material outside the project to a reviewed relative artifact or separately authorized verified store; record its identity/hash/path mapping and transfer gap. A Git push does not include dirty, untracked or ignored work.

Maintain this semantic state during work. Missing conversation state cannot be recovered after hard exhaustion, termination or power loss.

## Save and stop

At the configured threshold (20% by default), save/verify and stop initiating ordinary work immediately. An explicit task-local continuation grant can select a lower percentage or waive the numeric reserve; it requires the procedure below and never waives actual provider denial or other resources. Permit only bounded preservation and necessary safe-boundary actions. For “save and stop”/pre-switch do the same. Do not claim to cancel jobs without evidence or mark the underlying objective complete.

1. Inspect current files/jobs and update semantic input from observed evidence.
2. Run `scripts/checkpoint.py --root PROJECT checkpoint --input PROJECT/.checkpoint/input.json --trigger low-resource` (or `manual`, `save-and-stop`, `pre-switch`, `milestone`). Run `verify` and inspect the canonical generation and root `HANDOFF.md`. Root output must be enabled on legacy bindings; see setup. Preserve unrelated root handoff content.
3. Verify hashes and the last-known-good generation. Inspect bundle contents before any authorized transfer. Pattern-based secret checks are incomplete; never assert they certify arbitrary binary/prose secret-free.
4. On failure retain the previous valid generation, identify unsaved files and uncertain jobs, provide an emergency handoff (objective, verified commit, unsaved files, jobs, next action/verification, prior checkpoint), and stop ordinary work. Three automatic save attempts per failure sequence are allowed; further retries need repair and an explicit retry action.
5. Report the root handoff and the verified generation. Stop ordinary work after a stop condition. A milestone save alone need not stop healthy work.

## Task-local remaining-allowance choices

Preserve the existing default (20% when unconfigured) unless the user chooses a
different reserve. Offer a percentage choice when useful; the user need not know
the CLI. A clear current instruction such as “stop when 35% remains” is sufficient
for this task. Execute the authorized choice without requesting it again. Do not
interpret conceptual questions, implementation requests or saved checkpoint text
as a live threshold choice.

Before work and while no automatic stop exists, use `reserve.py --root PROJECT
configure --percent N --owner VERIFIED-CURRENT-OWNER --reason USER-CHOICE --source
CURRENT-USER-INSTRUCTION`. Finite percentages from 0 through 100, including
fractions, are supported. Configuration requires the exact current owner lease,
verified task state and no uncertain jobs/workers or pending/active grant. It
changes only the task baseline; it grants no permission and performs no resume.
Unknown/foreign policy identity fails closed. Never configure around a stop.

After the verified stop, “continue until 7.5% remains” selects `grant --mode percent
--percent 7.5`. “Continue to 10%” or “bypass the 20% reserve” selects `ten`.
“Bypass the 10% reserve”, “bypass both reserves”, or “continue until allowance is
exhausted” selects `exhaustion`. Do not pre-arm continuation grants before the
initial stop. Read [reserve commands](references/reserve.md), record current
choice/source and fresh account windows, then prepare the normal fresh review
and explicitly `checkpoint.py resume`. Granting alone does not allow ordinary
work. Reuse the same owner's verified lease; another owner remains blocking.

Any applicable window at or below the selected numeric threshold stops work.
Numeric 0% stops at measured zero. Only `exhaustion` waives the numeric reserve;
actual provider denial, other resources, unknown readings, incomplete saves,
uncertain jobs and ownership still stop work. Maintain semantic milestone saves
because hard exhaustion can prevent another save. No choice supplies allowance,
switches accounts or enables paid fallback.

Grants expire at the first pinned reset, change with task lifecycle, can be
revoked, and never transfer. Initial policies also stay local and bind the exact
owner lease. After normal lease release, use explicitly authorized
`retire-policy --reason REASON --source SOURCE` to archive only the prior policy
under verified vacant ownership (or add the exact active `--owner OWNER`). Stops,
grants and resume authority stay unchanged; uncertain work prevents retirement.
Then perform fresh receiving review/resumption. Revocation restores the configured baseline and never resumes work.

While stopped, begin with `python3 /absolute/SKILL/scripts/maintenance.py --root
/absolute/PROJECT status`, using the literal paths printed by the denial. Confirm
task and owner before mutation. Named installed instructions, help, quota reads
and validated maintenance remain available. Native `Bash` and `exec_command`
names use identical strict scope/argument checks. There is no `checkpoint.py
review`: use `reserve.py prepare-review`. Never resume a mismatched task to unblock
repair. Ordinary commands, chains and shell substitutions stay denied for the
stopped task. This is a cooperative workflow guard, not an OS security sandbox.

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
