# Optional delivery and reset verification

These helpers run only when requested. They create no pause latch, background monitor, application registration, notification permission or task resume. Keep explicit user holds and existing ownership intact.

## One native notification

```sh
python3 scripts/notifications.py --adapter auto --message "Requested checkpoint report"
```

macOS uses existing `osascript` notification access. Linux requires existing `notify-send` (with `--print-id`), a user D-Bus session and a display; markup is escaped. Windows uses existing Windows PowerShell and WinForms `NotifyIcon` in an interactive user session. It creates a temporary tray icon and disposes it after eight seconds; no app ID, shortcut or registry entry is installed. Dependencies are never installed automatically on the user's machine.

`accepted_by_command` means the command succeeded. Linux also returns its notification server ID. Windows separately reports the `BalloonTipShown` OS event. `display_observed` remains false: command acceptance and OS events do not prove a person saw the notification. Focus, desktop policy, accessibility settings, absent shell/UI and hosted runner limitations can prevent display. Do not retry an uncertain notification automatically.

## Real reset evidence

Capture a fresh signed-in observation with the existing optional collector, then save an explicit baseline in the task's private case directory:

```sh
python3 scripts/account.py tick
python3 scripts/quota_reset.py baseline --signals /path/to/account-state/signals.json > /path/to/private-case/baseline.json
```

After every recorded window's reset, collect again and verify:

```sh
python3 scripts/account.py tick
python3 scripts/quota_reset.py verify --baseline /path/to/private-case/baseline.json --signals /path/to/account-state/signals.json
```

The verifier is read-only. It requires fresh observations, identical account/window identities, observations after the previous reset and a strictly advanced reset timestamp for every window. It rejects stale, future, duplicate, invalid or changed-account readings. It reports the observed remaining allowance; it does not infer full recovery or authorize work. Exit 0 means verified or not yet due; read the `verified` and `status` fields. Exit 2 means unverified/error.

Arrange a follow-up only when the current user requests it, using the host's supported scheduler. Record the baseline and schedule ID in existing task evidence. The prompt must limit the follow-up to collecting and reporting, preserve explicit holds/ownership, retire its one-use schedule and prohibit implementation. Never synthesize a real reset. Simulated-clock tests are labeled separately from future account observations.

## CI evidence

The normal Linux/macOS suite checks limits, checkpoints, ownership, installation, hostile notification content and simulated reset transitions. Windows/Linux jobs run adapter/reset regressions. Linux also sends through an isolated Xvfb/D-Bus/dunst session and checks the daemon's history. Windows parses the exact PowerShell source, loads WinForms and attempts the bounded native adapter; a service session reports unavailable honestly. Neither hosted test is a claim of human-visible display.

References: [Windows notification API](https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.notifyicon.showballoontip), [Windows display event](https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.notifyicon.balloontipshown), [desktop notification protocol and markup](https://specifications.freedesktop.org/notification/latest-single/).
