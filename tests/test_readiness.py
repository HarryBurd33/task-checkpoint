import datetime as dt
from pathlib import Path
import subprocess,sys,tempfile,unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import checkpoint as cp
import readiness,monitor
class ReadinessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'repo';self.root.mkdir()
  for a in [('init','-b','main'),('config','user.name','Fixture'),('config','user.email','fixture@example.invalid')]:subprocess.run(['git',*a],cwd=self.root,check=True,capture_output=True)
  (self.root/'.gitignore').write_text('.checkpoint/\n');(self.root/'work.txt').write_text('alpha\n')
  for a in [('add','.'),('commit','-m','fixture')]:subprocess.run(['git',*a],cwd=self.root,check=True,capture_output=True)
  self.store=self.root/'.checkpoint';self.store.mkdir()
  cp.atomic(self.store/'config.json',cp.encoded({'schema_version':1,'task_id':'fixture','project_id':'example/fixture','ownership':'local','store':None}))
  t=cp.read(cp.ASSETS/'task-template.json');t['next_action']={'description':'Append beta','verification':'Read alpha and confirm beta absent'}
  cp.atomic(self.store/'input.json',cp.encoded(t));self.saved=cp.checkpoint(self.root,self.store/'input.json');self.base=readiness.stamp(cp.now())
  self.marker={'schema_version':1,'task_id':'fixture','project_id':'example/fixture','requested_at':self.base.isoformat(),'checkpoint_status':'verified','checkpoint_id':self.saved['id'],'low_kinds':['codex_plan'],'automatic_resume':False}
  cp.atomic(self.store/'automatic-stop.json',cp.encoded(self.marker));self.settings={'enabled':True,'notifier':'macos','scheduler_id':'fixture-collector'}
  self.deliver=mock.Mock(return_value={'adapter':'spy','display_observed':False})
 def at(self,n):return self.base+dt.timedelta(seconds=n)
 def signals(self,values=(10,15),at=0,reset=(60,120),account='profile-a'):
  return {'records':[{'kind':'codex_plan','source':'fixture','unit':'percent_remaining','remaining':v,'observed_at':self.at(at).isoformat(),'resets_at':self.at(r).isoformat(),'window':str(i),'account_fingerprint':account} for i,(v,r) in enumerate(zip(values,reset))]}
 def update(self,s,at=0):return readiness.update(self.root,s,self.settings,now=self.at(at),deliver=self.deliver)
 def arm(self):return self.update(self.signals())
 def healthy(self):return self.signals((80,90),181,(500,600))
 def test_all_resets_plus_60(self):
  t=self.arm();self.assertEqual(t['not_before'],self.at(180).isoformat());self.assertFalse(t['automatic_resume']);self.assertEqual(t['scheduler_id'],'fixture-collector')
  self.assertEqual(self.update(self.signals((80,10),61,(500,120)),61)['status'],'pending');self.deliver.assert_not_called()
 def test_one_notification_no_implementation(self):
  self.arm();before=(self.root/'work.txt').read_bytes();t=self.update(self.healthy(),181)
  self.assertEqual(t['status'],'notified');self.assertEqual(self.update(self.healthy(),181)['status'],'notified');self.deliver.assert_called_once()
  self.assertTrue((self.store/'automatic-stop.json').exists());self.assertFalse(t['execution_authorized']);self.assertIn('Resume from HANDOFF.md',t['message']);self.assertEqual(before,(self.root/'work.txt').read_bytes())
 def test_missing_stale_past_reset_unknown(self):
  self.arm()
  for s in ({'records':[]},self.signals((90,90)),self.signals((90,90),181)):
   self.assertIn(self.update(s,181)['status'],('pending','user-action-required'))
  self.deliver.assert_not_called()
 def test_missing_window_or_different_account_unknown(self):
  self.arm();s=self.healthy();s['records'].pop();self.assertEqual(self.update(s,181)['status'],'pending')
  self.assertEqual(self.update(self.signals((90,90),181,(500,600),'profile-b'),181)['status'],'pending');self.deliver.assert_not_called()
 def test_missing_reset_manual_fallback(self):
  s=self.signals();s['records'][0].pop('resets_at');t=self.update(s);self.assertEqual(t['status'],'user-action-required');self.assertEqual(t['schedule_status'],'unsupported')
 def test_zero_is_low_null_unknown(self):
  self.assertEqual(self.update(self.signals((0,0)))['status'],'pending');self.assertEqual(self.update(self.signals((None,None)),181)['status'],'pending');self.deliver.assert_not_called()
 def test_custom_guard(self):
  s=self.signals((30,80));s['records'][0]['guard']=35;self.assertEqual(self.update(s)['status'],'pending')
 def test_lifecycle_retirement(self):
  for status in ('completed','canceled','transferred','resumed'):
   (self.store/'readiness.json').unlink(missing_ok=True);(self.store/'task-lifecycle.json').unlink(missing_ok=True)
   self.arm();readiness.lifecycle(self.root,status,'fixture instruction');self.assertEqual(self.update(self.healthy(),181)['status'],'retired')
  self.deliver.assert_not_called()
 def test_disable_or_cleared_stop_retires(self):
  self.arm();self.settings['enabled']=False;self.assertEqual(self.update(self.healthy(),181)['status'],'retired')
  (self.store/'readiness.json').unlink();self.settings['enabled']=True;self.arm();(self.store/'automatic-stop.json').unlink();self.assertEqual(self.update(self.healthy(),181)['status'],'retired')
 def test_delivery_failure_not_retried(self):
  self.arm();self.deliver.side_effect=OSError('fixture');self.assertEqual(self.update(self.healthy(),181)['status'],'delivery-failed');self.update(self.healthy(),181);self.deliver.assert_called_once()
 def test_uncertain_delivery_not_repeated(self):
  self.arm();t=cp.read(self.store/'readiness.json');t['status']='delivery-uncertain';cp.atomic(self.store/'readiness.json',cp.encoded(t));self.assertEqual(self.update(self.healthy(),181)['status'],'delivery-uncertain');self.deliver.assert_not_called()
 def test_worker_corruption_and_fence(self):
  self.arm();cp.atomic(self.store/'router.json',cp.encoded({'active':{'status':'unknown'}}));self.assertEqual(self.update(self.healthy(),181)['status'],'user-action-required');(self.store/'router.json').unlink()
  Path(self.saved['state']).write_text('{}');self.assertEqual(self.update(self.healthy(),181)['status'],'user-action-required');self.deliver.assert_not_called()
  with cp.lock(self.store/'readiness-fence'):
   with self.assertRaises(cp.Fault):self.update(self.healthy(),181)
 def test_wrong_ticket_preserved(self):
  self.arm();t=cp.read(self.store/'readiness.json');t['task_id']='other';cp.atomic(self.store/'readiness.json',cp.encoded(t))
  with self.assertRaises(cp.Fault):self.update(self.healthy(),181)
  self.assertEqual(cp.read(self.store/'readiness.json')['task_id'],'other')
 def test_preservation_bounded_to_three_attempts(self):
  account=Path(self.tmp.name)/'account';account.mkdir();cp.atomic(account/'config.json',cp.encoded({'enabled':True,'projects':[dict(root=str(self.root),task_id='fixture',project_id='example/fixture',readiness=self.settings)]}))
  with mock.patch.object(cp,'checkpoint',side_effect=cp.Fault('injected')) as save:
   for _ in range(5):monitor.evaluate_registered(account,self.signals())
  self.assertEqual(save.call_count,3);self.assertEqual(cp.latest(self.store)[0]['id'],self.saved['id'])
 def test_native_command_argv_and_timeout(self):
  with mock.patch.object(readiness.sys,'platform','darwin'),mock.patch.object(readiness.subprocess,'run',return_value=mock.Mock(returncode=0)) as run:r=readiness.notify('untrusted " & text','macos')
  self.assertFalse(r['display_observed']);self.assertEqual(run.call_args.kwargs['timeout'],15);self.assertEqual(run.call_args.args[0][-1],'untrusted " & text');self.assertNotIn('shell',run.call_args.kwargs)
