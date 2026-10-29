# Attribution

Task checkpoint 0.8 derives from the MIT-licensed task-checkpoint/checkpoint-handoff runtime by HarryBurd33. The original copyright and full MIT license are retained.

0.8 keeps verified snapshots, root handoff projection and ownership ledgers, replaces persistent stop/grant machinery with direct usage limits, and removes router dispatch, automatic enrollment, reset notification and transfer execution. No external implementation was copied for this cleanup.

The quota probe uses the local Codex app-server read-only `account/rateLimits/read` and `account/read` methods. It does not start model turns.
