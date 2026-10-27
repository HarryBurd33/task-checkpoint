> Historical compatibility reference inherited from v0.5.0. For this candidate, current SKILL.md, README.md, readiness.md and capabilities.md control activation, delivery and validation claims. No publishing, installing services, changing accounts or resuming after recovery is implied.

# Two Codex accounts and local text workers

Version 0.5 adds explicit profile-pinned Codex workers and a macOS `local_text` execution adapter. Both reuse the existing checkpoint store, router journal, acceptance commands and ownership ledger. No second queue, credential transfer, paid API fallback or desktop-account switching is introduced.

Each plan worker has an absolute `codex_home` and the SHA256 fingerprint of its actual account ID. Before launch, the native probe must report ChatGPT authentication and the same account identity as that profile's local login. Its own fresh allowance, model and effort must be available. The child gets that exact `CODEX_HOME`; API key and alternate API endpoint environment variables are removed. A changed or logged-out profile fails before process intent. Folder rules and native hook trust remain device/profile-local.

The existing account collector accepts optional `codex_profiles` entries with `id`, `codex_home` and `account_fingerprint`. Distinct account windows remain under `signals.json.accounts`; aliases of one account cannot count twice. A failed probe is unknown, never refreshed old capacity. The status output reports each profile's observed windows. Primary `signals.json.records` still govern the coordinator's reserve. Worker selection uses its pinned account readings and rechecks them immediately before launch. A stop caused by a secondary account retains that account fingerprint: healthy primary readings cannot clear it. Recovery still requires explicit reviewed resume.

Keep the current reserve (20% in this deployment). This feature does not automatically bypass a coordinator stop by changing accounts or models. A separate CLI worker does not move the current desktop conversation to another account. For a chat/device handoff, save/verify, reconcile jobs, release, transfer or inspect the existing bundle, then perform fresh authorization/resource/ownership review in the destination. Never copy account credentials or execution receipts.

`local_text` uses the already installed local Ollama endpoint, pinned model digest, no proxy/redirects, a clean credential-free environment and macOS confinement permitting only that loopback port. It receives only the bounded objective and output schema; it cannot read the checkpoint, acceptance oracle, project files or account secrets. Model output is JSON data. The coordinator writes the result and runs independent acceptance. The adapter fixes context at 4096, generation at 512, and thinking off. The runtime must already be running; no model download or another service is installed.

Qualification binds model digest, adapter-source hash, exact output schema, tools, privacy and task class. Only checked `checkpoint-extraction` text tasks passed in this deployment. The schema-free baseline had a branch-type failure, retained separately; schema-constrained qualification passed all three unchanged expected cases. This does not qualify local coding, dependency reasoning, shell tools or 64K context. Failed acceptance remains a real failure and can escalate only within the task's authorized providers/budget. `local_only` privacy forbids cloud routes. Electricity/hardware cost remains unknown even though local inference has no paid API charge.

Set `prefer_local_for_qualified:true` in the private router config to prefer an eligible free worker over a prior plan worker despite switching hysteresis. Ineligible local tasks remain manual or select another qualified permitted worker. Estimated relative cost is a preference estimate, not measured subscription savings.

Manual inspection and a reviewed task use the existing commands, with fresh multi-profile signals explicitly supplied:

```sh
python3 "$HOME/.agents/skills/task-checkpoint/scripts/account.py" --state "$HOME/.codex/checkpoint-handoff" status
python3 "$HOME/.agents/skills/task-checkpoint/scripts/router.py" --root PROJECT dispatch \
  --input PROJECT/.checkpoint/TASK.json --config PROJECT/.checkpoint/router-config.json \
  --collector signals --signals "$HOME/.codex/checkpoint-handoff/signals.json"
```

A dry run does not authorize execution. After the standard reviewed resume and exact task/config/acceptance authorization, add `--execute`. Planned boundaries use the same native collector and exact approvals; no model call polls usage. Maintain semantic input and work packages before substantial work. New private source changes invalidate approval and need fresh review. Imported state never restores authority.

Other machines need independent profile authentication, local paths and native verification. Local confinement is currently Mac-only. Existing Windows 0.4/two-device work remains deferred; no Mac source paths or claims should be copied as Windows proof.

Private transfers preserve a stop’s affected account fingerprints as guard data. Account-scoped stops use transport envelope version 2 so older readers fail closed instead of discarding identity; unscoped version 1 bundles remain readable. Upgrade both endpoints before moving an account-scoped stop. After reviewed adoption, every affected account still needs fresh adequate observations before a separate reviewed resume; a healthy primary or missing secondary cannot clear it. No credentials or execution permissions are transferred.
