# Task checkpoint 0.7.3 verification

## Resulting behavior

Normal recovery prepares a fresh issue-free review against the stopped task's live
collector readings without inventing a reserve grant. Every known affected account
window must be present, fresh, supported and adequate. Prior reviews are retained;
only explicit reviewed resume can clear the stop and allow bounded work.

Observation-only account collection still assesses preservation but skips planned
and scheduled dispatch, private publication and private receive. Existing project
configuration is retained.

Preservation retry requires a current repair reason and authorization source, plus
either the exact matching active owner ledger/receipt or explicit verified vacancy.
It serializes against the existing collector, router and writer fences, validates
stop/task/lifecycle/prior-generation identity, rejects active or uncertain workers,
and grants at most three more save attempts. It changes only the incomplete stop's
attempt counter and retry audit record. It never acquires/releases ownership,
clears a stop, resumes a job, changes a reserve or changes native permissions.
Uncertain jobs can be captured as uncertain; execution still requires reconciliation.
Only this validated retry command joins the stopped-task maintenance exception.

## Observed checks

- Fifteen isolated retry tests passed: exact owner, vacancy, wrong/stale/foreign
  ownership, current authorization, invalid stops/counts, lifecycle, corrupt prior
  generation, worker/journal identity, lock conflicts, bounded repeated failures,
  preservation of uncertain jobs and strict maintenance CLI/callback handling.
- Seven isolated normal-recovery tests passed, including fresh live-source resume,
  missing windows, low/unknown/stale/future/wrong-account readings, unresolved jobs,
  owner/worker conflicts, incomplete preservation and expired/changed reviews.
- Thirteen maintenance tests passed. Shell chains, substitutions, foreign paths and
  incomplete retry arguments remain denied.
- The skill metadata validator passed. Distributable hashes, MIT notices and the
  public-tree privacy checks passed. Pattern-based privacy checks are incomplete.
- Full runtime and installer suite: 385 tests passed locally on Python 3.15.
  The suite emitted a subprocess ResourceWarning; its named process was checked
  afterward and was no longer present. Cross-platform CI is recorded by commit.

## Native host evidence

On macOS with Codex CLI 0.164.0, seven exact checkpoint hook definitions were
registered and trusted in an isolated temporary Git fixture. Native tool execution
confirmed that an ordinary marker command was denied, the named readiness guide
was readable, and the authorized vacant-owner retry command succeeded after normal
scoped host approval for the protected Git metadata lock. The marker file was
absent. The retry left the prior checkpoint pointer and ownership ref unchanged,
retained the stop and created no resume receipt. A separate bounded collector call
then saved and verified a checkpoint while retaining the stop and vacant ownership.

The fixture used actual supported account observations; no healthy quota/reset was
fabricated. Model and reasoning overrides were not requested; the effective native
model setting is unknown. Early probes exposed missing project trust and a reason
containing a conservatively rejected shell delimiter; these were corrected in the
fixture/example without weakening the maintenance classifier. Another probe proved
that a sandbox lock denial left retry state unchanged before approved execution.

Only fixture-specific project trust and exact hook hashes were temporarily added.
Those exact sections were removed, restoring the original configuration bytes.
Existing hook definitions and stored permissions remained unchanged. No production
project was resumed, owned, reconfigured or enrolled for this test.

## Limits

Native evidence covers this isolated macOS CLI fixture, not all desktop chats,
other operating systems, cross-device ownership coordination or OS notification
display. Installing/updating the skill does not enable or trust production hooks.
A protected collector or Git metadata fence still needs normal scoped host access;
retry fails closed when that access is unavailable. Locks are cooperative and a
reason/source string is an operator authorization record, not an independent proof
of human consent. A disabled/offline collector will not retry until explicitly
invoked or restored through its separately authorized setup. Retry cannot repair
the underlying content/storage failure or reconstruct unmaintained semantic state.
