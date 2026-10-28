# Host requirements and evidence

Manual save/verify/resume requires Python 3.9+, Git, an initial commit and writable local files. User-wide Codex discovery uses ~/.agents/skills. Native CLI account telemetry uses a supported signed-in account/rateLimits/read source. Inspect the installed CLI capabilities before activation; API-key-only access does not imply subscription allowance.

Use [capabilities](capabilities.md), [readiness](readiness.md), [account setup](account.md) and [automatic preservation](automation.md). Historical integration observations from upstream are not this release's host guarantee. The current release report is VALIDATION.md in the skill root.

A real collector/hook/wrapper is required for automatic triggers. Not all specialized/hosted tools emit covered hooks. Review native trust in the host UI; never alter trust records to bypass review. A skill file does not monitor, interrupt or change the desktop model by itself.

## macOS Documents access

A launchd collector can collect account readings successfully while failing to
open a registered project in Documents. Inspect each project's preservation
result; service exit zero alone does not establish access. Verify the responsible
executable from the installed service and narrowly filtered macOS TCC logs before
changing a privacy setting. The system Python shim can be the responsible path
even when `sys.executable` names a different framework interpreter.

Use System Settings → Privacy & Security → Files & Folders for Documents access
when that entry is available. Full Disk Access is broader and requires the user's
informed choice. For a verified `/usr/bin/python3` subject, Finder → Go → Go to
Folder → `/usr/bin`, then drag the exact `python3` file into Full Disk Access and
enable it. A similarly named framework library is a different identity. Do not
modify TCC databases, reset unrelated approvals or select speculative executables.

Wait for a fresh normal collector run and inspect the affected project again.
`no-low-signal` establishes background access, not a checkpoint write or resume.
Verify preservation separately in an authorized isolated fixture. Full Disk Access
applies to that launcher, not just this script. See Apple's
[file access guide](https://support.apple.com/en-mk/guide/mac-help/mchld5a35146/mac)
and [privacy settings](https://support.apple.com/guide/mac-help/mchl211c911f/mac).

## Scoped resume access

Explicit resume needs write access to the task store and the existing collector's
`preservation` lock directory. In a sandboxed host, request that exact additional
directory through its supported permission flow. The runtime takes this lock
before writing ownership, a resume receipt or grant activation; a denied or busy
lock leaves those records unchanged. Do not delete a busy lock or waive the
collector synchronization. Retry only with current authorization and a fresh
review after resolving access or contention.

Every applicable quota window retains source, account identity, observation/reset timestamps, percent remaining and threshold. Account quota is distinct from context/API/disk signals. Missing/stale/future/past-reset observations stay unknown. Recovery and scheduled readiness do not authorize task execution.

Local native notification display, exact wake timing, Windows/Linux runtime, second-device/account access and externally hosted transfers must be verified on the receiving host. A stopped/asleep/offline machine may not execute its target-time check. No conversation can be reconstructed after hard exhaustion or power loss if semantic progress was never maintained.

Official references: [Skills](https://learn.chatgpt.com/docs/build-skills), [Hooks](https://learn.chatgpt.com/docs/hooks), [App server](https://learn.chatgpt.com/docs/app-server).
