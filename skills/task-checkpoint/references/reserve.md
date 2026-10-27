# Explicit reserve overrides

The normal account preservation reserve is 20% by default. Existing configured guards remain unchanged. At or below that reserve, save and verify the checkpoint and stop ordinary work first. A fresh current user choice may then select `ten` or `exhaustion` for this task only.

An override changes the checkpoint policy. It does not change account quota, grant task permission, enable paid API fallback, switch accounts, cancel jobs or defeat context/API/disk/ownership stops. A displayed 0% can be rounded; exhaustion mode permits numerical zero only while the provider has not denied usage. Actual provider refusal still stops work and can prevent a final save. Preserve milestone state throughout.

## Grant, review, resume

Example after an explicit “continue to 10%” instruction, using absolute project/skill paths and a fresh native account signal file:

```sh
python3 SKILL/scripts/reserve.py --root PROJECT grant --mode ten --signals SIGNALS --reason 'User chose continue to 10 percent' --source 'Current explicit user instruction'
```

For a separate explicit “continue until allowance is exhausted” choice:

```sh
python3 SKILL/scripts/reserve.py --root PROJECT grant --mode exhaustion --signals SIGNALS --reason 'User chose continue until allowance is exhausted' --source 'Current explicit user instruction'
```

The existing store receives `allowance-override.json`, a private signal snapshot and audit history. Fields include project/task identity, the original verified stop pointer, mode, pending/active/revoked state, user reason/source, account/window/reset identities and lifecycle binding. Full snapshots, credentials, permissions and account allowance are not invented by the record. Pattern checks are incomplete; keep this local state private.

Grants require a verified stop checkpoint, fresh sourced identified quota readings with reset times, no incomplete preservation, no unresolved jobs/workers, and no competing owner. All stopped non-account resources need fresh adequate readings. Existing project non-account observations are combined with native account readings. Do not pre-arm an override while allowance is healthy. `ten` is unavailable at <=10%; exhaustion is then a separate user choice.

Granting leaves ordinary work blocked until the normal review/resume flow passes. State the first unfinished action and verification, inspect current files/artifacts/instructions, write a fresh authorized resource/job/conflict review, then:

```sh
python3 SKILL/scripts/checkpoint.py --root PROJECT resume --review REVIEW --owner SAME-VERIFIED-OWNER --capability REQUIRED-CAPABILITY
python3 SKILL/scripts/checkpoint.py --root PROJECT owner-check
```

The existing matching lease may be retained; another owner is never replaced. If a collector makes a newer checkpoint during review, the original verified stop remains pinned and the latest checkpoint still needs its own current review. The CLI keeps the supplied signal path for fresh re-reading; direct API grants use their private snapshot, which becomes stale after 120 seconds. Refresh readings/regrant when needed. The resource review must truthfully assess the bounded action under the chosen reserve.

## Boundaries and revocation

`ten` saves/stops again at <=10% in any applicable window. `exhaustion` disables only the numeric account reserve. Both retain explicit provider denial, other resource stops, missing/stale/future/unsupported/foreign/missing-window observations, ownership and uncertain-operation gates. Account-wide concurrent consumption can change between readings.

The first pinned reset expires the grant to the normal configured policy. A lifecycle change cannot revive a previous grant even if a task later returns to active. Completed/canceled/transferred tasks use the normal policy and need new current authorization for future work. Private grants are excluded from the existing transfer allowlist; a receiving machine must use its own current user instruction, readings, permissions and ownership.

```sh
python3 SKILL/scripts/reserve.py --root PROJECT status
python3 SKILL/scripts/reserve.py --root PROJECT revoke --reason 'Restore the normal preservation reserve'
```

Revocation returns to the configured reserve on the next check. It does not resume work. Reset/recovery notifications remain notification-only.

## Maintenance while stopped

Quota reads and exact local commands through installed `reserve.py` (`status`, `grant`, `revoke`) or `checkpoint.py` (`inspect`, `verify`, `policy`, `checkpoint`, `resume`, `owner-check`, `release`, `recover-previous`, `refresh-handoff`) remain available through covered PreToolUse/PostToolUse hooks. Use a direct `python3 /absolute/SKILL/scripts/FILE.py --root /absolute/PROJECT COMMAND ...` invocation. Shell chains, redirects, substitutions, arbitrary Python code, different scripts/projects and ordinary `run` commands receive no maintenance exemption. This is a cooperative workflow guard, not a general-purpose security sandbox.

If hooks were previously removed for this upgrade, restore only the exact definitions from the recorded temporary backup:

```sh
python3 SKILL/scripts/account.py --state ACCOUNT-STATE restore-hooks --codex-home CODEX-DIRECTORY --backup ACCOUNT-STATE/hooks-temporary-backup-ID.json
```

The backup must be inside the existing account state, contain the exact recorded managed definitions, and have the expected temporary-backup name. Restoration is idempotent, keeps unrelated new entries and does not alter native trust. This maintenance command and account `status` are allowed while stopped. No background service, new queue or watcher is created by an override.
