from pathlib import Path
import subprocess,sys,unittest,tempfile,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import checkpoint as cp,transfer
from test_root_handoff import RootHandoffTests
from test_readiness import ReadinessTests
class IndexAndReleaseTests(RootHandoffTests):
 def test_actual_index_blob_and_worktree_survive_bundle(self):
  p=self.root/'alpha.txt';p.write_bytes(b'B staged\x00binary');self.git('add','alpha.txt');p.write_bytes(b'C working\x00binary')
  self.save();s,folder=cp.latest(self.store)
  self.assertEqual((folder/'index/0/alpha.txt').read_bytes(),b'B staged\x00binary')
  self.assertEqual((folder/'files/alpha.txt').read_bytes(),b'C working\x00binary')
  self.assertEqual(self.git('show','HEAD:alpha.txt'),b'alpha complete\n')
  self.assertEqual(cp.inspect(self.root)[1]['issues'],[])
  archive=self.store/'transfer.zip';m=transfer.package(self.root,archive)
  transfer.verify(archive,s['project_id'],s['task_id'],s['repository']['commit'])
  with zipfile.ZipFile(archive) as z:
   self.assertEqual(z.read('snapshots/'+s['id']+'/index/0/alpha.txt'),b'B staged\x00binary')
   self.assertEqual(z.read('snapshots/'+s['id']+'/files/alpha.txt'),b'C working\x00binary')
 def test_index_only_change_invalidates_resume_fingerprint(self):
  p=self.root/'alpha.txt';p.write_text('B');self.git('add','alpha.txt');p.write_text('C');self.save();before=cp.repo(self.root)['fingerprint']
  blob=self.git('hash-object','-w','--stdin',) if False else self.git('hash-object','-w','alpha.txt').decode().strip()
  self.git('update-index','--cacheinfo','100644,'+blob+',alpha.txt')
  self.assertNotEqual(cp.repo(self.root)['fingerprint'],before);self.assertIn('index-missing-or-changed:alpha.txt:0',cp.inspect(self.root)[1]['issues'])
 def test_unknown_job_blocks_release_until_verified_new_checkpoint(self):
  self.task['jobs']=[{'id':'synthetic-child','kind':'owned-child','status':'unknown','source':'fixture; no actual process','observed_at':cp.now()}]
  cp.atomic(self.source,cp.encoded(self.task));self.save();owner=cp.Ownership(self.root,self.binding,self.store);owner.acquire('fixture')
  with self.assertRaises(cp.Fault):owner.release()
  owner.check();self.task['jobs'][0]['status']='completed';cp.atomic(self.source,cp.encoded(self.task));self.save();self.assertTrue(owner.release()['released'])
class IdentityTests(ReadinessTests):
 def test_anonymous_low_and_recovered_records_never_notify(self):
  for values,at in [((10,15),0),((90,90),181)]:
   s=self.signals(values,at,(500,600))
   for r in s['records']:r.pop('account_fingerprint');r.pop('window')
   self.assertEqual(self.update(s,at)['status'],'user-action-required')
  self.deliver.assert_not_called()

class CollectorIdentityTests(unittest.TestCase):
 def test_supported_account_identity_survives_single_profile_normalization(self):
  import telemetry,hashlib
  payload={'accountId':'synthetic-account','rateLimits':{'primary':{'usedPercent':85,'resetsAt':4102444800},'secondary':{'usedPercent':90,'resetsAt':4102444860}}}
  observed=telemetry.normalize_codex(payload,cp.now())
  self.assertEqual(len(observed['records']),2)
  self.assertTrue(all(r['account_fingerprint']==hashlib.sha256(b'synthetic-account').hexdigest() for r in observed['records']))
  self.assertEqual([r['remaining'] for r in observed['records']],[15,10])
  payload.pop('accountId');self.assertTrue(all('account_fingerprint' not in r for r in telemetry.normalize_codex(payload,cp.now())['records']))
