> Historical compatibility reference inherited from v0.5.0. For this candidate, current SKILL.md, README.md, readiness.md and capabilities.md control activation, delivery and validation claims. No publishing, installing services, changing accounts or resuming after recovery is implied.

# Usage Router operator guide

Requires Python 3.9+, Git, and the existing checkpoint binding. Automatic model execution additionally requires an installed Codex CLI supporting the verified flags and app-server methods. Commands below run from the project root; set `RUNTIME` to this skill's `scripts` directory if installed elsewhere.

## Policy and contract

Use [routed-task-template.json](../assets/routed-task-template.json) as the existing `.checkpoint/input.json`, or add its optional `routing` object to that file. This is the same checkpoint schema/version, not a second handoff. The bounded task includes acceptance commands, complexity/risk, required tools, privacy, allowed providers, attempt/wall/API budgets, dependencies and a work-size estimate. Original task tools, capabilities, dependencies, corrections and authorization remain applicable. Give changed work a new bounded ID; reusing an accepted ID with a changed contract is rejected.

Copy [router-config.example.json](../assets/router-config.example.json) into ignored `.checkpoint/router-config.json`. Set `queue_authority` exactly to `checkpoint:PROJECT-ID:TASK-ID` from the existing binding. There is no task backlog or queue database here. `router.json` is a private transition/attempt journal; `router-schedule.json` is one wake ticket for the same task. An external queue requires a reviewed lease adapter; do not duplicate it or synchronize live state through Git.

Workers need fresh availability evidence and representative passing results for the task class, tools and privacy. Every template worker starts disabled and unqualified. Availability is checked again through `model/list` before a plan worker starts. Qualification evidence records sample count, acceptance rate, total time including repair/review, source and timestamp. Selection ranks qualified candidates by observed total time per accepted result, with capability rank as a tie-breaker and failure escalation floor. This is a measured time proxy, not a dollar-cost estimate. The sample in `evidence/router-live-reassessed.json` qualifies only public, tool-free JSON transformations. Re-run qualification for coding, tool use, long context or private data; there is no qualified local model here.

Use low/medium effort routinely. Higher effort requires a recorded ambiguity/review reason or a prior failure. Ultra can add agent work; do not enable it without evidence that the expected benefit exceeds the extra cost. Dispatch is sequential. A failed cheaper worker can move to a higher qualified capability rank within the attempt/time/retry budgets. Failed workers are not automatically retried. Minimum task size, cooldown and measured switching cost suppress unnecessary switches. A worker override cannot bypass qualification, provider, privacy, tools, budget or active-work checks. Independent review is required before a high-risk result is accepted.

## Telemetry and real triggers

```sh
RUNTIME=skills/task-checkpoint/scripts
python3 "$RUNTIME/router.py" collect-codex --output .checkpoint/signals.json
python3 "$RUNTIME/checkpoint.py" policy --input .checkpoint/signals.json
```

The collector starts a short-lived, read-only app-server connection: initialize, `account/rateLimits/read`, `model/list`, `account/read`, then exit. It starts no model turn. Native desktop `get_usage_limits` exports can also be normalized with `telemetry.normalize_codex`. `normalize_direct` accepts only explicitly sourced context/API/local observations; `disk_usage` measures local free disk space. Local disk space does not represent memory, GPU capacity or CPU pressure. Those remain unknown unless a separate supported sensor supplies the declared signal. No API-balance endpoint was observed; the adapter accepts actual provider observations but never derives dollars from Codex credits or tokens.

Each record keeps kind, source, unit, timestamp, remaining value, uncertainty note and optional observed reset/guard. Unsupported estimates, malformed/stale/future readings and readings past their reset become unknown. Factual measurement uncertainty is retained; unsupported guesses set `supported:false`. Explicit `ordinaryUsageAllowed:false` is a blocking event without a fabricated numeric balance. All account windows are preserved. Defaults use a 120-second freshness window. Plan allowance, API balance, context and local resources remain separate.

The existing hook and boundary wrapper accept this normalized signal file as well as their legacy signal format. A **trusted, actually delivered** covered hook can checkpoint and stop/deny covered work on fresh low readings. Native hook trust and ongoing collection are separate deployment tasks. Hook callbacks do not run the router or switch this chat's model. Specialized host paths may bypass hooks. Keep semantic input current: telemetry cannot reconstruct the conversation.

`dispatch` is a real boundary execution entry point; invoke it when a task becomes bounded, after a supported telemetry event, or manually. It considers all signals and configured budgets on every call. A foreground `watch` process supplies an actual clock trigger. Instruction text alone does not provide a trigger or force the current desktop conversation to change models.

## Boundary execution

First follow the existing checkpoint `inspect` → verified review → `resume` procedure to acquire ownership. Confirm active jobs ended and current tools/capabilities are available. After editing a task/config, checkpoint the current state and inspect it again. Review the exact acceptance argument vectors as commands you authorize to run; they are trusted operator checks, not model-generated shell text.

```sh
python3 "$RUNTIME/checkpoint.py" --root . checkpoint --input .checkpoint/input.json --trigger milestone
python3 "$RUNTIME/checkpoint.py" --root . inspect
python3 "$RUNTIME/router.py" --root . authorize \
  --input .checkpoint/input.json --config .checkpoint/router-config.json \
  --scope 'Complete this bounded task and run its listed acceptance checks' \
  --source 'Current user request, reviewed task and worker configuration'
python3 "$RUNTIME/router.py" --root . dispatch \
  --input .checkpoint/input.json --config .checkpoint/router-config.json \
  --collector codex --trigger new-task --execute
python3 "$RUNTIME/router.py" --root . report
```

