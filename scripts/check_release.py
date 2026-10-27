#!/usr/bin/env python3
"""Check the release manifest and reject private artifacts in the public tree."""
import hashlib,json,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
skill=root/'skills/task-checkpoint'
manifest=json.loads((skill/'PACKAGE-MANIFEST.json').read_text())['files']
actual={p.relative_to(skill).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in skill.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in ('PACKAGE-MANIFEST.json','.install-receipt.json')}
assert actual==manifest, 'Skill manifest differs from actual contents'
assert 'MIT License' in (root/'LICENSE').read_text()
assert (skill/'LICENSE').read_bytes()==(root/'LICENSE').read_bytes()
for p in root.rglob('*'):
 if not p.is_file() or any(x in p.parts for x in ('.git','__pycache__')):continue
 rel=p.relative_to(root)
 assert not any(x in rel.parts for x in ('.checkpoint','.private','.forge','.codex')), 'Private state in release: '+str(rel)
 assert not p.is_symlink(), 'Linked release file: '+str(rel)
 text=p.read_text(encoding='utf-8')
 assert not re.search(r'/[U]sers/|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]+PRIVATE KEY-----',text), 'Private marker: '+str(rel)
print('MIT notices, skill manifest, and public-file privacy checks passed; pattern checks cannot certify arbitrary content secret-free.')
