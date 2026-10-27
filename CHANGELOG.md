# Changelog

## 0.6.0

- Keep the configured default reserve (20%) and add explicit task-local 10% or exhaustion overrides after the verified stop.
- Pending grants require fresh reviewed resume and exclusive ownership; preserve context/API/resource/provider stops, unknown readings and job gates.
- Pin account/window/reset and checkpoint identities; expire/revoke grants and exclude them from transfers.
- Allow quota reads and narrow maintenance commands while ordinary work is stopped.
- Restore only recorded temporarily disabled hooks, preserving unrelated edits and native trust.

## 0.5.1

First public distribution of the reusable skill, extending the MIT checkpoint runtime:

- Managed root HANDOFF.md with next action and verification first, preserved user text and tamper detection.
- Notification-only readiness tickets in the existing collector, targeting all blocking resets plus 60 seconds; explicit user resume remains required.
- Distinct staged index blob preservation alongside working-tree bytes and Git history.
- Account identity retained for single-profile telemetry; anonymous windows cannot establish recovery.
- Lease release blocked by unresolved canonical jobs as well as active/uncertain routed workers.
- Failed automatic preservation bounded to three attempts, with explicit repair/retry.
- User-wide managed installation, rollback support, cross-device procedures, capability documentation, reproducible tests and CI.
