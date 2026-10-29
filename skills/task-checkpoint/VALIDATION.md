# Validation for 0.8.1

The focused regression suite passes 61 tests on local macOS/Python. It retains snapshot integrity, interrupted promotion, root handoff preservation, staged/unstaged/binary artifacts, previous-generation recovery and competing remote owners. Tests for retired pause/grant/router behavior are replaced by tests of the 0.8 contract.

New checks cover direct 20/10/custom/zero thresholds, exhaustion override, explicit provider denial, all quota windows, unknown/stale/future/past-reset readings, failed preservation followed by repair, continuation without a review file, legacy-marker migration, cached hooks that never deny tools, and existing owner leases. Collector tests verify fresh values, read-only probe methods, unchanged legacy configuration, no task dispatch and no paid API fallback. Installer tests cover customized installations, managed rollback, standalone installation and exact legacy project hook retirement.

Run `python3 -m unittest discover -s tests -v`. Run `python3 scripts/check_release.py` for package hashes and public-file checks. CI runs the same suite on Linux and macOS. Python tests do not prove a continuously running model will invoke the skill correctly; monitoring remains cooperative. Actual provider exhaustion and a second physical device are not deliberately exercised. No native hook or new background service is required.

The 0.8.1 quota-source regression adds eight cases: stale/empty local caches, fresh collector low limits, fresh local precedence, account mismatch, explicit collector selection, local non-quota limits, all quota windows, and both sources unknown. The unchanged 0.8.0 source failed four of these cases; the repaired source passes all eight.
