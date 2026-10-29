"""Isolated retry authorization and collector invariants; no native-host claim."""
import json
from pathlib import Path
import shlex
import subprocess
import sys
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'
sys.path.insert(0, str(SCRIPTS))
import checkpoint as cp
import maintenance
import monitor
import readiness
import test_reserve_policy as fixtures


class PreservationRetryTests(unittest.TestCase):
    setUp = fixtures.ReserveTests.setUp
    signals = fixtures.ReserveTests.signals

    def failed(self, owned=False):
        if owned:
            cp.Ownership(self.root, self.binding, self.store).acquire('fixture')
        with mock.patch.object(monitor, '_source', side_effect=cp.Fault('fixture denied source')):
            for _ in range(3):
                with self.assertRaises(cp.Fault):
                    monitor.stop_for_signals(self.root, self.signals(20))
        self.assertEqual(cp.read(self.store/'automatic-stop.json')['preservation_attempts'], 3)

    def state(self):
        return {str(p.relative_to(self.store)): p.read_bytes() for p in self.store.rglob('*')
                if p.is_file() and p.name != 'writer.lock'}

    def retry(self, **kwargs):
        return readiness.retry_preservation(self.root, 'Repaired fixture source',
                    'Current fixture user', **(kwargs or {'vacant_owner': True}))

    def deny_unchanged(self, **kwargs):
        before = self.state()
        with self.assertRaises(cp.Fault):
            self.retry(**kwargs)
        self.assertEqual(before, self.state())

    def test_vacant_retry_retains_prior_stop_then_preserves_without_resume(self):
        self.failed()
        before = self.state(); marker = cp.read(self.store/'automatic-stop.json')
        result = self.retry()
        after = self.state()
        for name in before:
            if name != 'automatic-stop.json':
                self.assertEqual(before[name], after[name], name)
        updated = cp.read(self.store/'automatic-stop.json')
        for key in marker:
            if key != 'preservation_attempts':
                self.assertEqual(marker[key], updated[key], key)
        self.assertEqual(updated['preservation_attempts'], 0)
        self.assertFalse(result['implementation_allowed'])
        self.assertFalse(cp.Ownership(self.root, self.binding, self.store).tip())
        self.deny_unchanged()  # Cannot repeatedly renew an unused retry sequence.
        monitor.stop_for_signals(self.root, self.signals(20))
        self.assertEqual(cp.read(self.store/'automatic-stop.json')['checkpoint_status'], 'verified')
        self.assertFalse((self.store/'resume.json').exists())
        self.assertFalse(cp.Ownership(self.root, self.binding, self.store).tip())

    def test_matching_owner_keeps_exact_lease(self):
        self.failed(owned=True)
        owner = cp.Ownership(self.root, self.binding, self.store)
        before = (owner.tip(), (self.store/'owner.json').read_bytes())
        self.retry(owner='fixture')
        self.assertEqual(before, (owner.tip(), (self.store/'owner.json').read_bytes()))

    def test_wrong_owner_or_false_vacancy_denied(self):
        self.failed(owned=True)
        self.deny_unchanged(owner='other')
        self.deny_unchanged(vacant_owner=True)

    def test_named_owner_without_lease_denied(self):
        self.failed()
        self.deny_unchanged(owner='fixture')

    def test_foreign_ledger_and_receipt_identity_denied_even_with_matching_token(self):
        self.failed(owned=True)
        ledger=cp.Ownership(self.root,self.binding,self.store)
        receipt=cp.read(self.store/'owner.json')
        changed=dict(receipt,task_id='foreign')
        cp.atomic(self.store/'owner.json',cp.encoded(changed)); self.deny_unchanged(owner='fixture')
        cp.atomic(self.store/'owner.json',cp.encoded(receipt))
        ledger.update(ledger.tip(),changed); self.deny_unchanged(owner='fixture')
        (self.store/'owner.json').unlink()
        ledger.update(ledger.tip(),{'owner':None,'task_id':'foreign'})
        self.deny_unchanged(vacant_owner=True)

    def test_stale_or_missing_ownership_receipt_denied(self):
        self.failed(owned=True)
        owner = self.store/'owner.json'; saved = owner.read_bytes(); owner.unlink()
        self.deny_unchanged(owner='fixture')
        owner.write_bytes(saved)
        ledger = cp.Ownership(self.root, self.binding, self.store)
        ledger.update(ledger.tip(), {'owner': None})
        self.deny_unchanged(vacant_owner=True)

    def test_stop_identity_status_counts_and_missing_stop_fail_closed(self):
        self.failed(); path = self.store/'automatic-stop.json'; original = cp.read(path)
        for change in ({'task_id':'foreign'}, {'project_id':'foreign'},
                       {'checkpoint_status':'verified'}, {'preservation_attempts':True},
                       {'preservation_attempts':0}, {'preservation_attempts':4},
                       {'preservation_attempts':-1}, {'incident_id':''}, {'retry_history':{}}):
            with self.subTest(change=change):
                cp.atomic(path, cp.encoded(dict(original, **change))); self.deny_unchanged()
        path.unlink(); self.deny_unchanged()

    def test_terminal_foreign_and_unknown_lifecycle_denied(self):
        self.failed()
        for status in ('completed', 'transferred', 'canceled', 'resumed', 'unknown'):
            readiness.lifecycle(self.root, 'active', 'Fixture lifecycle')
            value = cp.read(self.store/'task-lifecycle.json'); value['status'] = status
            cp.atomic(self.store/'task-lifecycle.json', cp.encoded(value)); self.deny_unchanged()
        value['status']='active'; value['task_id']='foreign'
        cp.atomic(self.store/'task-lifecycle.json', cp.encoded(value)); self.deny_unchanged()

    def test_active_uncertain_and_foreign_router_denied(self):
        self.failed()
        for journal in ({'version':1,'task_id':self.binding['task_id'],'active':{'status':'unknown'}},
                        {'version':1,'task_id':'foreign','active':None}):
            cp.atomic(self.store/'router.json',cp.encoded(journal)); self.deny_unchanged()

    def test_collector_router_and_store_locks_refuse_concurrent_retry(self):
        self.failed()
        guard = self.store/'preservation'; guard.mkdir(exist_ok=True)
        common = self.root/'.git/checkpoint-router'; common.mkdir(exist_ok=True)
        for folder in (guard, common, self.store):
            with self.subTest(folder=folder), cp.lock(folder):
                self.deny_unchanged()

    def test_corrupt_previous_generation_denied(self):
        self.failed()
        pointer = cp.read(self.store/'latest.json'); pointer['hashes']['state.json']='0'*64
        cp.atomic(self.store/'latest.json',cp.encoded(pointer)); self.deny_unchanged()

    def test_reason_source_and_owner_selection_are_required(self):
        self.failed()
        for reason,source,kwargs in [(' ','User',{'vacant_owner':True}),
                ('Repair',' ',{'vacant_owner':True}), ('Repair','User',{}),
                ('Repair','User',{'owner':'fixture','vacant_owner':True}),
                ('Repair','User',{'owner':' '})]:
            before=self.state()
            with self.assertRaises(cp.Fault):
                readiness.retry_preservation(self.root,reason,source,**kwargs)
            self.assertEqual(before,self.state())

    def test_repeated_failure_is_still_bounded_to_three_then_explicit_retry(self):
        self.failed(); self.retry()
        with mock.patch.object(monitor,'_source',side_effect=cp.Fault('still broken')) as source:
            for _ in range(5):
                with self.assertRaises(cp.Fault): monitor.stop_for_signals(self.root,self.signals(20))
        self.assertEqual(source.call_count,3)
        self.assertEqual(cp.read(self.store/'automatic-stop.json')['preservation_attempts'],3)
        self.retry()
        self.assertEqual(len(cp.read(self.store/'automatic-stop.json')['retry_history']),2)

    def test_unknown_jobs_can_be_preserved_but_never_resumed_by_retry(self):
        self.failed(); task=cp.read(self.source)
        task['jobs']=[{'id':'uncertain','kind':'fixture','status':'unknown',
                      'source':'Current fixture observation','observed_at':cp.now()}]
        cp.atomic(self.source,cp.encoded(task)); self.retry()
        monitor.stop_for_signals(self.root,self.signals(20))
        saved,_=cp.latest(self.store)
        self.assertEqual(saved['task']['jobs'][0]['status'],'unknown')
        self.assertTrue((self.store/'automatic-stop.json').exists())
        self.assertFalse((self.store/'resume.json').exists())

    def test_stopped_native_callback_allows_only_exact_retry_cli(self):
        self.failed()
        argv=['python3',str(SCRIPTS/'readiness.py'),'--root',str(self.root.resolve()),
              'retry-preservation','--vacant-owner','--reason','Repaired fixture source',
              '--source','Current fixture user']
        cmd=shlex.join(argv)
        for name in ('exec_command','Bash'):
            self.assertTrue(maintenance.classify({'tool_name':name,'tool_input':{'cmd':cmd}},
                            self.root.resolve())[0])
        event={'cwd':str(self.root),'hook_event_name':'PreToolUse','tool_name':'Bash',
               'tool_input':{'command':cmd}}
        hook=subprocess.run([sys.executable,str(SCRIPTS/'hook.py')],input=json.dumps(event),
                            text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(hook.stdout),{})
        result=subprocess.run(argv,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        for bad in (cmd+'; echo work',cmd.replace(str(self.root.resolve()),'/foreign'),
                    cmd.replace('--vacant-owner',''),cmd.replace('retry-preservation','check')):
            self.assertFalse(maintenance.classify({'tool_name':'Bash','tool_input':{'command':bad}},
                             self.root.resolve())[0])


if __name__=='__main__': unittest.main()
