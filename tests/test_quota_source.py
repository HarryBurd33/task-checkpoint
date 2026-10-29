"""Regression: retired project caches must not hide fresh collector allowance."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import checkpoint as cp
import usage
import test_runtime as fixtures


class QuotaSourceTests(unittest.TestCase):
    setUp=fixtures.RuntimeTests.setUp
    g=fixtures.RuntimeTests.g
    cli=fixtures.RuntimeTests.cli
    write=fixtures.RuntimeTests.write

    def prepare(self,local,shared):
        self.home=Path(self.temp.name)/'home'
        self.shared=self.home/'.codex/checkpoint-handoff';self.shared.mkdir(parents=True)
        self.local=self.root/'.checkpoint/signals.json'
        cp.atomic(self.local,cp.encoded({'records':local}))
        cp.atomic(self.shared/'signals.json',cp.encoded({'records':shared}))
        self.home_patch=mock.patch.object(usage.Path,'home',return_value=self.home)
        self.home_patch.start();self.addCleanup(self.home_patch.stop)

    def record(self,n,stamp=None,identity='same-account',**extra):
        return dict(kind='codex_plan',unit='percent_remaining',source='fixture-collector',
                    account_fingerprint=identity,window='codex:primary',remaining=n,observed_at=stamp or cp.now(),**extra)

    def test_stale_project_cache_yields_to_fresh_same_account_collector_without_writes(self):
        self.prepare([self.record(11,'2000-01-01T00:00:00Z')],[self.record(50)])
        old=self.local.read_bytes()
        result=usage.assess(usage.signals_for(self.root),self.root)
        self.assertEqual(result['quota_status'],'available')
        self.assertEqual(result['observations'][0]['remaining'],50)
        self.assertEqual(self.local.read_bytes(),old)

    def test_fresh_low_collector_reaches_user_threshold_despite_stale_healthy_cache(self):
        self.prepare([self.record(90,'2000-01-01T00:00:00Z')],[self.record(10)])
        self.assertEqual(usage.assess(usage.signals_for(self.root),self.root)['action'],'handoff')

    def test_fresh_local_reading_is_not_replaced(self):
        self.prepare([self.record(10)],[self.record(90)])
        self.assertEqual(usage.assess(usage.signals_for(self.root),self.root)['action'],'handoff')

    def test_other_account_is_not_used_to_recover_a_scoped_stale_reading(self):
        self.prepare([self.record(10,'2000-01-01T00:00:00Z','account-a')],[self.record(90,identity='account-b')])
        self.assertEqual(usage.assess(usage.signals_for(self.root),self.root)['quota_status'],'unknown')

    def test_explicit_collector_is_never_replaced_by_implicit_healthy_source(self):
        self.prepare([self.record(80)],[self.record(90)])
        explicit=Path(self.temp.name)/'explicit';explicit.mkdir()
        cp.atomic(explicit/'signals.json',cp.encoded({'records':[self.record(5,'2000-01-01T00:00:00Z')]}))
        self.assertEqual(usage.assess(usage.signals_for(self.root,explicit),self.root)['quota_status'],'unknown')

    def test_local_non_quota_limits_and_all_collector_windows_are_preserved(self):
        disk=dict(kind='local_resource',unit='bytes_available',source='fixture',remaining=0,observed_at=cp.now())
        self.prepare([disk],[self.record(90),dict(self.record(8),window='codex:weekly')])
        result=usage.assess(usage.signals_for(self.root),self.root)
        self.assertEqual(result['action'],'handoff')
        self.assertEqual({r['kind'] for r in result['reasons']},{'codex_plan','local_resource'})
        self.assertEqual(len(result['observations']),3)

    def test_empty_project_cache_does_not_shadow_fresh_collector(self):
        self.prepare([],[self.record(50)])
        self.assertEqual(usage.assess(usage.signals_for(self.root),self.root)['quota_status'],'available')

    def test_both_sources_stale_remain_unknown(self):
        self.prepare([self.record(9,'2000-01-01T00:00:00Z')],[self.record(90,'2000-01-01T00:00:00Z')])
        self.assertEqual(usage.assess(usage.signals_for(self.root),self.root)['quota_status'],'unknown')
