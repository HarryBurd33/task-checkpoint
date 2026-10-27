import copy,json,subprocess,sys,tempfile,unittest,shlex,datetime as dt
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import checkpoint as cp, reserve, monitor, hook, account, telemetry
import test_reserve_policy as fixtures

class ReserveIntegrationTests(unittest.TestCase):
    setUp=fixtures.ReserveTests.setUp
    signals=fixtures.ReserveTests.signals
    grant=fixtures.ReserveTests.grant
    def review(self):
        s,r=cp.inspect(self.root)
        self.assertEqual(r['issues'],[])
        value={'checkpoint_id':s['id'],'task_id':s['task_id'],'next_action':s['task']['next_action']['description'],'verification':s['task']['next_action']['verification'],'current_fingerprint':r['current_fingerprint'],'observed_at':cp.now(),'authorization':{'confirmed':True,'scope':'fixture work only','source':'Current explicit fixture user instruction'},'resources':{'adequate_for_bounded_action':True,'evidence':'Fresh account readings under explicit reserve; bounded fixture no paid work','observed_at':cp.now()},'resolutions':{}}
        path=self.store/'review.json';cp.atomic(path,cp.encoded(value));return path
    def test_normal_review_is_required_then_hook_and_collector_obey_ten(self):
        self.grant();cp.atomic(self.store/'signals.json',cp.encoded(self.signals()))
        with self.assertRaises(cp.Fault):
            cp.resume(self.root,self.store/'missing-review.json','fixture',[])
        self.assertTrue(cp.policy(self.signals(),self.root)['checkpoint_required'])
        cp.resume(self.root,self.review(),'fixture',[])
        self.assertFalse(cp.policy(self.signals(),self.root)['checkpoint_required'])
        self.assertEqual(reserve.status(self.root)['override']['state'],'active')
        state=self.root.parent/('account-'+self.root.name);state.mkdir()
        self.addCleanup(lambda:__import__('shutil').rmtree(state,ignore_errors=True))
        cp.atomic(state/'config.json',cp.encoded({'enabled':True,'projects':[{'root':str(self.root),'task_id':self.binding['task_id'],'project_id':self.binding['project_id']}]}))
        cp.atomic(state/'signals.json',cp.encoded(self.signals()))
        result=monitor.evaluate_registered(state,self.signals());self.assertEqual(result['projects'][0]['status'],'no-low-signal')
        result=monitor.evaluate_registered(state,self.signals(10));self.assertEqual(result['projects'][0]['status'],'checkpoint-verified')
        self.assertTrue((self.store/'automatic-stop.json').exists());self.assertTrue(cp.policy(self.signals(10),self.root)['checkpoint_required'])
    def test_ten_then_exhaustion_with_retained_owner_and_actual_resume(self):
        self.grant();cp.resume(self.root,self.review(),'fixture',[])
        monitor.stop_for_signals(self.root,self.signals(10))
        reserve.grant(self.root,'exhaustion',self.signals(9),'User explicitly chooses exhaustion','Current fixture user')
        cp.resume(self.root,self.review(),'fixture',[])
        self.assertFalse((self.store/'automatic-stop.json').exists())
        self.assertFalse(cp.policy(self.signals(0),self.root)['checkpoint_required'])
        denied=self.signals(0);denied['records'][0]['blocked']=True
        self.assertTrue(cp.policy(denied,self.root)['checkpoint_required'])
    def test_legacy_and_native_obey_identical_pending_active_and_denial_gates(self):
        def legacy(signals):
            return {'account_quota':[dict(r) for r in signals['records']]}
        self.grant()
        self.assertTrue(cp.policy(legacy(self.signals(21)),self.root)['checkpoint_required'])
        cp.resume(self.root,self.review(),'fixture',[])
        self.assertFalse(cp.policy(legacy(self.signals(14)),self.root)['checkpoint_required'])
        self.assertTrue(cp.policy(legacy(self.signals(10)),self.root)['checkpoint_required'])
        denied=legacy(self.signals(99));denied['account_quota'][0]['blocked']=True
        self.assertTrue(cp.policy(denied,self.root)['checkpoint_required'])
        self.assertTrue(cp.policy(denied)['checkpoint_required'])

    def test_hook_stop_persists_after_fresh_healthy_reading_until_review(self):
        cp.atomic(self.store/'signals.json',cp.encoded(self.signals(20)))
        def invoke():
            result=subprocess.run([sys.executable,str(Path(hook.__file__)),],input=json.dumps({'cwd':str(self.root),'hook_event_name':'PreToolUse','tool_name':'exec_command','tool_input':{'cmd':'echo ordinary'}}),text=True,capture_output=True,check=True)
            return json.loads(result.stdout)
        self.assertEqual(invoke()['hookSpecificOutput']['permissionDecision'],'deny')
        self.assertTrue((self.store/'automatic-stop.json').exists())
        cp.atomic(self.store/'signals.json',cp.encoded(self.signals(80)))
        self.assertEqual(invoke()['hookSpecificOutput']['permissionDecision'],'deny')
        cp.resume(self.root,self.review(),'fixture',[])
        self.assertEqual(invoke(),{})

    def test_missing_input_or_failed_save_keeps_durable_stop(self):
        self.source.unlink()
        cp.atomic(self.store/'signals.json',cp.encoded(self.signals(20)))
        def invoke():
            response=subprocess.run([sys.executable,str(Path(hook.__file__))],input=json.dumps({'cwd':str(self.root),'hook_event_name':'PreToolUse','tool_name':'exec_command','tool_input':{'cmd':'echo ordinary'}}),text=True,capture_output=True)
            return response,json.loads(response.stdout)
        response,data=invoke()
        self.assertTrue((self.store/'automatic-stop.json').exists())
        cp.atomic(self.store/'signals.json',cp.encoded(self.signals(80)))
        self.assertEqual(invoke()[1]['hookSpecificOutput']['permissionDecision'],'deny')
        # No prior semantic source/generation: saving fails but the stop survives.
        (self.store/'automatic-stop.json').unlink();(self.store/'latest.json').unlink()
        cp.atomic(self.store/'signals.json',cp.encoded(self.signals(20)))
        response,data=invoke();self.assertEqual(response.returncode,2)
        self.assertTrue((self.store/'automatic-stop.json').exists())
        cp.atomic(self.store/'signals.json',cp.encoded(self.signals(80)))
        self.assertEqual(invoke()[1]['hookSpecificOutput']['permissionDecision'],'deny')

    def test_pending_reset_is_not_automatic_resume(self):
        self.grant();future=self.base+dt.timedelta(hours=2)
        fresh=self.signals(80,at=future,reset=future+dt.timedelta(hours=1))
        self.assertTrue(reserve.blocked(reserve.assess(self.root,fresh,now=future)))
        self.assertFalse(reserve.blocked(reserve.assess(self.root,fresh,now=future,allow_pending=True)))

    def test_override_does_not_enter_transfer_bundle(self):
        import transfer,zipfile
        self.grant();archive=self.store/'bundle.zip';transfer.package(self.root,archive)
        with zipfile.ZipFile(archive) as z:
            self.assertFalse(any('allowance-override' in name for name in z.namelist()))
    def test_resume_preserves_other_owner_gate(self):
        self.grant();cp.resume(self.root,self.review(),'first',[])
        with self.assertRaises(cp.Fault):cp.resume(self.root,self.review(),'second',[])
        self.assertEqual(cp.Ownership(self.root,self.binding,self.store).check()['owner'],'first')

class HookMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.gettempdir()).resolve();self.scripts=Path(hook.__file__).resolve().parent
    def event(self,command):return {'tool_name':'exec_command','tool_input':{'cmd':command}}
    def command(self,script,verb):return shlex.join(['python3',str(self.scripts/script),'--root',str(self.root)]+shlex.split(verb))
    def test_exact_maintenance_and_quota_allowed(self):
        for script,verb in [('reserve.py','status'),('reserve.py','grant --mode ten --reason user --source user --signals /tmp/signals.json'),('checkpoint.py','resume --review /tmp/review.json --owner current')]:
            self.assertTrue(hook.maintenance(self.event(self.command(script,verb)),self.root))
        self.assertTrue(hook.maintenance({'tool_name':'mcp__codex_app__get_usage_limits'},self.root))
    def test_ordinary_chained_foreign_and_injected_commands_rejected(self):
        values=['python3 -c "print(1)"','cat file',self.command('checkpoint.py','run --input data.json -- python3 work.py'),self.command('reserve.py','status')+'; touch /tmp/work',self.command('reserve.py','status')+' && echo work',self.command('reserve.py','status')+'\necho work',self.command('reserve.py','status').replace(str(self.root),'/another-root'),self.command('reserve.py','status')+' $(echo work)']
        for value in values:self.assertFalse(hook.maintenance(self.event(value),self.root),value)

    def test_untrusted_interpreter_named_python3_is_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            fake=Path(folder)/'python3';fake.write_text('#!/bin/sh\nexit 0\n');fake.chmod(0o755)
            command=shlex.join([str(fake),str(self.scripts/'reserve.py'),'--root',str(self.root),'status'])
            self.assertFalse(hook.maintenance(self.event(command),self.root))

class HookRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.state=self.root/'state';self.state.mkdir();self.home=self.root/'home';self.home.mkdir()
        self.owned={'hooks':[{'type':'command','command':'owned checkpoint callback'}]};self.other={'hooks':[{'type':'command','command':'unrelated callback'}]}
        cp.atomic(self.state/'hooks-receipt.json',cp.encoded({'definitions':{'PreToolUse':self.owned}}))
        self.backup=self.state/'hooks-temporary-backup-fixture.json';cp.atomic(self.backup,cp.encoded({'hooks':{'PreToolUse':[self.owned]}}))
        cp.atomic(self.home/'hooks.json',cp.encoded({'hooks':{'PreToolUse':[self.other]}}))
    def test_restore_is_idempotent_and_keeps_unrelated_edits(self):
        first=account.restore_hooks(self.state,self.home,self.backup);self.assertEqual(first['restored'],['PreToolUse'])
        self.assertEqual(account.restore_hooks(self.state,self.home,self.backup)['restored'],[])
        self.assertEqual(cp.read(self.home/'hooks.json')['hooks']['PreToolUse'],[self.other,self.owned])
        self.assertFalse(first['native_trust_changed'])
    def test_wrong_backup_fails_without_overwrite(self):
        before=cp.content(self.home/'hooks.json');cp.atomic(self.backup,cp.encoded({'hooks':{}}))
        with self.assertRaises(cp.Fault):account.restore_hooks(self.state,self.home,self.backup)
        self.assertEqual(cp.content(self.home/'hooks.json'),before)
