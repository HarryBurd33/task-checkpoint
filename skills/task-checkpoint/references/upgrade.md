# Upgrade from 0.7

0.8 deliberately retires the persistent stop/grant/review system, automatic enrollment, router execution, reset notifications and automatic transfers. Historical releases remain in Git tags. Existing snapshot schemas, manifests and ownership ledgers remain readable; routing data inside old snapshots is retained as task data but is never executed.

1. Remove old managed global hooks before installing:

   ```sh
   python3 "$HOME/.agents/skills/task-checkpoint/scripts/account.py" --state "$HOME/.codex/checkpoint-handoff" uninstall --codex-home "$HOME/.codex"
   ```

   If an old hook blocks the command in Codex, run it in your terminal. Fully quit/reopen Codex if a cached callback remains. The 0.8 compatibility hook always returns an empty response, even for cached registrations. Native hook trust and unrelated definitions are preserved.

2. Upgrade with `install.py --skills-dir "$HOME/.agents/skills" --repair`. For an old managed project hook installation, also pass `--project /path/to/project` to restore its exact recorded pre-install hook configuration. Customized configurations require comparison; the installer preserves them.

3. Old pause/grant files are ignored. Optionally archive them with `usage.py --root PROJECT migrate`, adding the exact active `--owner NAME` before `migrate` when needed. This leaves snapshots, owner refs, leases and semantic input intact. Existing explicit human holds or native permission decisions remain current instructions.

4. Set the current choice with `usage.py set --percent N` or `--exhaustion`. Old grant policies do not silently migrate; the current user's choice is authoritative. Without a new choice the default is 20% remaining.

5. An existing minute collector calling `account.py tick` can remain: 0.8 collects quota only, regardless of old dispatch settings. It does not restart tasks, save across registered projects, switch accounts, notify or acquire ownership. A removed version-specific Codex CLI path falls back to the stable `codex` command on PATH while retaining the same configured profile. No service is created by 0.8. To disable an old OS service, use its existing service receipt and the OS service manager; do not remove unrelated jobs.

When allowance returns, read the handoff and say “Continue.” No pause-clearing procedure remains. Actual provider limits and current permissions still govern work.
