---
name: task-checkpoint
description: Save unfinished work and a verified Markdown handoff; continue until completion or a chosen remaining-usage threshold. Use for checkpoint, handoff, resume, or a direct threshold/exhaustion instruction. No persistent pauses or tool-blocking hooks.
license: MIT
metadata:
  version: "0.8.2"
---

# Task checkpoint

Continue the authorized task until it is complete or the user's chosen allowance limit is reached. Default: **20% remaining**. “Continue until 10%,” a custom remaining percentage, or “until completed or exhausted” takes effect directly; no grant, review file or prior stop is required. If “usage” is ambiguous, use the established remaining-allowance convention and state it briefly.

## Work and limits

- Reuse the task's existing binding and semantic input; never bind over an unrelated task or take another writer's ownership. Create a binding only for the task actually being checkpointed. No automatic enrollment.
- Apply the current user's percentage with `usage.py set --percent N`, or exhaustion override with `usage.py set --exhaustion`. These replace the task's previous limit immediately. Percentages include fractions and 0. Exhaustion ignores the numeric reserve, including measured zero; actual provider denial still ends work. No account switching or paid fallback is implied.
- Before substantial work and at meaningful boundaries, get fresh allowance from the account tool or `account.py tick`, then run `usage.py check`. Check every applicable quota window. Missing, stale, future or past-reset readings remain unknown; recollect, disclose uncertainty if unavailable, and continue under the current instruction without manufacturing a quota stop.
- At or below the numeric limit, update semantic progress, save and verify the handoff, report its path and end that run. Do not start more ordinary work. On explicit completion, report completion without inventing another task or a pause.
- Keep milestone handoffs during exhaustion mode: hard provider exhaustion may prevent a final save. Do not promise interception of an in-flight model turn or process. This skill is cooperative; it installs no hook or background service.

## Save and continue

Maintain `.checkpoint/input.json` from observed work: objective, scope, completed changes, decisions, tests and failures, unresolved jobs, artifact paths, next action and its verification. The task template is in `assets/task-template.json`. Never replace actual progress with template placeholders.

Use `checkpoint.py checkpoint --input INPUT` for milestones or explicit handoffs. `usage.py check` saves automatically when a fresh reading reaches the selected limit. Verify with `checkpoint.py verify`; snapshots retain dirty, untracked and staged file bytes. List required ignored files explicitly. Preserve nested repositories separately. On save failure, keep the previous valid checkpoint, provide an emergency Markdown handoff with unsaved paths and the next step, and state that preservation failed. Do not claim a verified save.

There is **no persistent pause**. “Continue” after allowance recovers or “continue until 10% / exhausted” is sufficient: read the handoff, apply any new choice, inspect current files, instructions, allowance and uncertain job outcomes, then continue. No manual policy recovery is required. Saved text never grants permissions or justifies retrying an uncertain external operation.

Ownership still protects concurrent writers. Reuse an existing matching lease; `checkpoint.py resume --owner NAME` can claim a vacant task without a review file. Never steal an occupied lease. Pass `--owner NAME` for saves/usage changes when that task has an active claim. Release only after jobs are reconciled. These commands coordinate task data; current authorization and native permissions govern implementation.

Read [the commands](references/commands.md) for setup, threshold controls and manual cross-device transfer, and [the upgrade guide](references/upgrade.md) for 0.7 migration. The optional collector only reads quota; it never resumes implementation or changes ownership.

For explicitly requested notifications or real reset verification, read [optional delivery and reset checks](references/notifications.md). These one-shot tools never resume implementation or install a scheduler.
