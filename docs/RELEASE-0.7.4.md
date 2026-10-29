# Task checkpoint 0.7.4 verification

## Repair

A healthy collector can coexist with absent lifecycle hooks and a lost managed
receipt. Status now reports registration counts, receipt presence and historical
delivery separately. Configuration completeness does not establish native delivery.

`restore-hooks --recover-receipt --python ABSOLUTE-PYTHON` is an explicit repair
operation. It accepts only a complete canonical backup for the installed script,
existing account/profile and a recognized interpreter. Changed, duplicated,
missing or wrong-event callbacks fail before writes. Unrelated hooks and native
trust are retained. A failed hook write may leave an exact recovered receipt for
a normal retry; this partial result is not reported as a successful restoration.
The extended recovery form is not added to stopped-task maintenance exemptions.

Native delivery metadata is recorded before enrollment, with host chat identity,
root, event, timestamp and process provenance. Account-maintenance inspection in an
unbound Git workspace records delivery without creating a blank domain task.
Ordinary tool enrollment, task stops and ownership gates remain unchanged.

## Observed verification

- All 393 runtime/installer tests passed locally on Python 3.15, including eight
  new receipt-recovery, failure-preservation and unbound-maintenance regressions.
- Fifteen restoration/integration tests and two installer checks passed separately.
- Metadata validation, package manifest, MIT notices and public-file checks passed.
- The installed macOS notification adapter accepted a clearly labeled display test.
  The user explicitly confirmed seeing it. No readiness ticket, task reset, resume,
  notification permission or Focus setting was changed. A visible test establishes
  that observation, not future scheduler timing or every host's display behavior.

## Native delivery boundary

The actual desktop had no configured checkpoint hooks and no managed receipt.
Its canonical saved backup still contained the expected seven definitions. The
running desktop app-server uses its app-owned stdio transport; the optional CLI
control socket is unavailable, and direct Codex Computer Use is blocked. A CLI
child is not counted as desktop delivery. Live restoration and any fresh native
receipt are recorded separately in the private deployment review. A fresh desktop
turn may be needed to reload repaired registrations; if it does not reload, save
active work before a user-performed app restart. No force restart, fabricated trust
record, ordinary-work bypass or unrelated task resume is part of this repair.

The local suite emitted a subprocess ResourceWarning. This is recorded separately
from test success. Cross-platform results are attached to the exact release commit.
