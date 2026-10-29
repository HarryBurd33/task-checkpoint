# Task checkpoint 0.8.2

Optional native notification adapters and a read-only real-reset verifier complete the remaining cross-platform checks while retaining the simplified 0.8 workflow. Nothing automatically resumes task implementation. Existing explicit holds, task state, ownership and native permission settings remain controlling.

Windows uses a bounded temporary WinForms tray icon; Linux uses the existing user notification daemon; macOS uses existing notification access. Results distinguish command acceptance, an OS receipt/event and actual visible-display evidence. Hosted Windows services may have no interactive desktop. Linux native CI uses an isolated desktop/notification daemon. Actual human visibility on another desktop remains unverified.

Quota-reset tests use simulated clocks. Real account reset verification needs a user-authorized future follow-up and actual post-reset same-account readings; no release or test can establish that future result in advance.

Managed upgrades preserve prior file/directory uid, gid and modes before replacement and retain rollback bytes. The installer changes no native hook or notification settings unless the user separately requests an exact legacy project-hook retirement.
