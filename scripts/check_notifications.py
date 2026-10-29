#!/usr/bin/env python3
"""Bounded native CI probe in an ephemeral runner, never a visible-display claim."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import notifications


def main():
    daemon=None
    result={'platform':sys.platform,'display_observed':False}
    try:
        if sys.platform.startswith('linux'):
            daemon=subprocess.Popen(['dunst'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for attempt in range(30):
                ready=subprocess.run(['dunstctl','is-paused'],capture_output=True,timeout=2)
                if ready.returncode==0:break
                time.sleep(0.1)
            else:raise RuntimeError('Isolated notification daemon unavailable')
        try:
            started=time.monotonic()
            result.update(notifications.notify('CI DISPLAY TEST ONLY: literal <b>& $() ;',title='Checkpoint CI'))
            result['command_elapsed_seconds']=round(time.monotonic()-started,3)
        except notifications.Unavailable as exc:
            # Windows hosted runners may be services without an interactive shell.
            # This is explicit missing native display coverage, never a success receipt.
            if sys.platform!='win32':raise
            result.update(accepted_by_command=False,os_display_event=False,native_status='unavailable',reason=str(exc))
        if sys.platform.startswith('linux'):
            subprocess.run(['dunstctl','close-all'],check=True,timeout=5)
            history=subprocess.run(['dunstctl','history'],check=True,capture_output=True,text=True,timeout=5)
            json.loads(history.stdout)
            if 'CI DISPLAY TEST ONLY' not in history.stdout:raise RuntimeError('Native daemon receipt missing')
            result['native_daemon_receipt']=True
        if sys.platform=='win32':
            # Parse the exact script and load the API even when UI is unavailable.
            script="$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; $t=$null; $e=$null; [void][Management.Automation.Language.Parser]::ParseInput([Console]::In.ReadToEnd(),[ref]$t,[ref]$e); if ($e.Count) { exit 3 }"
            subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],input=notifications.WINDOWS_SCRIPT,text=True,check=True,timeout=30)
            result['native_script_parsed_and_api_loaded']=True
        print(json.dumps(result,indent=2))
    finally:
        if daemon:
            daemon.terminate()
            try:daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:daemon.kill();daemon.wait()


if __name__=='__main__':main()
