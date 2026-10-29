# task-checkpoint 0.7.6

Version 0.7.6 routes same-owner stopped checkpoint saves through the existing fenced preservation path, keeping the stop and saved generation aligned. Raw snapshots and rewinding away from a pinned stop fail closed. Saving never resumes work or replaces ownership.

Version 0.7.5 fixes stopped-chat compaction deadlocks and read-only diagnosis before a first checkpoint. Persistent pauses still block ordinary tools and require explicit reviewed resume. Missing semantic input is reported on every startup.
Paused recovery can read the verified handoff and ask the user for clarification.
Later reviews can explicitly select the existing registered collector, retaining
its reserve and rechecking every quota window at resume. [Verification and limits](docs/RELEASE-0.7.5.md).

Version 0.7.4 adds explicit recovery of missing managed hook receipts from exact
installed definitions, separates hook registration from collector health, and
records delivery before task enrollment. Account maintenance leaves unbound repair
contexts unbound. Native hook trust and OS notification permissions are unchanged.

Version 0.7.3 supports normal recovery with fresh collector readings and explicit
reviewed resume, observation-only collection without dispatch or transfer, and
owner-aware bounded preservation retry. Stops, ownership and native permissions
remain in force. See the [0.7.3 verification report](docs/RELEASE-0.7.3.md).

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

Installing the skill makes its workflow available in local chats on this computer. Other computers/accounts and cloud environments need their own installation, files, permissions and independently provisioned authentication. Installation alone does not enable a background service or enroll projects. Automatic enrollment is a separate account-level opt-in with root and chat exclusions.

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

## Automatic enrollment and chat isolation

With an existing enabled account collector and trusted hooks, opt in once through
`enrollment.py --state ACCOUNT-STATE configure --enabled true`. Add repeated
`--exclude-root PATH` or `--exclude-session CHAT-ID` options for exceptions.
Exclusions affect new enrollment; they never clear an existing stop.

On `SessionStart` or `PreToolUse`, a verified stable chat identity can enroll a
writable Git repository with an initial commit. Enrollment creates an ignored
`.checkpoint` binding and registers preservation with the existing collector.
An unborn repository or busy collector lock defers enrollment without pausing
the task. Enrollment does not create a service, schedule execution, acquire
ownership or invent semantic progress. The agent must maintain real `input.json` state.

Existing bindings remain intact. Reviewed chat mappings name both owning and explicitly unrelated chats.
Only a recorded unrelated chat avoids inheriting the bound task's stop. The native
hook `session_id` identifies the current root chat, including subagent hooks. An
explicit event `thread_id` is accepted when no session ID is supplied; conflicting
host fields fail closed. Inherited `CODEX_THREAD_ID` is ignored. Missing identity,
unknown chat IDs and legacy mappings stay conservative.
A new same-task continuation cannot bypass its stop. Another chat needs a separate checkout
for its own checkpoint; it does not inherit permission or ownership.
[Setup, exclusions and existing-chat repair](skills/task-checkpoint/references/enrollment.md).

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
| Automatic enrollment | Account opt-in, exclusions and stable host chat identity; eligible new Git workspaces join the existing collector |
| Chat isolation | Reviewed mapping or enrolled binding scopes stops to verified chat IDs; unknown/legacy identities remain conservative |
| Automatic low-allowance save | Real collector and delivered trusted hooks/wrapper; default <=20% remaining or an explicitly configured task-local percentage |
| Readiness after reset | Existing minute collector processes a notification-only ticket targeting the latest blocking reset +60 seconds; fresh readings/lifecycle/ownership still required |
| Native notification | macOS adapter supplied; command acceptance/display/permissions need host validation. Windows/Linux native notification requires another reviewed adapter |
| Cross-device continuation | Transfer actual source history + verified private checkpoint bundle + explicit external exports, then independently authenticate/review/acquire ownership |
| Optional Usage Router | Retained for compatibility; separately authorized bounded work, qualification, tools/privacy/budget and ownership gates required |

Manual mode needs no model/API call, scheduler or background service. Automatic mode requires the supported account-limit source, an awake/available host, access to the project, a configured collector and delivered/trusted hook coverage. A skill file alone cannot monitor usage or guarantee interruption. The default 20% is a preservation reserve, not an estimate of exact work remaining. Explicit task-local overrides are described below. Account allowance, context capacity, API spending and disk/memory signals are separate.

Readiness checks **never execute unfinished implementation** or clear a stop. Recovery requires fresh adequate readings and an explicit reviewed user resume. A scheduled target is not guaranteed execution/recovery time. No automatic account switching, credential transfer, paid fallback or purchase is performed. [Readiness setup and manual fallback](skills/task-checkpoint/references/readiness.md).

## Choose how much allowance to preserve

The default is **20% remaining** in any applicable account window. Before work,
say **“Stop when 35% remains”** or choose any finite percentage from 0–100,
including fractions. The agent can offer this choice when useful; you need not
know the command or choose a percentage unless you want a different reserve.
A clear current choice is enough authorization and is not requested again.

Initial configuration uses `reserve.py ... configure --percent N` with the
verified owner. It changes only this task's baseline. Existing stops, uncertain
jobs/workers and pending grants prevent this configuration from bypassing a stop.
After a verified stop, **“Continue until 7.5% remains”** uses a pending `percent`
grant, fresh review and explicit resume. **“Continue to 10%”** remains supported.
A numeric **0%** still stops at measured zero. **“Continue until allowance is
exhausted”** separately waives the numeric reserve; actual provider refusal,
other resource stops, ownership and permissions remain enforced.

Granting is not resumption. Grants bind task, workspace, owner, checkpoint and
account windows, expire at reset or lifecycle changes, and stay out of portable
bundles. Initial policies also stay local and require their exact owner lease. After an
ownership handoff, explicitly retire the prior policy before reviewed resume;
retirement preserves all stops and authority checks.
No option adds allowance, switches accounts or enables paid fallback. Hard
exhaustion can prevent another save, so retain milestone checkpoints.
[Configuration, grant and recovery commands](skills/task-checkpoint/references/reserve.md).

Quota reads, named installed instructions and narrowly parsed maintenance CLI
commands remain available during a stop. Native `Bash` and `exec_command` names
share the same strict checks; shell chains, substitutions and ordinary work
remain blocked for the stopped task.

## Inspection and collector repairs

Inspection reports untracked nested repositories as unsaved boundaries instead
of failing on Git's directory paths. A checkpoint refuses to claim those files
were preserved; preserve the nested repository separately or explicitly exclude
it. Collector quota refresh remains independent of optional transfer dependency
failures and per-project preservation errors. Errors stay visible and affected
scheduled work stays blocked. Python 3.9 remains supported.

## Test and verify

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
```

The standard-library suite uses isolated repositories, simulated quota/clock signals and subprocess fixtures; it does not deliberately exhaust real allowance or make paid model/API calls. CI runs the suite on Linux and macOS. CI results, local checks, simulated platform adapters and prior fresh-context exercises are distinct evidence. [Validation report](validation/REPORT.md).

The release does not claim every host/integration is verified. Local macOS notification display was observed in native acceptance. Exact reset/wake timing, background notification display, a second physical laptop/account and native Windows/Linux application behavior still require deployment verification. Files over 16 MiB, symlinks and external artifacts need an explicitly reviewed preservation route. Secret detection uses patterns and cannot certify arbitrary contents secret-free. A crash can leave a stale root projection; verification detects it and refresh is explicit.

## License

[MIT](LICENSE), copyright 2026 HarryBurd33. The same notice is included inside the installable skill. [Source attribution](skills/task-checkpoint/ATTRIBUTION.md).
