"""A terminal hook must not replace the generation pinned by a persistent stop."""
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'))
import checkpoint as cp
import hook
import monitor
import reserve
import test_reserve_policy as fixtures


class StoppedShutdownTests(unittest.TestCase):
    signals = fixtures.ReserveTests.signals

    def setUp(self):
        fixtures.ReserveTests.setUp(self)
        self.root = self.root.resolve()
        self.store = self.root / '.checkpoint'
        self.source = self.store / 'input.json'
        self.binding['root_handoff'] = True
        cp.atomic(self.store / 'config.json', cp.encoded(self.binding))
        cp.checkpoint(self.root, self.source, 'milestone')
        cp.Ownership(self.root, self.binding, self.store).acquire('fixture-owner')
        self.stop()

    def stop(self):
        result = monitor.stop_for_signals(self.root, self.signals(20))
        self.assertEqual(result['status'], 'checkpoint-verified')
        marker = cp.read(self.store / 'automatic-stop.json')
        self.assertEqual(marker['checkpoint_id'], cp.latest(self.store)[0]['id'])

    def event(self, name):
        return {'cwd': str(self.root), 'hook_event_name': name,
                'session_id': 'fixture-owning-chat', 'tool_name': 'exec_command',
                'tool_input': {'cmd': 'echo ordinary-work'}}

    def protected(self):
        paths = [self.store / name for name in ('config.json', 'input.json', 'automatic-stop.json',
                                                'latest.json', 'owner.json', 'router.json', 'boundary.json',
                                                'resume.json')]
        paths.append(self.root / 'HANDOFF.md')
        return {str(path): path.read_bytes() if path.exists() else None for path in paths}

    def invoke(self, name):
        with mock.patch.object(sys, 'stdin', io.StringIO(json.dumps(self.event(name)))):
            return hook.main()

    def assert_stopped_unchanged(self, name, informational=False):
        before = self.protected()
        generations = set((self.store / 'snapshots').iterdir())
        with mock.patch.object(cp, 'checkpoint', wraps=cp.checkpoint) as checkpoint:
            result = self.invoke(name)
        checkpoint.assert_not_called()
        self.assertEqual(before, self.protected())
        self.assertEqual(generations, set((self.store / 'snapshots').iterdir()))
        self.assertFalse((self.store / 'hook-input.json').exists())
        self.assertIn('automatic usage stop persists', json.dumps(result))
        if informational:
            self.assertEqual(set(result), {'systemMessage'})
        elif name == 'PreToolUse':
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        else:
            self.assertFalse(result['continue'])

    def test_terminal_events_keep_verified_pinned_checkpoint_and_owner(self):
        for name in ('SessionEnd', 'Interrupt'):
            with self.subTest(event=name):
                self.assert_stopped_unchanged(name, informational=True)

    def test_terminal_events_keep_next_explicit_grant_valid(self):
        pinned = cp.read(self.store / 'automatic-stop.json')['checkpoint_id']
        for name in ('SessionEnd', 'Interrupt'):
            self.assert_stopped_unchanged(name, informational=True)
        value = reserve.grant(self.root, 'ten', self.signals(14),
                              'Explicit isolated user continuation', 'Current fixture instruction',
                              owner='fixture-owner')
        self.assertEqual(value['checkpoint_id'], pinned)
        self.assertEqual(value['state'], 'pending_resume')
        self.assertEqual(cp.latest(self.store)[0]['id'], pinned)

    def test_stop_precompact_and_tool_boundaries_remain_blocked(self):
        for name in ('Stop', 'PreCompact', 'PreToolUse', 'PostToolUse'):
            with self.subTest(event=name):
                self.assert_stopped_unchanged(name)

    def test_recovered_signals_do_not_make_terminal_events_resume_or_resave(self):
        cp.atomic(self.store / 'signals.json', cp.encoded(self.signals(90)))
        for name in ('SessionEnd', 'Interrupt'):
            with self.subTest(event=name):
                self.assert_stopped_unchanged(name, informational=True)

    def test_active_uncertain_jobs_and_router_are_preserved(self):
        task = cp.read(self.source)
        task['jobs'] = [{'id': 'uncertain-job', 'kind': 'owned-child', 'status': 'unknown',
                         'source': 'isolated fixture', 'observed_at': cp.now()}]
        cp.atomic(self.source, cp.encoded(task))
        cp.atomic(self.store / 'router.json', cp.encoded({'active': {'id': 'active-worker', 'status': 'unknown'}}))
        self.stop()
        saved_jobs = cp.latest(self.store)[0]['task']['jobs']
        self.assertTrue(any(job['id'] == 'uncertain-job' for job in saved_jobs))
        for name in ('SessionEnd', 'Interrupt', 'PreCompact', 'Stop'):
            with self.subTest(event=name):
                self.assert_stopped_unchanged(name, informational=name in ('SessionEnd', 'Interrupt'))
        self.assertEqual(cp.latest(self.store)[0]['task']['jobs'], saved_jobs)

    def test_failed_or_pending_stops_are_not_implicitly_retried_at_shutdown(self):
        for status in ('failed', 'pending'):
            marker = cp.read(self.store / 'automatic-stop.json')
            marker['checkpoint_status'] = status
            cp.atomic(self.store / 'automatic-stop.json', cp.encoded(marker))
            for name in ('SessionEnd', 'Interrupt'):
                with self.subTest(status=status, event=name):
                    self.assert_stopped_unchanged(name, informational=True)

    def test_malformed_stop_fails_closed_without_touching_checkpoint(self):
        (self.store / 'automatic-stop.json').write_text('{broken-json')
        before = self.protected()
        for name in ('SessionEnd', 'Interrupt', 'PreCompact', 'Stop'):
            with self.subTest(event=name):
                response = subprocess.run([sys.executable, str(Path(hook.__file__).resolve())],
                                          input=json.dumps(self.event(name)), capture_output=True, text=True)
                self.assertEqual(response.returncode, 2, response.stderr)
                self.assertIn('Stop normal work', json.loads(response.stdout)['systemMessage'])
                self.assertEqual(before, self.protected())

    def test_without_persistent_stop_shutdown_still_preserves_semantic_input(self):
        (self.store / 'automatic-stop.json').unlink()
        before = cp.latest(self.store)[0]['id']
        with mock.patch.object(cp, 'checkpoint', wraps=cp.checkpoint) as checkpoint:
            result = self.invoke('SessionEnd')
        checkpoint.assert_called_once()
        self.assertEqual(result, {})
        self.assertNotEqual(cp.latest(self.store)[0]['id'], before)
        self.assertEqual(cp.latest(self.store)[0]['trigger'], 'shutdown')
