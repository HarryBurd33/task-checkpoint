"""A preservation command must not strand a stop on another generation."""
import contextlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import checkpoint as cp
import monitor
import reserve
import test_stopped_shutdown as stopped

class StoppedCheckpointCliTests(unittest.TestCase):
    setUp=stopped.StoppedShutdownTests.setUp
    signals=stopped.StoppedShutdownTests.signals
    stop=stopped.StoppedShutdownTests.stop
    protected=stopped.StoppedShutdownTests.protected
    def command(self,*extra):
        return [sys.executable,str(Path(cp.__file__)),'--root',str(self.root),'checkpoint','--input',str(self.source),'--trigger','milestone',*extra]
    def run_cli(self,*extra):
        return subprocess.run(self.command(*extra),capture_output=True,text=True)
    def new_input(self):
        task=cp.read(self.source);task['completed'].append('Fixture job reconciled from independent current evidence.')
        cp.atomic(self.source,cp.encoded(task));return task
    def test_owner_preservation_keeps_stop_pointer_consistent_then_requires_resume(self):
        self.new_input();old=cp.read(self.store/'automatic-stop.json');owner=(self.store/'owner.json').read_bytes()
        out=self.run_cli('--owner','fixture-owner');self.assertEqual(out.returncode,0,out.stdout+out.stderr)
        value=json.loads(out.stdout);self.assertTrue(value['stop_normal_work']);self.assertFalse(value['automatic_resume'])
        self.assertTrue(Path(value['canonical_handoff']).is_file());self.assertTrue(Path(value['state']).is_file())
        saved,_=cp.latest(self.store);marker=cp.read(self.store/'automatic-stop.json')
        self.assertEqual(marker['checkpoint_id'],saved['id'])
        self.assertNotEqual(saved['id'],old['checkpoint_id'])
        self.assertEqual(marker['incident_id'],old['incident_id'])
        self.assertEqual(saved['task']['completed'],cp.read(self.source)['completed'])
        self.assertEqual((self.store/'owner.json').read_bytes(),owner)
        self.assertFalse((self.store/'resume.json').exists())
        self.assertEqual(cp.latest(self.store,previous=True)[0]['id'],old['checkpoint_id'])
    def test_direct_checkpoint_cannot_advance_past_a_stop(self):
        self.new_input();before=self.protected()
        with self.assertRaises(cp.Fault):cp.checkpoint(self.root,self.source,'milestone')
        self.assertEqual(before,self.protected())
    def test_unowned_or_foreign_request_leaves_pause_unchanged(self):
        self.new_input()
        for extra in [(),('--owner','other')]:
            before=self.protected();out=self.run_cli(*extra)
            self.assertNotEqual(out.returncode,0);self.assertEqual(before,self.protected())
    def test_foreign_input_and_retry_exhaustion_do_not_advance(self):
        self.new_input();other=self.root/'different.json';other.write_bytes(self.source.read_bytes())
        cmd=self.command('--owner','fixture-owner');cmd[cmd.index('--input')+1]=str(other)
        before=self.protected();out=subprocess.run(cmd,capture_output=True,text=True)
        self.assertNotEqual(out.returncode,0);self.assertEqual(before,self.protected())
        marker=cp.read(self.store/'automatic-stop.json');marker.update(checkpoint_status='failed',preservation_attempts=3);cp.atomic(self.store/'automatic-stop.json',cp.encoded(marker))
        before=self.protected();out=self.run_cli('--owner','fixture-owner')
        self.assertNotEqual(out.returncode,0);self.assertEqual(before,self.protected())
    def test_uncertain_worker_cannot_be_bypassed(self):
        cp.atomic(self.store/'router.json',cp.encoded({'version':1,'task_id':self.binding['task_id'],'history':[],'active':{'id':'busy','status':'unknown'}}))
        before=self.protected();out=self.run_cli('--owner','fixture-owner')
        self.assertNotEqual(out.returncode,0);self.assertEqual(before,self.protected())
    def test_fresh_review_and_explicit_resume_still_required_after_save(self):
        self.new_input();out=self.run_cli('--owner','fixture-owner');self.assertEqual(out.returncode,0,out.stdout)
        cp.atomic(self.store/'signals.json',cp.encoded(self.signals(90)))
        self.assertTrue((self.store/'automatic-stop.json').exists())
        review=reserve.prepare_review(self.root,'Bounded fixture recovery','Explicit fixture user resume','Fresh fixture resources and verified completed jobs',owner='fixture-owner')
        self.assertTrue((self.store/'automatic-stop.json').exists())
        result=cp.resume(self.root,Path(review['review']),'fixture-owner',[])
        self.assertTrue(result['implementation_allowed']);self.assertFalse((self.store/'automatic-stop.json').exists())
    def test_busy_collector_fence_does_not_move_checkpoint(self):
        before=self.protected()
        (self.store/'preservation').mkdir(exist_ok=True)
        with cp.lock(self.store/'preservation'):
            out=self.run_cli('--owner','fixture-owner')
        self.assertNotEqual(out.returncode,0);self.assertEqual(before,self.protected())
    def test_stop_appearing_during_snapshot_is_checked_before_promotion(self):
        marker=cp.read(self.store/'automatic-stop.json');(self.store/'automatic-stop.json').unlink()
        before=(self.store/'latest.json').read_bytes();real=cp.repo;calls=[]
        def inspect(root):
            result=real(root);calls.append(1)
            if len(calls)==2:cp.atomic(self.store/'automatic-stop.json',cp.encoded(marker))
            return result
        with mock.patch.object(cp,'repo',side_effect=inspect):
            with self.assertRaises(cp.Fault):cp.checkpoint(self.root,self.source,'milestone')
        self.assertEqual((self.store/'latest.json').read_bytes(),before)
        self.assertEqual(cp.read(self.store/'automatic-stop.json'),marker)
    def test_recover_previous_cannot_rewind_away_from_a_valid_stop(self):
        before=self.protected()
        out=subprocess.run([sys.executable,str(Path(cp.__file__)),'--root',str(self.root),'recover-previous','--owner','fixture-owner','--reason','Fixture explicit recovery'],capture_output=True,text=True)
        self.assertNotEqual(out.returncode,0);self.assertEqual(before,self.protected())
    def test_pending_lower_reserve_grant_keeps_its_original_anchor(self):
        grant=reserve.grant(self.root,'ten',self.signals(14),'Fixture explicit lower reserve','Current fixture user',owner='fixture-owner')
        original=grant['checkpoint_id'];self.new_input()
        out=self.run_cli('--owner','fixture-owner');self.assertEqual(out.returncode,0,out.stdout)
        self.assertTrue((self.store/'automatic-stop.json').exists())
        self.assertEqual(cp.read(self.store/reserve.NAME)['checkpoint_id'],original)
        review=reserve.prepare_review(self.root,'Bounded fixture','Current fixture user','Fresh scoped readings and completed jobs',owner='fixture-owner')
        result=cp.resume(self.root,Path(review['review']),'fixture-owner',[])
        self.assertTrue(result['implementation_allowed'])
        record=cp.read(self.store/reserve.NAME);self.assertEqual(record['checkpoint_id'],original)
        self.assertEqual(record['state'],'active')
    def test_failed_save_keeps_previous_generation_and_owner(self):
        (self.root/'work.txt').write_text('api_key=fixture-only-sensitive-value\n')
        before=(self.store/'latest.json').read_bytes();owner=(self.store/'owner.json').read_bytes()
        out=self.run_cli('--owner','fixture-owner');self.assertNotEqual(out.returncode,0)
        self.assertEqual((self.store/'latest.json').read_bytes(),before)
        self.assertEqual((self.store/'owner.json').read_bytes(),owner)
        self.assertEqual(cp.read(self.store/'automatic-stop.json')['checkpoint_status'],'failed')
        self.assertFalse((self.store/'resume.json').exists())
    def test_reviewed_recovery_can_restore_the_actual_pinned_generation(self):
        original=cp.read(self.store/'automatic-stop.json');self.new_input()
        out=self.run_cli('--owner','fixture-owner');self.assertEqual(out.returncode,0,out.stdout)
        # Model the old pointer drift while retaining both verified generations.
        cp.atomic(self.store/'automatic-stop.json',cp.encoded(original))
        owner=(self.store/'owner.json').read_bytes()
        out=subprocess.run([sys.executable,str(Path(cp.__file__)),'--root',str(self.root),'recover-previous','--owner','fixture-owner','--reason','Fixture explicitly restores verified pinned generation'],capture_output=True,text=True)
        self.assertEqual(out.returncode,0,out.stdout)
        self.assertEqual(cp.latest(self.store)[0]['id'],original['checkpoint_id'])
        self.assertEqual(cp.read(self.store/'automatic-stop.json'),original)
        self.assertEqual((self.store/'owner.json').read_bytes(),owner)

    def test_recovery_rechecks_owner_after_the_collector_fence(self):
        original=cp.read(self.store/'automatic-stop.json');self.new_input()
        self.assertEqual(self.run_cli('--owner','fixture-owner').returncode,0)
        cp.atomic(self.store/'automatic-stop.json',cp.encoded(original))
        before=(self.store/'latest.json').read_bytes();guard=monitor.resume_guard
        @contextlib.contextmanager
        def release_at_fence(root,store):
            with guard(root,store):
                cp.Ownership(root,self.binding,store).release()
                yield
        argv=['checkpoint.py','--root',str(self.root),'recover-previous','--owner','fixture-owner','--reason','Isolated pinned recovery']
        with mock.patch.object(monitor,'resume_guard',release_at_fence),mock.patch.object(sys,'argv',argv):
            with self.assertRaises(cp.Fault):cp.main()
        self.assertEqual((self.store/'latest.json').read_bytes(),before)
        self.assertEqual(cp.read(self.store/'automatic-stop.json'),original)

    def owner_loss_during_save(self,call):
        self.new_input();before=(self.store/'latest.json').read_bytes();original=cp.read(self.store/'automatic-stop.json')
        inspect=cp.repo;calls=[]
        def release_during_capture(root):
            result=inspect(root);calls.append(1)
            # Simulate a remote authority transition beyond this machine's
            # router fence; ordinary local release remains serialized by it.
            if len(calls)==call:cp.Ownership(root,self.binding,self.store)._release()
            return result
        with mock.patch.object(cp,'repo',side_effect=release_during_capture):
            with self.assertRaises(cp.Fault):monitor.preserve_stopped(self.root,self.source,'fixture-owner')
        self.assertEqual((self.store/'latest.json').read_bytes(),before)
        marker=cp.read(self.store/'automatic-stop.json')
        self.assertEqual(marker['checkpoint_id'],original['checkpoint_id'])
        self.assertEqual(marker['checkpoint_status'],'failed')
        self.assertIsNone(cp.Ownership(self.root,self.binding,self.store).value(cp.Ownership(self.root,self.binding,self.store).tip()).get('owner'))

    def test_stopped_save_rechecks_owner_before_capture(self):self.owner_loss_during_save(1)
    def test_stopped_save_rechecks_owner_before_promotion(self):self.owner_loss_during_save(3)

    def test_unchanged_stopped_save_rechecks_owner_before_success(self):
        before=(self.store/'latest.json').read_bytes();original=cp.read(self.store/'automatic-stop.json')
        inspect=cp.repo;released=[]
        def lose_remote_owner(root):
            result=inspect(root)
            if not released:
                released.append(1);cp.Ownership(root,self.binding,self.store)._release()
            return result
        with mock.patch.object(cp,'repo',side_effect=lose_remote_owner):
            with self.assertRaises(cp.Fault):monitor.preserve_stopped(self.root,self.source,'fixture-owner')
        self.assertEqual((self.store/'latest.json').read_bytes(),before)
        self.assertEqual(cp.read(self.store/'automatic-stop.json')['checkpoint_id'],original['checkpoint_id'])

if __name__=='__main__':unittest.main()
