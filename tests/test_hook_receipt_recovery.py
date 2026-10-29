"""Exact receipt recovery and registration diagnostics, without native trust edits."""
from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest
import subprocess
import shlex
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import account
import checkpoint as cp
import hook


class ReceiptRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.state=self.root/'state';self.state.mkdir()
        self.home=self.root/'home';self.home.mkdir()
        self.python=Path(sys.executable).resolve()
        self.defs=account.hook_definitions(Path(account.__file__).with_name('hook.py').resolve(),self.state,self.python)
        self.other={'hooks':[{'type':'command','command':'existing unrelated callback'}]}
        self.original={'hooks':{event:[value] for event,value in self.defs.items()}}
        self.backup=self.state/'hooks-temporary-backup-fixture.json'
        cp.atomic(self.backup,cp.encoded(self.original))
        cp.atomic(self.home/'hooks.json',cp.encoded({'hooks':{'SessionStart':[self.other]}}))
        cp.atomic(self.home/'config.toml',b'# Existing native permissions remain unchanged.\n')
        cp.atomic(self.state/'config.json',cp.encoded({'enabled':True,'codex_home':str(self.home),'observation_only':True,'projects':[]}))

    def files(self):
        return {str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file() and p.name!='writer.lock'}

    def recover(self,**kwargs):
        return account.restore_hooks(self.state,self.home,self.backup,True,kwargs.get('python',self.python))

    def deny_unchanged(self,**kwargs):
        before=self.files()
        with self.assertRaises((cp.Fault,OSError,ValueError)):self.recover(**kwargs)
        self.assertEqual(before,self.files())

    def test_missing_receipt_is_explicit_and_status_does_not_claim_collector_proves_delivery(self):
        before=self.files()
        with self.assertRaisesRegex(cp.Fault,'receipt missing'):
            account.restore_hooks(self.state,self.home,self.backup)
        self.assertEqual(before,self.files())
        result=account.registration_status(self.state)
        self.assertFalse(result['receipt_present']);self.assertFalse(result['configuration_complete'])
        self.assertFalse(result['native_delivery_verified_by_configuration'])

    def test_complete_exact_backup_recovery_preserves_other_hooks_config_and_trust(self):
        before=self.files();result=self.recover()
        self.assertTrue(result['receipt_recovered']);self.assertEqual(result['owned_definitions'],7)
        self.assertEqual(cp.read(self.home/'hooks.json')['hooks']['SessionStart'],[self.other,self.defs['SessionStart']])
        for key in ('home/config.toml','state/config.json','state/hooks-temporary-backup-fixture.json'):
            self.assertEqual(before[key],self.files()[key])
        self.assertFalse(result['native_trust_changed'])
        self.assertTrue(account.registration_status(self.state)['configuration_complete'])
        self.assertEqual(account.restore_hooks(self.state,self.home,self.backup)['restored'],[])

    def test_changed_missing_duplicate_and_wrong_event_backup_fail_closed(self):
        for kind in ('changed','missing','duplicate','wrong-event'):
            value=copy.deepcopy(self.original)
            if kind=='changed':value['hooks']['Stop'][0]['hooks'][0]['timeout']=60
            elif kind=='missing':value['hooks'].pop('Stop')
            elif kind=='duplicate':value['hooks']['Stop']*=2
            else:value['hooks']['UserPromptSubmit']=[copy.deepcopy(value['hooks']['Stop'][0])]
            cp.atomic(self.backup,cp.encoded(value));self.deny_unchanged()

    def test_wrong_profile_and_unrecognized_interpreter_fail_closed(self):
        config=cp.read(self.state/'config.json');config['codex_home']=str(self.root/'other')
        cp.atomic(self.state/'config.json',cp.encoded(config));self.deny_unchanged()
        config['codex_home']=str(self.home);cp.atomic(self.state/'config.json',cp.encoded(config))
        fake=self.root/'python3';fake.write_text('not an interpreter')
        self.deny_unchanged(python=fake)
        self.deny_unchanged(python=None)

    def test_customized_or_duplicate_current_hook_not_adopted(self):
        for event,entry in [('Stop',copy.deepcopy(self.defs['Stop'])),('UserPromptSubmit',copy.deepcopy(self.defs['Stop']))]:
            if event=='Stop':entry['hooks'][0]['timeout']=60
            cp.atomic(self.home/'hooks.json',cp.encoded({'hooks':{event:[entry]}}));self.deny_unchanged()
        cp.atomic(self.home/'hooks.json',cp.encoded({'hooks':{'Stop':[self.defs['Stop'],self.defs['Stop']]}}));self.deny_unchanged()

    def test_hook_write_failure_leaves_valid_receipt_for_safe_normal_retry(self):
        real=cp.atomic;before=(self.home/'hooks.json').read_bytes()
        def write(path,data):
            if path==self.home/'hooks.json':raise PermissionError('fixture denied hook write')
            return real(path,data)
        with mock.patch.object(cp,'atomic',side_effect=write):
            with self.assertRaises(PermissionError):self.recover()
        self.assertEqual((self.home/'hooks.json').read_bytes(),before)
        self.assertTrue((self.state/'hooks-receipt.json').exists())
        self.assertFalse(account.registration_status(self.state)['configuration_complete'])
        self.assertEqual(len(account.restore_hooks(self.state,self.home,self.backup)['restored']),7)

    def test_registration_diagnoses_missing_duplicate_and_historical_delivery(self):
        self.recover();path=self.home/'hooks.json';value=cp.read(path)
        value['hooks']['Stop']=[];value['hooks']['PreToolUse']*=2;cp.atomic(path,cp.encoded(value))
        delivery={'event':'Stop','observed_at':'2026-01-01T00:00:00+00:00','task_id':'historical'}
        cp.atomic(self.state/'hook-delivery.json',cp.encoded(delivery))
        status=account.registration_status(self.state)
        self.assertFalse(status['configuration_complete']);self.assertEqual(status['managed_definition_counts']['Stop'],0)
        self.assertEqual(status['managed_definition_counts']['PreToolUse'],2)
        self.assertEqual(status['last_delivery'],delivery)
        self.assertFalse(status['native_delivery_verified_by_configuration'])

    def test_unbound_account_maintenance_records_delivery_without_enrollment(self):
        project=self.root/'project';project.mkdir()
        subprocess.run(['git','init','-q',str(project)],check=True)
        (project/'work.txt').write_text('fixture')
        subprocess.run(['git','add','.'],cwd=project,check=True)
        subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],cwd=project,check=True)
        config=cp.read(self.state/'config.json');config['auto_enrollment']={'enabled':True}
        cp.atomic(self.state/'config.json',cp.encoded(config));before=(self.state/'config.json').read_bytes()
        cmd=shlex.join(['python3',str(Path(account.__file__)),'--state',str(self.state),'status'])
        event={'cwd':str(project),'session_id':'actual-fixture-chat','hook_event_name':'PreToolUse',
               'tool_name':'Bash','tool_input':{'command':cmd}}
        result=subprocess.run([sys.executable,str(Path(hook.__file__)),'--account-state',str(self.state)],
                              input=json.dumps(event),text=True,capture_output=True,check=True)
        self.assertEqual(json.loads(result.stdout),{})
        self.assertFalse((project/'.checkpoint').exists())
        self.assertEqual((self.state/'config.json').read_bytes(),before)
        receipt=cp.read(self.state/'chat-delivery'/(cp.sha(b'actual-fixture-chat')+'.json'))
        self.assertEqual(receipt['chat_id'],'actual-fixture-chat');self.assertIsNone(receipt['task_id'])
        self.assertEqual(receipt['event'],'PreToolUse');self.assertTrue(receipt['parent_pid'])


if __name__=='__main__':unittest.main()
