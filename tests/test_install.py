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
            self.assertEqual(installed['hooks']['Interrupt'][0]['hooks'][0]['timeout'],3)
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
if __name__=='__main__':unittest.main()
