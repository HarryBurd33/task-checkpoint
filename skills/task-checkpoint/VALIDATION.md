# Version 0.7.0 verification

The final complete suite passed **342 tests on Python 3.9.6 in 97.862 seconds**. An earlier Python 3.15 run passed 335 tests in 151.458 seconds; the subsequent percentage/configuration/retirement (27 tests) and final enrollment/Bash/identity (15 tests) suites passed on both interpreters. All 78 reserve tests passed together on 3.9.6. The clean exported distribution passed 28 packaging/automation tests in 11.907 seconds and the release manifest/privacy checks.

Isolated tests cover custom initial thresholds, fractional post-stop grants, zero versus exhaustion, pending grants and reviewed resume, identity/owner/lease/reset binding, stale or missing telemetry, provider denial, policy retirement without clearing stops, and bounded continuation. Enrollment covers idempotency, exclusions, preserved legacy bindings, explicit unrelated-chat routing, unknown identity conservatism, first-commit and collector-lock deferral.

Nested repositories are explicit unsaved artifact boundaries: inspection works and checkpoint promotion refuses to silently omit them. Collector tests cover dependency failure isolation, transfer identity checks, and the three-attempt preservation bound. Bash maintenance retains strict CLI/shell validation.

## Native acceptance

Actual Codex CLI app-server 0.164.0 delivered trusted PreToolUse/PostToolUse callbacks on macOS in an isolated, unregistered Git fixture. The corrected native run executed maintenance status successfully (shell exit 0), denied an ordinary printf before execution, retained its persistent stop, and identified the actual root chat from event session_id despite a stale inherited CODEX_THREAD_ID. Existing global hook definitions and trust configuration were byte-identical before/after.

The first native run found two defects missed by simulation: inherited environment identity was not the new root chat identity, and the macOS system Python launcher differed from sys.executable. Both were fixed, covered by regressions and verified in a second native run. Two bounded subscription turns used the configured Astra model at low effort; no paid API, live telemetry replacement or deliberate allowance exhaustion occurred.

This proves native maintenance access, stop enforcement and identity delivery on this host. Percentage transitions and automatic enrollment/exclusion paths are isolated logic/callback tests; full native quota depletion, exact reset notification display/timing, native Windows/Linux and a second physical device/account remain unverified. A background macOS Documents access restriction still affects one pre-existing collector project and requires host permission repair.

Independent review drove fixes for unfamiliar-chat stop bypass, unborn repositories, collector lock contention, enrollment preflight side effects and released-lease policy recovery. A reviewed live routing map separates 16 unrelated chats while retaining the two owning chats of a protected stopped task. No live task was resumed; protected checkpoint/ownership/stop files and hook definitions were hash-checked unchanged.

Reproduce with `python3 -m unittest discover -s tests -v` and `python3 scripts/check_release.py`. Private ignored local evidence stays outside the public export; tracked files remain checked. Pattern checks cannot certify arbitrary contents secret-free.
