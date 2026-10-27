import copy
import datetime as dt
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'))
import checkpoint as cp
import reserve

class ReserveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for args in [('init','-b','main'),('config','user.name','Fixture'),('config','user.email','fixture@example.invalid')]:
            subprocess.run(['git',*args],cwd=self.root,check=True,capture_output=True)
        (self.root/'.gitignore').write_text('.checkpoint/\n'); (self.root/'work.txt').write_text('alpha\n')
        for args in [('add','.'),('commit','-m','fixture')]:
            subprocess.run(['git',*args],cwd=self.root,check=True,capture_output=True)
        self.store=self.root/'.checkpoint';self.store.mkdir()
        self.binding={'schema_version':1,'task_id':'reserve-fixture','project_id':'fixture/reserve','ownership':'local','store':None}
        cp.atomic(self.store/'config.json',cp.encoded(self.binding))
        self.task=cp.read(cp.ASSETS/'task-template.json')
        self.source=self.store/'input.json';cp.atomic(self.source,cp.encoded(self.task));self.saved=cp.checkpoint(self.root,self.source,'low-resource')
        self.base=reserve._current()
    def signals(self,n=14,at=None,reset=None,account='fixture-account',window='weekly'):
        return {'records':[{'kind':'codex_plan','remaining':n,'unit':'percent_remaining','source':'supported-fixture','observed_at':(at or self.base).isoformat(),'resets_at':(reset or self.base+dt.timedelta(hours=1)).isoformat(),'account_fingerprint':account,'window':window}]}
    def grant(self,mode='ten',signals=None):
        return reserve.grant(self.root,mode,signals or self.signals(),'User explicitly chose this reserve','Current fixture user instruction',now=self.base)
    def activate(self):
        owner=cp.Ownership(self.root,self.binding,self.store).acquire('fixture')
        cp.atomic(self.store/'resume.json',cp.encoded({'checkpoint_id':self.saved['id'],'owner':owner,'resumed_at':cp.now()}))
        reserve.activate(self.root)
    def check(self,signals,**kwargs):return reserve.assess(self.root,signals,**kwargs)
    def test_default_threshold_and_zero(self):
        for n,want in [(21,False),(20,True),(19,True),(0,True)]:self.assertEqual(reserve.blocked(self.check(self.signals(n))),want)
    def test_pending_is_not_resume_and_ten_floor(self):
        self.grant();self.assertTrue(reserve.blocked(self.check(self.signals())))
        self.assertFalse(reserve.blocked(self.check(self.signals(),allow_pending=True)))
        self.activate()
        for n,want in [(14,False),(10,True),(9,True),(0,True)]:self.assertEqual(reserve.blocked(self.check(self.signals(n))),want)
    def test_exhaustion_zero_vs_hard_denial(self):
        self.grant('exhaustion');self.activate()
        for n in (9,0):self.assertFalse(reserve.blocked(self.check(self.signals(n))))
        s=self.signals(0);s['records'].append({'kind':'codex_plan','unit':'percent_remaining','source':'provider','observed_at':self.base.isoformat(),'remaining':None,'blocked':True})
        self.assertTrue(reserve.blocked(self.check(s)))
    def test_unrelated_resources_not_waived(self):
        self.grant('exhaustion');self.activate()
        for kind,unit in [('context','tokens_remaining'),('api_balance','usd_remaining'),('local_resource','bytes_available')]:
            s=self.signals();s['records'].append({'kind':kind,'unit':unit,'source':'fixture','observed_at':self.base.isoformat(),'remaining':0})
            self.assertIn(kind,reserve.kinds(self.check(s)));self.assertTrue(reserve.blocked(self.check(s)))
    def test_missing_stale_future_unsupported_and_identity_fail_closed(self):
        self.grant();self.activate()
        cases=[{'records':[]},self.signals(at=self.base-dt.timedelta(minutes=3)),self.signals(at=self.base+dt.timedelta(minutes=1)),self.signals(account='other'),self.signals(window='other')]
        s=self.signals();s['records'][0]['supported']=False;cases.append(s)
        for s in cases:
            result=self.check(s);self.assertTrue(result['override_blocked']);self.assertIn('codex_plan',reserve.kinds(result))
    def test_multiple_windows_missing_or_low_secondary(self):
        s=self.signals();s['records']+=self.signals(60,window='daily')['records'];self.grant(signals=s);self.activate()
        self.assertTrue(self.check(self.signals())['override_blocked'])
        s['records'][1]['remaining']=10;self.assertTrue(reserve.blocked(self.check(s)))
    def test_reset_expiry_reverts_to_default(self):
        self.grant();self.activate();later=self.base+dt.timedelta(hours=1,seconds=1)
        s=self.signals(14,at=later,reset=later+dt.timedelta(hours=1));r=self.check(s,now=later)
        self.assertEqual(r['override']['effective'],'expired-default');self.assertTrue(reserve.blocked(r))
        s['records'][0]['remaining']=90;self.assertFalse(reserve.blocked(self.check(s,now=later)))
    def test_no_implicit_prearm_and_bad_mode(self):
        for n in (21,60):
            with self.assertRaises(cp.Fault):self.grant(signals=self.signals(n))
        with self.assertRaises(cp.Fault):reserve.grant(self.root,'other',self.signals(),'reason','source')
        for field in ('reason','source'):
            args=dict(reason='reason',source='source');args[field]=' '
            with self.assertRaises(cp.Fault):reserve.grant(self.root,'ten',self.signals(),**args)
    def test_ten_already_low_and_hard_denied_grants(self):
        for n in (10,0):
            with self.assertRaises(cp.Fault):self.grant(signals=self.signals(n))
        s=self.signals();s['records'][0]['blocked']=True
        with self.assertRaises(cp.Fault):self.grant('exhaustion',s)
    def test_initial_stop_must_have_been_preserved(self):
        cp.checkpoint(self.root,self.source,'milestone')
        with self.assertRaises(cp.Fault):self.grant()
    def test_grant_rejects_stale_unknown_anonymous_and_other_low(self):
        cases=[{'records':[]},self.signals(at=self.base-dt.timedelta(minutes=3))]
        s=self.signals();s['records'][0].pop('account_fingerprint');cases.append(s)
        s=self.signals();s['records'].append({'kind':'context','remaining':0,'unit':'tokens_remaining','source':'fixture','observed_at':self.base.isoformat()});cases.append(s)
        for s in cases:
            with self.assertRaises(cp.Fault):self.grant(signals=s)
    def test_active_router_or_unknown_job_rejects_grant(self):
        cp.atomic(self.store/'router.json',cp.encoded({'active':{'status':'unknown'}}))
        with self.assertRaises(cp.Fault):self.grant()
        (self.store/'router.json').unlink();self.task['jobs']=[{'id':'job','kind':'owned-child','status':'unknown','source':'fixture','observed_at':cp.now()}]
        cp.atomic(self.source,cp.encoded(self.task));cp.checkpoint(self.root,self.source,'low-resource')
        with self.assertRaises(cp.Fault):self.grant()
    def test_competing_owner_rejects(self):
        cp.Ownership(self.root,self.binding,self.store).acquire('other');(self.store/'owner.json').unlink()
        with self.assertRaises(cp.Fault):self.grant()
    def test_activation_requires_review_and_lease(self):
        self.grant()
        with self.assertRaises(cp.Fault):reserve.activate(self.root)
        cp.Ownership(self.root,self.binding,self.store).acquire('fixture')
        with self.assertRaises(cp.Fault):reserve.activate(self.root)
    def test_revoke_and_terminal_lifecycle_restore_default(self):
        self.grant();self.activate();reserve.revoke(self.root,'explicit user revocation');self.assertTrue(reserve.blocked(self.check(self.signals())))
        for status in ('completed','canceled','transferred'):
            cp.atomic(self.store/'task-lifecycle.json',cp.encoded({'project_id':self.binding['project_id'],'task_id':self.binding['task_id'],'status':status}))
            with self.assertRaises(cp.Fault):self.grant()
    def test_original_readings_not_changed(self):
        self.grant('exhaustion');self.activate();s=self.signals(0);old=copy.deepcopy(s);r=self.check(s)
        self.assertEqual(s,old);self.assertEqual(r['records'][0]['remaining'],0)
    def test_wrong_task_record_fails_closed(self):
        self.grant();v=cp.read(self.store/reserve.NAME);v['task_id']='foreign';cp.atomic(self.store/reserve.NAME,cp.encoded(v))
        with self.assertRaises(cp.Fault):self.check(self.signals())
    def test_no_authority_imported_into_transfer(self):
        import transfer,zipfile
        self.grant();a=self.store/'bundle.zip';transfer.package(self.root,a)
        with zipfile.ZipFile(a) as z:self.assertFalse(any('allowance-override' in n for n in z.namelist()))
    def test_pending_validate_uses_fresh_sourced_snapshot(self):
        self.grant();reserve.validate_resume(self.root)
        s=self.signals(at=self.base-dt.timedelta(minutes=3));cp.atomic(self.store/'allowance-override-signals.json',cp.encoded(s))
        with self.assertRaises(cp.Fault):reserve.validate_resume(self.root)

    def test_failed_or_changed_marker_denies_even_low_resource_generation(self):
        for status,ident in [('failed',self.saved['id']),('pending',self.saved['id']),('verified','wrong-generation')]:
            cp.atomic(self.store/'automatic-stop.json',cp.encoded({'project_id':self.binding['project_id'],'task_id':self.binding['task_id'],'checkpoint_status':status,'checkpoint_id':ident,'low_kinds':['codex_plan']}))
            with self.assertRaises(cp.Fault):self.grant()
    def test_stopped_context_missing_low_unknown_then_fresh_adequate(self):
        cp.atomic(self.store/'automatic-stop.json',cp.encoded({'project_id':self.binding['project_id'],'task_id':self.binding['task_id'],'checkpoint_status':'verified','checkpoint_id':self.saved['id'],'low_kinds':['codex_plan','context']}))
        with self.assertRaises(cp.Fault):self.grant()
        for remaining,stamp in [(0,self.base),(20000,self.base-dt.timedelta(minutes=3))]:
            cp.atomic(self.store/'signals.json',cp.encoded({'records':[{'kind':'context','source':'fixture','unit':'tokens_remaining','remaining':remaining,'observed_at':stamp.isoformat()}]}))
            with self.assertRaises(cp.Fault):self.grant()
        cp.atomic(self.store/'signals.json',cp.encoded({'records':[{'kind':'context','source':'fixture','unit':'tokens_remaining','remaining':20000,'observed_at':self.base.isoformat()}]}))
        self.assertEqual(self.grant()['state'],'pending_resume')

    def test_new_preservation_generation_does_not_destroy_valid_grant(self):
        self.grant();original=self.saved['id'];new=cp.checkpoint(self.root,self.source,'low-resource')
        owner=cp.Ownership(self.root,self.binding,self.store).acquire('fixture')
        cp.atomic(self.store/'resume.json',cp.encoded({'checkpoint_id':new['id'],'owner':owner,'resumed_at':cp.now()}))
        reserve.activate(self.root)
        value=cp.read(self.store/reserve.NAME);self.assertEqual(value['checkpoint_id'],original);self.assertEqual(value['resume_checkpoint_id'],new['id'])
        self.assertFalse(reserve.blocked(self.check(self.signals())))
    def test_arbitrary_receipt_generation_cannot_activate(self):
        self.grant();owner=cp.Ownership(self.root,self.binding,self.store).acquire('fixture')
        cp.atomic(self.store/'resume.json',cp.encoded({'checkpoint_id':'unrelated','owner':owner,'resumed_at':cp.now()}))
        with self.assertRaises(cp.Fault):reserve.activate(self.root)
    def test_lifecycle_away_and_back_cannot_revive_grant(self):
        self.grant();self.activate()
        for status in ('canceled','active'):
            cp.atomic(self.store/'task-lifecycle.json',cp.encoded({'project_id':self.binding['project_id'],'task_id':self.binding['task_id'],'status':status,'observed_at':cp.now()}))
            result=self.check(self.signals());self.assertTrue(reserve.blocked(result));self.assertNotEqual(result['override'].get('effective'),'ten')
    def test_original_stop_corruption_prevents_activation(self):
        self.grant();self.activate()
        # A new explicit pending grant pins this valid current stop, then corruption
        # cannot be hidden merely by creating a newer receipt.
        cp.Ownership(self.root,self.binding,self.store).release();self.grant()
        Path(self.saved['state']).write_text('{}')
        owner=cp.Ownership(self.root,self.binding,self.store).acquire('fixture')
        cp.atomic(self.store/'resume.json',cp.encoded({'checkpoint_id':self.saved['id'],'owner':owner,'resumed_at':cp.now()}))
        with self.assertRaises(cp.Fault):reserve.activate(self.root)
