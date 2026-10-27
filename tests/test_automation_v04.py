import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'skills/task-checkpoint/scripts'))
import checkpoint as cp
import planner
import router
import router_policy as policy
import telemetry
import transfer
import test_monitor as fixtures_monitor
import test_router_runtime as fixtures_router


class PlanTests(unittest.TestCase):
    g=fixtures_router.RouterRuntimeTests.g
    prepare=fixtures_router.RouterRuntimeTests.prepare
    def setUp(self):
        fixtures_router.RouterRuntimeTests.setUp(self)
        contract=copy.deepcopy(self.task['routing']);contract['escalation_reason']='Escalate to a higher qualified assignment on failed validation, within retry budget'
        package={'objective':'Return exactly42','permitted_files':[],'permitted_actions':['return-result'],
                 'capabilities':[],'assignment':{'model':'deterministic-fixture','effort':'medium','reason':'Test-only qualified adapter'},
                 'checkpoint_boundary':'Exact result acceptance passes','contract':contract}
        self.task['routing']['work_packages']=[package]
        self.prepare()
    def test_cli_uses_configured_signals_without_project_copy(self):
        external=Path(self.temp.name)/'account-signals.json'
        cp.atomic(external,cp.encoded(self.signals))
        self.config['signals_path']=str(external)
        cp.atomic(self.config_path,cp.encoded(self.config))
        argv=['planner.py','--root',str(self.root),'status']
        with mock.patch.object(sys,'argv',argv),mock.patch.object(planner,'boundary',return_value={'action':'pause'}) as boundary,mock.patch('builtins.print'):
            planner.main()
        self.assertEqual(boundary.call_args.args[3],self.signals)
        override=Path(self.temp.name)/'override.json';cp.atomic(override,cp.encoded({'records':[]}))
        with mock.patch.object(sys,'argv',argv+['--signals',str(override)]),mock.patch.object(planner,'boundary',return_value={}) as boundary,mock.patch('builtins.print'):
            planner.main()
        self.assertEqual(boundary.call_args.args[3],{'records':[]})
        external.unlink()
        with mock.patch.object(sys,'argv',argv),self.assertRaises(cp.Fault):
            planner.main()

    def test_automatic_boundary_acceptance_and_dedup(self):
        planner.approve(self.root,self.source,self.config_path,'fixture package','current test')
        result=planner.boundary(self.root,self.source,self.config_path,self.signals,True)
        self.assertEqual(result['status'],'accepted')
        self.assertEqual(planner.boundary(self.root,self.source,self.config_path,self.signals,True)['action'],'complete')
        self.assertEqual(len(router.state(self.root)['history']),1)
    def test_dependencies_and_uncertainty(self):
        p=copy.deepcopy(self.task['routing']['work_packages'][0]);p['contract']['id']='second';p['contract']['dependencies']=[{'id':'one','status':'pending'}]
        self.task['routing']['work_packages'].append(p)
        choice=planner.select(self.task,self.config,self.signals,router.state(self.root))
        self.assertEqual(choice['task']['routing']['id'],'one')
        self.assertEqual(planner.select(self.task,self.config,self.signals,{'active':{'status':'uncertain'},'history':[]})['action'],'pause')
        self.task['routing']['work_packages'][0]['contract']['dependencies']=[{'id':'second','status':'pending'}]
        with self.assertRaisesRegex(cp.Fault,'cyclic'):planner.validate(self.task['routing']['work_packages'])
    def test_accepted_id_cannot_change_in_plan(self):
        planner.approve(self.root,self.source,self.config_path,'fixture','test')
        planner.boundary(self.root,self.source,self.config_path,self.signals,True)
        self.task['routing']['work_packages'][0]['objective']='Different objective'
        with self.assertRaisesRegex(cp.Fault,'changed after execution'):
            planner.select(self.task,self.config,self.signals,router.state(self.root))

    def test_source_change_requires_review(self):
        planner.approve(self.root,self.source,self.config_path,'fixture','test')
        (self.root/'work.txt').write_text('changed')
        with self.assertRaisesRegex(cp.Fault,'fresh review'):planner.boundary(self.root,self.source,self.config_path,self.signals,True)
    def test_source_change_between_approval_and_authorization_is_denied(self):
        planner.approve(self.root,self.source,self.config_path,'fixture','test')
        original=cp.checkpoint
        def raced(*args,**kwargs):
            (self.root/'work.txt').write_text('concurrent editor')
            return original(*args,**kwargs)
        with mock.patch.object(cp,'checkpoint',side_effect=raced):
            with self.assertRaisesRegex(cp.Fault,'Source changed after plan approval'):
                planner.boundary(self.root,self.source,self.config_path,self.signals,True)
        self.assertIsNone(router.state(self.root)['active'])

    def test_same_model_lower_effort_can_be_selected(self):
        low=copy.deepcopy(self.config['workers'][0]);low.update(id='same-low',effort='low',estimated_relative_cost=1)
        self.config['workers'][0].update(estimated_relative_cost=2)
        self.config['workers'].append(low)
        self.assertNotEqual(planner.select(self.task,self.config,self.signals,router.state(self.root))['assignment']['effort'],'low')
        low['qualification']['effort']='low'
        low['qualification']['source']='Separate synthetic lower-effort fixture qualification'
        choice=planner.select(self.task,self.config,self.signals,router.state(self.root))
        self.assertEqual(choice['assignment']['effort'],'low')
        self.assertIsNone(choice['assignment']['usage_savings'])
    def test_raw_twenty_percent_persists_stop(self):
        signals={'records':[{'kind':'codex_plan','source':'synthetic','observed_at':cp.now(),'remaining':20,'unit':'percent_remaining'}]}
        result=router.dispatch(self.root,self.source,self.config_path,signals,execute=True)
        self.assertTrue(result['normal_work_must_stop'])
        self.assertEqual(cp.read(self.root/'.checkpoint/automatic-stop.json')['checkpoint_status'],'verified')
        # A different model on the shared allowance cannot bypass the durable stop.
        with self.assertRaises(cp.Fault):router.dispatch(self.root,self.source,self.config_path,self.signals,execute=True)


