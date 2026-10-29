# Task checkpoint

A Codex skill that keeps working until the task is complete or a chosen **remaining-usage** limit is reached, then saves a verified Markdown handoff. Version 0.8 removes persistent pauses, continuation grants, automatic task dispatch and tool-blocking hooks.

## Install globally

Requires Python 3.9+ and Git. Clone this repository and run:

```sh
git clone https://github.com/HarryBurd33/task-checkpoint.git
cd task-checkpoint
python3 install.py --skills-dir "$HOME/.agents/skills" --repair
```

The skill is available as `$task-checkpoint` in any project. Reopen a chat if its skill catalog is already loaded. Installation creates no hooks or background services. Existing managed versions are archived for rollback; customized installations are preserved for comparison. To check installed bytes:

```sh
python3 install.py --skills-dir "$HOME/.agents/skills" --status
```

## Use it

- `$task-checkpoint Continue working until completed or 20% remains.`
- `Continue until 10% remains.`
- `Continue until 7.5% remains.`
- `Continue until completed or exhausted.`
- `Save a handoff now.`
- `Continue from HANDOFF.md.`

A current instruction changes the task limit directly. At the limit, Codex saves progress and ends that run. When allowance returns, say “Continue.” There is no pause latch to clear or recovery approval to manufacture. Native permissions, actual provider denial, ownership and uncertain job outcomes still apply.

The default is 20% remaining across applicable account quota windows. Unknown telemetry is reported as unknown and recollected; it does not become a fabricated low-quota stop. Exhaustion mode bypasses the numeric reserve, so keep milestone saves: a hard limit may prevent a final save.

The agent must maintain semantic progress and check fresh usage at work boundaries. This skill cannot continuously interrupt inference, reconstruct unsaved conversation state, or guarantee a save after hard exhaustion. The read-only collector uses the authenticated Codex CLI app-server when available; no model turn or paid API call is made.

See [commands](skills/task-checkpoint/references/commands.md) and [upgrade from 0.7](skills/task-checkpoint/references/upgrade.md). Verified snapshots preserve dirty, untracked and staged bytes while retaining the previous generation. Checkpoints are private task data; do not push them to a public repository. Cross-device handoffs require a private transfer and independently provisioned permissions.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
python3 release.py --output dist/task-checkpoint-public.zip
```

MIT licensed. Historical 0.7 releases remain available through Git tags; their pause/router APIs are retired in 0.8.
