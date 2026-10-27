# task-checkpoint

[![Tests](https://github.com/HarryBurd33/task-checkpoint/actions/workflows/test.yml/badge.svg)](https://github.com/HarryBurd33/task-checkpoint/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A reusable Codex skill for saving unfinished work and continuing safely in another chat, account or device. It creates a detailed project-root `HANDOFF.md`, versioned file snapshots and integrity manifests. Continuation always requires the user's explicit resume instruction and verified current authorization and ownership.

## Install for all your local Codex chats

Requires Python 3.9+ and Git. From a terminal:

```sh
git clone https://github.com/HarryBurd33/task-checkpoint.git
cd task-checkpoint
python3 install.py --skills-dir "$HOME/.agents/skills" --repair
```

The managed installer preserves an unchanged previous version for rollback and refuses to overwrite customized/unmanaged installations. The skill is installed at `~/.agents/skills/task-checkpoint`, Codex's user-wide skill directory. It is available on your next turn; if the skill list has not refreshed, restart Codex. [Official skill-discovery documentation](https://learn.chatgpt.com/docs/build-skills).

Installing the skill makes its workflow available in local chats on this computer. Other computers/accounts and cloud environments need their own installation, files, permissions and independently provisioned authentication. Installation does not enable a background service or automatically bind every project.

For PowerShell on Windows, replace the install command with:

```powershell
python install.py --skills-dir "$HOME/.agents/skills" --repair
```

Core runtime design uses Python/Git; native Windows/Linux notification delivery is not supplied. See the capability table before choosing automatic mode.

## Use it in chat

Use any of these prompts in a writable project:

- `$task-checkpoint checkpoint now` — save and verify progress, then continue if resources are healthy.
- `$task-checkpoint save and stop` — preserve work, verify the checkpoint and stop ordinary work.
- `$task-checkpoint prepare a handoff for another laptop` — preserve actual files and source history, prepare transfer instructions and a receiving prompt.
- `$task-checkpoint resume from HANDOFF.md` — inspect current files and artifacts, reconcile changes, verify resources/authority/ownership, then continue the first unfinished step.

The agent inspects existing instructions, task bindings, jobs and checkpoint state before acting. Checkpoints need a writable Git project with an initial commit. A plain chat without project/filesystem access can retain an emergency text handoff, but cannot claim it created a durable file snapshot.

A copied HANDOFF is context, not permission. Another account does not inherit your access, credentials or active ownership.

## Manual command setup

Inside the intended project, first inspect existing checkpoint stores/queues and project instructions. Ensure `.checkpoint/` is ignored by Git; do not initialize over an existing binding. Select a unique task and stable project identity. For a new single-computer task:

```sh
skill_dir="$HOME/.agents/skills/task-checkpoint"
project_dir="/absolute/path/to/project"
python3 "$skill_dir/scripts/checkpoint.py" --root "$project_dir" init \
  --task my-task --project-id owner/project --ownership local
```

`local` ownership coordinates cooperating agents sharing one Git common directory. For multiple devices, omit `--ownership local` and use the existing remote coordination authority; do not change modes to bypass another owner.

Copy `assets/task-template.json` to the bound store's `input.json` and fill it with the real objective, completion criteria, final corrections, current scope/authorization, progress, decisions/reasons, actual checks, uncertain jobs, artifacts and exact next action/verification. Then:

```sh
python3 "$skill_dir/scripts/checkpoint.py" --root "$project_dir" checkpoint \
  --input "$project_dir/.checkpoint/input.json" --trigger save-and-stop
python3 "$skill_dir/scripts/checkpoint.py" --root "$project_dir" verify
python3 "$skill_dir/scripts/checkpoint.py" --root "$project_dir" inspect
```

New bindings enable root HANDOFF output. An existing binding can opt in with `enable-root-handoff` after verifying its current canonical generation. Root output preserves unrelated text and fails closed on altered/foreign managed sections. See [full setup, upgrade, rollback, disable and uninstall](skills/task-checkpoint/README.md), [operator commands](skills/task-checkpoint/references/operator.md), and [cross-device transfer](skills/task-checkpoint/references/cross-device.md).

## What is implemented and what requires setup

| Capability | Implementation and limits |
|---|---|
| Manual save/verify/explicit resume | Python/Git runtime; atomic versioned generations, manifests and previous-generation recovery |
| Preserve unfinished work | Working files, distinct staged index blobs, binary/untracked/deleted files, recorded staging/modes; never silently overwrites destination edits |
| Root handoff | Next unfinished action/verification first; progress, evidence, corrections, files, uncertain jobs and receiving prompt |
| Ownership | Local or append-only remote Git coordination for cooperating agents; unknown jobs/active workers prevent release |
| Automatic low-allowance save | Opt-in project registration plus a real collector and trusted hooks/wrapper; default <=20% remaining, existing thresholds preserved |
| Readiness after reset | Existing minute collector processes a notification-only ticket targeting the latest blocking reset +60 seconds; fresh readings/lifecycle/ownership still required |
| Native notification | macOS adapter supplied; command acceptance/display/permissions need host validation. Windows/Linux native notification requires another reviewed adapter |
| Cross-device continuation | Transfer actual source history + verified private checkpoint bundle + explicit external exports, then independently authenticate/review/acquire ownership |
| Optional Usage Router | Retained for compatibility; separately authorized bounded work, qualification, tools/privacy/budget and ownership gates required |

Manual mode needs no model/API call, scheduler or background service. Automatic mode requires the supported account-limit source, an awake/available host, access to the project, a configured collector and delivered/trusted hook coverage. A skill file alone cannot monitor usage or guarantee interruption. The default 20% is a preservation reserve, not an estimate of exact work remaining. Explicit task-local overrides are described below. Account allowance, context capacity, API spending and disk/memory signals are separate.

Readiness checks **never execute unfinished implementation** or clear a stop. Recovery requires fresh adequate readings and an explicit reviewed user resume. A scheduled target is not guaranteed execution/recovery time. No automatic account switching, credential transfer, paid fallback or purchase is performed. [Readiness setup and manual fallback](skills/task-checkpoint/references/readiness.md).

## Continue beyond the preservation reserve

The automatic verified stop at 20% remains the default. After it happens, explicitly tell the agent:

- **“Continue to 10%”** — grant a pending task-local override, perform the normal reviewed resume, then save/stop again at <=10% in any applicable quota window.
- **“Continue until allowance is exhausted”** — separately authorize waiving the numeric reserve for this task. Milestone saves continue; Codex's actual refusal, other resource stops, ownership and permissions remain enforced.

An override never adds allowance, switches accounts or enables paid fallback. It binds current project/task/account/window/reset identities and expires at reset or lifecycle change. Grants are not transferable. Granting alone is not resumption. Hard exhaustion can prevent another checkpoint, so retain milestone saves. [Commands and revocation](skills/task-checkpoint/references/reserve.md).

Quota reads and narrowly parsed maintenance CLI commands remain available during a stop, so hooks no longer need to be disabled merely to inspect, grant or resume. Ordinary commands and shell chains remain stopped.

## Test and verify

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
```

The standard-library suite uses isolated repositories, simulated quota/clock signals and subprocess fixtures; it does not deliberately exhaust real allowance or make paid model/API calls. CI runs the suite on Linux and macOS. CI results, local checks, simulated platform adapters and prior fresh-context exercises are distinct evidence. [Validation report](validation/REPORT.md).

The release does not claim every host/integration is verified. Actual native notification display, exact wake timing, a second physical laptop/account and native Windows/Linux behavior for this version require deployment verification. Files over 16 MiB, symlinks and external artifacts need an explicitly reviewed preservation route. Secret detection uses patterns and cannot certify arbitrary contents secret-free. A crash can leave a stale root projection; verification detects it and refresh is explicit.

## License

[MIT](LICENSE), copyright 2026 HarryBurd33. The same notice is included inside the installable skill. [Source attribution](skills/task-checkpoint/ATTRIBUTION.md).
