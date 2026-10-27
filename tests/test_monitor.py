import json
from pathlib import Path, PureWindowsPath
import plistlib
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'
sys.path.insert(0, str(SCRIPTS))
import checkpoint as cp
import monitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        for args in [('init','-b','main'),('config','user.name','Fixture'),('config','user.email','fixture@example.invalid')]:
            subprocess.run(['git',*args],cwd=self.root,check=True,capture_output=True)
        (self.root/'.gitignore').write_text('.checkpoint/\n')
        (self.root/'work.txt').write_text('completed alpha\n')
        for args in [('add','.'),('commit','-m','fixture')]:
            subprocess.run(['git',*args],cwd=self.root,check=True,capture_output=True)
        self.store = self.root/'.checkpoint';self.store.mkdir()
        self.binding = {'schema_version':1,'task_id':'fixture','project_id':'example/fixture','store':None,'ownership':'local'}
        cp.atomic(self.store/'config.json',cp.encoded(self.binding))
        self.task = cp.read(cp.ASSETS/'task-template.json')
        self.task['objective'] = 'Complete beta without repeating alpha'
        self.task['completed'] = ['alpha completed']
        self.task['artifacts'] = [{'path':'work.txt','required':True,'preserve':True}]
        self.task['next_action'] = {'description':'Create beta.txt','verification':'Check alpha hash and confirm beta is absent'}
        cp.atomic(self.store/'input.json',cp.encoded(self.task))
        self.initial = cp.checkpoint(self.root,self.store/'input.json')
        self.state = Path(self.tmp.name)/'account';self.state.mkdir()
        self.config = {'version':1,'enabled':True,'guard_percent':20,'projects':[dict(root=str(self.root),task_id='fixture',project_id='example/fixture')]}
        cp.atomic(self.state/'config.json',cp.encoded(self.config))

    def signals(self, remaining=15, observed=None):
        value = {'records':[{'kind':'codex_plan','remaining':remaining,'unit':'percent_remaining','observed_at':observed or cp.now(),'source':'test-supported-sensor','window':'weekly','resets_at':'2099-01-01T00:00:00+00:00'}]}
        cp.atomic(self.state/'signals.json',cp.encoded(value))
        return value

    def evaluate(self, *args):
        return monitor.evaluate_registered(self.state,self.signals(*args))

    def test_threshold_saves_readback_and_preserves_next_action(self):
        before = cp.repo(self.root)
        result = self.evaluate()
        self.assertEqual(result['projects'][0]['status'],'checkpoint-verified')
        state,folder = cp.latest(self.store)
        self.assertEqual(state['task']['next_action'],self.task['next_action'])
        self.assertEqual(state['trigger'],'low-resource')
        self.assertTrue((folder/'HANDOFF.md').exists())
        self.assertEqual(before,cp.repo(self.root))
        self.assertFalse(cp.read(self.store/'automatic-stop.json')['automatic_resume'])

    def test_repeated_readings_and_percentage_drops_do_not_duplicate(self):
        self.evaluate(18);first = cp.latest(self.store)[0]['id']
        result = self.evaluate(10)
        self.assertEqual(result['projects'][0]['status'],'already-preserved')
        self.assertEqual(cp.latest(self.store)[0]['id'],first)
        (self.root/'work.txt').write_text('completed alpha\nexternal edit\n')
        self.evaluate(10)
        self.assertNotEqual(cp.latest(self.store)[0]['id'],first)

    def test_stale_unknown_high_and_reset_do_not_trigger(self):
        for signals in [self.signals(80),self.signals(10,'2000-01-01T00:00:00+00:00'),{'records':[]}]:
            result = monitor.evaluate_registered(self.state,signals)
            self.assertEqual(result['projects'][0]['status'],'no-low-signal')
        signals = self.signals(0);signals['records'][0]['resets_at']='2000-01-01T00:00:00+00:00'
        monitor.evaluate_registered(self.state,signals)
        self.assertEqual(cp.latest(self.store)[0]['id'],self.initial['id'])
        self.assertFalse((self.store/'automatic-stop.json').exists())

    def test_failed_save_keeps_previous_and_stop_then_recovers(self):
        with mock.patch.object(cp,'checkpoint',side_effect=cp.Fault('injected write failure')):
            result = self.evaluate()
        self.assertEqual(result['projects'][0]['status'],'preservation-failed')
        self.assertEqual(cp.latest(self.store)[0]['id'],self.initial['id'])
        self.assertEqual(cp.read(self.store/'automatic-stop.json')['checkpoint_status'],'failed')
        with self.assertRaises(cp.Fault):monitor.validate_resume(self.root,self.store)
        self.evaluate(80)
        self.assertEqual(cp.read(self.store/'automatic-stop.json')['checkpoint_status'],'verified')
        monitor.validate_resume(self.root,self.store)
        self.assertTrue((self.store/'automatic-stop.json').exists())

    def test_recovery_never_auto_resumes_or_clears_marker(self):
        self.evaluate()
        with self.assertRaises(cp.Fault):monitor.validate_resume(self.root,self.store)
        self.evaluate(80)
        monitor.validate_resume(self.root,self.store)
        self.assertTrue((self.store/'automatic-stop.json').exists())
        self.signals(10,'2000-01-01T00:00:00+00:00')
        with self.assertRaises(cp.Fault):monitor.validate_resume(self.root,self.store)
        self.signals(80)
        monitor.validate_resume(self.root,self.store)
        monitor.acknowledge_resume(self.root,self.store)
        self.assertFalse((self.store/'automatic-stop.json').exists())
        self.assertEqual(len(list((self.store/'automatic-stop-history').glob('*.json'))),1)

    def test_last_valid_fallback_honestly_stale_and_deduplicated(self):
        (self.store/'input.json').unlink()
        result = self.evaluate()
        self.assertEqual(result['projects'][0]['semantic_source'],'last-valid-checkpoint-fallback')
        first = cp.latest(self.store)[0]['id']
        result = self.evaluate(10)
        self.assertEqual(result['projects'][0]['status'],'already-preserved')
        self.assertEqual(cp.latest(self.store)[0]['id'],first)

    def test_missing_semantics_keeps_stop_without_inventing_summary(self):
        (self.store/'input.json').unlink();(self.store/'latest.json').unlink()
        self.assertEqual(self.evaluate()['projects'][0]['status'],'preservation-failed')
        self.assertTrue((self.store/'automatic-stop.json').exists())
        self.assertFalse((self.store/'input.json').exists())

    def test_wrong_binding_is_not_overwritten_and_other_projects_continue(self):
        self.config['projects'].insert(0,dict(self.config['projects'][0],task_id='wrong'))
        cp.atomic(self.state/'config.json',cp.encoded(self.config))
        results = self.evaluate()['projects']
        self.assertEqual(results[0]['status'],'preservation-failed')
        self.assertEqual(results[1]['status'],'checkpoint-verified')
        self.assertEqual(cp.read(self.store/'config.json'),self.binding)

    def test_active_worker_is_recorded_and_not_cancelled(self):
        cp.atomic(self.store/'router.json',cp.encoded({'active':{'id':'worker-7','pid':999999}}))
        self.evaluate()
        jobs = cp.latest(self.store)[0]['task']['jobs']
        self.assertEqual(jobs[-1]['id'],'worker-7')
        self.assertEqual(jobs[-1]['status'],'unknown')
        self.assertEqual(cp.read(self.store/'router.json')['active']['pid'],999999)

    def test_context_and_api_remain_separate_signals(self):
        cp.atomic(self.store/'signals.json',cp.encoded({'records':[{'kind':'context','remaining':100,'guard':1000,'unit':'tokens_remaining','observed_at':cp.now(),'source':'fixture-context'}]}))
        self.evaluate(80)
        self.assertEqual(cp.read(self.store/'automatic-stop.json')['low_kinds'],['context'])
        self.evaluate(80)
        cp.atomic(self.store/'signals.json',cp.encoded({'records':[]}))
        self.evaluate(80)
        with self.assertRaises(cp.Fault):monitor.validate_resume(self.root,self.store)

    def test_existing_guard_is_preserved_and_new_default_is_twenty(self):
        self.config['guard_percent']=10;cp.atomic(self.state/'config.json',cp.encoded(self.config))
        self.assertEqual(self.evaluate(14)['projects'][0]['status'],'no-low-signal')
        del self.config['guard_percent'];cp.atomic(self.state/'config.json',cp.encoded(self.config))
        self.assertEqual(self.evaluate(14)['projects'][0]['status'],'checkpoint-verified')

    def test_unresolved_resource_kind_survives_a_later_different_low_signal(self):
        cp.atomic(self.store/'signals.json',cp.encoded({'records':[{'kind':'context','remaining':10,'guard':1000,'unit':'tokens_remaining','observed_at':cp.now(),'source':'fixture-context'}]}))
        self.evaluate(80)
        cp.atomic(self.store/'signals.json',cp.encoded({'records':[]}))
        self.evaluate(10)
        self.assertEqual(cp.read(self.store/'automatic-stop.json')['low_kinds'],['codex_plan','context'])
        self.evaluate(80)
        with self.assertRaises(cp.Fault):monitor.validate_resume(self.root,self.store)

    def test_new_active_worker_changes_the_preservation_digest(self):
        self.evaluate();first=cp.latest(self.store)[0]['id']
        cp.atomic(self.store/'router.json',cp.encoded({'active':{'id':'new-worker','pid':888888}}))
        self.evaluate()
        state,_=cp.latest(self.store)
        self.assertNotEqual(state['id'],first)
        self.assertEqual(state['task']['jobs'][-1]['id'],'new-worker')
        again=state['id'];self.evaluate()
        self.assertEqual(cp.latest(self.store)[0]['id'],again)

    def test_secondary_marker_write_failure_does_not_block_other_project(self):
        other=Path(self.tmp.name)/'second'
        subprocess.run(['git','clone','--branch','main',str(self.root),str(other)],check=True,capture_output=True)
        store=other/'.checkpoint';store.mkdir()
        cp.atomic(store/'config.json',cp.encoded(dict(self.binding,task_id='second',project_id='example/second')))
        cp.atomic(store/'input.json',cp.encoded(self.task))
        self.config['projects'].append({'root':str(other),'task_id':'second','project_id':'example/second'})
        cp.atomic(self.state/'config.json',cp.encoded(self.config))
        original=cp.atomic
        def failing(path,data):
            if path==self.store/'automatic-stop.json':raise PermissionError('injected')
            return original(path,data)
        with mock.patch.object(cp,'atomic',side_effect=failing):result=self.evaluate()
        self.assertEqual(result['projects'][0]['status'],'preservation-failed')
        self.assertEqual(result['projects'][1]['status'],'checkpoint-verified')

    def test_low_reading_arriving_before_acknowledgment_keeps_stop(self):
        self.evaluate();self.evaluate(80)
        monitor.validate_resume(self.root,self.store)
        self.signals(1)
        with self.assertRaises(cp.Fault):monitor.acknowledge_resume(self.root,self.store)
        self.assertTrue((self.store/'automatic-stop.json').exists())

    def test_windows_install_failure_rolls_back_under_collector_lock_simulated(self):
        calls=[]
        def run(args,check=True):
            calls.append(args)
            self.assertTrue((self.state/'writer.lock').exists())
            if args==['whoami']:return subprocess.CompletedProcess(args,0,b'DESKTOP\\user',b'')
            if '/Query' in args and '/Create' not in str(calls):return subprocess.CompletedProcess(args,1,b'',b'')
            if '/Query' in args:raise subprocess.CalledProcessError(1,args)
            return subprocess.CompletedProcess(args,0,b'',b'')
        with mock.patch.object(monitor,'_run',side_effect=run):
            with self.assertRaises(cp.Fault):monitor.install_service(self.state,Path(sys.executable),'win32')
        self.assertTrue(any('/Delete' in a for a in calls))
        self.assertFalse((self.state/'monitor-service.json').exists())
        self.assertEqual(cp.read(self.state/'monitor-service-transaction.json')['rollback'],'restored')
        self.assertFalse((self.state/'writer.lock').exists())

    def test_service_mutation_refuses_active_worker(self):
        cp.atomic(self.store/'router.json',cp.encoded({'active':{'id':'busy'}}))
        with mock.patch.object(monitor,'_run') as run:
            with self.assertRaises(cp.Fault):monitor.install_service(self.state,Path(sys.executable),'win32')
            run.assert_not_called()

    def test_windows_service_success_then_modified_task_is_preserved_simulated(self):
        xml=monitor.windows_task_xml('python.exe','account.py',str(self.state),'DESKTOP\\user')
        calls=[]
        def run(args,check=True):
            calls.append(args)
            if args==['whoami']:return subprocess.CompletedProcess(args,0,b'DESKTOP\\user',b'')
            if '/Query' in args and not any('/Create' in a for a in calls):return subprocess.CompletedProcess(args,1,b'',b'')
            return subprocess.CompletedProcess(args,0,xml,b'')
        with mock.patch.object(monitor,'_run',side_effect=run):
            result=monitor.install_service(self.state,Path(sys.executable),'win32')
        self.assertTrue(result['installed']);self.assertFalse(result['execution_verified'])
        changed=xml.replace('account.py'.encode('utf-16-le'),'custom.py'.encode('utf-16-le'))
        with mock.patch.object(monitor,'_run',return_value=subprocess.CompletedProcess([],0,changed,b'')):
            with self.assertRaises(cp.Fault):monitor.uninstall_service(self.state)
        self.assertTrue((self.state/'monitor-service.json').exists())

    def test_macos_bootstrap_failure_restores_prior_service_simulated(self):
        home=Path(self.tmp.name)/'user-home';destination=home/'Library/LaunchAgents'/(monitor.LABEL+'.plist')
        destination.parent.mkdir(parents=True)
        prior=plistlib.dumps({'Label':monitor.LABEL,'ProgramArguments':['python','owned/account.py','--state',str(self.state),'tick'],'StartInterval':60})
        destination.write_bytes(prior)
        bootstraps=[]
        def run(args,check=True):
            self.assertTrue((self.state/'writer.lock').exists())
            if 'bootstrap' in args:
                bootstraps.append(args)
                if len(bootstraps)==1:raise subprocess.CalledProcessError(1,args)
            return subprocess.CompletedProcess(args,0,b'',b'')
        with mock.patch.object(Path,'home',return_value=home),mock.patch.object(monitor,'_run',side_effect=run):
            with self.assertRaises(cp.Fault):monitor.install_service(self.state,Path(sys.executable),'darwin')
        self.assertEqual(destination.read_bytes(),prior)
        self.assertEqual(len(bootstraps),2)
        self.assertEqual(cp.read(self.state/'monitor-service-transaction.json')['rollback'],'restored')

    def test_acknowledgment_cannot_race_collector_preservation_fence(self):
        self.evaluate();self.evaluate(80)
        with cp.lock(self.state/'preservation'):
            with self.assertRaises(cp.Fault):monitor.acknowledge_resume(self.root,self.store)
        self.assertTrue((self.store/'automatic-stop.json').exists())

    def test_macos_reinstall_keeps_original_uninstall_backup_simulated(self):
        home=Path(self.tmp.name)/'user-home';destination=home/'Library/LaunchAgents'/(monitor.LABEL+'.plist')
        destination.parent.mkdir(parents=True)
        prior=plistlib.dumps({'Label':monitor.LABEL,'ProgramArguments':['python','owned/account.py','--state',str(self.state),'tick'],'StartInterval':123})
        destination.write_bytes(prior)
        with mock.patch.object(Path,'home',return_value=home),mock.patch.object(monitor,'_run',return_value=subprocess.CompletedProcess([],0,b'',b'')):
            monitor.install_service(self.state,Path(sys.executable),'darwin')
            monitor.install_service(self.state,Path(sys.executable),'darwin')
            monitor.uninstall_service(self.state)
        self.assertEqual(destination.read_bytes(),prior)
        self.assertEqual(plistlib.loads((self.state/'monitor-service-before.plist').read_bytes())['StartInterval'],123)

    def test_windows_scheduler_xml_simulated(self):
        data = monitor.windows_task_xml(PureWindowsPath('C:/Program Files/Python/python.exe'),PureWindowsPath('C:/User/Skill/account.py'),PureWindowsPath('C:/User/State'), 'DESKTOP\\user')
        root = ET.fromstring(data);ns={'t':monitor.NS}
        self.assertEqual(root.find('.//t:Interval',ns).text,'PT1M')
        self.assertEqual(root.find('.//t:LogonType',ns).text,'InteractiveToken')
        self.assertEqual(root.find('.//t:RunLevel',ns).text,'LeastPrivilege')
        self.assertEqual(root.find('.//t:MultipleInstancesPolicy',ns).text,'IgnoreNew')
        self.assertEqual(root.find('.//t:DisallowStartIfOnBatteries',ns).text,'false')
        self.assertEqual(root.find('.//t:Command',ns).text,'C:\\Program Files\\Python\\python.exe')
        self.assertNotIn('Password',data.decode('utf-16'))

    def test_redirected_windows_scheduler_xml_encoding(self):
        # Native schtasks output: single-byte console text, UTF-16 declaration.
        xml = monitor.windows_task_xml('python.exe', 'account.py', 'state', 'DESKTOP\\user')
        console_output = xml.decode('utf-16').encode('ascii')
        self.assertEqual(monitor._xml_hash(console_output), monitor._xml_hash(xml))
        self.assertEqual(monitor._xml_hash(xml.decode('utf-16')), monitor._xml_hash(xml))
        utf8_output = b'\xef\xbb\xbf' + xml.decode('utf-16').encode('utf-8')
        self.assertEqual(monitor._xml_hash(utf8_output), monitor._xml_hash(xml))

    def test_launchd_template_simulated(self):
        path = monitor.service_template(self.state,Path(sys.executable),'darwin')
        value = plistlib.loads(path.read_bytes())
        self.assertEqual(value['Label'],monitor.LABEL)
        self.assertEqual(value['StartInterval'],60)
        self.assertTrue(value['RunAtLoad'])
        self.assertIn('account.py',value['ProgramArguments'][1])

if __name__=='__main__':unittest.main()
