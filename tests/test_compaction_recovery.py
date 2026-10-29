"""Compaction is recovery housekeeping; it must not bypass ordinary-work guards."""
import json
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skills/task-checkpoint/scripts'))
import checkpoint as cp
import enrollment
import maintenance
import test_stopped_shutdown as stopped
import test_enrollment_v07 as enrolled

class CompactionRecoveryTests(unittest.TestCase):
    setUp = stopped.StoppedShutdownTests.setUp
    signals = stopped.StoppedShutdownTests.signals
    stop = stopped.StoppedShutdownTests.stop
    event = stopped.StoppedShutdownTests.event
    invoke = stopped.StoppedShutdownTests.invoke
    protected = stopped.StoppedShutdownTests.protected
    def test_stopped_status_exposes_actual_resume_prerequisites_without_mutation(self):
        before=self.protected()
        saved,_=cp.latest(self.store)
        result=maintenance.status(self.root)
        self.assertEqual(result['required_capabilities'],saved['task']['capabilities'])
        self.assertEqual(result['required_tools'],saved['task']['tools'])
        self.assertFalse(result['implementation_allowed'])
        self.assertEqual(before,self.protected())
    def test_compaction_allows_recovery_but_never_resumes_or_changes_pinned_state(self):
        for status in ('verified','failed','pending'):
            marker=cp.read(self.store/'automatic-stop.json');marker['checkpoint_status']=status
            cp.atomic(self.store/'automatic-stop.json',cp.encoded(marker))
            before=self.protected()
            output=self.invoke('PreCompact')
            self.assertNotEqual(output.get('continue'),False)
            self.assertIn('automatic usage stop persists',json.dumps(output))
            self.assertEqual(before,self.protected())
            self.assertEqual(self.invoke('PreToolUse')['hookSpecificOutput']['permissionDecision'],'deny')

class UninitializedRecoveryTests(unittest.TestCase):
    setUp = enrolled.EnrollmentTests.setUp
    git = enrolled.EnrollmentTests.git
    invoke = enrolled.EnrollmentTests.invoke
    def test_missing_first_checkpoint_has_readonly_actionable_status(self):
        enrollment.enroll(self.state,self.root,'owner-chat')
        before=(self.root/'.checkpoint/config.json').read_bytes()
        result=maintenance.status(self.root,self.state)
        self.assertIsNone(result['checkpoint']['checkpoint_id'])
        self.assertIn('semantic-input-missing',result['checkpoint']['issues'])
        self.assertFalse(result['implementation_allowed'])
        self.assertIsNone(result['owner']['owner'])
        self.assertEqual(before,(self.root/'.checkpoint/config.json').read_bytes())
        self.assertFalse((self.root/'.checkpoint/latest.json').exists())
    def test_existing_binding_always_warns_about_missing_semantic_input(self):
        enrollment.enroll(self.state,self.root,'owner-chat')
        result=self.invoke(name='SessionStart')
        self.assertIn('input.json is missing',json.dumps(result))
        self.assertFalse((self.root/'.checkpoint/input.json').exists())
    def test_corrupt_existing_checkpoint_is_not_reported_as_absent(self):
        enrollment.enroll(self.state,self.root,'owner-chat')
        cp.atomic(self.root/'.checkpoint/latest.json',b'{broken')
        with self.assertRaises((cp.Fault,ValueError,KeyError)):
            maintenance.status(self.root,self.state)

if __name__=='__main__':unittest.main()
