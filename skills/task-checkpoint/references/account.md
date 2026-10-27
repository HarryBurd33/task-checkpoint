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
