#!/usr/bin/env python3
"""Optional one-shot native notifications; no registration, settings or task writes."""
import argparse
import html
import json
import os
import shutil
import subprocess
import sys


class Unavailable(RuntimeError):
    pass


WINDOWS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
if (-not [Environment]::UserInteractive -or [Diagnostics.Process]::GetCurrentProcess().SessionId -eq 0) {
    @{accepted_by_command=$false; os_display_event=$false; reason='No interactive Windows desktop'} | ConvertTo-Json -Compress
    exit 0
}
$nativeClock = [Diagnostics.Stopwatch]::StartNew()
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$icon = New-Object System.Windows.Forms.NotifyIcon
$seen = @{value=$false}
try {
    $icon.Icon = [Drawing.SystemIcons]::Information
    $icon.add_BalloonTipShown({ $seen.value = $true })
    $icon.Visible = $true
    $icon.ShowBalloonTip(8000, [string]$payload.title, [string]$payload.message, [Windows.Forms.ToolTipIcon]::Info)
    $clock = [Diagnostics.Stopwatch]::StartNew()
    while ($clock.ElapsedMilliseconds -lt 8000) {
        [Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 50
    }
    @{accepted_by_command=$true; os_display_event=[bool]$seen.value; reason=$null; native_elapsed_ms=$nativeClock.ElapsedMilliseconds} | ConvertTo-Json -Compress
} finally {
    $icon.Visible = $false
    $icon.Dispose()
}
"""
MACOS_SCRIPT = 'on run argv\n display notification (item 2 of argv) with title (item 1 of argv)\nend run'


def notify(message, adapter='auto', title='Task checkpoint'):
    # Bound native API sizes and reject NUL before starting any command.
    if not isinstance(title, str) or not title.strip() or len(title) > 60 or '\0' in title:
        raise ValueError('Title must contain 1-60 characters without NUL')
    if not isinstance(message, str) or not message.strip() or len(message) > 240 or '\0' in message:
        raise ValueError('Message must contain 1-240 characters without NUL')
    platform = 'macos' if sys.platform == 'darwin' else ('windows' if sys.platform == 'win32' else ('linux' if sys.platform.startswith('linux') else None))
    adapter = platform if adapter == 'auto' else adapter
    if adapter is None or adapter != platform:
        raise Unavailable('Adapter does not match this operating system')
    details = {'os_display_event': False}
    if adapter == 'linux':
        if not os.environ.get('DBUS_SESSION_BUS_ADDRESS') or not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            raise Unavailable('An existing desktop and user D-Bus session are required')
        executable = shutil.which('notify-send')
        if not executable:
            raise Unavailable('notify-send is unavailable; no dependency is installed automatically')
        args = [executable, '--print-id', '--app-name=Task checkpoint', '--', title, html.escape(message, quote=False)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            raw = result.stdout.strip()
            if not raw.isdigit() or int(raw) <= 0:
                raise Unavailable('Notification server did not return a valid ID')
            details['notification_id'] = int(raw)
    elif adapter == 'windows':
        executable = shutil.which('powershell.exe')
        if not executable:
            raise Unavailable('Windows PowerShell is unavailable')
        # Fixed source; user content travels through JSON stdin, never PowerShell source.
        result = subprocess.run([executable, '-NoProfile', '-NonInteractive', '-STA', '-Command', WINDOWS_SCRIPT],
                                input=json.dumps({'title': title, 'message': message}, ensure_ascii=True),
                                capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            details = json.loads(result.stdout)
            if details.get('accepted_by_command') is not True:
                raise Unavailable(details.get('reason') or 'No interactive desktop')
    else:
        result = subprocess.run(['/usr/bin/osascript', '-e', MACOS_SCRIPT, '--', title, message],
                                capture_output=True, text=True, timeout=15)
    if result.returncode:
        # Do not log command stderr, which may echo user message content.
        raise Unavailable('Native notification command failed (exit %d)' % result.returncode)
    return dict(details, adapter=adapter, accepted_by_command=True, display_observed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--adapter', choices=('auto', 'macos', 'linux', 'windows'), default='auto')
    parser.add_argument('--title', default='Task checkpoint')
    parser.add_argument('--message', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(notify(args.message, args.adapter, args.title), indent=2))
    except (Unavailable, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'accepted_by_command': False, 'display_observed': False,
                          'error': str(exc) if isinstance(exc, (Unavailable, ValueError)) else type(exc).__name__}))
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
