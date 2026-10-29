# task-checkpoint 0.7.5

This release repairs recovery deadlocks while retaining legitimate stops,
exclusive ownership, configured reserves and native permissions.

## Resulting behavior

- A persistent stop no longer aborts native context compaction. Compaction does
  not clear the stop or authorize ordinary tools.
- Read-only maintenance works before the first checkpoint and identifies missing
  semantic input. It reports actual required capability labels and tool names.
- `maintenance.py --root PROJECT handoff` reads the bound task's verified
  canonical handoff. It accepts no arbitrary path and rejects corrupted or foreign
  checkpoints. User clarification questions can be presented during a stop.
- After a prior stop was acknowledged, `reserve.py ... prepare-review --signals
  ACCOUNT-STATE/signals.json` can select the existing enabled collector registered
  to that exact task. It retains the collector reserve and local non-account
  resource signals. Resume rereads the source and rejects low, stale, missing or
  changed account/window/reset observations. It cannot replace an active stop or
  grant source. A review still does not resume or acquire ownership.

## Verification

The complete runtime/installer suite and focused installed regressions cover
preserved stop/owner state, canonical handoff integrity, clarification access,
post-release continuation, configured collector reserves, source registration,
freshness, account/window changes, other resource stops and pending grants.
GitHub Actions runs the suite on Ubuntu with Python 3.11 and 3.13, and macOS
with Python 3.13. Inspect the workflow checks for this tag for their actual result.

Native macOS Codex desktop verification observed a delivered PreCompact event,
an actual compaction record, successful explicit reviewed resume with both
required Python and Git capability labels, ordinary Git status access and normal
release of the verification lease. A fresh native PreToolUse receipt matched
the intended desktop chat and workspace. These observations are distinct from
isolated callback tests or a separate CLI process.

Native notification command acceptance and visible display were checked
separately; the user confirmed seeing the labeled display-only test. No task
recovery or resumption was represented by that notification.

## Remaining boundaries

Future quota-reset timing was not verified by exhausting a real account or
fabricating collector readings. Readiness depends on the existing enabled
collector, host availability, project opt-in and native notification permissions.
Windows/Linux notification adapters and other devices/cloud installations require
their own supported integration and verification. A skill cannot supply missing
semantic task history or change those native capabilities.

Hook trust, OS permissions, unrelated task owners/stops and shared reserve
configuration remain unchanged. Public file allowlists and pattern checks reduce
accidental disclosure; they do not certify arbitrary content secret-free.
