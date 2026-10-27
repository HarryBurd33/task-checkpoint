import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts/checkpoint.py'
spec = importlib.util.spec_from_file_location('root_cp', SCRIPT)
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)

class RootHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for args in [('init','-b','main'),('config','user.name','Fixture'),('config','user.email','fixture@example.invalid')]:
            self.git(*args)
        (self.root/'.gitignore').write_text('.checkpoint/\n')
        (self.root/'alpha.txt').write_text('alpha complete\n')
        (self.root/'HANDOFF.md').write_bytes(b'# Existing user notes\nKeep these bytes.\n')
        self.git('add','.');self.git('commit','-m','fixture')
        self.store=self.root/'.checkpoint';self.store.mkdir()
        self.binding={'schema_version':1,'task_id':'root-test','project_id':'example/root','ownership':'local','store':None,'root_handoff':True}
        cp.atomic(self.store/'config.json',cp.encoded(self.binding))
        self.task=cp.read(cp.ASSETS/'task-template.json')
        self.task.update(objective='Complete beta',completed=['alpha complete'],next_action={'description':'Write beta.txt','verification':'Hash alpha.txt and verify beta.txt absent'})
        self.source=self.store/'input.json';cp.atomic(self.source,cp.encoded(self.task))
    def git(self,*args):
        return subprocess.check_output(['git',*args],cwd=self.root,stderr=subprocess.DEVNULL)
    def save(self):return cp.checkpoint(self.root,self.source)
    def test_existing_text_and_detailed_next_step(self):
        before=cp.repo(self.root);saved=self.save();s,_=cp.latest(self.store)
        raw=(self.root/'HANDOFF.md').read_bytes()
        self.assertTrue(raw.endswith(b'# Existing user notes\nKeep these bytes.\n'))
        self.assertLess(raw.index(b'Write beta.txt'),300)
        self.assertIn(b'Hash alpha.txt',raw);self.assertIn(b'Copy this prompt',raw)
        self.assertIn(b'current authorization',raw);self.assertEqual(before,cp.repo(self.root))
        cp.verify_root(self.root,s)
        self.assertEqual(saved['handoff'],str(self.root/'HANDOFF.md'))
    def test_repeated_save_has_no_recursive_drift(self):
        first=self.save();before=cp.repo(self.root);second=self.save()
        self.assertNotEqual(first['id'],second['id']);self.assertEqual(before,cp.repo(self.root))
        s,_=cp.latest(self.store);cp.verify_root(self.root,s)
        self.assertEqual(cp.inspect(self.root)[1]['issues'],[])
        self.assertEqual((self.root/'HANDOFF.md').read_bytes().count(b' begin -->'),1)
    def test_tamper_and_foreign_task_fail_closed(self):
        self.save();root=self.root/'HANDOFF.md';raw=root.read_bytes()
        root.write_bytes(raw.replace(b'Write beta.txt',b'Write evil.txt'))
        with self.assertRaises(cp.Fault):self.save()
        root.write_bytes(raw.replace(b' root-test ',b' other-task '))
        with self.assertRaises(cp.Fault):self.save()
    def test_pointer_failure_rolls_back_root_and_prior_valid(self):
        first=self.save();old=(self.root/'HANDOFF.md').read_bytes();original=cp.atomic
        def fail(path,data):
            if path==self.store/'latest.json':raise OSError('fixture promotion failure')
            return original(path,data)
        with mock.patch.object(cp,'atomic',side_effect=fail):
            with self.assertRaises(OSError):self.save()
        self.assertEqual(cp.latest(self.store)[0]['id'],first['id'])
        self.assertEqual((self.root/'HANDOFF.md').read_bytes(),old)
    def test_staged_unstaged_binary_untracked_and_deleted(self):
        (self.root/'alpha.txt').write_text('alpha staged\n');self.git('add','alpha.txt')
        (self.root/'alpha.txt').write_text('alpha unstaged\n')
        (self.root/'binary.dat').write_bytes(bytes(range(256)))
        (self.root/'extra.txt').write_text('untracked\n')
        self.save();s,folder=cp.latest(self.store)
        self.assertIn('MM alpha.txt',s['repository']['status'])
        self.assertIn('?? binary.dat',s['repository']['status'])
        self.assertEqual((folder/'files/binary.dat').read_bytes(),bytes(range(256)))
        (self.root/'alpha.txt').unlink();self.save();s,_=cp.latest(self.store)
        self.assertTrue(next(x for x in s['artifacts'] if x['path']=='alpha.txt')['deleted'])
    def test_unrelated_edits_remain_visible(self):
        self.save();p=self.root/'HANDOFF.md';p.write_bytes(p.read_bytes()+b'Later user note\n')
        _,report=cp.inspect(self.root)
        self.assertIn('repository-changed',report['issues']);self.save()
        self.assertTrue(p.read_bytes().endswith(b'Later user note\n'))
        self.assertEqual(cp.inspect(self.root)[1]['issues'],[])
    def test_stale_projection_requires_explicit_refresh(self):
        self.save();old=(self.root/'HANDOFF.md').read_bytes();self.save();s,_=cp.latest(self.store)
        (self.root/'HANDOFF.md').write_bytes(old)
        with self.assertRaises(cp.Fault):cp.verify_root(self.root,s)
        self.assertIn('root-handoff-needs-reconciliation',cp.inspect(self.root)[1]['issues'])
        result=subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),'refresh-handoff'],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr);cp.verify_root(self.root,s)
    def test_enable_legacy_projection_explicitly(self):
        self.binding.pop('root_handoff');cp.atomic(self.store/'config.json',cp.encoded(self.binding))
        self.save()
        result=subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),'enable-root-handoff'],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(cp.read(self.store/'config.json')['root_handoff'])
        cp.verify_root(self.root,cp.latest(self.store)[0])
        self.assertTrue((self.root/'HANDOFF.md').read_bytes().endswith(b'# Existing user notes\nKeep these bytes.\n'))
    def test_legacy_binding_does_not_change_root(self):
        self.binding.pop('root_handoff');cp.atomic(self.store/'config.json',cp.encoded(self.binding))
        old=(self.root/'HANDOFF.md').read_bytes();self.save();self.assertEqual((self.root/'HANDOFF.md').read_bytes(),old)

if __name__=='__main__':unittest.main()
