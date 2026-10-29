import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
INSTALL=Path(__file__).resolve().parents[1]/'install.py'
class InstallationTests(unittest.TestCase):
    def test_install_preserves_existing_hooks_and_uninstall_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);skills=root/'skills';project=root/'project';hooks=project/'.codex/hooks.json'
            hooks.parent.mkdir(parents=True)
            initial=json.dumps({'hooks':{'SessionStart':[{'hooks':[{'type':'command','command':'existing-herdr-session-hook'}]}]}})+'\n'
            hooks.write_text(initial)
            cmd=[sys.executable,str(INSTALL),'--skills-dir',str(skills),'--project',str(project)]
            subprocess.run(cmd,check=True,capture_output=True)
            installed=json.loads(hooks.read_text())
            self.assertEqual(installed['hooks']['SessionStart'][0]['hooks'][0]['command'],'existing-herdr-session-hook')
            self.assertEqual(hooks.read_text(),initial)
            self.assertTrue((skills/'task-checkpoint/.install-receipt.json').exists())
            subprocess.run(cmd+['--uninstall'],check=True,capture_output=True)
            self.assertEqual(hooks.read_text(),initial)
            self.assertFalse((skills/'task-checkpoint').exists())
    def test_modified_install_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills=Path(tmp)/'skills';cmd=[sys.executable,str(INSTALL),'--skills-dir',str(skills)]
            subprocess.run(cmd,check=True,capture_output=True)
            target=skills/'task-checkpoint/SKILL.md';target.write_text(target.read_text()+'\ncustomization\n')
            r=subprocess.run(cmd+['--uninstall'],capture_output=True)
            self.assertEqual(r.returncode,2)
            self.assertIn('customization',target.read_text())

class UpgradeTests(unittest.TestCase):
    def test_repair_archives_old_managed_version_and_installs_same_bytes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            skills=Path(tmp)/'skills';cmd=[sys.executable,str(INSTALL),'--skills-dir',str(skills)]
            subprocess.run(cmd,check=True,capture_output=True)
            target=skills/'task-checkpoint';receipt=target/'.install-receipt.json'
            old=target/'obsolete-runtime.py';old.write_text('old runtime preserved in rollback')
            value=json.loads(receipt.read_text());value['version']='0.7.6';value['files']['obsolete-runtime.py']=hashlib.sha256(old.read_bytes()).hexdigest();receipt.write_text(json.dumps(value))
            subprocess.run(cmd+['--repair'],check=True,capture_output=True)
            self.assertFalse(old.exists())
            self.assertTrue(list((skills/'.task-checkpoint-rollback').glob('0.7.6-*.zip')))
            result=subprocess.run(cmd+['--status'],check=True,capture_output=True,text=True)
            self.assertTrue(json.loads(result.stdout)['up_to_date'])
            self.assertEqual(json.loads(result.stdout)['version'],'0.8.2')

    @unittest.skipUnless(sys.platform != 'win32', 'POSIX ownership and modes')
    def test_upgrade_preserves_existing_directory_and_file_metadata(self):
        import hashlib
        import stat
        with tempfile.TemporaryDirectory() as tmp:
            skills=Path(tmp)/'skills';cmd=[sys.executable,str(INSTALL),'--skills-dir',str(skills)]
            subprocess.run(cmd,check=True,capture_output=True)
            target=skills/'task-checkpoint';receipt=target/'.install-receipt.json'
            paths=[target,target/'scripts',target/'SKILL.md',receipt]
            for p in paths:p.chmod(0o700 if p.is_dir() else 0o600)
            before={p:(p.stat().st_uid,p.stat().st_gid,stat.S_IMODE(p.stat().st_mode)) for p in paths}
            obsolete=target/'old.py';obsolete.write_text('managed rollback bytes')
            value=json.loads(receipt.read_text());value['version']='fixture-old';value['files']['old.py']=hashlib.sha256(obsolete.read_bytes()).hexdigest();receipt.write_text(json.dumps(value))
            subprocess.run(cmd+['--repair'],check=True,capture_output=True)
            self.assertEqual({p:(p.stat().st_uid,p.stat().st_gid,stat.S_IMODE(p.stat().st_mode)) for p in paths},before)
            self.assertFalse(obsolete.exists())

    def test_standalone_skill_installer_and_legacy_project_hook_retirement(self):
        import hashlib
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);standalone=root/'standalone'
            shutil.copytree(INSTALL.parent/'skills/task-checkpoint',standalone,ignore=shutil.ignore_patterns('__pycache__'))
            project=root/'project';settings=project/'.codex';settings.mkdir(parents=True)
            original='{"hooks": {"PreToolUse": [{"hooks": [{"command": "unrelated"}]}]}}\n'
            old='{"hooks": {"PreToolUse": [{"hooks": [{"command": "old-checkpoint"}]}]}}\n'
            hooks=settings/'hooks.json';hooks.write_text(old)
            (settings/'task-checkpoint-hooks-backup.json').write_text(json.dumps({'existed':True,'content':original}))
            (settings/'task-checkpoint-install.json').write_text(json.dumps({'sha256':hashlib.sha256(hooks.read_bytes()).hexdigest()}))
            subprocess.run([sys.executable,str(standalone/'install.py'),'--skills-dir',str(root/'skills'),'--project',str(project)],check=True,capture_output=True)
            self.assertEqual(hooks.read_text(),original)
            self.assertFalse((settings/'task-checkpoint-install.json').exists())
            self.assertTrue((root/'skills/task-checkpoint/SKILL.md').exists())

if __name__ == '__main__':
    unittest.main()