Without `--execute`, dispatch saves a checkpoint and reports a decision/manual command. Authorization is a fresh operator attestation bound to exact task/config and repository fingerprints, default five minutes (explicit maximum one day). It cannot be recovered as permission from a checkpoint. Changes require new review. `pause:true` prevents launches; `--worker ID` pins only a permitted, qualified route. Unknown telemetry defaults to manual. `unknown_telemetry:"explicit_budget"` permits bounded work using the explicit attempt/wall budget and observable events; it never enables paid fallback. Known low signals still block affected routes.

Before process creation, dispatch holds the Git common-directory lock and existing task lease, writes durable intent, saves/validates the original handoff, and records the worker. One coordinator retains that lease through the child's completion and validation; it does not create a second owner for the child. Worker output and logs live only under `.checkpoint/router-runs/`. The prompt carries the entire current task. The parent must stop its own ordinary writes while the worker runs. Unrelated editors are outside this cooperative protocol.

The Codex adapter verifies ChatGPT login and live model availability, supplies an explicit model/provider/effort, and allows read-only or workspace-write sandboxes without bypass flags. It does not write user settings. Local provider changes require separately configured workers; custom agents inherit the parent provider. Generic command, unverified local and paid API execution are currently manual because their billing/isolation cannot be established by a descriptive config field. The owned `fixture` interface emits only two synthetic test values and cannot execute arbitrary commands.

After a worker exits, acceptance commands must pass. Exit zero alone does not mean useful completion. For high risk, `reconcile --run-id ID --outcome accepted --reviewer DISTINCT-ID --evidence 'observed independent review'` additionally records independent review. These attestations do not cryptographically prove reviewer independence. Source changes should receive an actual separate review, as this implementation did.

## Manual transfer and uncertain outcomes

Unavailable routes save a verified checkpoint and report the limitation. A missing Codex executable produces a ready-to-run dispatch command for a capable host. Generic/manual worker definitions expose the configured argument vector for operator review; installing/running an unsupported adapter is an explicit manual step. Re-check signals, authorization and model availability before running. A command is not evidence it already ran.

To move devices, finish or reconcile the worker, save/verify, release the original owner, push source, transfer the private checkpoint bundle through an approved channel, inspect on the target, prepare a current review, and acquire the same remote lease before executing the provided command. The CLI command alone cannot transfer the private bundle or grant remote ownership.

Interrupts, timeouts, process-creation ambiguity, snapshot failures and interrupted validation retain an active transition. No restart retries it. Ownership cannot be released while a transition is active/uncertain. Check the recorded PID **and originating process identity**, worker logs, artifacts and external outcomes; PID existence alone is insufficient. Use `reconcile --run-id ID --outcome rejected --evidence 'specific verified outcome and side effects'` only after that investigation. Then reconcile checkpoint job issues and prepare a fresh authorized boundary. Automatic timeout handling does not claim that descendants were cancelled.

An abandoned common-directory lock after SIGKILL needs the same manual process verification as the checkpoint writer lock. Preserve it as evidence before removing it. Never steal a remote claim. A terminal record whose final snapshot failed still blocks a duplicate launch. Exact task digests prevent old acceptance from satisfying changed requirements.

## Explicit scheduling

```sh
python3 "$RUNTIME/router.py" --root . schedule \
  --input .checkpoint/input.json --config .checkpoint/router-config.json \
  --collector codex --at 'ACTUAL-TIME-WITH-TIMEZONE' --basis verified_reset
python3 "$RUNTIME/router.py" --root . watch \
  --input .checkpoint/input.json --config .checkpoint/router-config.json \
  --collector codex --interval 15 --max-polls 240 --execute
```

`verified_reset` requires an exact reset from fresh low plan telemetry; no reset is inferred from token counts. Use `explicit_user_schedule` only for a user-specified time. This is a bounded foreground scheduler, not an installed OS service. Keep the process running, or invoke `wake` from a separately approved native scheduler. Restarting the process reuses the durable ticket. It marks the ticket checking before collecting fresh telemetry, rechecks budgets/authorization, and consumes it once. A crash in checking never redelivers automatically. Reconcile the outcome before archiving the ticket and creating another. An expired authorization, unknown disallowed telemetry or still-low budget blocks execution after the scheduled time. No login, credit purchase, or permission change happens automatically.

## Evidence and maintenance

`python3 examples/router_demo.py --output /tmp/router-demo.json` exercises real subprocesses, clock triggering, baseline versus routing, cheap-worker failure, recovery, and low/stale/missing telemetry without a model call. `examples/live_router_models.py` is an explicit opt-in plan-usage evaluation. The original arithmetic-oracle failure, separate correction and reassessment are retained; the frozen original was not rewritten. Reassessment reused retained outputs, avoiding four repeated model calls.

Reports separate attempt acceptance, useful tasks, retries, elapsed time, evaluation time, observed token fields, account-wide plan windows and API cost. Unknown is null, including attributable plan usage and API dollars. Small single-task timing observations do not establish general savings. Keep the original frozen acceptance file unchanged and add evidence separately.

Commit source, templates, tests/results, README and sanitized HANDOFF at meaningful boundaries. Push through existing branch rules and verify the remote commit. Never publish `.checkpoint/`, `.codex/`, credentials, private source records, raw model logs or queue databases. Before upgrading, retain the previous managed installation, uninstall its unchanged managed files, then install this version. Native trust must be reviewed through the host; it is never granted by this runtime.

Official interface references checked 2026-10-25: [App server](https://learn.chatgpt.com/docs/app-server), [CLI reference](https://learn.chatgpt.com/docs/cli/reference), [Subagent inheritance](https://learn.chatgpt.com/docs/agent-configuration/subagents). Installed CLI 0.164.0 help and live method calls additionally verified the used interfaces.
