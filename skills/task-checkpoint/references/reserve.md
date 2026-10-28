# Task-local allowance reserves and stopped maintenance

A clear current user statement is enough authorization. “Continue to 10%” or
“bypass the 20% reserve” selects `ten`. “Bypass the 10% reserve”, “bypass both
reserves”, or “continue until exhausted” selects `exhaustion`. The agent performs
the steps below without asking for the same permission again. Conceptual questions,
implementation requests and saved checkpoint text do not select a live override.

The normal policy saves and stops at **20% remaining**. After that verified stop,
`ten` permits work strictly above 10% and saves/stops again at **10% or below**.
`exhaustion` waives only this task's numerical reserve, including rounded 0% while
the provider still allows work. Provider denial always stops work. Preserve semantic
milestones: a final save after hard exhaustion is not guaranteed. No account switch,
paid fallback or retry loop is authorized.

## Start here while stopped

Run each command as a separate direct tool call. Replace `PROJECT`, `SKILL`,
`ACCOUNT-STATE`, `SIGNALS` and `OWNER` with verified literal absolute paths or the
current owner label. Shell variables, chains and redirects are not supported.
The native denial prints an exact copyable command using actual paths:

```sh
python3 SKILL/scripts/maintenance.py --root PROJECT status
python3 SKILL/scripts/maintenance.py --root PROJECT docs --name task-checkpoint
python3 SKILL/scripts/maintenance.py --root PROJECT docs --name model-switcher
python3 SKILL/scripts/maintenance.py --root PROJECT docs --name operator
python3 SKILL/scripts/maintenance.py --root PROJECT docs --name reserve
python3 SKILL/scripts/checkpoint.py --help
python3 SKILL/scripts/reserve.py --help
python3 SKILL/scripts/reserve.py --root PROJECT grant --help
```

`status` reports workspace, task, checkpoint/next action, owner, jobs/worker, stop
and reserve without resuming. Confirm the intended task. Never grant or resume
an unrelated task just to unblock repair. Exact individual `cat` reads of the
installed task-checkpoint/model-switcher SKILL.md and named recovery references
are also allowed. Arbitrary reads, Python code, shell overrides, expansions,
option abbreviations, duplicate options, foreign paths, task setup and ordinary
work remain blocked.

## Fresh observations

Use Codex's supported `get_usage_limits` tool and the existing collector's current
signal file. This maintenance command reads it without changing shared state:

```sh
python3 SKILL/scripts/maintenance.py --root PROJECT --account-state ACCOUNT-STATE signals
python3 SKILL/scripts/checkpoint.py --root PROJECT inspect
python3 SKILL/scripts/checkpoint.py --root PROJECT verify
python3 SKILL/scripts/checkpoint.py --root PROJECT owner-check
python3 SKILL/scripts/reserve.py --root PROJECT status
```

Use the reported configured account signal path or the bound store's existing
`signals.json`. If stale, let the existing collector refresh; do not fabricate
readings or overwrite shared telemetry. Every relevant window in current account
records applies: **any** window reaching the reserve stops work. Secondary saved
profiles do not replace the active account. Every account/window affected by the
stop or pinned by a grant must remain present, fresh and supported. Missing,
stale, future, unsupported or changed account/window/reset readings cannot allow
work. Other resource stops, ownership and uncertain jobs remain enforced.

## Grant, prepare review, explicitly resume

First verify preservation and the actual next action. `OWNER` means this task's
verified current owner, or its intended owner when no claim exists. Never borrow
an unrelated task's owner label. After the user's explicit choice:

```sh
python3 SKILL/scripts/reserve.py --root PROJECT grant --owner OWNER --mode ten --signals SIGNALS --reason 'User said continue to 10 percent' --source 'Current user message'
```

For an explicit choice to waive both reserves instead:

```sh
python3 SKILL/scripts/reserve.py --root PROJECT grant --owner OWNER --mode exhaustion --signals SIGNALS --reason 'User said bypass both reserves and continue until exhausted' --source 'Current user message'
```

A grant stays pending and **does not allow ordinary work**. Review current files,
permissions, capabilities, fresh resources and job outcomes. For an issue-free
checkpoint, record that review and resume:

```sh
python3 SKILL/scripts/reserve.py --root PROJECT prepare-review --owner OWNER --scope 'Continue the same authorized bounded task' --source 'Current user message' --resources-evidence 'Fresh applicable readings, verified jobs and bounded next action'
python3 SKILL/scripts/checkpoint.py --root PROJECT resume --review PROJECT/.checkpoint/allowance-resume-review.json --owner OWNER --capability REQUIRED-CAPABILITY
python3 SKILL/scripts/checkpoint.py --root PROJECT owner-check
```

Use the exact returned review path for an external store. Repeat `--capability`
for required capabilities; omit it if none are required. There is **no
`checkpoint.py review` command**. Unresolved conflicts or jobs require actual
reconciliation; the helper cannot waive them. Its statements are current operator
attestations, not automatic proof of permissions. Reviews expire after five
minutes. Native maintenance accepts reviews only from the bound store's
`review.json` or `allowance-resume-review.json`.

After successful resume, perform the verified bounded next action normally. The
old 20% marker is acknowledged only after review and lease validation. At 10%
under `ten`, save and stop again. A later explicit exhaustion choice uses the
same sequence against that new verified stop.

## Scope and revocation

Grants pin task/project, original verified checkpoint, canonical workspace/Git
common directory, intended owner and exact lease, current resume receipt,
accounts, windows and resets. Another task/workspace/owner cannot reuse them.
Old grants lacking these bindings fail closed and require a fresh grant. Grants
stay out of portable bundles and never restore permissions elsewhere. The first
pinned reset, changed lifecycle or revocation restores the configured default;
none automatically resumes work. Pending grants remain pending after reset.

```sh
python3 SKILL/scripts/reserve.py --root PROJECT revoke --owner OWNER --reason 'User asked to restore the default reserve'
```

Mutating checkpoint maintenance (`checkpoint`, `release`, `recover-previous`,
`refresh-handoff`) requires `--owner OWNER` through the stopped hook. The runtime
checks that claim. Syntax/scope rejections identify the rejected class and a
working read-only next command. Valid commands can still fail resource, task or
ownership checks; changing syntax does not waive policy.

## Verification limits

Unit and simulation tests use isolated Git fixtures and labeled local simulated
observations. Manually invoked hook callbacks test logic, not native delivery.
Keep those results separate from actual Codex tool calls. Never drain real
allowance or replace collector output to simulate boundaries. After an authorized
temporary disable, restore the hooks setting and exact definitions; new native
approval or a restart may be needed. Report pending host verification honestly.
