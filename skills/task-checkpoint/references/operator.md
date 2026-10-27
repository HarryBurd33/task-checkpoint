> Historical compatibility reference inherited from v0.5.0. For this candidate, current SKILL.md, README.md, readiness.md and capabilities.md control activation, delivery and validation claims. No publishing, installing services, changing accounts or resuming after recovery is implied.

# Operator procedure

Requires Python 3.9+ and Git, with per-device Git identity and authentication. No third-party Python packages, model API, queue daemon or background watcher is required for checkpointing. The optional [Usage Router](router.md) adds configured boundary execution using the same task format and lease.

## Bind once

Inspect existing checkpoints/queues/device records first. Bind one task to one workspace; this prevents unrelated tasks sharing a latest pointer. Existing external formats stay authoritative for their own work: list them as source/artifact/dependency references rather than overwrite them. `--store PATH` selects a new explicitly chosen location; importing an existing incompatible store needs a reviewed migration. `init` refuses an existing binding.

From the repository root, after its initial commit:

```sh
python3 SKILL/scripts/checkpoint.py --root . init --task task-slug --project-id owner/repository
```

This defaults to online remote ownership. `--ownership local` is an explicit single-machine mode. Ignore `.checkpoint/` in Git before saving. Copy `SKILL/assets/task-template.json` to `.checkpoint/input.json`, then fill it from observed work. List selected artifacts using repository-relative POSIX paths and `preserve: true` to back them up. Changed tracked and nonignored untracked regular files are backed up automatically. Deleted files are recorded. Ignored files are excluded unless explicitly listed; explicitly list necessary ignored outputs. Symlinks, internal Git state, credential paths and files over 16 MiB fail closed. Large datasets need an externally verified artifact store and stable reference, not a fabricated backup.

```sh
python3 SKILL/scripts/checkpoint.py --root . checkpoint --input .checkpoint/input.json --trigger milestone
python3 SKILL/scripts/checkpoint.py --root . verify
python3 SKILL/scripts/checkpoint.py --root . inspect
```

Triggers: manual, milestone, pre-switch, error, shutdown, save-and-stop, low-resource. Input schema is `assets/task.schema.json`; output schema is `assets/checkpoint.schema.json`. The bundled validator implements only the subset used by these schemas (types, required fields, properties, arrays, enum, minLength, finite numbers). JSON schema files also work with a full external validator.

## Review and resume

`inspect` does not grant implementation permission. It returns checkpoint ID, current fingerprint, next action and issues. Read the actual current user instruction and verify the next action before preparing this review:

```json
{
  "checkpoint_id": "COPY_FROM_INSPECT",
  "task_id": "task-slug",
  "next_action": "EXACT_CHECKPOINT_ACTION",
  "verification": "EXACT_CHECKPOINT_VERIFICATION",
  "current_fingerprint": "COPY_FROM_INSPECT_AFTER_REVIEW",
  "observed_at": "CURRENT_TIME_WITH_TIMEZONE",
  "authorization": {
    "confirmed": true,
    "scope": "Current authorized bounded work",
    "source": "Current user request reference"
  },
  "resources": {"adequate_for_bounded_action": true, "evidence": "Fresh readings or explicitly bounded manual assessment; unknown measurements recorded", "observed_at": "CURRENT_TIME_WITH_TIMEZONE"},
  "resolutions": {}
}
```

Each reported issue requires its own resolution object keyed by the exact issue text, containing `evidence` and a fresh `observed_at`. Job issues also require `status`: completed, failed, cancelled, or running-observe-only. Running-observe-only permits observation, not retrying or duplicating that operation. Reviews expire after five minutes; checkpoint stale threshold is 24 hours. Reconcile newer instructions explicitly in the scope/evidence. These attestations record the operator's checks; the runtime cannot independently prove arbitrary authorization or provider status.

```sh
python3 SKILL/scripts/checkpoint.py --root . resume --review .checkpoint/review.json --owner mac-agent --capability python
python3 SKILL/scripts/checkpoint.py --root . owner-check
python3 SKILL/scripts/checkpoint.py --root . run --input .checkpoint/input.json -- python3 bounded_task.py
python3 SKILL/scripts/checkpoint.py --root . release
```

`run` checks current ownership and a reviewed resume, saves a pre-boundary snapshot, executes the selected command, then records its exit status and a post-boundary checkpoint. Update semantic input after meaningful work. An error snapshot records failure, not success. SIGINT/SIGTERM requests preserve the child's uncertain status without asserting cancellation; the child may outlive the wrapper. SIGKILL, power loss and inaccessible files can lose everything since the last durable save. Wrappers are not an OS sandbox. Use a fresh resume review after new checkpoints before starting another bounded command.

## Ownership and transfer

Remote mode uses `refs/heads/checkpoint-owner/TASK` as one append-only ownership ledger. Acquire/release commits have the exact observed tip as parent, and ordinary non-force pushes reject competing siblings. No live queue database is copied. Claims do not expire; network failure blocks acquisition/checks. Never switch to local mode to bypass a remote owner. Branch protections may prohibit ledger branches; use the existing queue's authoritative lease through a reviewed adapter in that environment instead of disabling protections. No generic queue lease API was observed in the inspected host.

Before switching devices: stop the bounded writer, verify active jobs, checkpoint, release ownership, and push source through the established workflow. Transfer the **entire** private `.checkpoint` bundle through an approved private channel, separately from source Git. Do not transfer only `HANDOFF.md`. Keep the old copy until the destination verifies the manifest. On the destination, clone the correct branch/commit, provision credentials independently, place the bundle at `.checkpoint`, inspect, reconcile, state and verify the next action, then resume and acquire ownership. Absolute external store bindings need rebinding after review; default stores are relative.

For dirty file recovery, compare `snapshots/ID/files/PATH` against the current file and apply an explicit patch or restore into a separate worktree. The runtime does not overwrite either version. Deletions and staged/unstaged differences are recorded as state; staging is not recreated automatically. Ignored or oversized artifacts require separate transfer. Hashes detect accidental corruption/missing files, not malicious rewriting of both content and manifest.

## Recovery and removal

`verify --previous` checks the retained prior generation. `recover-previous --reason TEXT` records the discarded pointer and promotes the verified previous generation without changing the worktree. Never silently recover. If `writer.lock` remains after SIGKILL, verify the recorded process on the originating device and that no writer is active, preserve the lock as evidence, then remove it manually. Ownership is separate: only the verified owner can release normally. A lost ownership token requires human investigation and a reviewed append-only release commit; no lock-stealing command is provided.

Installer: `python3 install.py --skills-dir DIR [--project PROJECT]`. It installs exactly this version and refuses customized managed copies. It saves a receipt and prior project hook file. Hooks still require native trust review. Uninstall: `python3 install.py --skills-dir DIR [--project PROJECT] --uninstall`. Preserve private state first. It removes only unmodified managed files and restores the prior hooks file. It does not delete checkpoints, queue state, Git branches, credentials or the repository.

Emergency chat fallback when durable writes fail: objective; last verified commit; unsaved files; active job IDs/outcomes; next bounded action plus verification; prior valid checkpoint path. Clearly label this as an emergency copy, not a successful durable save.
