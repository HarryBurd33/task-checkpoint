import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts/checkpoint.py'
spec = importlib.util.spec_from_file_location('checkpoint', SCRIPT)
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        self.g('init', '-b', 'main')
        self.g('config', 'user.name', 'Checkpoint Test')
        self.g('config', 'user.email', 'test@example.invalid')
        (self.root / '.gitignore').write_text('.checkpoint/\n__pycache__/\n')
        (self.root / 'work.txt').write_text('completed step one\n')
        self.g('add', '.')
        self.g('commit', '-m', 'Fixture')
        self.cli('init', '--task', 'fixture', '--project-id', 'fixture-project', '--ownership', 'local')
        self.task = cp.read(cp.ASSETS / 'task-template.json')
        self.task.update(objective='Complete step two without repeating step one',completed=['Step one completed in work.txt'],next_action={'description':'Append step two to work.txt','verification':'Confirm work.txt contains completed step one and no step two'},artifacts=[{'path':'work.txt','required':True,'preserve':True}])
        self.source = self.root / '.checkpoint/input.json'
        self.write()

    def g(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.DEVNULL).decode().strip()

    def cli(self, *args, ok=True, root=None):
        r = subprocess.run([sys.executable,str(SCRIPT),'--root',str(root or self.root),*args],capture_output=True,text=True)
        self.assertEqual(r.returncode == 0,ok,r.stderr+r.stdout)
        return r

    def write(self):
        cp.atomic(self.source,cp.encoded(self.task))

    def save(self):
        return cp.checkpoint(self.root,self.source)

    def review(self):
        s,r=cp.inspect(self.root)
        value={'checkpoint_id':s['id'],'task_id':s['task_id'],'next_action':s['task']['next_action']['description'],'verification':s['task']['next_action']['verification'],'current_fingerprint':r['current_fingerprint'],'observed_at':cp.now(),'authorization':{'confirmed':True,'scope':'fixture edit only','source':'test user request'},'resolutions':{},'resources':{'adequate_for_bounded_action':True,'evidence':'Bounded fixture; no model calls required','observed_at':cp.now()}}
        path=self.root/'.checkpoint/review.json'
        cp.atomic(path,cp.encoded(value))
        return path

    def test_roundtrip_preserves_dirty_work(self):
        (self.root/'work.txt').write_text('completed step one\nlocal change\n')
        before=cp.repo(self.root);saved=self.save()
        self.assertEqual(before,cp.repo(self.root))
        s,folder=cp.latest(self.root/'.checkpoint')
        self.assertEqual((folder/'files/work.txt').read_bytes(),(self.root/'work.txt').read_bytes())
        self.cli('verify')
        self.assertIn('Append step two',Path(saved['handoff']).read_text())

    def test_interrupted_write(self):
        first=self.save()
        with self.assertRaises(cp.Fault):cp.checkpoint(self.root,self.source,failpoint='before-promote')
        self.assertEqual(cp.latest(self.root/'.checkpoint')[0]['id'],first['id'])
        self.assertFalse((self.root/'.checkpoint/writer.lock').exists())

    def test_corruption_and_explicit_recovery(self):
        first=self.save();second=self.save();Path(second['state']).write_text('{}')
        self.cli('verify',ok=False);self.cli('verify','--previous')
        self.cli('recover-previous','--reason','corrupt fixture')
        self.assertEqual(cp.latest(self.root/'.checkpoint')[0]['id'],first['id'])

    def test_missing_backup_or_manifest(self):
        saved=self.save();folder=Path(saved['state']).parent
        (folder/'files/work.txt').unlink();self.cli('verify',ok=False)
        (folder/'manifest.json').unlink();self.cli('verify',ok=False)

    def test_changed_and_missing_workspace(self):
        self.save();(self.root/'work.txt').unlink()
        _,r=cp.inspect(self.root)
        self.assertIn('repository-changed',r['issues'])
        self.assertIn('artifact-missing-or-changed:work.txt',r['issues'])
        self.cli('resume','--review',str(self.review()),'--owner','second',ok=False)

    def test_stale_and_wrong_task(self):
        self.save();_,r=cp.inspect(self.root,max_age=-1)
        self.assertIn('stale-checkpoint',r['issues'])
        c=cp.read(self.root/'.checkpoint/config.json');c['task_id']='wrong'
        cp.atomic(self.root/'.checkpoint/config.json',cp.encoded(c));self.cli('inspect',ok=False)

    def test_duplicate_resume(self):
        self.save();review=self.review()
        self.cli('resume','--review',str(review),'--owner','first')
        self.cli('resume','--review',str(review),'--owner','second',ok=False)
        self.cli('owner-check');self.cli('release','--owner','first')
        self.cli('resume','--review',str(review),'--owner','second')

    def test_resume_requires_action_authorization_job_evidence(self):
        self.task['jobs']=[{'id':'external-1','kind':'deployment','status':'unknown','source':'fixture','observed_at':cp.now()}]
        self.write();self.save();review=self.review()
        self.cli('resume','--review',str(review),'--owner','agent',ok=False)
        r=cp.read(review)
        r['resolutions']={'job-needs-live-verification:external-1':{'evidence':'Provider reports completed; transaction ID checked','observed_at':cp.now(),'status':'completed'}}
        r['next_action']='wrong';cp.atomic(review,cp.encoded(r))
        self.cli('resume','--review',str(review),'--owner','agent',ok=False)
        r['next_action']=self.task['next_action']['description'];r['authorization']['confirmed']=False
        cp.atomic(review,cp.encoded(r));self.cli('resume','--review',str(review),'--owner','agent',ok=False)
        r['authorization']['confirmed']=True;cp.atomic(review,cp.encoded(r))
        self.cli('resume','--review',str(review),'--owner','agent')

    def test_schema_and_secrets(self):
        self.task['observations']=['key='+'sk-'+'Z'*30,'password='+'fake-secret-value']
        self.write();saved=self.save()
        self.assertNotIn('Z'*30,Path(saved['state']).read_text())
        self.assertNotIn('fake-secret-value',Path(saved['handoff']).read_text())
        (self.root/'work.txt').write_text('token: '+'ghp_'+'A'*30)
        with self.assertRaises(cp.Fault):self.save()
        self.assertEqual(cp.latest(self.root/'.checkpoint')[0]['id'],saved['id'])
        self.task['objective']=7;self.write()
        with self.assertRaises(cp.Fault):self.save()

    def test_sensitive_paths_and_symlinks(self):
        (self.root/'.env').write_text('PRIVATE=fixture')
        with self.assertRaises(cp.Fault):self.save()
        (self.root/'.env').unlink();(self.root/'linked').symlink_to(self.root/'work.txt')
        with self.assertRaises(cp.Fault):self.save()

    def test_windows_paths_simulated(self):
        for bad in ['C:/private/file','C:\\private\\file','../file','/tmp/file','a/../b','a\\b','//server/share']:
            with self.assertRaises(cp.Fault,msg=bad):cp.relative(bad)
        self.assertEqual(cp.relative('results/step two.txt'),'results/step two.txt')

    def test_boundary_error_and_success(self):
        self.save();self.cli('resume','--review',str(self.review()),'--owner','wrapper')
        r=self.cli('run','--input',str(self.source),'--',sys.executable,'-c','raise SystemExit(4)',ok=False)
        self.assertEqual(r.returncode,4);self.assertEqual(cp.latest(self.root/'.checkpoint')[0]['trigger'],'error')
        self.cli('release','--owner','wrapper');self.cli('resume','--review',str(self.review()),'--owner','wrapper')
        self.cli('run','--input',str(self.source),'--',sys.executable,'-c','print("bounded success")')
        self.assertEqual(cp.latest(self.root/'.checkpoint')[0]['trigger'],'milestone')

    def test_abrupt_exit_before_promotion(self):
        saved=self.save()
        code="import importlib.util,os;from pathlib import Path;spec=importlib.util.spec_from_file_location('cp',"+repr(str(SCRIPT))+");cp=importlib.util.module_from_spec(spec);spec.loader.exec_module(cp);original=cp.atomic;cp.atomic=lambda p,d:os._exit(91) if p.name=='latest.json' else original(p,d);cp.checkpoint(Path("+repr(str(self.root))+"),Path("+repr(str(self.source))+"))"
        r=subprocess.run([sys.executable,'-c',code])
        self.assertEqual(r.returncode,91)
        self.assertEqual(cp.latest(self.root/'.checkpoint')[0]['id'],saved['id'])
        self.assertTrue((self.root/'.checkpoint/writer.lock').exists())

    def test_controlled_shutdown_preserves_uncertain_child(self):
        import signal,time
        self.save();self.cli('resume','--review',str(self.review()),'--owner','wrapper')
        proc=subprocess.Popen([sys.executable,str(SCRIPT),'--root',str(self.root),'run','--input',str(self.source),'--',sys.executable,'-c',"from pathlib import Path;import time;Path('child-ready').touch();time.sleep(2)"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline=time.monotonic()+5
        while not (self.root/'child-ready').exists() and time.monotonic()<deadline:time.sleep(.05)
        proc.send_signal(signal.SIGTERM)
        out,err=proc.communicate(timeout=8)
        self.assertEqual(proc.returncode,143,err)
        state=cp.latest(self.root/'.checkpoint')[0]
        self.assertEqual(state['trigger'],'shutdown')
        self.assertEqual(state['task']['jobs'][-1]['status'],'unknown')
        self.assertIn('no cancellation claimed',json.loads(out)['child_status'])

    def test_manifest_named_artifact_and_credential_values(self):
        (self.root/'manifest.json').write_text('{"artifact":"fixture"}')
        self.save();self.cli('verify')
        secret='-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----'
        self.assertEqual(cp.redact(secret),'[REDACTED]')
        self.assertEqual(cp.redact({'api_key':'fictional'}),{'api_key':'[REDACTED]'})

    def test_remote_ownership_race(self):
        remote=Path(self.temp.name)/'remote.git'
        subprocess.check_call(['git','init','--bare',str(remote)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        binding=cp.read(self.root/'.checkpoint/config.json');binding['ownership']='remote';cp.atomic(self.root/'.checkpoint/config.json',cp.encoded(binding))
        self.g('remote','add','origin',str(remote));self.g('push','-u','origin','main')
        clone=Path(self.temp.name)/'clone'
        subprocess.check_call(['git','clone','--branch','main',str(remote),str(clone)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for key,value in [('user.name','Checkpoint Test'),('user.email','test@example.invalid')]:subprocess.check_call(['git','config',key,value],cwd=clone)
        self.cli('init','--task','fixture','--project-id','fixture-project','--ownership','remote',root=clone)
        c,store=cp.config(self.root);c['ownership']='remote';cp.atomic(self.root/'.checkpoint/config.json',cp.encoded(c))
        c2,store2=cp.config(clone);first,second=cp.Ownership(self.root,c,store),cp.Ownership(clone,c2,store2)
        self.assertEqual(first.tip(),second.tip())
        results=[];barrier=threading.Barrier(2)
        def race(ledger,label):
            barrier.wait()
            try:ledger.update('',{'owner':label,'token':label});results.append('won')
            except cp.Fault:results.append('rejected')
        a=threading.Thread(target=race,args=(first,'one'));b=threading.Thread(target=race,args=(second,'two'))
        a.start();b.start();a.join();b.join();self.assertCountEqual(results,['won','rejected'])
        with self.assertRaises(cp.Fault):first.acquire('third')

if __name__=='__main__':unittest.main()
