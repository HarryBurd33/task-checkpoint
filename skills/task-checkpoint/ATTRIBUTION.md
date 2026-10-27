# Sources and modifications

Adapted from task-checkpoint 0.5.0, source https://github.com/HarryBurd33/checkpoint-handoff.git at b2ea94fd0f9803b460ee5c0ca5e304208abad78a, inspected 2026-10-26 America/Denver. MIT copyright 2026 HarryBurd33; full LICENSE retained. Installed/source runtime hashes and baseline retained in the build validation records.

Changes: managed root HANDOFF projection and templates; notification-only readiness in the same private store/collector; bounded failed preservation attempts; focused activation/setup/transfer documentation. The optional existing router/transfer modules remain for compatibility and require separate authorization. No external implementation copied.

Primary reference inspected: [Codex app-server account limits](https://learn.chatgpt.com/docs/app-server). Other inspected foundations: ciumbar/continuity-handoff (MIT) and lifang336/codex-session-handoff (Unlicense), rejected as replacements because they introduce incompatible stores and lack verified quota/ownership handling; immutable remote revisions unverified. Hugging Face skipped: no model/dataset needed.
