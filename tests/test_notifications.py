import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import notifications as n


class NotificationTests(unittest.TestCase):
    def test_linux_literal_markup_options_and_shell_content(self):
        message = '--hint $(touch sentinel); <b>&\"'
        with mock.patch.object(n.sys, 'platform', 'linux'), mock.patch.dict(os.environ, {'DISPLAY': ':9', 'DBUS_SESSION_BUS_ADDRESS': 'fixture'}), mock.patch.object(n.shutil, 'which', return_value='/fixture/notify-send'), mock.patch.object(n.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '17\n', '')) as run:
            result = n.notify(message, 'linux', title='--literal-title')
        args = run.call_args.args[0]
        self.assertEqual(args[-3:], ['--', '--literal-title', '--hint $(touch sentinel); &lt;b&gt;&amp;\"'])
        self.assertNotIn('shell', run.call_args.kwargs)
        self.assertEqual(result['notification_id'], 17)
        self.assertTrue(result['accepted_by_command'])
        self.assertFalse(result['display_observed'])

    def test_windows_content_is_json_data_never_executable_source(self):
        message = "'; [IO.File]::WriteAllText('sentinel','bad'); #"
        with mock.patch.object(n.sys, 'platform', 'win32'), mock.patch.object(n.shutil, 'which', return_value='powershell.exe'), mock.patch.object(n.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"accepted_by_command":true,"os_display_event":true}', '')) as run:
            result = n.notify(message, 'windows')
        self.assertNotIn(message, run.call_args.args[0][-1])
        self.assertEqual(json.loads(run.call_args.kwargs['input'])['message'], message)
        self.assertTrue(result['os_display_event'])
        self.assertFalse(result['display_observed'])
        self.assertLessEqual(run.call_args.kwargs['timeout'], 30)

    def test_macos_literal_arguments_and_no_inferred_display(self):
        message = '" & do shell script "bad"'
        with mock.patch.object(n.sys, 'platform', 'darwin'), mock.patch.object(n.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            result = n.notify(message)
        self.assertEqual(run.call_args.args[0][-3:], ['--', 'Task checkpoint', message])
        self.assertFalse(result['display_observed'])

    def test_headless_missing_dependency_wrong_platform_and_failed_command_do_not_claim_success(self):
        with mock.patch.object(n.sys, 'platform', 'linux'), mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(n.subprocess, 'run') as run:
            with self.assertRaises(n.Unavailable): n.notify('message')
            with self.assertRaises(n.Unavailable): n.notify('message', 'windows')
            run.assert_not_called()
        with mock.patch.object(n.sys, 'platform', 'linux'), mock.patch.dict(os.environ, {'DISPLAY': ':9', 'DBUS_SESSION_BUS_ADDRESS': 'fixture'}), mock.patch.object(n.shutil, 'which', return_value=None):
            with self.assertRaises(n.Unavailable): n.notify('message')
        with mock.patch.object(n.sys, 'platform', 'win32'), mock.patch.object(n.shutil, 'which', return_value='powershell.exe'), mock.patch.object(n.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{"accepted_by_command":false,"reason":"No interactive Windows desktop"}', '')):
            with self.assertRaises(n.Unavailable): n.notify('message')
        with mock.patch.object(n.sys, 'platform', 'darwin'), mock.patch.object(n.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'private content')):
            with self.assertRaisesRegex(n.Unavailable, 'exit 1'): n.notify('message')

    def test_bad_input_fails_before_native_execution(self):
        with mock.patch.object(n.subprocess, 'run') as run:
            for message in ('', ' ', 'x'*241, 'a\0b', None):
                with self.assertRaises(ValueError): n.notify(message)
            for title in ('', 'x'*61, 'a\0b', None):
                with self.assertRaises(ValueError): n.notify('message', title=title)
            run.assert_not_called()

    def test_missing_server_id_and_timeout_are_not_success(self):
        with mock.patch.object(n.sys, 'platform', 'linux'), mock.patch.dict(os.environ, {'DISPLAY': ':9', 'DBUS_SESSION_BUS_ADDRESS': 'fixture'}), mock.patch.object(n.shutil, 'which', return_value='notify-send'), mock.patch.object(n.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            with self.assertRaises(n.Unavailable): n.notify('message')
        with mock.patch.object(n.sys, 'platform', 'darwin'), mock.patch.object(n.subprocess, 'run', side_effect=subprocess.TimeoutExpired('osascript',15)):
            with self.assertRaises(subprocess.TimeoutExpired): n.notify('message')

    def test_windows_total_deadline_is_bounded_and_timeout_never_retries(self):
        with mock.patch.object(n.sys, 'platform', 'win32'), mock.patch.object(n.shutil, 'which', return_value='powershell.exe'), mock.patch.object(n.subprocess, 'run', side_effect=subprocess.TimeoutExpired('powershell.exe',30)) as run:
            with self.assertRaises(subprocess.TimeoutExpired): n.notify('message')
            run.assert_called_once()
            self.assertEqual(run.call_args.kwargs['timeout'], 30)
