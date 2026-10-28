"""Isolated enrollment and chat-scoped stop regression tests, not native proof."""
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
SCRIPTS = Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'
sys.path.insert(0, str(SCRIPTS))
import checkpoint as cp
import enrollment
import hook
import maintenance

class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()/'repo'; self.root.mkdir()
        self.state = self.root.parent/'account'; self.state.mkdir()
        for args in [('init','-b','main'),('config','user.name','Test'),('config','user.email','test@example.invalid')]: self.git(*args)
        (self.root/'work.txt').write_text('original\n')
        self.git('add','.'); self.git('commit','-m','Fixture')
        cp.atomic(self.state/'config.json',cp.encoded({'version':1,'enabled':True,'guard_percent':20,'projects':[]}))
        enrollment.configure(self.state,True)
    def git(self,*args):
        return subprocess.check_output(['git',*args],cwd=self.root,stderr=subprocess.DEVNULL).decode().strip()
    def invoke(self,chat='owner-chat',name='PreToolUse',command='echo work',session=None):
        event={'cwd':str(self.root),'hook_event_name':name,'session_id':session or chat,'tool_name':'Bash','tool_input':{'command':command}}
        with mock.patch.dict(os.environ,{},clear=True), mock.patch('sys.stdin',io.StringIO(json.dumps(event))):
            if chat: os.environ['CODEX_THREAD_ID']=chat
            return hook.main(self.state)
    def stopped(self):
        enrollment.enroll(self.state,self.root,'owner-chat')
        binding,store=cp.config(self.root)
        cp.atomic(store/'automatic-stop.json',cp.encoded({'schema_version':1,'task_id':binding['task_id'],'project_id':binding['project_id'],'checkpoint_status':'verified','checkpoint_id':'retained'}))
        return {p.name:p.read_bytes() for p in store.iterdir() if p.is_file()}
    def test_idempotent_enrollment_does_not_invent_progress_or_ownership(self):
        result=enrollment.enroll(self.state,self.root,'owner-chat')
        self.assertTrue(result['semantic_input_required']); self.assertFalse(result['ownership_acquired'])
        self.assertFalse(result['execution_scheduled'])
        enrollment.enroll(self.state,self.root,'owner-chat')
        config=cp.read(self.state/'config.json')
        self.assertEqual(len(config['projects']),1); self.assertFalse(config['projects'][0]['scheduled_dispatch'])
        self.assertEqual(self.git('check-ignore','.checkpoint/config.json'),'.checkpoint/config.json')
        self.assertFalse((self.root/'.checkpoint/input.json').exists())
        self.assertFalse((self.root/'.checkpoint/owner.json').exists())
    def test_disabled_root_and_session_exclusions_are_side_effect_free(self):
        enrollment.configure(self.state,False)
        self.assertEqual(enrollment.enroll(self.state,self.root,'one')['status'],'disabled')
        enrollment.configure(self.state,True,[self.root.parent],[])
        self.assertEqual(enrollment.enroll(self.state,self.root,'one')['status'],'excluded')
        enrollment.configure(self.state,True,[],['one'])
        self.assertEqual(enrollment.enroll(self.state,self.root,'one')['status'],'excluded')
        self.assertFalse((self.root/'.checkpoint').exists()); self.assertFalse((self.root/'.gitignore').exists())
    def test_exclusion_cannot_clear_existing_stop(self):
        self.stopped(); enrollment.configure(self.state,True,[self.root],['owner-chat'])
        self.assertEqual(self.invoke()['hookSpecificOutput']['permissionDecision'],'deny')
        self.assertTrue((self.root/'.checkpoint/automatic-stop.json').exists())
    def test_foreign_chat_does_not_inherit_or_write_task_state(self):
        protected=self.stopped()
        config=cp.read(self.state/'config.json')
        config['chat_scopes'][str(self.root)]['unrelated_session_ids']=['unrelated-chat']
        cp.atomic(self.state/'config.json',cp.encoded(config))
        for name in ('PreToolUse','PostToolUse','Stop','PreCompact','Interrupt','SessionEnd'):
            self.assertEqual(self.invoke('unrelated-chat',name),{})
        for name,data in protected.items(): self.assertEqual((self.root/'.checkpoint'/name).read_bytes(),data)
        self.assertFalse((self.root/'.checkpoint/native-hook-delivery.json').exists())
        receipt=cp.read(self.state/'chat-delivery'/(cp.sha(b'unrelated-chat')+'.json'))
        self.assertEqual(receipt['scope'],'foreign'); self.assertEqual(receipt['identity_source'],'session_id')
    def test_owner_and_unknown_identity_remain_stopped(self):
        self.stopped()
        for chat in ('owner-chat','new-continuation-chat',None): self.assertEqual(self.invoke(chat)['hookSpecificOutput']['permissionDecision'],'deny')
        self.assertEqual(self.invoke(None,session='unrelated-chat')['hookSpecificOutput']['permissionDecision'],'deny')
    def test_conflicting_or_invalid_identity_fails_closed(self):
        with mock.patch.dict(os.environ,{'CODEX_THREAD_ID':'one'}):
            with self.assertRaises(cp.Fault): enrollment.host_identity({'thread_id':'two','session_id':'one'})
        with self.assertRaises(cp.Fault): enrollment.enroll(self.state,self.root,'../../wrong')
    def test_host_session_identity_ignores_inherited_parent_environment(self):
        with mock.patch.dict(os.environ,{'CODEX_THREAD_ID':'parent-chat'}):
            self.assertEqual(enrollment.host_identity({'session_id':'child-root'}),('child-root','session_id'))
            self.assertEqual(enrollment.host_identity({}),(None,'unknown'))
    @unittest.skipUnless(sys.platform=='darwin','macOS system Python launcher')
    def test_native_system_python_launcher_is_valid_maintenance(self):
        self.stopped()
        safe=shlex.join(['/usr/bin/python3',str(SCRIPTS/'maintenance.py'),'--root',str(self.root),'status'])
        self.assertEqual(self.invoke(command=safe),{})
    def test_legacy_binding_never_auto_claimed_and_mapping_never_resumes(self):
        subprocess.run([sys.executable,str(SCRIPTS/'checkpoint.py'),'--root',str(self.root),'init','--task','existing','--project-id','project','--ownership','local'],check=True,capture_output=True)
        before=(self.root/'.checkpoint/config.json').read_bytes()
        self.assertEqual(enrollment.enroll(self.state,self.root,'other')['status'],'existing-binding')
        binding,_=cp.config(self.root); self.assertEqual(enrollment.scope({},self.root,binding,'other'),'legacy')
        self.assertFalse(enrollment.bind(self.state,self.root,'existing',['owner'])['resumed'])
        self.assertEqual((self.root/'.checkpoint/config.json').read_bytes(),before)
        self.assertEqual(cp.read(self.state/'config.json')['projects'],[])
        with self.assertRaises(cp.Fault): enrollment.bind(self.state,self.root,'wrong',['owner'])
        with self.assertRaises(cp.Fault): enrollment.bind(self.state,self.root,'existing',['replacement'])
    def test_existing_unknown_store_and_symlink_never_overwritten(self):
        (self.root/'.checkpoint').mkdir()
        self.assertEqual(enrollment.enroll(self.state,self.root,'owner')['status'],'existing-store-needs-review')
        (self.root/'.checkpoint').rmdir(); (self.root/'.checkpoint').symlink_to(self.state)
        with self.assertRaises(cp.Fault): enrollment.enroll(self.state,self.root,'owner')
    def test_changed_task_scope_rejected(self):
        enrollment.enroll(self.state,self.root,'owner'); binding,_=cp.config(self.root); binding['task_id']='replacement'
        with self.assertRaises(cp.Fault): enrollment.scope(cp.read(self.state/'config.json'),self.root,binding,'owner')
    def test_collector_lock_defers_enrollment_without_pausing(self):
        with cp.lock(self.state):
            self.assertEqual(enrollment.enroll(self.state,self.root,'owner')['status'],'deferred-collector-busy')
            self.assertEqual(self.invoke(),{})
        self.assertFalse((self.root/'.checkpoint').exists())
    def test_unborn_repository_defers_enrollment_and_allows_first_commit(self):
        self.git('update-ref','-d','refs/heads/main')
        self.assertEqual(enrollment.enroll(self.state,self.root,'owner')['status'],'not-eligible-no-commit')
        self.assertEqual(self.invoke(),{})
        self.assertFalse((self.root/'.checkpoint').exists())
    def test_registry_conflict_is_detected_before_any_workspace_write(self):
        config=cp.read(self.state/'config.json')
        config['projects']=[{'root':str(self.root),'task_id':'stale','project_id':'stale'}]
        cp.atomic(self.state/'config.json',cp.encoded(config))
        self.assertEqual(enrollment.enroll(self.state,self.root,'owner')['status'],'registry-conflict-needs-review')
        self.assertFalse((self.root/'.checkpoint').exists()); self.assertFalse((self.root/'.gitignore').exists())
    def test_bash_maintenance_allowed_but_ordinary_and_chained_commands_denied(self):
        self.stopped(); safe=shlex.join(['python3',str(SCRIPTS/'maintenance.py'),'--root',str(self.root),'status'])
        self.assertEqual(self.invoke(command=safe),{})
        for cmd in ('echo work',safe+' && echo work',safe+'; echo work'):
            self.assertEqual(self.invoke(command=cmd)['hookSpecificOutput']['permissionDecision'],'deny')
        for name in ('Bash','tools.Bash','exec_command','functions.exec_command'):
            self.assertTrue(maintenance.classify({'tool_name':name,'tool_input':{'command':safe}},self.root)[0])

if __name__=='__main__': unittest.main()
