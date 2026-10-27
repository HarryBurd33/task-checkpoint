#!/usr/bin/env python3
"""Idempotent local setup/status/repair. Native login/trust stay explicit."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'skills/task-checkpoint/scripts'))
import checkpoint as cp
import account
import monitor


def status(project, skills, state, codex_home):
    target=skills/'task-checkpoint';receipt=target/'.install-receipt.json'
    import importlib.util
    spec=importlib.util.spec_from_file_location('managed_install',ROOT/'install.py')
    managed=importlib.util.module_from_spec(spec);spec.loader.exec_module(managed)
    result={'project':str(project),'prerequisites':{x:shutil.which(x) for x in ('git','codex','gh')},
            'python':sys.version.split()[0],'installed':target.is_dir(),'managed':receipt.exists(),
            'native_windows_verified':False,'native_trust':'Review in Codex /hooks; no trust changes made'}
    if receipt.exists():
        expected=cp.read(receipt)['files'];actual=managed.files(target)
        result.update(customized=actual!=expected,up_to_date=actual==managed.files(ROOT/'skills/task-checkpoint'))
    if (project/'.checkpoint/config.json').exists():
        binding,store=cp.config(project)
        result['binding']={**binding,'store_path':str(store)}
        result['persistent_stop']=(store/'automatic-stop.json').exists()
        result['router_active']=cp.read(store/'router.json').get('active') if (store/'router.json').exists() else None
        # Account-wide events may belong to another registered project. Only
        # an exact binding receipt establishes delivery for this project.
        result['project_hook_delivery_status']='missing'
        delivery=store/'native-hook-delivery.json'
        if delivery.exists():
            try:
                event=cp.read(delivery)
                matches=(Path(event['root']).resolve()==project.resolve()
                         and event.get('task_id')==binding['task_id']
                         and event.get('project_id')==binding['project_id'])
                result['project_hook_delivery_status']='observed' if matches else 'binding-mismatch'
                if matches:result['project_hook_delivery']=event
            except (cp.Fault,OSError,ValueError,KeyError,TypeError):
                result['project_hook_delivery_status']='invalid-receipt'
    if (state/'config.json').exists():
        config=cp.read(state/'config.json')
        result['account']={'enabled':config.get('enabled'),'reserve':config.get('guard_percent'),
                           'projects':config.get('projects',[]),'profile_matches':config.get('codex_home')==str(codex_home)}
        if (state/'status.json').exists():
            data=cp.read(state/'status.json');result['last_collection']=data.get('last_success')
            result['fresh_collection']=0<=cp.age(data.get('last_success'))<=120 if data.get('last_success') else False
        if (state/'hook-delivery.json').exists():result['hook_delivery']=cp.read(state/'hook-delivery.json')
        if (state/'monitor-service.json').exists():
            service=cp.read(state/'monitor-service.json');result['service_receipt']=service
            try:
                if service['platform']=='darwin':
                    native=subprocess.run(['launchctl','print','gui/'+str(os.getuid())+'/'+service['label']],capture_output=True,timeout=10)
                    result['service_registered']=native.returncode==0
                    path=Path(service['path'])
                    result['service_customized']=not path.exists() or cp.sha(cp.content(path))!=service['sha256']
                elif service['platform']=='win32':
                    native=subprocess.run(['schtasks','/Query','/TN',service['task_name'],'/XML'],capture_output=True,timeout=10)
                    result['service_registered']=native.returncode==0
                    result['service_customized']=native.returncode==0 and monitor._xml_hash(native.stdout)!=service['scheduler_definition_sha256']
            except (OSError,subprocess.SubprocessError):
                result['service_registered']=None
    result['authentication']={}
    for name,args in [('codex',['codex','login','status']),('github',['gh','api','user','--jq','.login'])]:
        try:
            observed=subprocess.run(args,capture_output=True,text=True,timeout=12)
            result['authentication'][name]={'status':'authenticated' if observed.returncode==0 else 'unknown-or-unavailable'}
            if name=='github' and observed.returncode==0:result['authentication'][name]['login']=observed.stdout.strip()
        except (OSError,subprocess.SubprocessError):result['authentication'][name]={'status':'unknown-or-unavailable'}
    return result


def setup(project, skills, state, codex_home, task=None, project_id=None, native_service=True, reserve=None, private_repository=None):
    project=project.resolve();skills=skills.resolve();state=state.resolve();codex_home=codex_home.resolve()
    if not shutil.which('git') or not shutil.which('codex'):
        raise cp.Fault('Install Git, Python3.9+ and Codex CLI, then authenticate codex login on this device')
    # Never initialize over a retired/incompatible directory or silently invent task IDs.
    if not (project/'.checkpoint/config.json').exists():
        if (project/'.checkpoint').exists() or not task or not project_id:
            raise cp.Fault('Inspect existing stores/queues first; new binding requires explicit --task and --project-id')
    before=status(project,skills,state,codex_home)
    if before.get('customized') or before.get('service_customized') or before.get('router_active'):
        raise cp.Fault('Customized managed installation or active/uncertain worker; preserve and reconcile first')
    if before.get('account') and not before['account']['profile_matches']:
        raise cp.Fault('Account profile mismatch; use existing device-local profile/state')
    if (state/'monitor-service-transaction.json').exists() and cp.read(state/'monitor-service-transaction.json').get('status')=='failed':
        raise cp.Fault('Review previous service transaction before repair')
    subprocess.run([sys.executable,str(ROOT/'install.py'),'--skills-dir',str(skills),'--repair'],check=True,capture_output=True)
    if not (project/'.checkpoint/config.json').exists():
        subprocess.run([sys.executable,str(ROOT/'skills/task-checkpoint/scripts/checkpoint.py'),'--root',str(project),'init','--task',task,'--project-id',project_id],check=True,capture_output=True)
    # Run from installed source so hook definitions and scheduler keep stable paths.
    runtime=skills/'task-checkpoint/scripts'
    import shlex
    python = sys.executable
    if (state/'hooks-receipt.json').exists():
        definition = next(iter(cp.read(state/'hooks-receipt.json')['definitions'].values()))
        if sys.platform != 'win32':
            python = shlex.split(definition['hooks'][0]['command'])[0]
    subprocess.run([sys.executable,str(runtime/'account.py'),'--state',str(state),'install','--codex-home',str(codex_home),'--project',str(project),'--python',python],check=True,capture_output=True)
    config=cp.read(state/'config.json')
    if private_repository:
        import transfer
        transfer.private_repo(private_repository)
        binding,_=cp.config(project)
        if binding['project_id'].lower()!=private_repository.lower():raise cp.Fault('Private transport must match existing project identity')
        for record in config['projects']:
            if record['root']==str(project):
                record.update(planned_dispatch=True,private_transfer={'repository':private_repository},private_receive={'repository':private_repository})
        cp.atomic(state/'config.json',cp.encoded(config))
    if reserve is not None:
        if not 0<=reserve<=100:raise cp.Fault('Invalid reserve')
        config['guard_percent']=reserve;cp.atomic(state/'config.json',cp.encoded(config))
    if native_service and (not (state/'monitor-service.json').exists() or before.get('service_registered') is False):
        subprocess.run([sys.executable,str(runtime/'monitor.py'),'--state',str(state),'install-service','--python',python],check=True,capture_output=True)
    # Do not restart a matching existing service or rewrite native trust records.
    subprocess.run([sys.executable,str(runtime/'account.py'),'--state',str(state),'tick'],check=True,capture_output=True)
    return status(project,skills,state,codex_home)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['setup','status','repair'])
    p.add_argument('--project',type=Path,default=Path.cwd());p.add_argument('--skills-dir',type=Path,default=Path.home()/'.agents/skills')
    p.add_argument('--state',type=Path,default=Path.home()/'.codex/checkpoint-handoff');p.add_argument('--codex-home',type=Path,default=Path.home()/'.codex')
    p.add_argument('--task');p.add_argument('--project-id');p.add_argument('--private-repository');p.add_argument('--reserve',type=float);p.add_argument('--no-service',action='store_true')
    a=p.parse_args()
    result=status(a.project.resolve(),a.skills_dir.resolve(),a.state.resolve(),a.codex_home.resolve()) if a.command=='status' else setup(a.project,a.skills_dir,a.state,a.codex_home,a.task,a.project_id,not a.no_service,a.reserve,a.private_repository)
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (cp.Fault,OSError,ValueError,subprocess.SubprocessError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)}),file=sys.stderr);sys.exit(2)
