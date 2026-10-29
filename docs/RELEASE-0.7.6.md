# task-checkpoint 0.7.6

An explicit checkpoint save during a persistent resource pause previously could
advance the latest generation while the stop still pinned the old generation.
Subsequent reviewed recovery then failed because the two identities differed.

The supported exact-owner checkpoint CLI now uses the existing collector/router
preservation fences. It saves truthful reconciled input and aligns the stop with
the verified generation while retaining the pause, incident, reserve and lease.
It executes no task command and acquires no owner. Raw snapshots cannot advance
past a persistent stop. Stop state is checked at capture and promotion; explicit
stopped saves revalidate the exact owner token at both boundaries and before
repinning. Automatic collector preservation retains its legitimate vacant-owner
path. Unchanged-input saves check that lease before reporting success too.
Losing ownership fails closed and never replaces another claim.

Recovery of a previous generation is limited to the actual verified checkpoint
pinned by the stop. The owner is checked again after the recovery fence is
acquired. This closes an independently reproduced race in which ownership could
be released after initial validation but before the pointer changed.

Focused regressions exercise the actual checkpoint CLI, unchanged incident and
owner state, raw snapshot denial, capture/promotion races, failed-save safety,
collector/worker fences, the pending grant's original anchor, true pinned recovery,
and fresh review followed by explicit resume. Ownership-transition simulations
use isolated Git fixtures; no live task or allowance is changed to reproduce them.

All 0.7.5 recovery improvements are retained, including compaction, read-only
bootstrap/handoff, clarification tools and explicit registered-collector review.
The existing native desktop compaction, reviewed resume, ordinary tool delivery
and user-confirmed notification test remain separate evidence from callback tests.

Future real quota-reset timing, other device/cloud installation and unsupported
native notification platforms retain the boundaries described in the
[0.7.5 verification notes](RELEASE-0.7.5.md). No permissions, hook trust, shared
reserve or unrelated task state is changed by this release.
