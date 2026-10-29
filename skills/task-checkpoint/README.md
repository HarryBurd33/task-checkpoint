# Installation and operation

Install from the public repository using its root `install.py`, or from a standalone copy of this skill folder using this folder's `install.py`:

```sh
python3 install.py --skills-dir "$HOME/.agents/skills" --repair
```

Use `$task-checkpoint` in any project. Reopen an existing chat to refresh its loaded skill instructions. No hooks or background services are installed. `--status` compares all managed bytes; `--uninstall` removes only an unchanged managed installation and retains private checkpoints. Rollback archives are kept beside the skill in `.task-checkpoint-rollback/`.

See [commands](references/commands.md) for actual task use and [upgrade](references/upgrade.md) when coming from 0.7.
