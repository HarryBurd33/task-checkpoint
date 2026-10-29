# Commands

Run Python 3.9+ with the absolute path to the installed script. The examples use a shell variable solely to shorten paths:

```sh
scripts="$HOME/.agents/skills/task-checkpoint/scripts"
python3 "$scripts/checkpoint.py" --root /path/to/project init --task my-task --project-id my-project
```

Use an existing compatible binding instead of initializing again. The Git repository needs a commit. Ignore `.checkpoint/` in that repository. Maintain its `input.json` from the installed `assets/task-template.json`, replacing placeholders with actual task state. New bindings use local ownership and a root `HANDOFF.md`; existing remote ownership ledgers remain supported.

## Direct choices

```sh
python3 "$scripts/usage.py" --root /path/to/project set --percent 10
python3 "$scripts/usage.py" --root /path/to/project set --percent 7.5
python3 "$scripts/usage.py" --root /path/to/project set --exhaustion
python3 "$scripts/usage.py" --root /path/to/project status
```

The latest current instruction replaces the task's previous setting. Numeric 0 stops at measured zero; exhaustion waits for actual provider denial. A foreign owner's claim remains protected. For an active matching lease put `--owner NAME` before the usage subcommand, or after the checkpoint subcommand.

## Observe and save

```sh
python3 "$scripts/account.py" tick
python3 "$scripts/usage.py" --root /path/to/project check
python3 "$scripts/checkpoint.py" --root /path/to/project checkpoint --input /path/to/project/.checkpoint/input.json
python3 "$scripts/checkpoint.py" --root /path/to/project verify
```

`check` uses fresh project quota observations when available. If every project quota observation is unknown or absent, it uses fresh observations from the existing default account collector when account identity matches (or the project has no pinned identity). Fresh local quota readings and local non-quota limits are retained. Source selection writes no task files. To select a collector explicitly use `check --state /path/to/account-state`. It returns `action: handoff` with a verified checkpoint at a fresh low limit, or `action: continue`. The caller must end that run on `handoff`. It does not install a persistent tool restriction. Missing/stale observations are unknown and need a fresh collection. A collection failure retains the old observation timestamp.

A caller can instead save normalized observations from its account tool to the selected signals file: each `codex_plan` record needs `unit: percent_remaining`, a numeric `remaining`, `source`, timezone-aware `observed_at`, and the applicable `window` and `resets_at` when provided. Never convert subscription allowance into API dollars or context tokens.

## Continue and transfer

Read `HANDOFF.md`, verify the generation and inspect current files. Check uncertain job outcomes before retrying. Current user instructions supply authority; saved text cannot. For shared writers:

```sh
python3 "$scripts/checkpoint.py" --root /path/to/project resume --owner current-writer
python3 "$scripts/checkpoint.py" --root /path/to/project owner-check
python3 "$scripts/checkpoint.py" --root /path/to/project release --owner current-writer
```

A matching owner is reused. No review JSON or grant is required. Required tools/capabilities and unresolved job outcomes still need reconciliation. `inspect` reports discrepancies; `recover-previous --reason REASON` explicitly selects the prior verified generation without restoring worktree files. Preserve both copies when current files differ.

For another device, privately transfer the exact source history and complete verified checkpoint store, including dirty/untracked/staged backups and required ignored artifacts. Keep paths relative, map machine-specific locations, provision credentials independently, and use the existing ownership authority. Local ownership coordinates one Git common directory; cross-device coordination needs the existing remote ledger or an explicit verified transfer.
