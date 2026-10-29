#!/usr/bin/env python3
"""Managed idempotent install/repair with customization preservation and rollback."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parent
VERSION='0.7.6'

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def files(root):return {p.relative_to(root).as_posix():digest(p) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='.install-receipt.json'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--skills-dir',type=Path,required=True);p.add_argument('--project',type=Path)
    group=p.add_mutually_exclusive_group();group.add_argument('--uninstall',action='store_true');group.add_argument('--repair',action='store_true');group.add_argument('--status',action='store_true')
    a=p.parse_args();target=a.skills_dir.resolve()/'task-checkpoint';receipt=target/'.install-receipt.json'
    if target.is_symlink():raise RuntimeError('Linked skill destination refused')
    prior=json.loads(receipt.read_text()) if receipt.exists() else None
    actual=files(target) if target.exists() else None
    source=files(ROOT)
    if a.status:
        print(json.dumps({'installed':target.exists(),'managed':prior is not None,'customized':actual is not None and (prior is None or actual!=prior['files']),'up_to_date':actual==source,'version':prior.get('version') if prior else None}));return
    if target.exists() and (prior is None or actual!=prior['files']):raise RuntimeError('Existing/customized skill preserved; compare manually')
    if a.uninstall and not target.exists():raise RuntimeError('No managed installation')
    if target.exists() and not (a.repair or a.uninstall):raise RuntimeError('Managed skill already installed; use --repair for idempotent upgrade')
    hook_operation=None
    if a.project:
        project=a.project.resolve();hooks=project/'.codex/hooks.json';backup=project/'.codex/task-checkpoint-hooks-backup.json';marker=project/'.codex/task-checkpoint-install.json'
        if marker.exists():
            if not hooks.exists() or digest(hooks)!=json.loads(marker.read_text())['sha256']:raise RuntimeError('Hook configuration changed; preserve and reconcile manually')
            if a.uninstall:
                previous=json.loads(backup.read_text());hook_operation=('restore',previous)
        elif a.uninstall:raise RuntimeError('No managed project hook receipt; preserve unrelated hooks')
        else:
            if backup.exists():raise RuntimeError('Existing hook integration preserved')
            value=json.loads(hooks.read_text()) if hooks.exists() else {'hooks':{}}
            if not isinstance(value.get('hooks'),dict):raise RuntimeError('Unsupported existing hook configuration')
            command=subprocess.list2cmdline([sys.executable,str(target/'scripts/hook.py')]) if sys.platform=='win32' else shlex.join([sys.executable,str(target/'scripts/hook.py')])
            for event in ['SessionStart','PreToolUse','PostToolUse','PreCompact','Stop','Interrupt','SessionEnd']:
                value['hooks'].setdefault(event,[]).append({'hooks':[{'type':'command','command':command,'timeout':3 if event in ('Interrupt','SessionEnd') else 15}]})
            hook_operation=('install',value)
    if a.uninstall:
        if hook_operation:
            previous=hook_operation[1]
            if previous['existed']:hooks.write_text(previous['content'])
            else:hooks.unlink()
            marker.unlink();backup.unlink()
        shutil.rmtree(target)
        print('Removed unchanged managed skill. Private checkpoints and ownership retained.');return
    a.skills_dir.mkdir(parents=True,exist_ok=True)
    if actual!=source:
        if target.exists():
            rollback=a.skills_dir/'.task-checkpoint-rollback';rollback.mkdir(exist_ok=True)
            name=prior['version']+'-'+hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest()[:16]+'.zip'
            with zipfile.ZipFile(rollback/name,'w',zipfile.ZIP_DEFLATED) as z:
                for f in sorted(target.rglob('*')):
                    if f.is_file() and '__pycache__' not in f.parts:z.write(f,'task-checkpoint/'+f.relative_to(target).as_posix())
        with tempfile.TemporaryDirectory(prefix='.task-checkpoint-stage-',dir=a.skills_dir) as d:
            stage=Path(d)/'task-checkpoint';shutil.copytree(ROOT,stage,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            (stage/'.install-receipt.json').write_text(json.dumps({'version':VERSION,'files':files(stage)},indent=2)+'\n')
            old=Path(d)/'old'
            if target.exists():target.rename(old)
            try:stage.rename(target)
            except Exception:
                if old.exists():old.rename(target)
                raise
    if hook_operation and hook_operation[0]=='install':
        hooks.parent.mkdir(parents=True,exist_ok=True)
        backup.write_text(json.dumps({'existed':hooks.exists(),'content':hooks.read_text() if hooks.exists() else ''},indent=2)+'\n')
        hooks.write_text(json.dumps(hook_operation[1],indent=2)+'\n')
        marker.write_text(json.dumps({'sha256':digest(hooks),'runtime_version':VERSION},indent=2)+'\n')
    print('Installed task-checkpoint '+VERSION+'. Native hook trust must be reviewed separately.')

if __name__=='__main__':
    try:main()
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(2)
