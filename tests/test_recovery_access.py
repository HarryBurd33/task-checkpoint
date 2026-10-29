"""Recovery reads and user questions preserve the stop and all execution gates."""
import datetime as dt
import io
import json
from pathlib import Path
import shlex
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'))
import checkpoint as cp
import hook
import maintenance
import reserve
import test_stopped_shutdown as stopped
import test_reserve_policy as fixtures


class StoppedRecoveryAccessTests(unittest.TestCase):
    setUp = stopped.StoppedShutdownTests.setUp
    signals = stopped.StoppedShutdownTests.signals
    stop = stopped.StoppedShutdownTests.stop
    protected = stopped.StoppedShutdownTests.protected

    def test_verified_handoff_is_readable_without_resume_or_mutation(self):
        before = self.protected()
        saved, folder = cp.latest(self.store)
        command = shlex.join(['python3', str(maintenance.SCRIPTS/'maintenance.py'),
                              '--root', str(self.root), 'handoff'])
        event = {'cwd': str(self.root), 'session_id': 'fixture-owning-chat',
                 'hook_event_name': 'PreToolUse', 'tool_name': 'exec_command',
                 'tool_input': {'cmd': command}}
        self.assertTrue(maintenance.classify(event, self.root)[0])
        with mock.patch.object(sys, 'stdin', io.StringIO(json.dumps(event))):
            self.assertEqual(hook.main(), {})
        self.assertEqual(maintenance.handoff(self.root), (folder/'HANDOFF.md').read_text())
        self.assertEqual(before, self.protected())
        event['tool_input']['cmd'] = 'git status'
        with mock.patch.object(sys, 'stdin', io.StringIO(json.dumps(event))):
            self.assertEqual(hook.main()['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_handoff_rejects_corruption_and_foreign_task_identity(self):
        saved, folder = cp.latest(self.store)
        original = (folder/'HANDOFF.md').read_bytes()
        (folder/'HANDOFF.md').write_bytes(original+b'tampered')
        with self.assertRaises(cp.Fault): maintenance.handoff(self.root)
        (folder/'HANDOFF.md').write_bytes(original)
        cp.atomic(self.store/'config.json', cp.encoded(dict(self.binding, task_id='foreign-task')))
        with self.assertRaises(cp.Fault): maintenance.handoff(self.root)

    def test_user_questions_remain_available_but_never_clear_a_stop(self):
        before = self.protected()
        for name in ('request_user_input', 'request_user_input_async', 'functions.request_user_input_async'):
            event = {'cwd': str(self.root), 'session_id': 'fixture-owning-chat',
                     'hook_event_name': 'PreToolUse', 'tool_name': name,
                     'tool_input': {'questions': [{'title': 'Current reserve choice?'}]}}
            with mock.patch.object(sys, 'stdin', io.StringIO(json.dumps(event))):
                self.assertEqual(hook.main(), {})
            self.assertEqual(before, self.protected())
        self.assertFalse(maintenance.classify({'tool_name': 'send_message_to_thread'}, self.root)[0])
        self.assertFalse(maintenance.classify({'tool_name': 'exec_command',
                         'tool_input': {'cmd': 'cat /etc/hosts'}}, self.root)[0])


class CollectorReviewTests(unittest.TestCase):
    setUp = fixtures.ReserveTests.setUp
    signals = fixtures.ReserveTests.signals

    def collector(self, guard=20):
        state = (self.root/'collector').resolve(); state.mkdir()
        # Keep fixture collector files outside the repository fingerprint.
        with (self.root/'.git/info/exclude').open('a') as f: f.write('\ncollector/\n')
        cp.atomic(state/'config.json', cp.encoded({'enabled': True, 'guard_percent': guard,
            'projects': [{'root': str(self.root), 'task_id': self.binding['task_id'],
                          'project_id': self.binding['project_id']}]}))
        cp.atomic(state/'signals.json', cp.encoded(self.signals(80)))
        return state

    def prepare(self, path):
        return reserve.prepare_review(self.root, 'Same-task bounded continuation', 'Current fixture user',
            'Actual isolated collector observations', owner='fixture', signals_path=path)

    def test_explicit_collector_review_after_acknowledged_stop_and_lease_release(self):
        state = self.collector()
        self.assertFalse((self.store/'signals.json').exists())
        prepared = self.prepare(state/'signals.json')
        self.assertFalse(prepared['implementation_allowed'])
        self.assertTrue(cp.resume(self.root, Path(prepared['review']), 'fixture', [])['implementation_allowed'])
        cp.Ownership(self.root, self.binding, self.store).release()
        prepared = self.prepare(state/'signals.json')
        self.assertTrue(cp.resume(self.root, Path(prepared['review']), 'fixture', [])['implementation_allowed'])

    def test_collector_guard_and_registration_must_match(self):
        state = self.collector(guard=85)
        with self.assertRaises(cp.Fault): self.prepare(state/'signals.json')
        config = cp.read(state/'config.json'); config['guard_percent'] = 20
        for change in ({'enabled': False}, {'projects': []},
                       {'projects': [dict(config['projects'][0], task_id='foreign')]}):
            cp.atomic(state/'config.json', cp.encoded(dict(config, **change)))
            with self.assertRaises(cp.Fault): self.prepare(state/'signals.json')
        self.assertFalse((self.store/'owner.json').exists())

    def test_resume_rechecks_freshness_all_windows_and_other_resources(self):
        state = self.collector()
        for readings in (self.signals(20), self.signals(80, at=self.base-dt.timedelta(minutes=3)),
                         self.signals(80, account='different'), self.signals(80, window='different')):
            cp.atomic(state/'signals.json', cp.encoded(self.signals(80)))
            prepared = self.prepare(state/'signals.json')
            cp.atomic(state/'signals.json', cp.encoded(readings))
            with self.assertRaises(cp.Fault): cp.resume(self.root, Path(prepared['review']), 'fixture', [])
            self.assertFalse((self.store/'owner.json').exists())
        cp.atomic(state/'signals.json', cp.encoded(self.signals(80)))
        local = self.signals(80)
        local['records'].append({'kind': 'context', 'remaining': 0, 'unit': 'tokens_remaining',
            'source': 'fixture', 'observed_at': cp.now()})
        cp.atomic(self.store/'signals.json', cp.encoded(local))
        with self.assertRaises(cp.Fault): self.prepare(state/'signals.json')


    def test_explicit_source_is_scoped_and_cannot_replace_pending_grant_source(self):
        state = self.collector()
        prefix = ['python3', str(maintenance.SCRIPTS/'reserve.py'), '--root', str(self.root.resolve()),
                  'prepare-review', '--owner', 'fixture', '--scope', 'Same task', '--source', 'Current user',
                  '--resources-evidence', 'Fresh isolated readings', '--signals']
        event = {'tool_name': 'exec_command', 'tool_input': {'cmd': shlex.join(prefix+[str(state/'signals.json')])}}
        self.assertTrue(maintenance.classify(event, self.root.resolve(), state)[0])
        event['tool_input']['cmd'] = shlex.join(prefix+['/foreign/signals.json'])
        self.assertFalse(maintenance.classify(event, self.root.resolve(), state)[0])
        reserve.grant(self.root, 'ten', self.signals(14), 'Current explicit fixture choice',
                      'Current fixture user', owner='fixture')
        before = (self.store/'allowance-override.json').read_bytes()
        with self.assertRaises(cp.Fault): self.prepare(state/'signals.json')
        self.assertEqual(before, (self.store/'allowance-override.json').read_bytes())


if __name__ == '__main__': unittest.main()
