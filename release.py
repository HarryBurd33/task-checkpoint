#!/usr/bin/env python3
"""Reproducible allowlisted public export; never copy private Git history."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import sys
import zipfile

ROOT=Path(__file__).resolve().parent


def export(root, output, allowlist=None):
    entries=json.loads((allowlist or root/'public-export.json').read_text())
    if entries.get('version')!=1 or not isinstance(entries.get('files'),dict):
        raise ValueError('Explicit versioned public file map required')
    content={}
    for dest,source in entries['files'].items():
        for name in (dest,source):
            p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or str(p)!=name or any(x in ('.git','.checkpoint','.private','.codex') for x in p.parts):
                raise ValueError('Private or unsafe export path')
        path=root/source
        if any(p.is_symlink() for p in [path,*path.parents]) or not path.is_file():
            raise ValueError('Missing or linked allowlisted source')
        data=path.read_bytes()
        if len(data)>16*1024*1024:raise ValueError('Oversized public source')
        text=data.decode('utf-8')
        # Concrete private markers supplement an exact allowlist, not certify arbitrary prose.
        if re.search(r'/[U]sers/|[C]:\\[U]sers\\|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]+PRIVATE KEY',text):
            raise ValueError('Private marker in allowlisted file: '+source)
        content[dest]=data
    if 'LICENSE' not in content:raise ValueError('License notice required')
    manifest={n:hashlib.sha256(b).hexdigest() for n,b in sorted(content.items())}
    content['PUBLIC-MANIFEST.json']=(json.dumps({'version':1,'files':manifest},indent=2,sort_keys=True)+'\n').encode()
    with tempfile.NamedTemporaryFile(dir=output.parent,delete=False) as f:temporary=Path(f.name)
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for n,b in sorted(content.items()):
                info=zipfile.ZipInfo(n,(2020,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.create_system=3;info.external_attr=0o100644<<16
                z.writestr(info,b)
        raw=temporary.read_bytes()
        if output.exists() and output.read_bytes()!=raw:raise ValueError('Export output exists with different content; use a new versioned path')
        temporary.replace(output)
    finally:temporary.unlink(missing_ok=True)
    verify(output)
    return {'sha256':hashlib.sha256(raw).hexdigest(),'files':manifest,'archive':str(output)}


def verify(archive):
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate exported files')
        m=json.loads(z.read('PUBLIC-MANIFEST.json'))['files']
        if set(names)!=set(m)|{'PUBLIC-MANIFEST.json'}:raise ValueError('Unexpected exported member')
        for name,digest in m.items():
            p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or str(p)!=name:raise ValueError('Unsafe exported path')
            if hashlib.sha256(z.read(name)).hexdigest()!=digest:raise ValueError('Public content hash mismatch')
    return m


def managed_path(root, name):
    p=PurePosixPath(name)
    if (not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or str(p)!=name
        or any(part in ('.git','.checkpoint','.private','.codex') for part in p.parts)):
        raise ValueError('Unsafe public managed path')
    path=root/name
    current=path
    while current!=root:
        if current.is_symlink():raise ValueError('Linked public managed path')
        current=current.parent
    return path


def command(args, cwd=None):
    p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=120)
    if p.returncode:raise RuntimeError('Command failed: '+args[0]+' '+args[1]+'; inspect authentication/network and remote outcome before retry')
    return p.stdout.strip()


def publish(root, repository):
    """Create clean public history or update only manifest-owned unchanged files."""
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):raise ValueError('Explicit public owner/repository required')
    profile=json.loads(command(['gh','api','user']));login=profile['login']
    if repository.split('/')[0].lower()!=login.lower():raise ValueError('Verify authenticated publication owner')
    if command(['git','status','--porcelain'],root):raise ValueError('Commit and review source before public publication')
    probe=subprocess.run(['gh','api','repos/'+repository],capture_output=True,text=True,timeout=30)
    if probe.returncode:
        try:not_found=json.loads(probe.stdout).get('status')=='404' or json.loads(probe.stdout).get('status')==404
        except ValueError:not_found=False
        if not not_found:raise RuntimeError('Repository lookup failed; do not infer availability from network/auth failure')
        info=None
    else:
        info=json.loads(probe.stdout)
        if info.get('private') is not False or not info.get('permissions',{}).get('push'):raise ValueError('Existing target must be a writable public repository; visibility is never changed')
    with tempfile.TemporaryDirectory(prefix='checkpoint-public-publish-') as d:
        work=Path(d);archive=work/'public.zip';result=export(root,archive);manifest=verify(archive)
        checkout=work/'checkout'
        if info:
            command(['git','clone','https://github.com/'+repository+'.git',str(checkout)])
            prior_file=checkout/'PUBLIC-MANIFEST.json'
            if prior_file.is_symlink() or not prior_file.exists():raise ValueError('Existing public target lacks managed manifest; preserve and review')
            prior=json.loads(prior_file.read_text())['files']
            for name,digest in prior.items():
                path=managed_path(checkout,name)
                if not path.is_file() or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                    raise ValueError('Public managed file changed; preserve and review: '+name)
            for name in set(manifest)-set(prior):
                if managed_path(checkout,name).exists():raise ValueError('Public unmanaged path conflict: '+name)
            for name in set(prior)-set(manifest):managed_path(checkout,name).unlink()
        else:
            checkout.mkdir();command(['git','init','-b','main'],checkout)
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                path=managed_path(checkout,name);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(name))
        # Publication never assumes a successful export implies a working package.
        validation=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=checkout,capture_output=True,text=True,timeout=240)
        if validation.returncode:raise ValueError('Exported distribution tests failed; no commit or push performed')
        if not info:
            command(['gh','repo','create',repository,'--public','--description','Verified checkpoint preservation and bounded task handoffs'])
            command(['git','remote','add','origin','https://github.com/'+repository+'.git'],checkout)
        else:
            command(['git','remote','get-url','origin'],checkout)
        command(['git','config','user.name',login],checkout)
        command(['git','config','user.email',str(profile['id'])+'+'+login+'@users.noreply.github.com'],checkout)
        command(['git','add','--all'],checkout)
        if command(['git','diff','--cached','--name-only'],checkout):
            command(['git','commit','-m','Release reusable Checkpoint and Handoff distribution'],checkout)
            command(['git','push','origin','HEAD'],checkout)
        commit=command(['git','rev-parse','HEAD'],checkout)
        branch=command(['git','branch','--show-current'],checkout)
        remote=command(['git','ls-remote','origin','refs/heads/'+branch],checkout).split()[0]
        if remote!=commit:raise ValueError('Public remote commit mismatch')
        return {'repository':repository,'branch':branch,'commit':commit,'archive_sha256':result['sha256'],
                'files':len(manifest),'exported_tests':'passed','remote_verified':True}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--publish',action='store_true');p.add_argument('--repository')
    a=p.parse_args()
    if a.publish:
        if not a.repository:p.error('--repository required for publication')
        result=publish(ROOT,a.repository)
    else:
        if not a.output:p.error('--output required for export')
        a.output.parent.mkdir(parents=True,exist_ok=True)
        result=export(ROOT,a.output)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
