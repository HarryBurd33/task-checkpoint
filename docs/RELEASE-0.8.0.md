# 0.8.0: direct limits and handoffs

Task checkpoint now works until completion or a chosen remaining-usage threshold, saves a verified handoff at that threshold, and ends the run. A current instruction can directly change the limit to 20%, 10%, a custom percentage or exhaustion. When allowance recovers, ordinary continuation is enough.

Removed: persistent pause enforcement, staged grants, required recovery reviews, maintenance command allowlists, automatic enrollment, router execution, automatic account/transfer dispatch and reset notifications. Installation creates no hooks or background services. The compatibility hook is inert even if an old process still invokes it. An existing account collector can continue to collect quota; it never implements tasks.

Retained: checkpoint hashes, prior generations, semantic progress, dirty/untracked/staged backups, preservation of unrelated HANDOFF content, ownership ledgers and uncertain-job checks. Old checkpoint schemas and ownership remain readable. Legacy policy files can be archived without changing task history or ownership.

This is a breaking API cleanup; use the upgrade guide in the skill. Historical APIs remain in 0.7 tags. Current user authorization and native permissions remain controlling. Cooperative usage checks happen at work boundaries; hard exhaustion can prevent a final save, so exhaustion mode needs milestone handoffs.

Validation: 53 focused tests passed locally. Public export tests and Linux/macOS CI validate the distributable independently. Exact real-world provider exhaustion and cross-device execution remain untested.
