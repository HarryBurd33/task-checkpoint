# Task checkpoint 0.8.3

Completes the optional Windows/Linux notification adapters, read-only quota-reset verifier and metadata-preserving managed upgrades introduced in the 0.8.2 candidate. The 0.8.2 tag exposed an intermittent Windows total-process deadline; 0.8.3 allows up to 30 seconds including PowerShell startup and API loading, with the notification loop still bounded at eight seconds. Timeouts never automatically retry a notification.

Persistent pauses and automatic task resume remain removed. The one-shot tools change no ownership, hooks, notification permissions, thresholds or services. Existing explicit human holds remain controlling. Human-visible display on Windows/Linux and a future real account reset remain separate observations.

Validation includes 74 source/export regression tests, public-file/skill validation, all applicable account/reset windows, failed/unknown observations, hostile notification content, managed metadata preservation and hosted Windows/Linux native evidence. The failed 0.8.2 tag is retained; this is a new version rather than rewritten history.
