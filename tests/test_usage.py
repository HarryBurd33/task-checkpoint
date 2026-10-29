import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import checkpoint as cp
import usage
import test_runtime as fixtures


class UsageTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    g = fixtures.RuntimeTests.g
    cli = fixtures.RuntimeTests.cli
    write = fixtures.RuntimeTests.write
    save = fixtures.RuntimeTests.save

    def signals(self, remaining=20, **extra):
        value = {'records': [dict(kind='codex_plan', unit='percent_remaining', source='fixture-observation',
                                  remaining=remaining, observed_at=cp.now(), window='primary', **extra)]}
        cp.atomic(self.root/'.checkpoint/signals.json', cp.encoded(value))
        return value

    def test_default_exact_limit_saves_real_handoff_and_dirty_bytes(self):
        (self.root/'work.txt').write_text('one\nverified change\n')
        self.signals(20)
        result = usage.check(self.root)
        self.assertEqual(result['action'], 'handoff')
        s, folder = cp.latest(self.root/'.checkpoint')
        cp.verify_root(self.root, s)
        self.assertEqual((folder/'files/work.txt').read_text(), 'one\nverified change\n')
        self.assertIn(self.task['next_action']['description'], (self.root/'HANDOFF.md').read_text())
        self.assertFalse((self.root/'.checkpoint/automatic-stop.json').exists())

    def test_direct_10_custom_zero_and_exhaustion_replace_previous_choice(self):
        self.signals(14)
        usage.configure(self.root, 10)
        self.assertEqual(usage.check(self.root)['action'], 'continue')
        usage.configure(self.root, 7.5)
        self.assertEqual(usage.assess(self.signals(7.5), self.root)['action'], 'handoff')
        usage.configure(self.root, 0)
        self.assertEqual(usage.assess(self.signals(0), self.root)['action'], 'handoff')
        usage.configure(self.root, exhaustion=True)
        self.assertEqual(usage.check(self.root)['action'], 'continue')
        usage.configure(self.root, 20)
        self.assertEqual(usage.setting(self.root)['percent'], 20)

    def test_provider_denial_is_not_waived_by_exhaustion(self):
        usage.configure(self.root, exhaustion=True)
        self.signals(None, blocked=True)
        self.assertEqual(usage.check(self.root)['action'], 'handoff')

    def test_recovered_usage_continues_without_resume_ceremony(self):
        self.signals(19); usage.check(self.root)
        first = cp.latest(self.root/'.checkpoint')[0]['id']
        self.signals(80)
        self.assertEqual(usage.check(self.root)['action'], 'continue')
        self.assertEqual(cp.latest(self.root/'.checkpoint')[0]['id'], first)
        self.assertFalse((self.root/'.checkpoint/resume.json').exists())

    def test_old_pause_and_corrupt_grant_cannot_block_or_replace_choice(self):
        store = self.root/'.checkpoint'
        for name in ('automatic-stop.json', 'allowance-override.json', 'reserve-policy.json'):
            (store/name).write_text('old unreadable state')
        usage.configure(self.root, 10)
        self.signals(15)
        self.assertEqual(usage.check(self.root)['action'], 'continue')
        cp.checkpoint(self.root, self.source)
        self.assertEqual((store/'automatic-stop.json').read_text(), 'old unreadable state')

    def test_missing_stale_future_reset_unknown_and_zero_is_valid(self):
        cases = [None, {'remaining': 0, 'observed_at': '2000-01-01T00:00:00+00:00'},
                 {'remaining': 0, 'observed_at': (dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat()},
                 {'remaining': 0, 'resets_at': '2000-01-01T00:00:00+00:00'},
                 {'remaining': None}, {'remaining': float('inf')}, {'remaining': -1}, {'remaining': 101}]
        for case in cases:
            record = dict(kind='codex_plan',unit='percent_remaining',source='fixture',remaining=90,observed_at=cp.now())
            if case:record.update(case)
            result = usage.assess({'records': [record] if case else []}, self.root)
            self.assertEqual(result['action'], 'continue', case)
            self.assertEqual(result['quota_status'], 'unknown', case)
        self.assertEqual(usage.assess(self.signals(0), self.root)['action'], 'handoff')

    def test_each_window_is_checked_and_old_signal_guards_do_not_override_user(self):
        signals = self.signals(80, guard=99)
        signals['records'].append(dict(signals['records'][0], window='weekly', remaining=10))
        usage.configure(self.root, 10)
        self.assertEqual(usage.assess(signals, self.root)['action'], 'handoff')
        usage.configure(self.root, 5)
        self.assertEqual(usage.assess(signals, self.root)['action'], 'continue')

    def test_invalid_choice_does_not_change_existing_setting(self):
        usage.configure(self.root, 7.5)
        before = (self.root/'.checkpoint/usage-policy.json').read_bytes()
        for value in (True, -1, 101, float('inf'), float('nan'), None):
            with self.assertRaises(cp.Fault):usage.configure(self.root, value)
            self.assertEqual((self.root/'.checkpoint/usage-policy.json').read_bytes(), before)

    def test_foreign_owner_is_preserved_across_save_choice_migration_and_resume(self):
        binding, store = cp.config(self.root)
        self.save()
        ledger = cp.Ownership(self.root, binding, store)
        ledger.acquire('other-writer')
        tip = ledger.tip(); before = (store/'owner.json').read_bytes()
        for action in (lambda: usage.configure(self.root, 10), lambda: usage.migrate(self.root),
                       lambda: cp.checkpoint(self.root, self.source),
                       lambda: cp.resume(self.root, None, 'this-writer', [])):
            with self.assertRaises(cp.Fault):action()
            self.assertEqual(ledger.tip(), tip)
            self.assertEqual((store/'owner.json').read_bytes(), before)

    def test_same_owner_reused_for_direct_override_and_save(self):
        binding, store = cp.config(self.root)
        ledger = cp.Ownership(self.root, binding, store);ledger.acquire('writer')
        tip = ledger.tip(); before = (store/'owner.json').read_bytes()
        usage.configure(self.root, 10, owner='writer')
        self.signals(10); usage.check(self.root, owner='writer')
        cp.resume(self.root, None, 'writer', [])
        self.assertEqual(ledger.tip(), tip)
        self.assertEqual((store/'owner.json').read_bytes(), before)

    def test_owner_change_during_save_retains_prior_generation(self):
        first = self.save()
        binding, store = cp.config(self.root)
        ledger = cp.Ownership(self.root, binding, store)
        original = cp.atomic
        def racing(path, value):
            if path.name == 'manifest.json':ledger.acquire('another-writer')
            return original(path, value)
        with mock.patch.object(cp, 'atomic', side_effect=racing):
            with self.assertRaises(cp.Fault):cp.checkpoint(self.root, self.source)
        self.assertEqual(cp.latest(store)[0]['id'], first['id'])
        self.assertEqual(ledger.value(ledger.tip())['owner'], 'another-writer')

    def test_failed_preservation_has_no_persistent_lock_and_can_be_repaired(self):
        first = self.save(); self.signals(10)
        self.task['artifacts'] = [{'path':'missing.txt','required':True,'preserve':True}]
        self.write()
        with self.assertRaises(cp.Fault):usage.check(self.root)
        self.assertEqual(cp.latest(self.root/'.checkpoint')[0]['id'], first['id'])
        self.assertFalse((self.root/'.checkpoint/automatic-stop.json').exists())
        (self.root/'missing.txt').write_text('recovered actual bytes')
        self.assertEqual(usage.check(self.root)['action'], 'handoff')

    def test_migration_archives_only_obsolete_policy(self):
        first = self.save(); binding, store = cp.config(self.root)
        (store/'automatic-stop.json').write_text('historical automatic stop')
        cp.Ownership(self.root, binding, store).acquire('writer')
        owner = (store/'owner.json').read_bytes(); input_bytes = self.source.read_bytes()
        result = usage.migrate(self.root, owner='writer')
        self.assertIn('automatic-stop.json', result['archived'])
        self.assertEqual((store/'owner.json').read_bytes(), owner)
        self.assertEqual(self.source.read_bytes(), input_bytes)
        self.assertEqual(cp.latest(store)[0]['id'], first['id'])
        self.assertEqual(next((store/'legacy-policy').glob('*/automatic-stop.json')).read_text(), 'historical automatic stop')

    def test_continue_cli_requires_no_review_even_with_legacy_stop(self):
        self.save()
        (self.root/'.checkpoint/automatic-stop.json').write_text('{}')
        self.cli('resume', '--owner', 'writer')
        self.cli('checkpoint','--input',str(self.source),'--owner','writer')
        self.cli('release','--owner','writer')

    def test_uncertain_job_blocks_duplicate_execution_but_not_handoff(self):
        self.task['jobs'] = [{'id':'deployment','kind':'external','status':'unknown','source':'fixture','observed_at':cp.now()}]
        self.write(); self.save()
        self.cli('resume','--owner','writer',ok=False)
        self.signals(10)
        self.assertEqual(usage.check(self.root)['action'], 'handoff')

    def test_all_cached_hook_events_and_commands_allow_without_state_changes(self):
        self.save(); before = cp.latest(self.root/'.checkpoint')[0]['id']
        for event in ('SessionStart','PreToolUse','PostToolUse','PreCompact','Stop','Interrupt','SessionEnd'):
            response = subprocess.run([sys.executable,str(fixtures.SCRIPT.with_name('hook.py')),'--account-state',str(self.root)],
                input=json.dumps({'cwd':str(self.root),'hook_event_name':event,'tool_input':{'command':'uninstall'}}),capture_output=True,text=True)
            self.assertEqual(response.returncode, 0)
            self.assertEqual(json.loads(response.stdout), {})
        self.assertEqual(cp.latest(self.root/'.checkpoint')[0]['id'], before)

    def test_wrapper_skips_child_at_limit_then_honors_direct_override(self):
        self.save(); self.cli('resume','--owner','writer'); self.signals(15)
        command = ['run','--input',str(self.source),'--',sys.executable,'-c',"from pathlib import Path;Path('child-output').write_text('done')"]
        result = self.cli(*command, ok=False)
        self.assertEqual(result.returncode,75)
        self.assertFalse((self.root/'child-output').exists())
        usage.configure(self.root, 10, owner='writer')
        self.cli(*command)
        self.assertEqual((self.root/'child-output').read_text(),'done')
