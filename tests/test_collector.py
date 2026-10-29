import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import account
import checkpoint as cp
import codex_probe


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)/'account'; self.state.mkdir()
        self.config = {'enabled':False,'projects':[{'root':'unrelated-project','scheduled_dispatch':True}],
                       'private_receive':True,'codex_home':str(Path(self.tmp.name)/'codex')}
        cp.atomic(self.state/'config.json', cp.encoded(self.config))
        self.observed = {'rate_limits':{'accountId':'synthetic-account','ordinaryUsageAllowed':True,
                         'rateLimitsByLimitId':{'codex':{'primary':{'usedPercent':49,'resetsAt':4000000000},
                                                      'secondary':{'usedPercent':70,'resetsAt':4000000000}}}},
                         'account':{'account':{'type':'chatgpt'}},'observed_at':cp.now(),'source':'fixture-probe'}

    def test_collection_is_fresh_and_observation_only_even_with_legacy_dispatch_flags(self):
        before = (self.state/'config.json').read_bytes()
        with mock.patch.object(account,'probe',return_value=self.observed) as probe:
            result = account.tick(self.state)
        self.assertEqual(result['last_success'],self.observed['observed_at'])
        self.assertEqual(result['mode'],'observation-only')
        signals = cp.read(self.state/'signals.json')['records']
        self.assertEqual([r['remaining'] for r in signals],[51,30])
        self.assertTrue(all(r['source']=='fixture-probe' and r['account_fingerprint'] for r in signals))
        self.assertEqual((self.state/'config.json').read_bytes(),before)
        self.assertEqual({p.name for p in self.state.iterdir()},{'signals.json','status.json','config.json'})
        probe.assert_called_once_with(executable='codex',codex_home=self.config['codex_home'],timeout=25)

    def test_removed_version_path_uses_stable_cli_with_same_profile(self):
        self.config['codex_executable']=str(Path(self.tmp.name)/'retired-version/codex')
        cp.atomic(self.state/'config.json',cp.encoded(self.config))
        before=(self.state/'config.json').read_bytes()
        with mock.patch.object(account.shutil,'which',return_value='stable-codex'), mock.patch.object(account,'probe',return_value=self.observed) as probe:
            account.tick(self.state)
        probe.assert_called_once_with(executable='stable-codex',codex_home=self.config['codex_home'],timeout=25)
        self.assertEqual((self.state/'config.json').read_bytes(),before)

    def test_failed_collection_never_refreshes_old_values(self):
        cp.atomic(self.state/'signals.json',cp.encoded({'records':[{'observed_at':'2000-01-01T00:00:00Z'}]}))
        before = (self.state/'signals.json').read_bytes()
        with mock.patch.object(account,'probe',side_effect=cp.Fault('unavailable')):
            with self.assertRaises(cp.Fault):account.tick(self.state)
        self.assertEqual((self.state/'signals.json').read_bytes(),before)
        self.assertIsNone(cp.read(self.state/'status.json')['last_success'])
        self.assertFalse((self.state/'writer.lock').exists())

    def test_api_auth_is_not_used_as_paid_fallback(self):
        self.observed['account']['account']['type']='apiKey'
        with mock.patch.object(account,'probe',return_value=self.observed):
            with self.assertRaises(cp.Fault):account.tick(self.state)
        self.assertFalse((self.state/'signals.json').exists())

    def test_exact_hook_removal_preserves_unrelated_hooks_and_config(self):
        home = Path(self.config['codex_home']);home.mkdir()
        own = {'hooks':[{'type':'command','command':'managed-checkpoint'}]}
        other = {'hooks':[{'type':'command','command':'unrelated-permission-hook'}]}
        cp.atomic(home/'hooks.json',cp.encoded({'hooks':{'PreToolUse':[other,own]}}))
        cp.atomic(self.state/'hooks-receipt.json',cp.encoded({'definitions':{'PreToolUse':own}}))
        before = (self.state/'config.json').read_bytes()
        result = account.uninstall(self.state,home)
        self.assertEqual(result['hooks_removed'],1)
        self.assertEqual(cp.read(home/'hooks.json'),{'hooks':{'PreToolUse':[other]}})
        self.assertEqual((self.state/'config.json').read_bytes(),before)
        self.assertEqual(account.uninstall(self.state,home)['hooks_removed'],0)

    def test_changed_hook_is_preserved(self):
        home = Path(self.config['codex_home']);home.mkdir()
        cp.atomic(home/'hooks.json',cp.encoded({'hooks':{'PreToolUse':[{'hooks':[]}]}}))
        cp.atomic(self.state/'hooks-receipt.json',cp.encoded({'definitions':{'PreToolUse':{'hooks':[{'command':'owned'}]}}}))
        before = (home/'hooks.json').read_bytes()
        with self.assertRaises(cp.Fault):account.uninstall(self.state,home)
        self.assertEqual((home/'hooks.json').read_bytes(),before)

    def test_probe_uses_read_only_methods_and_never_starts_model_turn(self):
        executable = Path(self.tmp.name)/'synthetic-codex'
        executable.write_text('#!'+sys.executable+'''\nimport json, sys
for line in sys.stdin:
    request = json.loads(line)
    method = request['method']
    if method == 'initialized':continue
    if method not in ('initialize','account/rateLimits/read','account/read'):raise SystemExit(97)
    result = {'account':{'type':'chatgpt'}} if method == 'account/read' else {}
    print(json.dumps({'id':request['id'],'result':result}),flush=True)
''')
        executable.chmod(0o755)
        result = codex_probe.probe(str(executable),timeout=5)
        self.assertEqual(result['account'],{'account':{'type':'chatgpt'}})
        self.assertNotIn('models',result)
