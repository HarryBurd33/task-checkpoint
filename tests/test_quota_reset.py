"""All dates in these tests are simulated; no real account reset is claimed."""
import copy
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import quota_reset as q


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.before = dt.datetime(2030,1,1,0,0,tzinfo=dt.timezone.utc)
        self.after = self.before+dt.timedelta(seconds=70)
        self.old = {'records':[dict(kind='codex_plan',unit='percent_remaining',source='simulated-test',remaining=10,observed_at=self.before.isoformat(),resets_at=(self.before+dt.timedelta(seconds=60)).isoformat(),window='codex:primary',account_fingerprint='fixture-account')]}
        self.baseline = q.capture(self.old, now=self.before)
        self.new = copy.deepcopy(self.old)
        self.new['records'][0].update(remaining=100, observed_at=self.after.isoformat(), resets_at=(self.after+dt.timedelta(days=7)).isoformat())

    def test_actual_evidence_requirements_and_not_due(self):
        before = copy.deepcopy(self.baseline); signals = copy.deepcopy(self.new)
        result = q.verify(self.baseline, self.new, self.after)
        self.assertTrue(result['verified'])
        self.assertEqual(result['action'], 'report-only')
        self.assertEqual(self.baseline,before);self.assertEqual(self.new,signals)
        self.assertEqual(q.verify(self.baseline,self.old,self.before)['status'],'not-due')

    def test_stale_future_pre_reset_invalid_and_foreign_account_cannot_verify(self):
        mutations = [dict(observed_at=(self.after-dt.timedelta(seconds=121)).isoformat()),dict(observed_at=(self.after+dt.timedelta(seconds=1)).isoformat()),dict(observed_at=self.before.isoformat()),dict(account_fingerprint='other'),dict(window='other'),dict(resets_at=self.old['records'][0]['resets_at']),dict(remaining=None),dict(remaining=101),dict(blocked=True),dict(supported=False),dict(resets_at=None)]
        for mutation in mutations:
            signals=copy.deepcopy(self.new);signals['records'][0].update(mutation)
            self.assertFalse(q.verify(self.baseline,signals,self.after)['verified'],mutation)

    def test_every_window_and_duplicates_are_checked(self):
        old=copy.deepcopy(self.old);old['records'].append(dict(old['records'][0],window='codex:secondary',resets_at=(self.before+dt.timedelta(seconds=100)).isoformat()))
        baseline=q.capture(old,self.before)
        new=copy.deepcopy(self.new);new['records'].append(dict(old['records'][1],observed_at=self.after.isoformat()))
        self.assertFalse(q.verify(baseline,new,self.after)['verified'])
        self.assertEqual(q.verify(baseline,new,self.after)['status'],'not-due')
        for signals in ({'records':[]},{'records':self.new['records']*2}):
            self.assertFalse(q.verify(self.baseline,signals,self.after)['verified'])
        self.assertFalse(q.verify(baseline,self.new,self.after)['verified'])

    def test_invalid_baseline_and_unchanged_reset_rejected(self):
        for mutation in (dict(schema_version=2),dict(captured_at=(self.after+dt.timedelta(seconds=1)).isoformat()),dict(records=[])):
            baseline=copy.deepcopy(self.baseline);baseline.update(mutation)
            self.assertFalse(q.verify(baseline,self.new,self.after)['verified'])
        with self.assertRaises(ValueError):q.capture({'records':[]},self.before)

    def test_cli_is_read_only_even_when_verification_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);old=folder/'baseline.json';new=folder/'signals.json'
            old.write_text(json.dumps(self.baseline));new.write_text(json.dumps(self.old))
            before={p.name:p.read_bytes() for p in folder.iterdir()}
            result=subprocess.run([sys.executable,str(Path(q.__file__)),'verify','--baseline',str(old),'--signals',str(new)],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertFalse(json.loads(result.stdout)['verified'])
            self.assertEqual({p.name:p.read_bytes() for p in folder.iterdir()},before)
