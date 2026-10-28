# Automatic enrollment and chat isolation

Enrollment is an explicit opt-in in the existing account registry. It requires
an enabled collector configuration, installed trusted hooks, writable Git
workspace access and a verified stable host chat identity. Installing the skill
alone does not enable it or create a background service.

## Enable and exclude

Use reviewed absolute paths for `SKILL` and `STATE`. Inspect current configuration
with `status` before changing it:

```sh
python3 SKILL/scripts/enrollment.py --state STATE status
python3 SKILL/scripts/enrollment.py --state STATE configure --enabled true --exclude-root /absolute/excluded/root --exclude-session VERIFIED-CHAT-ID
```

Repeat `--exclude-root` and `--exclude-session` for multiple exclusions. A root
exclusion includes its descendants. When an exclusion option is supplied, its
repeated values replace that exclusion list; an omitted option retains the
existing list. Disabling with `configure --enabled false` stops future automatic
enrollment and preserves existing tasks, registrations, ownership and stops.
Exclusions apply to **new enrollment only**. They cannot bypass an existing stop.

On delivered `SessionStart` or `PreToolUse`, an eligible Git root with an initial
commit can receive an ignored `.checkpoint/config.json` and registration in the
existing collector. Existing `.gitignore` content is preserved. An unborn
repository, unavailable stable identity or busy collector lock defers enrollment;
none is evidence that a task must pause. Existing bindings and incomplete stores
are left for explicit review, never replaced.

Enrollment sets local ownership mode but does not acquire a lease, schedule
execution, invent task semantics, create a queue or install a second service.
The agent must maintain truthful `.checkpoint/input.json` before claiming a
semantic checkpoint. A low-resource stop can still require an emergency handoff
if no usable semantic input exists. Scope and authorization must be reviewed
before ordinary implementation.

## Review existing chat mappings

A Git root can contain only its existing task binding. Sharing that directory
must not make unrelated chats inherit the task's stop. After reviewing actual
chat identities and task association, record the owning chats and the chats
verified to be unrelated:

```sh
python3 SKILL/scripts/enrollment.py --state STATE bind-chat --root ROOT --task TASK --session OWNING-CHAT-ID --session ANOTHER-OWNING-CHAT-ID --unrelated-session REVIEWED-UNRELATED-CHAT-ID
```

Repeat `--session` for all verified owning chats and `--unrelated-session` for
reviewed unrelated chats. The task must match the actual binding. Existing
conflicting mappings require separate explicit reconciliation; the command does
not silently replace them. Mapping changes do not resume, release, rebind or
modify any task checkpoint, stop, lease or permission.

The documented native hook `session_id` identifies the root chat, including
its subagent hooks; an explicit host `thread_id` is also accepted when no session
ID is supplied. Conflicting host fields fail closed. Inherited environment
`CODEX_THREAD_ID` is ignored: native testing proved it can belong to a parent
process when a new app-server session is spawned.
Only an explicitly recorded unrelated chat avoids inheriting the mapped stop.
Unknown IDs, legacy mappings and missing stable identity retain conservative
behavior. A new same-task continuation cannot avoid its legitimate stop simply
because it has a different ID.

An unrelated chat still needs a separate checkout/binding for its own checkpoint
and must respect filesystem permissions and the other task's ownership. Scope
routing is not permission to edit another task or bypass shared resource limits.
Unknown or inconsistent state for a bound task remains blocking.

## Verify delivery

Check the account `chat-delivery` receipts for the actual chat ID, identity source,
root, task and hook event. Check project delivery receipts separately. A manual
callback, configured hook, installed file or scheduler entry does not prove that
Codex delivered a native event. Preserve existing legitimate stop and ownership
state while testing. The versioned validation report distinguishes isolated
logic tests, supported native delivery, and checks still pending on other hosts.