class BundleTests(unittest.TestCase):
    def setUp(self):fixtures_monitor.MonitorTests.setUp(self)
    def package(self):
        self.archive=Path(self.tmp.name)/'bundle.zip'
        return transfer.package(self.root,self.archive)
    def test_roundtrip_is_quarantined_and_reproducible(self):
        meta=self.package();first=self.archive.read_bytes()
        self.assertEqual(first,transfer.zip_bytes({i.filename:zipfile.ZipFile(self.archive).read(i) for i in zipfile.ZipFile(self.archive).infolist()}))
        store=self.root/'.checkpoint';before=cp.read(store/'latest.json')
        receipt=transfer.quarantine(self.root,self.archive,meta['archive_sha256'],self.binding['project_id'],self.binding['task_id'],meta['source_revision'],store/'incoming'/meta['checkpoint_id'])
        self.assertFalse(receipt['worker_started']);self.assertFalse(receipt['owner_acquired'])
        self.assertEqual(cp.read(store/'latest.json'),before)
        self.assertNotIn('config.json',zipfile.ZipFile(self.archive).namelist())
        again=self.package();self.assertEqual(meta['archive_sha256'],again['archive_sha256'])
    def test_identity_revision_corruption_and_traversal_refused(self):
        meta=self.package()
        for project,task,revision in [('wrong',self.binding['task_id'],meta['source_revision']),(self.binding['project_id'],'wrong',meta['source_revision']),(self.binding['project_id'],self.binding['task_id'],'wrong')]:
            with self.assertRaises(cp.Fault):transfer.verify(self.archive,project,task,revision)
        with zipfile.ZipFile(self.archive,'a') as z:z.writestr('../escape',b'no')
        with self.assertRaises(cp.Fault):transfer.verify(self.archive,self.binding['project_id'],self.binding['task_id'],meta['source_revision'])
    def test_previous_valid_generation_preserved(self):
        first=cp.latest(self.store)[0]['id']
        (self.root/'work.txt').write_text('beta')
        cp.checkpoint(self.root,self.store/'input.json')
        meta=self.package()
        with zipfile.ZipFile(self.archive) as z:
            self.assertIn('snapshots/'+first+'/state.json',z.namelist())
    def test_offline_preserves_local_checkpoint(self):
        before=cp.read(self.store/'latest.json')
        with mock.patch.object(transfer,'gh',side_effect=cp.Fault('offline')):
            with self.assertRaises(cp.Fault):transfer.publish(self.root,'example/fixture')
        self.assertEqual(cp.read(self.store/'latest.json'),before)
    def test_public_repository_transport_refused(self):
        def response(args):
            return json.dumps({'full_name':'example/fixture','private':False,'permissions':{'push':True}} if args[-1]!='user' else {'login':'example'}).encode()
        with mock.patch.object(transfer,'gh',side_effect=response):
            with self.assertRaisesRegex(cp.Fault,'Private'):transfer.private_repo('example/fixture')

    def test_interrupted_upload_retries_without_duplicate_asset(self):
        uploads=[];remote={};release={}
        def backend(args):
            if args==['api','user']:return b'{"login":"example"}'
            if args==['api','repos/example/fixture']:return b'{"full_name":"example/fixture","private":true,"permissions":{"push":true}}'
            if args[:2]==['api','repos/example/fixture/releases?per_page=100']:return json.dumps([release] if release else []).encode()
            if args[0]=='api' and '/commits/' in args[1]:return b'{}'
            if args[:2]==['release','create']:
                release.update(tag_name=args[2],assets=[]);return b''
            if args[0]=='api' and '/releases/tags/' in args[1]:return json.dumps(release).encode()
            if args[:2]==['release','upload']:
                path=Path(args[3]);uploads.append(path.name);remote[path.name]=path.read_bytes()
                release['assets']=[{'name':path.name,'state':'uploaded'}]
                if len(uploads)==1:raise cp.Fault('connection lost after upload side effect')
                return b''
            if args[:2]==['release','download']:
                dest=Path(args[args.index('--dir')+1]);asset=args[args.index('--pattern')+1]
                (dest/asset).write_bytes(remote[asset]);return b''
            raise AssertionError(args)
        with mock.patch.object(transfer,'gh',side_effect=backend):
            with self.assertRaises(cp.Fault):transfer.publish(self.root,'example/fixture')
            result=transfer.publish(self.root,'example/fixture')
            self.assertEqual(result['status'],'verified');self.assertEqual(len(uploads),1)
            self.assertTrue(transfer.publish(self.root,'example/fixture')['deduplicated'])
        self.assertEqual(cp.latest(self.store)[0]['id'],self.initial['id'])
    def test_reviewed_adoption_keeps_stop_and_does_not_import_permission(self):
        cp.atomic(self.store/'automatic-stop.json',cp.encoded({'low_kinds':['codex_plan'],'checkpoint_status':'verified','checkpoint_id':self.initial['id']}))
        meta=self.package();ident=meta['checkpoint_id']
        transfer.quarantine(self.root,self.archive,meta['archive_sha256'],self.binding['project_id'],self.binding['task_id'],meta['source_revision'],self.store/'incoming'/ident)
        _,report=transfer.inspect_incoming(self.root,ident)
        cp.atomic(self.store/'plan-approval.json',cp.encoded({'stale':'not-imported'}))
        review={'checkpoint_id':ident,'current_fingerprint':report['current_fingerprint'],'observed_at':cp.now(),
                'authorization':{'confirmed':True,'scope':'adopt fixture data only','source':'current synthetic operator'},
                'destination_reconciliation':'Same verified source revision and snapshot; no dirty files or jobs'}
        cp.atomic(self.store/'adopt-review.json',cp.encoded(review))
        result=transfer.adopt(self.root,ident,self.store/'adopt-review.json')
        self.assertFalse(result['owner_acquired']);self.assertFalse(result['worker_started'])
        self.assertFalse((self.store/'plan-approval.json').exists())
        self.assertTrue((self.store/'automatic-stop.json').exists())
        self.assertFalse((self.store/'owner.json').exists())
    def test_tampered_quarantine_extraction_is_never_promoted(self):
        meta=self.package();ident=meta['checkpoint_id']
        incoming=self.store/'incoming'/ident
        transfer.quarantine(self.root,self.archive,meta['archive_sha256'],self.binding['project_id'],self.binding['task_id'],meta['source_revision'],incoming)
        tampered=cp.read(incoming/'semantic-input.json');tampered['objective']='fabricated accepted work'
        cp.atomic(incoming/'semantic-input.json',cp.encoded(tampered))
        _,report=transfer.inspect_incoming(self.root,ident)
        review={'checkpoint_id':ident,'current_fingerprint':report['current_fingerprint'],'observed_at':cp.now(),
                'authorization':{'confirmed':True,'scope':'fixture','source':'test'},'destination_reconciliation':'same source'}
        cp.atomic(self.store/'adopt-review.json',cp.encoded(review))
        transfer.adopt(self.root,ident,self.store/'adopt-review.json')
        self.assertEqual(cp.read(self.store/'input.json')['objective'],self.task['objective'])
    def test_interrupted_adoption_retries_verified_incoming_data(self):
        original_input=cp.read(self.store/'input.json')
        incoming_input=copy.deepcopy(original_input);incoming_input['objective']='Incoming beta objective'
        cp.atomic(self.store/'input.json',cp.encoded(incoming_input));meta=self.package()
        cp.atomic(self.store/'input.json',cp.encoded(original_input))
        ident=meta['checkpoint_id'];incoming=self.store/'incoming'/ident
        transfer.quarantine(self.root,self.archive,meta['archive_sha256'],self.binding['project_id'],self.binding['task_id'],meta['source_revision'],incoming)
        _,report=transfer.inspect_incoming(self.root,ident)
        review={'checkpoint_id':ident,'current_fingerprint':report['current_fingerprint'],'observed_at':cp.now(),
                'authorization':{'confirmed':True,'scope':'fixture','source':'test'},'destination_reconciliation':'Retain original input and adopt beta'}
        cp.atomic(self.store/'adopt-review.json',cp.encoded(review))
        atomic=cp.atomic
        def interrupted(path,data):
            result=atomic(path,data)
            if path==self.store/'input.json':raise RuntimeError('injected power loss after incoming input install')
            return result
        with mock.patch.object(cp,'atomic',side_effect=interrupted):
            with self.assertRaises(RuntimeError):transfer.adopt(self.root,ident,self.store/'adopt-review.json')
        self.assertEqual(cp.read(self.store/'latest.json')['id'],self.initial['id'])
        result=transfer.adopt(self.root,ident,self.store/'adopt-review.json')
        self.assertEqual(result['adopted'],ident)
        self.assertEqual(cp.read(self.store/'input.json')['objective'],'Incoming beta objective')
        self.assertEqual(cp.read(self.store/'adoption-retired'/ident/'input.json'),original_input)

    def test_new_publication_requires_current_remote_owner(self):
        binding=dict(self.binding,ownership='remote')
        cp.atomic(self.store/'config.json',cp.encoded(binding))
        with mock.patch.object(transfer,'private_repo'),mock.patch.object(cp.Ownership,'check',side_effect=cp.Fault('Foreign owner; no publish')),mock.patch.object(transfer,'gh') as network:
            with self.assertRaisesRegex(cp.Fault,'Foreign owner'):transfer.publish(self.root,'example/fixture')
            network.assert_not_called()
        self.assertEqual(cp.latest(self.store)[0]['id'],self.initial['id'])

    def test_automatic_receive_selects_task_and_never_adopts(self):
        tag='checkpoint-bundle-fixture-'+'a'*32;asset='bundle-'+'b'*64+'.zip'
        releases=[{'tag_name':tag,'published_at':cp.now(),'draft':False,'assets':[{'name':asset,'state':'uploaded'}]},
                  {'tag_name':'other-task','published_at':cp.now(),'assets':[]}]
        with mock.patch.object(transfer,'private_repo'),mock.patch.object(transfer,'gh',return_value=json.dumps(releases).encode()),mock.patch.object(transfer,'receive',return_value={'worker_started':False,'owner_acquired':False}) as receive:
            result=transfer.receive_latest(self.root,'example/fixture')
            self.assertFalse(result['automatic_adoption']);self.assertFalse(result['worker_started'])
            self.assertEqual(receive.call_args.args[2:4],(tag,asset))
            self.assertEqual(receive.call_args.args[4],cp.git_text(self.root,'rev-parse','HEAD'))
            releases[0]['published_at']=None
            transfer.gh.return_value=json.dumps(releases).encode()
            with self.assertRaises(cp.Fault):transfer.receive_latest(self.root,'example/fixture')

    def test_transferred_stop_retains_secondary_account_scope(self):
        import profiles,monitor
        primary=profiles.fingerprint('synthetic-primary')
        secondary=profiles.fingerprint('synthetic-secondary')
        cp.atomic(self.store/'automatic-stop.json',cp.encoded({'low_kinds':['codex_plan'],
            'resource_accounts':[secondary],'checkpoint_status':'verified','checkpoint_id':self.initial['id']}))
        meta=self.package();ident=meta['checkpoint_id']
        self.assertEqual(meta['version'],2)  # Legacy version1 readers reject this envelope.
        with zipfile.ZipFile(self.archive) as bundle:
            downgraded={n:bundle.read(n) for n in bundle.namelist()}
        legacy=json.loads(downgraded['bundle.json']);legacy['version']=1
        downgraded['bundle.json']=cp.encoded(legacy)
        invalid=Path(self.tmp.name)/'invalid-version1-scoped.zip';invalid.write_bytes(transfer.zip_bytes(downgraded))
        with self.assertRaisesRegex(cp.Fault,'bundle version2'):
            transfer.verify(invalid,self.binding['project_id'],self.binding['task_id'],meta['source_revision'])
        incoming=self.store/'incoming'/ident
        transfer.quarantine(self.root,self.archive,meta['archive_sha256'],self.binding['project_id'],
                            self.binding['task_id'],meta['source_revision'],incoming)
        # Simulate a different destination store's lack of a prior local stop.
        (self.store/'automatic-stop.json').unlink()
        _,report=transfer.inspect_incoming(self.root,ident)
        review={'checkpoint_id':ident,'current_fingerprint':report['current_fingerprint'],
            'observed_at':cp.now(),'authorization':{'confirmed':True,'scope':'fixture data adoption','source':'synthetic operator'},
            'destination_reconciliation':'Unchanged fixture source; source account stop must remain bound'}
        cp.atomic(self.store/'adopt-review.json',cp.encoded(review));transfer.adopt(self.root,ident,self.store/'adopt-review.json')
        self.assertEqual(cp.read(self.store/'automatic-stop.json').get('resource_accounts'),[secondary])
        def signal(ident,remaining):
            return {'records':[{'kind':'codex_plan','remaining':remaining,'unit':'percent_remaining',
                'source':'synthetic fixture','observed_at':cp.now(),'guard':20,'account_fingerprint':ident}]}
        signals=signal(primary,90);signals['accounts']={secondary:signal(secondary,10)}
        cp.atomic(self.store/'signals.json',cp.encoded(signals))
        with self.assertRaises(cp.Fault):monitor.validate_resume(self.root,self.store)
        signals['accounts']={}
        cp.atomic(self.store/'signals.json',cp.encoded(signals))
        with self.assertRaises(cp.Fault):monitor.validate_resume(self.root,self.store)
        signals['accounts'][secondary]=signal(secondary,90)
        cp.atomic(self.store/'signals.json',cp.encoded(signals));monitor.validate_resume(self.root,self.store)
        self.assertTrue((self.store/'automatic-stop.json').exists())

    def test_adoption_refuses_competing_owner(self):
        meta=self.package();ident=meta['checkpoint_id']
        transfer.quarantine(self.root,self.archive,meta['archive_sha256'],self.binding['project_id'],self.binding['task_id'],meta['source_revision'],self.store/'incoming'/ident)
        _,report=transfer.inspect_incoming(self.root,ident)
        review={'checkpoint_id':ident,'current_fingerprint':report['current_fingerprint'],'observed_at':cp.now(),
                'authorization':{'confirmed':True,'scope':'fixture','source':'test'},'destination_reconciliation':'fixture'}
        cp.atomic(self.store/'adopt-review.json',cp.encoded(review))
        cp.Ownership(self.root,self.binding,self.store).acquire('other-device')
        with self.assertRaisesRegex(cp.Fault,'still owned'):transfer.adopt(self.root,ident,self.store/'adopt-review.json')
        self.assertEqual(cp.latest(self.store)[0]['id'],ident)


