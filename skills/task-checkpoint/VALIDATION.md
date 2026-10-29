# Current release verification

For 0.7.3, see the [release verification report](https://github.com/HarryBurd33/task-checkpoint/blob/main/docs/RELEASE-0.7.3.md). The earlier report below records its original evidence and limitations.

# Version 0.7.1 verification

The complete local suite passed **362 tests on Python 3.9.6 in 127.025 seconds**. Focused readiness tests (24) and resume-lock regressions (3) passed on Python 3.9.6 and 3.15; stopped-shutdown regressions (8) passed on both. The clean exported distribution passed 2 installer and 28 packaging/automation tests. Full source tests use isolated repositories and simulated resource/clock inputs. CI and native host checks are separate evidence.

Version 0.7.0 introduced automatic enrollment/exclusions, conservative chat isolation, configurable finite initial and post-stop percentages, explicit released-lease policy retirement, nested repository inspection and collector fault isolation. Version 0.7.1 corrects three failures found during follow-up acceptance:

- Interrupt and SessionEnd preserve the generation pinned by a persistent stop. Previously shutdown could advance the checkpoint and make a later grant fail identity validation.
- Explicit resume acquires the existing collector preservation lock before changing ownership, the receipt or grant state. Denied or busy lock access preserves those records and reports the scoped permission requirement.
- Readiness uses the same configured threshold, active grant and ownership checks as preservation. It cannot notify from a healthy global default when the task's higher reserve remains low, or ignore invalid policy ownership.

## Observed native macOS acceptance

Codex CLI app-server 0.164.0 delivered the installed trusted hooks in isolated Git fixtures. Subscription turns used the configured Astra model at low effort, with fresh real account readings and no paid API fallback. Thresholds of 100% were artificial fixture-local choices; real shared telemetry was never replaced or deliberately exhausted.

Verified native behavior includes healthy ordinary work, automatic save and stop, pending fractional grant and review with the stop retained, then explicit resume and one bounded write with the same owner lease. The successful continuation used the official per-turn workspace sandbox policy naming only the fixture and the shared preservation lock directory. An earlier denied resume was preserved as failure evidence; the repaired path passed.

Native automatic enrollment created one session-bound registry record with scheduled dispatch disabled and no ownership or semantic-input invention, preserving existing ignore rules. Native root exclusion created no binding, registry entry or ignore edit. Temporary enrollment controls and registry entries were restored exactly under their existing lock. SessionEnd natively retained the stopped generation after the repair. Maintenance access and ordinary-command denial were verified, including root session identity despite a conflicting inherited environment thread ID. Bash and exec_command classification equivalence is covered by strict isolated tests; this host delivered exec_command.

A real native child thread executed the sole read-only probe command. Its recorded command output identified the child environment thread while the delivered PreToolUse receipt correctly retained the root session identity; native child turn metadata and hook notifications corroborated the relationship. This verifies child propagation rather than relying on root-model prose. Seven bounded follow-up root turns and one child were used, including preserved failed attempts.

The real launchd collector's Documents failure was resolved through a user-performed privacy approval for the verified responsible system Python shim. Three subsequent natural collector runs accessed the affected project successfully. A separate temporary fixture with a local 100% reserve was then preserved by the existing collector's next natural invocation: root HANDOFF, checkpoint manifest, changed text and binary snapshot hashes verified; stop and owner remained intact. No manual tick, new service, background worker or shared telemetry modification was used. Its registry entry was removed and the original account configuration restored exactly.

The installed macOS notification adapter returned command acceptance and the user subsequently observed its labelled test notification. Display was delayed; no exact latency or actual account-reset delivery timing is claimed. The readiness reset scheduler and deduplication remain isolated clock tests.

Native thread startup added exact fixture project trust entries through the host's normal behavior, even for ephemeral threads. These entries were preserved. No hook definition, hook trust hash or unrelated trust setting was edited by the harness. It would be inaccurate to claim all global configuration bytes stayed identical during these native runs.

## Preservation and limits

The protected stopped task was never resumed, replaced, released or enrolled. Twenty-eight protected files and ownership ref/reflog records matched the baseline after permission and collector checks. Other legitimate persistent stops remained in place. Only an explicitly authorized isolated continuation fixture was resumed.

Actual allowance depletion/provider exhaustion, exact reset-plus-60-seconds wake timing, background notification display, a second physical device/account, native Windows/Linux application callbacks and unsupported tool surfaces remain unverified. Linux/macOS CI exercises the Python runtime, not those application integrations. Existing terminal readiness tickets are preserved; historical over-delayed targets are not automatically shortened or notifications retracted. Mid-operation filesystem failures remain conservative stops; this release does not claim a general multi-file transaction.

Run `python3 -m unittest discover -s tests -v` and `python3 scripts/check_release.py`. Private local evidence is excluded from the public export. Pattern checks do not certify arbitrary content secret-free.
