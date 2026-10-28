"""Isolated tests; hook subprocesses are callback tests, not native-host proof."""
import datetime as dt
import json
from pathlib import Path
import shlex
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/task-checkpoint/scripts'))
import checkpoint as cp
import hook
import maintenance
import reserve
import test_reserve_policy as fixtures


class MaintenanceTests(unittest.TestCase):
    setUp = fixtures.ReserveTests.setUp
    signals = fixtures.ReserveTests.signals

    def command(self, script, *args):
        return shlex.join(['python3', str(Path(hook.__file__).parent / script), '--root', str(self.root.resolve()), *args])

    def classify(self, command, **kwargs):
        return maintenance.classify({'tool_name': 'exec_command', 'tool_input': {'cmd': command}}, self.root.resolve(), **kwargs)

    def invoke(self, command='echo ordinary'):
        result = subprocess.run([sys.executable, str(Path(hook.__file__))],
            input=json.dumps({'cwd': str(self.root), 'hook_event_name': 'PreToolUse',
                             'tool_name': 'exec_command', 'tool_input': {'cmd': command}}),
            text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def write_signals(self, value):
        cp.atomic(self.store / 'signals.json', cp.encoded(value))

    def run_cli(self, script, *args):
        command = self.command(script, *args)
        self.assertTrue(self.classify(command)[0], self.classify(command))
        self.assertEqual(self.invoke(command), {})
        result = subprocess.run(shlex.split(command), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def grant_resume(self, mode):
        self.run_cli('reserve.py', 'grant', '--mode', mode, '--owner', 'fixture',
                     '--signals', str((self.store/'signals.json').resolve()),
                     '--reason', 'Current user explicitly selected '+mode,
                     '--source', 'Isolated test authorization')
        self.assertEqual(self.invoke()['hookSpecificOutput']['permissionDecision'], 'deny')
        review = self.run_cli('reserve.py', 'prepare-review', '--owner', 'fixture',
                             '--scope', 'Bounded fixture work', '--source', 'Current test user',
                             '--resources-evidence', 'Fresh isolated readings and no uncertain jobs')
        self.run_cli('checkpoint.py', 'resume', '--review', review['review'], '--owner', 'fixture')

    def test_help_and_exact_installed_instruction_reads(self):
        for name in ('checkpoint.py', 'reserve.py', 'maintenance.py'):
            bare = shlex.join(['python3', str(Path(hook.__file__).parent/name), '--help'])
            for cmd in (bare, self.command(name, '--help')):
                self.assertTrue(self.classify(cmd)[0], cmd)
        for key in ('task-checkpoint', 'model-switcher', 'reserve', 'operator'):
            if key == 'model-switcher' and not maintenance.DOCS[key].is_file():
                continue  # Optional companion need not be installed in public CI.
            self.assertTrue(self.classify(shlex.join(['cat', str(maintenance.DOCS[key])]))[0])
        self.assertTrue(self.classify(self.command('reserve.py', 'prepare-review', '--help'))[0])
        self.assertFalse(self.classify(self.command('checkpoint.py', 'review', '--help'))[0])

    def test_shell_smuggling_duplicate_options_foreign_scope_and_bad_flags_denied(self):
        safe = self.command('reserve.py', 'status')
        bad = [safe+'; echo work', safe+' && echo work', safe+' | cat', safe+' > /tmp/output',
               safe+'\necho work', safe+' $(echo work)', safe+' `echo work`', safe+' # comment',
               safe+' --root '+shlex.quote(str(self.root.resolve())), safe+' --unknown',
               safe.replace(' status', ' --help status'),
               self.command('reserve.py','stat'),
               self.command('checkpoint.py','run','--input',str(self.source),'--','echo','work'),
               'python3 -c "print(1)"', 'cat /etc/hosts',
               self.command('checkpoint.py','policy','--input','/etc/hosts'),
               self.command('checkpoint.py','release'),
               self.command('reserve.py','grant','--mode','ten','--signals',str(self.store/'signals.json'),
                            '--reason','user','--source','user'),
               safe.replace(str(self.root.resolve()), '/another-project')]
        for command in bad:
            self.assertFalse(self.classify(command)[0], command)
        link=self.root/'linked.py';link.symlink_to(Path(hook.__file__).with_name('reserve.py'))
        self.assertFalse(self.classify(shlex.join(['python3',str(link),'--root',str(self.root),'status']))[0])

    def test_scope_rejects_foreign_signals_and_reviews(self):
        for field,script,tail in [
            ('--signals','reserve.py',['grant','--mode','ten','--owner','fixture','--reason','user','--source','user']),
            ('--review','checkpoint.py',['resume','--owner','fixture'])]:
            self.assertFalse(self.classify(self.command(script,*tail,field,'/tmp/foreign.json'))[0])

    def test_shell_override_cannot_wrap_an_allowed_command(self):
        event={'tool_name':'exec_command','tool_input':{'cmd':self.command('reserve.py','status'), 'shell':'/tmp/another-program'}}
        self.assertFalse(maintenance.classify(event,self.root.resolve())[0])

    def test_denial_has_runnable_readonly_next_command_and_task_identity(self):
        self.write_signals(self.signals(20))
        denied=self.invoke()['hookSpecificOutput']['permissionDecisionReason']
        next_cmd=maintenance.next_command(self.root.resolve())
        self.assertIn(next_cmd,denied)
        self.assertTrue(self.classify(next_cmd)[0])
        result=subprocess.run(shlex.split(next_cmd),capture_output=True,text=True,check=True)
        state=json.loads(result.stdout)
        self.assertEqual(state['binding']['task_id'],'reserve-fixture')
        self.assertFalse(state['implementation_allowed'])

    def test_actual_child_work_ten_second_stop_and_exhaustion_provider_denial(self):
        self.write_signals(self.signals(21));self.assertEqual(self.invoke(),{})
        self.write_signals(self.signals(20));self.assertIn('hookSpecificOutput',self.invoke())
        self.write_signals(self.signals(12));self.grant_resume('ten')
        self.assertEqual(self.invoke(),{})
        result=cp.run_boundary(self.root,self.source,[sys.executable,'-c',
            "from pathlib import Path; Path('work.txt').write_text('bounded work completed\\n')"],[])
        self.assertEqual(result['exit_code'],0)
        self.assertEqual((self.root/'work.txt').read_text(),'bounded work completed\n')
        self.write_signals(self.signals(10));self.assertIn('hookSpecificOutput',self.invoke())
        self.write_signals(self.signals(9));self.grant_resume('exhaustion')
        self.write_signals(self.signals(0));self.assertEqual(self.invoke(),{})
        denied=self.signals(0);denied['records'][0]['blocked']=True
        self.write_signals(denied);self.assertIn('hookSpecificOutput',self.invoke())
        first=cp.read(self.store/'latest.json')['id']
        self.assertIn('hookSpecificOutput',self.invoke())
        self.assertEqual(cp.read(self.store/'latest.json')['id'],first)

    def test_missing_active_readings_and_stale_default_readings_block(self):
        self.write_signals(self.signals(20));self.invoke()
        self.write_signals(self.signals(12));self.grant_resume('ten')
        (self.store/'signals.json').unlink()
        self.assertIn('hookSpecificOutput',self.invoke())
        self.assertTrue((self.store/'automatic-stop.json').exists())

    def test_stale_default_observations_do_not_allow_work(self):
        self.write_signals(self.signals(80,at=self.base-dt.timedelta(minutes=3)))
        self.assertIn('hookSpecificOutput',self.invoke())

    def test_legacy_stale_account_observations_do_not_allow_work(self):
        raw=self.signals(80,at=self.base-dt.timedelta(minutes=3))
        self.write_signals({'account_quota':raw['records']})
        self.assertIn('hookSpecificOutput',self.invoke())

    def test_wrapper_rechecks_freshness_before_starting_child(self):
        self.write_signals(self.signals(20));self.invoke()
        self.write_signals(self.signals(12));self.grant_resume('ten')
        reserve.revoke(self.root,'Restore default',owner='fixture')
        self.write_signals(self.signals(90,at=self.base-dt.timedelta(minutes=3)))
        result=cp.run_boundary(self.root,self.source,[sys.executable,'-c',"raise RuntimeError('must not start')"],[])
        self.assertEqual(result['exit_code'],75)

    def test_fresh_grant_source_supersedes_stale_stop_snapshot(self):
        self.write_signals(self.signals(20));self.invoke()
        live=self.store/'live-signals.json';cp.atomic(live,cp.encoded(self.signals(12)))
        reserve.grant(self.root,'ten',self.signals(12),'Explicit test user ten','Test',
                      signals_path=live,owner='fixture')
        self.write_signals(self.signals(20,at=self.base-dt.timedelta(minutes=3)))
        report=reserve.prepare_review(self.root,'Fixture work','Current user','Fresh pinned source',owner='fixture')
        cp.resume(self.root,Path(report['review']),'fixture',[])
        self.assertFalse((self.store/'automatic-stop.json').exists())


if __name__ == '__main__':
    unittest.main()