class PublicExportTests(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('public_release',ROOT/'release.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    def test_public_export_reproducible_and_exact(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            a=m.export(ROOT,Path(d)/'a.zip');b=m.export(ROOT,Path(d)/'b.zip')
            self.assertEqual(a['sha256'],b['sha256'])
            self.assertNotIn('AGENTS.md',a['files'])
            self.assertFalse(any(p.startswith(('.checkpoint/','.git/','evidence/')) for p in a['files']))
    def test_public_manifest_paths_cannot_escape_checkout(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            for path in ('../escape','.git/config','C:/escape'):
                with self.assertRaises(ValueError):m.managed_path(Path(d),path)
            (Path(d)/'linked').symlink_to(Path(d).parent,target_is_directory=True)
            with self.assertRaises(ValueError):m.managed_path(Path(d),'linked/escape')

    def test_allowlist_traversal_and_private_marker_refused(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'LICENSE').write_text('fixture notice');(root/'source').write_text('/'+'Users/'+'synthetic/private')
            (root/'public-export.json').write_text(json.dumps({'version':1,'files':{'LICENSE':'LICENSE','source':'source'}}))
            with self.assertRaises(ValueError):m.export(root,root/'out.zip')
            (root/'source').write_text('safe');(root/'public-export.json').write_text(json.dumps({'version':1,'files':{'LICENSE':'LICENSE','../escape':'source'}}))
            with self.assertRaises(ValueError):m.export(root,root/'out.zip')


class RepairTests(unittest.TestCase):
    def test_idempotent_repair_preserves_customization_and_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            cmd=[sys.executable,str(ROOT/'install.py'),'--skills-dir',d,'--repair']
            subprocess.run(cmd,check=True,capture_output=True)
            target=Path(d)/'task-checkpoint';before=(target/'.install-receipt.json').read_bytes()
            subprocess.run(cmd,check=True,capture_output=True)
            self.assertEqual(before,(target/'.install-receipt.json').read_bytes())
            (target/'SKILL.md').write_text('customized')
            self.assertEqual(subprocess.run(cmd,capture_output=True).returncode,2)
            self.assertEqual((target/'SKILL.md').read_text(),'customized')


class ProjectHookStatusTests(unittest.TestCase):
    def test_status_requires_project_binding_even_with_account_delivery(self):
        spec=importlib.util.spec_from_file_location('delivery_setup',ROOT/'setup.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);project=base/'project';store=project/'.checkpoint';store.mkdir(parents=True)
            state=base/'account';state.mkdir()
            binding={'schema_version':1,'ownership':'local','project_id':'example/project','task_id':'existing-task','store':None}
            cp.atomic(store/'config.json',cp.encoded(binding))
            cp.atomic(state/'config.json',cp.encoded({'codex_home':str(base/'profile')}))
            event={'root':str(base/'elsewhere'),'task_id':'other','project_id':'other','event':'SessionEnd','observed_at':cp.now()}
            cp.atomic(state/'hook-delivery.json',cp.encoded(event))
            def status():
                with mock.patch.object(module.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='example')):
                    return module.status(project,base/'skills',state,base/'profile')
            self.assertEqual(status()['project_hook_delivery_status'],'missing')
            self.assertNotIn('project_hook_delivery',status())
            cp.atomic(store/'native-hook-delivery.json',cp.encoded(event))
            self.assertEqual(status()['project_hook_delivery_status'],'binding-mismatch')
            event.update(root=str(project),task_id='existing-task',project_id='example/project')
            cp.atomic(store/'native-hook-delivery.json',cp.encoded(event))
            self.assertEqual(status()['project_hook_delivery_status'],'observed')
            self.assertEqual(status()['project_hook_delivery'],event)
            event['task_id']='other';cp.atomic(store/'native-hook-delivery.json',cp.encoded(event))
            self.assertEqual(status()['project_hook_delivery_status'],'binding-mismatch')
            cp.atomic(store/'native-hook-delivery.json',b'broken json')
            self.assertEqual(status()['project_hook_delivery_status'],'invalid-receipt')


class PortableZipMetadataTests(unittest.TestCase):
    def platform_zero(self):
        original=zipfile.ZipInfo
        class PlatformZeroInfo(original):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                self.create_system=0
        return PlatformZeroInfo

    def test_private_zip_bytes_ignore_host_platform_default(self):
        import io
        files={'HANDOFF.md':b'Synthetic portable handoff\n','state.json':b'{"fixture":true}\n'}
        native=transfer.zip_bytes(files)
        with mock.patch.object(transfer.zipfile,'ZipInfo',self.platform_zero()):
            other=transfer.zip_bytes(files)
        self.assertEqual(native,other)
        with zipfile.ZipFile(io.BytesIO(native)) as archive:
            self.assertTrue(all(i.create_system==3 for i in archive.infolist()))
            self.assertEqual({n:archive.read(n) for n in archive.namelist()},files)

    def test_public_export_ignores_host_platform_default(self):
        release=PublicExportTests().module()
        with tempfile.TemporaryDirectory() as d:
            native=release.export(ROOT,Path(d)/'native.zip')
            with mock.patch.object(release.zipfile,'ZipInfo',self.platform_zero()):
                other=release.export(ROOT,Path(d)/'other.zip')
            self.assertEqual(native['sha256'],other['sha256'])
            self.assertEqual(native['files'],other['files'])
