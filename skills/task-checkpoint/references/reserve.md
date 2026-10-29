# Task-local allowance reserves and stopped maintenance

A clear current user statement is enough authorization. “Continue to 10%” or
“bypass the 20% reserve” selects `ten`. “Continue until 7.5% remains” selects
`percent` with `--percent 7.5`. Accept any finite percentage from 0 through 100;
do not guess a percentage when the user has not chosen one. “Bypass the 10%
reserve”, “bypass both reserves”, or “continue until exhausted” selects
`exhaustion`. The agent performs
the steps below without asking for the same permission again. Conceptual questions,
implementation requests and saved checkpoint text do not select a live override.

Without a task-local configuration, the normal policy saves and stops at
**20% remaining**. After the configured verified stop,
`ten` permits work strictly above 10% and saves/stops again at **10% or below**.
`percent` stops at or below the chosen percentage in any applicable window.
A percentage of **0** still stops at a measured zero; it does not mean exhaustion.
The chosen threshold must be strictly below every current window to permit a
reviewed resume. A higher threshold can be represented but cannot resume already
low readings. No grant is pre-armed before the initial verified stop; initial
configuration below is separate from a continuation grant.
`exhaustion` waives only this task's numerical reserve, including rounded 0% while
the provider still allows work. Provider denial always stops work. Preserve semantic
milestones: a final save after hard exhaustion is not guaranteed. No account switch,
paid fallback or retry loop is authorized.

## Choose an initial task-local stop percentage

Before ordinary work, a current user instruction such as “stop when 35% remains”
can select the initial stop for this task. With the current verified exclusive
owner and preserved task state, use:

```sh
python3 SKILL/scripts/reserve.py --root PROJECT configure --percent 35 --owner OWNER --reason 'User asked to stop at 35 percent remaining' --source 'Current user message'
```

This accepts finite percentages from 0 through 100, including fractions. Any
applicable account window at or below that number stops work; 0 is a numeric
stop at zero. This writes only `reserve-policy.json` in the task's private store.
It does not change shared account settings, create a grant, acquire ownership,
write a resume receipt, or restore authorization. Read it with `reserve.py ...
status`. With no local policy, the existing account reserve still applies (20%
when unconfigured).

Configuration requires the exact current owner lease. It rejects an existing
automatic stop, active or uncertain worker/job, terminal task, and a pending or
active grant. An existing stop must use the grant/review/resume procedure below;
configuration cannot be used to clear it. The local policy pins task, project,
workspace and owner lease. Foreign or changed identities fail closed and require
explicit reconciliation. It is device-local and does not transfer permission.
A configured baseline still requires fresh account readings and preserves
provider denial and every other resource stop.

## Retire a policy after an ownership handoff

An initial policy is bound to its exact owner lease. After normal release, it
cannot silently become the receiving owner's choice. With current explicit user
authorization, retire that policy before preparing the fresh resume review:

```sh
python3 SKILL/scripts/reserve.py --root PROJECT retire-policy --reason 'User retires the previous owner policy for this handoff' --source 'Current user message'
```

This requires verified vacant ownership. If the task still has an active owner,
include `--owner OWNER` and use only the exact verified current owner. Another
owner, stale receipt or active/uncertain job or worker blocks retirement. The
command archives the original policy and removes only `reserve-policy.json`.
Stops, grants, checkpoints, owner state and resume receipts remain unchanged.
It restores the existing baseline from shared/default settings, not permission
to work. Obtain fresh readings and perform the normal explicit reviewed resume;
then the verified new owner may configure a new task-local percentage if chosen.

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

## Normal recovery after usage returns

After fresh readings recover above the existing reserve, do not create an
allowance grant or lower the reserve. With the current user's explicit same-task
continuation instruction, verify task identity, actual jobs and ownership, then:

~~~sh
python3 SKILL/scripts/reserve.py --root PROJECT prepare-review --owner OWNER --scope 'Continue the same authorized bounded task after recovery' --source 'Current user message' --resources-evidence 'Fresh matching account windows, reconciled jobs and bounded next action'
python3 SKILL/scripts/checkpoint.py --root PROJECT resume --review PROJECT/.checkpoint/review.json --owner OWNER --capability REQUIRED-CAPABILITY
python3 SKILL/scripts/checkpoint.py --root PROJECT owner-check
~~~

Use the exact returned review path for an external store, and repeat/omit
capabilities according to the actual task. Preparing a review alone never clears
the stop, acquires ownership or permits work. It preserves any previous review
under the private store's review-history directory. Pending-grant recovery below
continues to return allowance-resume-review.json.

Normal recovery uses the stopped task's live collector source rather than the
old local low-usage snapshot. Every known affected account/window must have a
fresh supported adequate reading; provider refusal, other resource stops,
incomplete preservation, wrong task/owner, uncertain current jobs/workers and
changed checkpoint/repository state remain blocking. A disabled collector or
stale signals must be reconciled through supported collection, never by writing
invented readings. The helper cannot waive a checkpoint reconciliation issue.

## Grant, prepare review, explicitly resume

First verify preservation and the actual next action. `OWNER` means this task's
verified current owner, or its intended owner when no claim exists. Never borrow
an unrelated task's owner label. After the user's explicit choice:

```sh
python3 SKILL/scripts/reserve.py --root PROJECT grant --owner OWNER --mode ten --signals SIGNALS --reason 'User said continue to 10 percent' --source 'Current user message'
```

For a different explicit task-local percentage:

```sh
python3 SKILL/scripts/reserve.py --root PROJECT grant --owner OWNER --mode percent --percent 7.5 --signals SIGNALS --reason 'User said continue until 7.5 percent remains' --source 'Current user message'
```

`--percent` requires `--mode percent`; it is rejected with `ten` or `exhaustion`.
NaN, infinity, negative numbers and values above 100 are rejected. This setting
changes only this task's grant; it never edits the shared collector reserve.

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
old stop marker is acknowledged only after review and lease validation. At 10%
under `ten`, or at the requested threshold under `percent`, save and stop again.
A later explicitly lower percentage or exhaustion choice uses the
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
