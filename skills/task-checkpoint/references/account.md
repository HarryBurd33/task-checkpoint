> Historical compatibility reference inherited from v0.5.0. For this candidate, current SKILL.md, README.md, readiness.md and capabilities.md control activation, delivery and validation claims. No publishing, installing services, changing accounts or resuming after recovery is implied.

# Local account activation

Version 0.3.0 adds user-wide Codex hooks and a real per-user collector. This uses the signed-in Codex CLI account on the installed computer. Other devices and cloud sessions need their own runtime and independent authentication.

Install the managed skill with `install.py`, preserving the previous version for rollback. Then run the installed script with the actual Python executable and existing project binding:

```sh
/usr/bin/python3 "$HOME/.agents/skills/task-checkpoint/scripts/account.py" \
  --state "$HOME/.codex/checkpoint-handoff" install \
  --codex-home "$HOME/.codex" --python /usr/bin/python3 \
  --project /absolute/path/to/bound/project
```

This preserves unrelated hooks, adds seven owned definitions, registers the selected binding, and generates a native service definition. Native trust records are never edited. Review each new definition through Codex `/hooks`, matching its source and exact command before trusting it. Migrate existing managed project hooks through the installer first to avoid duplicate callbacks. Global SessionStart instructions explain how to bind new repositories; they do not initialize projects or grant permission.

Install the service using the monitor adapter's `install-service` command; it uses launchd on macOS and a current-user Task Scheduler task on Windows. See [automatic preservation](automation.md) for platform commands and observed versus simulated coverage. The collector runs every minute, without model calls merely to read usage. It checks ChatGPT authentication, writes atomic sourced signals and model availability, evaluates preservation thresholds, and then processes only authorized scheduled tickets. Failed collection never refreshes old observations. Overlapping ticks are fenced by a lock. No API fallback or account-limit bypass is installed.

The installer records the resolved `git_executable` when first available. The collector prepends only its directory to its own process PATH, preserving an existing configured Git and restoring the caller environment afterward. This lets a current-user Windows task use a user-level bundled Git without changing machine PATH. A missing configured executable fails collection without refreshing old readings.

Account state lives privately under the configured Codex directory. `enabled:false` pauses collection. `guard_percent` sets the remaining-usage reserve; existing values are preserved. Global hooks consume shared account readings and project-specific context/API/local observations. The durable threshold stop marker blocks ordinary covered work until an explicit verified resume after resource recovery. A fresh reading alone never resumes work. Tool-hook coverage is limited by the host, so background preservation also operates without a hook event.

The collector can process explicit scheduled tickets through the same router, task binding and ownership authority. Exact contract, current authorization and budgets remain required. It does not invent a task from a conversation. Only qualified task classes/providers can launch. Covered ordinary parent writes are blocked while a routed worker is active or uncertain; its own matching run identity permits the worker's covered tools.

```sh
/usr/bin/python3 "$HOME/.agents/skills/task-checkpoint/scripts/account.py" \
  --state "$HOME/.codex/checkpoint-handoff" status
```

Verify a fresh last-success timestamp, native scheduler status, actual hook delivery and a validated routed result. Configuration alone is not activation evidence. Per-task plan usage and API dollars remain unknown unless directly observed; plan windows are account-wide.

To remove activation, reconcile workers and stop/remove the managed service with `monitor.py uninstall-service`, then run:

```sh
/usr/bin/python3 "$HOME/.agents/skills/task-checkpoint/scripts/account.py" \
  --state "$HOME/.codex/checkpoint-handoff" uninstall --codex-home "$HOME/.codex"
```

Only unchanged managed hooks are removed. Unrelated hooks, private checkpoints and native trust records are retained. A customized hook/service is preserved for reconciliation. Claude Code compatibility is a separate assessment.

Private exchange also records the resolved `gh_executable` when available. The collector prepends its directory with Git only in its own process and restores PATH afterward. A missing configured dependency fails without refreshing old signals. On packaged Windows apps, an interactive GitHub login may be isolated from native Task Scheduler. Verify actual scheduled exchange and authenticate the native user context independently when required; never copy credentials.

## Observation-only restoration

Set observation_only to true in the existing reviewed account configuration to
collect fresh quota/model metadata and evaluate pause preservation without
processing planned dispatch, scheduled task wakes, private publication or private
receive. Existing project settings remain stored. The tick result records
observation_only: true and empty scheduled/transfers/receives results. The
existing enabled flag still controls collection, and the existing collector
service must be verified independently. This mode neither clears task stops nor
resumes work; explicit reviewed task recovery remains required.

## Repair removed hook definitions

Collector success does not establish hook registration or delivery. `account.py
status` reports `hook_registration`, exact managed-definition counts, whether the
receipt exists, and the last delivery separately. A historical timestamp or a
complete configuration never proves a fresh event in the intended desktop chat.

Normal `restore-hooks --codex-home CODEX-HOME --backup BACKUP` requires its existing
managed receipt and preserves unrelated hooks and native trust. If that receipt
was lost, the current user may authorize explicit recovery in a repair context:

```sh
python3 SKILL/scripts/account.py --state ACCOUNT-STATE restore-hooks --codex-home CODEX-HOME --backup ACCOUNT-STATE/hooks-temporary-backup-ID.json --recover-receipt --python /absolute/installed/python3
```

The backup must contain exactly one canonical installed definition for every
managed event, using that account/profile, script and recognized Python. Changed,
missing, duplicated or wrong-event callbacks require manual reconciliation.
Recovery validates the full proposed write before saving an exact managed receipt
and restoring definitions. If the hook write fails after the receipt is saved,
retain both files and retry normal restoration; partial progress is not success.
The extended recovery form deliberately stays outside the stopped-task maintenance
exception. Do not resume a different task to run it.

Verify all restored definitions against existing native trust without creating
trust records. If definitions need review, use the host's human review flow. A
running desktop chat can retain an older configuration: verify a new native event
with the exact current chat ID, root and timestamp. If a fresh turn does not reload
it, save active work before a user-performed app restart. Never force-restart other
chats, forge a callback, or count a new CLI process as desktop delivery.

Unbound account-maintenance reads record delivery without enrolling a new domain
task. Ordinary covered tools still follow the existing enrollment policy. Delivery
receipts contain metadata, not execution permission or a new resume grant.
