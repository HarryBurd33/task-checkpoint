# Host requirements and evidence

Manual save/verify/resume requires Python 3.9+, Git, an initial commit and writable local files. User-wide Codex discovery uses ~/.agents/skills. Native CLI account telemetry uses a supported signed-in account/rateLimits/read source. Inspect the installed CLI capabilities before activation; API-key-only access does not imply subscription allowance.

Use [capabilities](capabilities.md), [readiness](readiness.md), [account setup](account.md) and [automatic preservation](automation.md). Historical integration observations from upstream are not this release's host guarantee. The current release report is VALIDATION.md in the skill root.

A real collector/hook/wrapper is required for automatic triggers. Not all specialized/hosted tools emit covered hooks. Review native trust in the host UI; never alter trust records to bypass review. A skill file does not monitor, interrupt or change the desktop model by itself.

Every applicable quota window retains source, account identity, observation/reset timestamps, percent remaining and threshold. Account quota is distinct from context/API/disk signals. Missing/stale/future/past-reset observations stay unknown. Recovery and scheduled readiness do not authorize task execution.

Local native notification display, exact wake timing, Windows/Linux runtime, second-device/account access and externally hosted transfers must be verified on the receiving host. A stopped/asleep/offline machine may not execute its target-time check. No conversation can be reconstructed after hard exhaustion or power loss if semantic progress was never maintained.

Official references: [Skills](https://learn.chatgpt.com/docs/build-skills), [Hooks](https://learn.chatgpt.com/docs/hooks), [App server](https://learn.chatgpt.com/docs/app-server).
