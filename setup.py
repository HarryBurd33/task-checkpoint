#!/usr/bin/env python3
"""Install the skill; optionally initialize one explicitly named task. No hooks."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('command', choices=['setup', 'repair', 'status'])
p.add_argument('--skills-dir', type=Path, default=Path.home()/'.agents/skills')
p.add_argument('--project', type=Path)
p.add_argument('--task')
p.add_argument('--project-id')
a = p.parse_args()
args = [sys.executable, str(ROOT/'install.py'), '--skills-dir', str(a.skills_dir)]
if a.project: args += ['--project', str(a.project)]
args += ['--status' if a.command == 'status' else '--repair']
subprocess.run(args, check=True)
if a.command != 'status' and a.project and a.task and a.project_id:
    if not (a.project/'.checkpoint/config.json').exists():
        subprocess.run([sys.executable, str(ROOT/'skills/task-checkpoint/scripts/checkpoint.py'),
                        '--root', str(a.project), 'init', '--task', a.task, '--project-id', a.project_id], check=True)
