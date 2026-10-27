import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS=Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'
sys.path.insert(0,str(SCRIPTS))
import checkpoint as cp
import profiles
import router
import router_policy
import monitor
import local_text
import local_text_worker
import test_router_policy as policy_tests


class ProfilesLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.home=self.base/'profile';self.home.mkdir()
        self.ident=profiles.fingerprint('account-A')
        cp.atomic(self.home/'auth.json',cp.encoded({'auth_mode':'chatgpt','tokens':{'account_id':'account-A','access_token':'PRIVATE-DO-NOT-COPY'}}))
        self.observed={'source':'fixture-native-probe','observed_at':cp.now(),
            'account':{'account':{'type':'chatgpt'}},'models':{'data':[]},
            'rate_limits':{'accountId':'account-A','rateLimits':{'primary':{'usedPercent':5}}}}

    def test_profile_identity_uses_auth_and_actual_account_id(self):
        self.assertEqual(profiles.inspect_profile(self.home,self.observed,self.ident),self.ident)
        for mutated in [dict(self.observed,rate_limits={'accountId':'account-B'}),dict(self.observed,account={'account':{'type':'apiKey'}})]:
            with self.assertRaises(cp.Fault):profiles.inspect_profile(self.home,mutated,self.ident)
        with self.assertRaises(cp.Fault):profiles.inspect_profile(self.home,self.observed,profiles.fingerprint('account-B'))

    def test_explicit_child_profile_and_no_api_key_inheritance(self):
        worker={'codex_home':str(self.home),'account_fingerprint':self.ident,'executable':'codex'}
        with mock.patch('codex_probe.probe',return_value=self.observed) as probe:
            observed,signals=profiles.worker_observation(worker,{})
        probe.assert_called_once_with('codex',codex_home=str(self.home.resolve()))
        self.assertEqual(signals['records'][0]['account_fingerprint'],self.ident)
        env=profiles.worker_environment(worker,{'OPENAI_API_KEY':'SECRET','CODEX_API_KEY':'SECRET','OPENAI_BASE_URL':'https://other','PATH':'safe'})
        self.assertEqual(env,{'PATH':'safe','CODEX_HOME':str(self.home.resolve())})
        self.assertNotIn('PRIVATE-DO-NOT-COPY',json.dumps(signals))

    def test_aliases_not_double_counted_and_failed_account_unknown(self):
        item={'id':'one','codex_home':str(self.home),'account_fingerprint':self.ident}
        config={'codex_home':str(self.home),'codex_profiles':[item,dict(item,id='alias')]}
        with self.assertRaises(cp.Fault):profiles.collect(config,self.observed)
        config['codex_profiles']=[dict(item,account_fingerprint=profiles.fingerprint('other'))]
        result=profiles.collect(config,self.observed)
        self.assertEqual(result['profiles'][0]['status'],'unknown')
        self.assertEqual(list(result['accounts'].values()),[{'records':[]}])

    def test_healthy_primary_cannot_recover_secondary_stop(self):
        other=profiles.fingerprint('account-B')
        high=profiles.signals_for(self.observed,self.ident)
        scoped=monitor.account_scope(high,{'resource_accounts':[other]})
        self.assertEqual(__import__('telemetry').assess(scoped)['statuses']['codex_plan'],'unknown')
        low=profiles.signals_for(dict(self.observed,rate_limits={'rateLimits':{'primary':{'usedPercent':90}}}),other)
        high['accounts']={other:low}
        self.assertTrue(__import__('telemetry').assess(monitor.account_scope(high,{'resource_accounts':[other]}))['low'])
        high['accounts'][other]=profiles.signals_for(self.observed,other)
        self.assertFalse(__import__('telemetry').assess(monitor.account_scope(high,{'resource_accounts':[other]}))['low'])


    def test_selection_uses_each_workers_own_account_capacity(self):
        fixture=policy_tests.RouterPolicyTests('test_selects_observed_useful_completion_cost');fixture.setUp()
        fixture.task['routing']['allowed_providers']=['openai'];fixture.config['allowed_providers']=['openai']
        a,b=profiles.fingerprint('A'),profiles.fingerprint('B')
        for w,ident in zip(fixture.config['workers'],[a,b]):
            w.update(provider='openai',codex_home=str(self.home),account_fingerprint=ident)
        fixture.signals['accounts']={a:{'records':[fixture.record('codex_plan',80,account_fingerprint=a)]},b:{'records':[fixture.record('codex_plan',10,account_fingerprint=b)]}}
        self.assertEqual(fixture.decide()['worker_id'],'small')
        self.assertEqual(fixture.decide(override='large')['action'],'manual')
        fixture.config['unknown_telemetry']='explicit_budget';fixture.signals.pop('accounts')
        self.assertEqual(fixture.decide()['action'],'manual')

    def runtime_fixture(self):
        import test_router_runtime as rt
        fixture=rt.RouterRuntimeTests('test_real_trigger_launch_acceptance_and_duplicate_completion');fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.config['workers']=fixture.config['workers'][:1]
        fixture.config['workers'][0].update(interface='codex_exec',provider='openai',billing='plan',codex_home=str(self.home),account_fingerprint=self.ident,executable=sys.executable)
        fixture.task['routing']['allowed_providers']=['openai'];fixture.config['allowed_providers']=['openai']
        fixture.signals={'records':[dict(kind='codex_plan',remaining=80,unit='percent_remaining',observed_at=cp.now(),source='fixture')],
            'accounts':{self.ident:profiles.signals_for(self.observed,self.ident)}}
        fixture.prepare();return fixture

    def test_fresh_low_target_account_saves_before_any_launch(self):
        fixture=self.runtime_fixture();low=profiles.signals_for(dict(self.observed,rate_limits={'rateLimits':{'primary':{'usedPercent':90}}}),self.ident)
        with mock.patch('profiles.worker_observation',return_value=(self.observed,low)),mock.patch('router._run') as launch:
            result=fixture.dispatch()
        launch.assert_not_called();self.assertEqual(result['action'],'pause')
        marker=cp.read(fixture.store/'automatic-stop.json') if hasattr(fixture,'store') else cp.read(fixture.root/'.checkpoint/automatic-stop.json')
        self.assertEqual(marker['resource_accounts'],[self.ident]);self.assertEqual(marker['checkpoint_status'],'verified')

    def test_account_identity_change_never_creates_worker_intent(self):
        fixture=self.runtime_fixture()
        with mock.patch('profiles.worker_observation',side_effect=cp.Fault('identity changed')),mock.patch('router._run') as launch:
            with self.assertRaises(cp.Fault):fixture.dispatch()
        launch.assert_not_called();self.assertIsNone(router.state(fixture.root)['active'])

    def test_plan_launch_receives_exact_profile_without_api_credentials(self):
        fixture=self.runtime_fixture();observed=copy.deepcopy(self.observed)
        observed['models']['data']=[{'model':fixture.config['workers'][0]['model'],'supportedReasoningEfforts':[{'reasoningEffort':'medium'}]}]
        captured=[]
        def run(cmd,root,environment,prompt,log,timeout,on_start):
            if prompt is not None:
                captured.append((cmd,dict(environment)))
                Path(environment['CHECKPOINT_RESULT']).write_text('42');log.write_text('')
            return dict(status='exited',exit_code=0,pid=12345)
        with mock.patch.dict('os.environ',{'OPENAI_API_KEY':'not-a-real-key'}),mock.patch('profiles.worker_observation',return_value=(observed,profiles.signals_for(observed,self.ident))),mock.patch('router._run',side_effect=run):
            result=fixture.dispatch()
        self.assertEqual(result.get('status'),'accepted',result);self.assertEqual(captured[0][1]['CODEX_HOME'],str(self.home.resolve()))
        self.assertNotIn('OPENAI_API_KEY',captured[0][1]);self.assertIn('forced_login_method="chatgpt"',captured[0][0])


    def test_output_schema_refuses_external_references_and_model_scope_drift(self):
        with self.assertRaises(cp.Fault):router_policy.validate_output_schema({'type':'object','$ref':'https://example.invalid/schema'})
        fixture=policy_tests.RouterPolicyTests('test_selects_observed_useful_completion_cost');fixture.setUp()
        fixture.config['workers']=fixture.config['workers'][:1];w=fixture.config['workers'][0]
        schema={'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
        fixture.task['routing'].update(required_tools=[],privacy='public',allowed_providers=['ollama'],output_schema=schema)
        fixture.config.update(allowed_providers=['ollama'],unknown_telemetry='explicit_budget')
        w.update(interface='local_text',provider='ollama',billing='local',tools=[],privacy=['public'],endpoint='http://127.0.0.1:11435',model_digest='a'*64)
        w['qualification'].update(model_digest='a'*64,output_schema_sha256=cp.sha(cp.encoded(schema)))
        self.assertEqual(fixture.decide()['action'],'launch')
        w['model_digest']='b'*64;self.assertEqual(fixture.decide()['action'],'manual')
        w['model_digest']='a'*64;fixture.task['routing']['output_schema']=dict(schema,required=[])
        self.assertEqual(fixture.decide()['action'],'manual')

    def test_persistent_secondary_stop_not_recovered_by_primary_collector(self):
        import test_monitor as mt
        fixture=mt.MonitorTests('test_recovery_never_auto_resumes_or_clears_marker');fixture.setUp();self.addCleanup(fixture.doCleanups)
        other=profiles.fingerprint('account-B')
        low=profiles.signals_for(dict(self.observed,rate_limits={'rateLimits':{'primary':{'usedPercent':90}}}),other)
        monitor.stop_for_signals(fixture.root,low)
        high=profiles.signals_for(self.observed,self.ident);high['accounts']={other:low}
        cp.atomic(fixture.state/'signals.json',cp.encoded(high));monitor.evaluate_registered(fixture.state,high)
        with self.assertRaises(cp.Fault):monitor.validate_resume(fixture.root,fixture.store)
        high['accounts'][other]=profiles.signals_for(self.observed,other)
        cp.atomic(fixture.state/'signals.json',cp.encoded(high));monitor.evaluate_registered(fixture.state,high)
        monitor.validate_resume(fixture.root,fixture.store)
        self.assertTrue((fixture.store/'automatic-stop.json').exists())

    def test_generated_resume_uses_explicit_profile_signals(self):
        path=self.base/'router-config.json'
        cp.atomic(path,cp.encoded({'signals_path':str(self.base/'account signals.json')}))
        text=router.resume_command(self.base,self.base/'input.json',path,'secondary')
        args=__import__('shlex').split(text)
        self.assertEqual(args[args.index('--collector')+1],'signals')
        self.assertEqual(args[args.index('--signals')+1],str((self.base/'account signals.json').resolve()))
        self.assertEqual(args[args.index('--worker')+1],'secondary')

    def test_local_url_rejects_remote_credentials_proxy_and_redirect(self):
        self.assertEqual(local_text_worker.endpoint('http://127.0.0.1:11435'),'http://127.0.0.1:11435')
        for url in ['https://ollama.com','http://localhost:11435','http' + '://' + '127.0.0.1:11435' + '@evil.test','http' + '://' + 'user:secret' + '@127.0.0.1:11435','http://127.0.0.1:11435/api','http://127.0.0.1:11435?remote=x']:
            with self.assertRaises(ValueError):local_text_worker.endpoint(url)
        with self.assertRaises(ValueError):local_text_worker.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_local_model_requires_exact_digest_and_never_calls_cloud(self):
        class Response:
            def __init__(self,data):self.data=json.dumps(data).encode()
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return self.data
        opener=mock.Mock();opener.open.return_value=Response({'models':[]})
        data=dict(endpoint='http://127.0.0.1:11435',model='qwen3.5:4b',model_digest='a'*64,prompt='public fixture')
        with mock.patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaises(ValueError):local_text_worker.work(data)
        self.assertEqual(opener.open.call_count,1)
        self.assertTrue(opener.open.call_args.args[0].full_url.startswith('http://127.0.0.1:11435/'))

    def test_local_success_records_real_token_counts_and_rejects_tools(self):
        class Response:
            def __init__(self,data):self.data=json.dumps(data).encode()
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return self.data
        data=dict(endpoint='http://127.0.0.1:11435',model='model',model_digest='a'*64,prompt='public fixture')
        tags={'models':[{'name':'model','digest':'a'*64}]}
        answer={'done':True,'done_reason':'stop','message':{'content':'{"ok":true}'},'prompt_eval_count':10,'eval_count':5}
        opener=mock.Mock();opener.open.side_effect=[Response(tags),Response(answer)]
        with mock.patch('urllib.request.build_opener',return_value=opener):value=local_text_worker.work(data)
        self.assertEqual((value['prompt_tokens'],value['completion_tokens'],value['paid_api_cost_usd']),(10,5,0))
        answer['message']['tool_calls']=[{'name':'do-not-run'}];opener.open.side_effect=[Response(tags),Response(answer)]
        with mock.patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaises(ValueError):local_text_worker.work(data)

    def test_local_prompt_excludes_checkpoint_prose_and_acceptance_oracle(self):
        task={'objective':'Extract the public notes','authorization':{'source':'PRIVATE'},'routing':{'required_tools':[],'acceptance':[{'argv':['oracle-secret']} ]}}
        w=dict(endpoint='http://127.0.0.1:11435',model='model',model_digest='a'*64)
        prompt=local_text.request(w,task)
        self.assertNotIn('PRIVATE',prompt);self.assertNotIn('oracle-secret',prompt)
        task['routing']['required_tools']=['shell']
        with self.assertRaises(cp.Fault):local_text.request(w,task)

    def test_local_sandbox_is_credential_free_and_loopback_only(self):
        w=dict(provider='ollama',billing='local',tools=[],endpoint='http://127.0.0.1:11435')
        with mock.patch('local_text.sys.platform','darwin'):
            cmd,env=local_text.command(w,self.base)
        self.assertEqual(cmd[0],'/usr/bin/sandbox-exec');self.assertIn('(deny default)',cmd[2])
        self.assertIn('localhost:11435',cmd[2]);self.assertNotIn('network*',cmd[2])
        self.assertEqual(set(env),{'PATH','HOME','TMPDIR','PYTHONNOUSERSITE','PYTHONDONTWRITEBYTECODE','LANG'})
        with mock.patch('local_text.sys.platform','win32'):
            with self.assertRaises(cp.Fault):local_text.command(w,self.base)

    def test_coordinator_materializes_data_only(self):
        log=self.base/'worker.log';output=self.base/'result.json'
        log.write_text(json.dumps({'answer':'{"ok":true}','model':'model','paid_api_cost_usd':0}))
        usage=local_text.result(log,output)
        self.assertEqual(json.loads(output.read_text()),{'ok':True});self.assertEqual(usage['paid_api_cost_usd'],0)


if __name__=='__main__':unittest.main()
