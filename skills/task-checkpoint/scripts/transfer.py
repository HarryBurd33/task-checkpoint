#!/usr/bin/env python3
"""Immutable verified private bundle exchange. Imports are quarantined task data.

GitHub CLI authentication is device-local. No credentials, ownership receipts,
queues, raw logs, hooks or execution authorization enter a bundle. Source Git
synchronization remains separate. GitHub assets are never overwritten.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import checkpoint as cp

MAX_ARCHIVE = 128 * 1024 * 1024


def gh(args):
    p = subprocess.run(['gh', *args], capture_output=True, timeout=90)
    if p.returncode:
        raise cp.Fault('GitHub operation failed; inspect authentication/network and retry the same immutable transfer')
    return p.stdout


def private_repo(repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise cp.Fault('Explicit owner/repository required')
    info = json.loads(gh(['api', 'repos/' + repository]))
    login = json.loads(gh(['api', 'user']))['login']
    if (info.get('full_name', '').lower() != repository.lower() or info.get('private') is not True
        or not info.get('permissions', {}).get('push') or not login):
        raise cp.Fault('Private repository identity and authenticated write access required')
    return {'repository': info['full_name'], 'login': login}


def zip_bytes(files):
    import io
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # Canonical POSIX metadata on every host.
            info.external_attr = 0o100600 << 16
            z.writestr(info, data)
    return result.getvalue()


def package(root, output):
    binding, store = cp.config(root)
    # A checkpoint writer can promote a generation while packaging. Take the same
    # store lock so metadata and both immutable generations form one valid unit.
    with cp.lock(store):
        pointer = cp.read(store/'latest.json')
        s, _ = cp.check_generation(store, pointer)
        files = {'latest.json': cp.encoded(pointer)}
        generations = [pointer] + ([pointer['previous']] if pointer.get('previous') else [])
        for p in generations:
            _, folder = cp.check_generation(store, p)
            for path in sorted(folder.rglob('*')):
                if path.is_symlink():
                    raise cp.Fault('Linked checkpoint artifact refused')
                if path.is_file():
                    files['snapshots/'+p['id']+'/'+path.relative_to(folder).as_posix()] = cp.content(path)
        semantic = store/'input.json'
        if semantic.exists():
            value = cp.read(semantic)
            cp.validate(value,cp.read(cp.ASSETS/'task.schema.json'))
            if cp.redact(value) != value:raise cp.Fault('Redact secret-like semantic input before transfer')
            files['semantic-input.json'] = cp.encoded(value)
        journal_path = store/'router.json'
        if journal_path.exists():
            journal = cp.read(journal_path)
            if journal.get('version')!=1 or journal.get('task_id')!=binding['task_id']:
                raise cp.Fault('Router journal identity mismatch')
            observed = {k:journal[k] for k in ('version','task_id','history','active','current_worker') if k in journal}
            if cp.redact(observed)!=observed:raise cp.Fault('Redact secret-like router evidence before transfer')
            files['router-state.json'] = cp.encoded(observed)
            records = list(journal.get('history',[])) + ([journal['active']] if journal.get('active') else [])
            for record in records:
                ident = record.get('id','')
                if not re.fullmatch(r'[a-f0-9]{32}',ident):raise cp.Fault('Invalid router run identity')
                result = store/'router-runs'/ident/'result.txt'
                if result.exists():
                    raw_result = cp.content(result)
                    if cp.unsafe(raw_result):raise cp.Fault('Secret-like worker result excluded; redact before transfer')
                    files['router-runs/'+ident+'/result.txt'] = raw_result
        stop = store/'automatic-stop.json'
        if stop.exists():
            marker = cp.read(stop)
            files['stop.json'] = cp.encoded({k: marker[k] for k in ('low_kinds','resource_accounts','checkpoint_status','checkpoint_id') if k in marker})
        scoped_stop = bool(json.loads(files['stop.json']).get('resource_accounts')) if 'stop.json' in files else False
        # Older readers must reject scoped stops rather than silently dropping identity.
        meta = {'version': 2 if scoped_stop else 1, 'project_id': binding['project_id'], 'task_id': binding['task_id'],
                'checkpoint_id': s['id'], 'source_revision': s['repository']['commit'],
                'created_at': s['created_at'], 'files': {k: cp.sha(v) for k,v in files.items()},
                'permissions_restored': False, 'execution_authorized': False}
        files['bundle.json'] = cp.encoded(meta)
        raw = zip_bytes(files)
        if len(raw) > MAX_ARCHIVE or sum(map(len,files.values())) > MAX_ARCHIVE:
            raise cp.Fault('Bundle too large; select an independently verified large-artifact transport')
        cp.atomic(output, raw)
    verify(output, binding['project_id'], binding['task_id'], meta['source_revision'])
    return dict(meta, archive_sha256=cp.sha(raw), path=str(output))


def unpack(archive, destination):
    if archive.stat().st_size > MAX_ARCHIVE:
        raise cp.Fault('Oversized private bundle')
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist(); names=[i.filename for i in infos]
        if len(names)!=len(set(names)) or len(names)>10000 or sum(i.file_size for i in infos)>MAX_ARCHIVE:
            raise cp.Fault('Duplicate, excessive or oversized archive entries')
        for info in infos:
            name=info.filename; parts=PurePosixPath(name).parts
            if ('\\' in name or ':' in name or not parts or name.startswith('/')
                or any(x in ('..','.') for x in parts) or '/'.join(parts)!=name
                or (info.external_attr >> 16) & 0o170000 not in (0,0o100000)):
                raise cp.Fault('Unsafe archive member')
            if name not in ('bundle.json','latest.json','stop.json','semantic-input.json','router-state.json') and not re.fullmatch(r'(snapshots/[a-f0-9]{32}/.+|router-runs/[a-f0-9]{32}/result.txt)',name):
                raise cp.Fault('Unexpected private state in bundle')
            target=destination/name; target.parent.mkdir(parents=True,exist_ok=True)
            cp.atomic(target,z.read(info))


def verify(archive, project, task, revision):
    with tempfile.TemporaryDirectory(prefix='checkpoint-verify-') as d:
        store=Path(d);unpack(archive,store)
        meta=cp.read(store/'bundle.json')
        if (meta.get('version') not in (1,2) or meta.get('project_id')!=project or meta.get('task_id')!=task
            or meta.get('source_revision')!=revision or meta.get('permissions_restored') is not False
            or meta.get('execution_authorized') is not False):
            raise cp.Fault('Bundle identity/source revision mismatch')
        files={p.relative_to(store).as_posix():cp.sha(cp.content(p)) for p in store.rglob('*') if p.is_file() and p != store/'bundle.json'}
        if files!=meta['files']:
            raise cp.Fault('Bundle manifest mismatch')
        pointer=cp.read(store/'latest.json')
        pointers=[pointer]+([pointer['previous']] if pointer.get('previous') else [])
        for ptr in pointers:
            s,_=cp.check_generation(store,ptr)
            if s['project_id']!=project or s['task_id']!=task:
                raise cp.Fault('Generation belongs to another task')
        state,_=cp.latest(store)
        if state['id']!=meta['checkpoint_id'] or state['repository']['commit']!=revision:
            raise cp.Fault('Checkpoint/source mismatch')
        expected={'latest.json'}
        if (store/'semantic-input.json').exists():
            semantic=cp.read(store/'semantic-input.json')
            cp.validate(semantic,cp.read(cp.ASSETS/'task.schema.json'))
            if 'routing' in semantic:
                import router_policy
                router_policy.validate_task(semantic)
            expected.add('semantic-input.json')
        if (store/'router-state.json').exists():
            journal=cp.read(store/'router-state.json')
            if journal.get('version')!=1 or journal.get('task_id')!=task or not isinstance(journal.get('history'),list):
                raise cp.Fault('Transferred router identity mismatch')
            expected.add('router-state.json')
            records=list(journal['history'])+([journal['active']] if journal.get('active') else [])
            for record in records:
                if not isinstance(record,dict) or not re.fullmatch(r'[a-f0-9]{32}',record.get('id','')):
                    raise cp.Fault('Invalid transferred router record')
                result='router-runs/'+record['id']+'/result.txt'
                if (store/result).exists():expected.add(result)
        if (store/'stop.json').exists():
            stop=cp.read(store/'stop.json')
            if not isinstance(stop.get('low_kinds'),list) or not all(k in ('codex_plan','context','api_balance','local_resource') for k in stop['low_kinds']):
                raise cp.Fault('Invalid transferred resource stop')
            accounts=stop.get('resource_accounts',[])
            if not isinstance(accounts,list) or any(not isinstance(a,str) or not re.fullmatch(r'[a-f0-9]{64}',a) for a in accounts) or len(accounts)!=len(set(accounts)):
                raise cp.Fault('Invalid transferred stop account identities')
            if accounts and meta['version']!=2:
                raise cp.Fault('Account-scoped stop requires bundle version2')
            expected.add('stop.json')
        if meta['version']==2 and (not (store/'stop.json').exists() or not cp.read(store/'stop.json').get('resource_accounts')):
            raise cp.Fault('Bundle version2 requires an account-scoped stop')
        for ptr in pointers:
            prefix='snapshots/'+ptr['id']+'/'
            expected.update(prefix+n for n in cp.read(store/prefix/'manifest.json'))
            expected.add(prefix+'manifest.json')
        if set(files)!=expected:
            raise cp.Fault('Unexpected generation files')
        return meta


def quarantine(root, archive, expected_sha256, project, task, revision, destination):
    """No promotion, restoration, lease acquisition, authorization or execution."""
    if archive.stat().st_size > MAX_ARCHIVE:
        raise cp.Fault('Oversized private bundle')
    if cp.sha(archive.read_bytes())!=expected_sha256:
        raise cp.Fault('Archive digest mismatch')
    binding, _=cp.config(root)
    if binding['project_id']!=project or binding['task_id']!=task:
        raise cp.Fault('Destination task identity mismatch')
    if cp.git_text(root,'rev-parse','HEAD')!=revision:
        raise cp.Fault('Synchronize and review the exact source revision before destination use')
    meta=verify(archive,project,task,revision)
    destination=destination.resolve()
    destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        receipt=cp.read(destination/'received.json')
        if receipt.get('archive_sha256')!=expected_sha256:
            raise cp.Fault('Destination exists with different content; preserve both')
        verify(destination/'bundle.zip',project,task,revision)
        return dict(receipt,deduplicated=True)
    with tempfile.TemporaryDirectory(prefix='checkpoint-incoming-',dir=destination.parent) as d:
        stage=Path(d)/'verified';stage.mkdir()
        unpack(archive,stage)
        shutil.copyfile(archive,stage/'bundle.zip')
        receipt={'archive_sha256':expected_sha256,'checkpoint_id':meta['checkpoint_id'],
                 'received_at':cp.now(),'review_required':True,'owner_acquired':False,'worker_started':False,
                 'source_revision':revision,'project_id':project,'task_id':task}
        cp.atomic(stage/'received.json',cp.encoded(receipt))
        os.rename(stage,destination)
    return receipt


def publish(root, repository):
    private_repo(repository)
    binding,store=cp.config(root)
    if binding['project_id'].lower()!=repository.lower():
        raise cp.Fault('Transfer repository must match bound project identity')
    guard=store/'transfer';guard.mkdir(exist_ok=True)
    with cp.lock(guard):
        current, _ = cp.latest(store)
        success = guard/'last-success.json'
        if success.exists() and cp.read(success).get('checkpoint_id') == current['id']:
            return dict(cp.read(success), deduplicated=True)
        if binding['ownership']=='remote':
            # New outbound generations require the current source lease. An old
            # device may keep a local preservation snapshot, but cannot publish
            # it over a handoff after ownership moved to another computer.
            cp.Ownership(root,binding,store).check()
        archive=guard/'bundle.zip';meta=package(root,archive)
        tag='checkpoint-bundle-'+binding['task_id']+'-'+meta['checkpoint_id']
        asset='bundle-'+meta['archive_sha256']+'.zip'
        archive_name=guard/asset
        if not archive_name.exists():cp.atomic(archive_name,archive.read_bytes())
        journal=guard/(meta['checkpoint_id']+'.json')
        cp.atomic(journal,cp.encoded({'status':'upload-intent','tag':tag,'asset':asset,'revision':meta['source_revision'],'at':cp.now()}))
        # Read the remote source commit first. State transfer never pushes source.
        gh(['api','repos/'+repository+'/commits/'+meta['source_revision']])
        releases=json.loads(gh(['api','repos/'+repository+'/releases?per_page=100']))
        release=next((r for r in releases if r['tag_name']==tag),None)
        if release is None:
            gh(['release','create',tag,'--repo',repository,'--target',meta['source_revision'],
                '--prerelease','--latest=false','--title',tag,'--notes','Verified private checkpoint bundle; import requires fresh review and ownership.'])
        release=json.loads(gh(['api','repos/'+repository+'/releases/tags/'+tag]))
        assets=release['assets']
        if any(a['name']!=asset for a in assets):
            raise cp.Fault('Conflicting release content; never overwrite immutable bundle assets')
        if not any(a['name']==asset for a in assets):
            gh(['release','upload',tag,str(archive_name),'--repo',repository])
        # Both new uploads and uncertain retries must pass actual remote readback.
        with tempfile.TemporaryDirectory(prefix='checkpoint-readback-') as d:
            gh(['release','download',tag,'--repo',repository,'--pattern',asset,'--dir',d])
            downloaded=Path(d)/asset
            if cp.sha(downloaded.read_bytes())!=meta['archive_sha256']:
                raise cp.Fault('Remote asset corrupt or incomplete; do not overwrite or claim upload success')
            verify(downloaded,binding['project_id'],binding['task_id'],meta['source_revision'])
        result={'status':'verified','tag':tag,'asset':asset,'archive_sha256':meta['archive_sha256'],
                'source_revision':meta['source_revision'],'checkpoint_id':meta['checkpoint_id'],'verified_at':cp.now()}
        cp.atomic(journal,cp.encoded(result));cp.atomic(guard/'last-success.json',cp.encoded(result))
        return result


def receive(root, repository, tag, asset, revision):
    private_repo(repository)
    binding,store=cp.config(root)
    if binding['project_id'].lower()!=repository.lower() or not re.fullmatch(r'bundle-[a-f0-9]{64}\.zip',asset):
        raise cp.Fault('Explicit bound repository and content-addressed bundle asset required')
    release=json.loads(gh(['api','repos/'+repository+'/releases/tags/'+tag]))
    if not any(a['name']==asset and a['state']=='uploaded' for a in release['assets']):
        raise cp.Fault('Complete requested release asset unavailable')
    digest=asset[7:-4]
    with tempfile.TemporaryDirectory(prefix='checkpoint-receive-') as d:
        gh(['release','download',tag,'--repo',repository,'--pattern',asset,'--dir',d])
        path=Path(d)/asset;meta=verify(path,binding['project_id'],binding['task_id'],revision)
        return quarantine(root,path,digest,binding['project_id'],binding['task_id'],revision,
                          store/'incoming'/meta['checkpoint_id'])


def receive_latest(root, repository):
    """Automatically quarantine the newest task asset; never adopt or execute.

    Source Git must already match the bundle. Unknown/future release timestamps,
    source drift and conflicting assets remain pending rather than selecting an
    older generation or granting recovery permission.
    """
    private_repo(repository)
    binding,_=cp.config(root)
    if binding['project_id'].lower()!=repository.lower():
        raise cp.Fault('Receive repository differs from bound project')
    releases=json.loads(gh(['api','repos/'+repository+'/releases?per_page=100']))
    prefix='checkpoint-bundle-'+binding['task_id']+'-'
    candidates=[]
    for release in releases:
        tag=release.get('tag_name','')
        if not tag.startswith(prefix) or not re.fullmatch(r'[a-f0-9]{32}',tag[len(prefix):]) or release.get('draft'):
            continue
        if not isinstance(release.get('published_at'),str):
            raise cp.Fault('Release freshness unknown; explicit review required')
        try: elapsed=cp.age(release.get('published_at'))
        except (cp.Fault,TypeError,ValueError,OverflowError):raise cp.Fault('Release freshness unknown; explicit review required')
        if elapsed<0:raise cp.Fault('Future release timestamp; no automatic receive')
        candidates.append((release['published_at'],release))
    if not candidates:return {'status':'no-task-bundle','worker_started':False,'owner_acquired':False}
    newest=max(candidates,key=lambda item:item[0])[1]
    assets=newest.get('assets',[])
    if len(assets)!=1 or assets[0].get('state')!='uploaded' or not re.fullmatch(r'bundle-[a-f0-9]{64}\.zip',assets[0].get('name','')):
        raise cp.Fault('Newest task asset incomplete/conflicting; preserve prior received state')
    revision=cp.git_text(root,'rev-parse','HEAD')
    received=receive(root,repository,newest['tag_name'],assets[0]['name'],revision)
    return dict(received,status='quarantined',automatic_adoption=False)


@contextlib.contextmanager
def verified_incoming(root, ident):
    if not re.fullmatch(r'[a-f0-9]{32}', ident):
        raise cp.Fault('Explicit checkpoint ID required')
    binding, store = cp.config(root)
    original = store/'incoming'/ident
    receipt = cp.read(original/'received.json')
    archive = original/'bundle.zip'
    if archive.is_symlink() or archive.stat().st_size > MAX_ARCHIVE:
        raise cp.Fault('Invalid quarantined archive')
    raw = archive.read_bytes()
    if cp.sha(raw) != receipt['archive_sha256']:
        raise cp.Fault('Quarantined archive changed')
    with tempfile.TemporaryDirectory(prefix='checkpoint-promote-') as d:
        copied=Path(d)/'bundle.zip';cp.atomic(copied,raw)
        meta=verify(copied,binding['project_id'],binding['task_id'],receipt['source_revision'])
        if meta['checkpoint_id'] != ident:
            raise cp.Fault('Incoming identity mismatch')
        tree=Path(d)/'tree';tree.mkdir();unpack(copied,tree)
        # Use only this fresh extraction of the exact verified archive. The
        # mutable convenient quarantine extraction is never promotion input.
        yield tree


def inspect_tree(root, ident, tree):
    binding, store = cp.config(root)
    meta=cp.read(tree/'bundle.json');state,_=cp.latest(tree)
    report={'checkpoint_id':ident,'task_id':binding['task_id'],'project_id':binding['project_id'],
            'current_fingerprint':cp.repo(root)['fingerprint'],'next_action':state['task']['next_action'],
            'review_required':True,'permissions_restored':False,'source_revision':meta['source_revision'],
            'unresolved_jobs':[j['id'] for j in state['task']['jobs'] if j['status'] not in ('completed','failed','cancelled')]}
    if (store/'latest.json').exists():report['destination_checkpoint']=cp.latest(store)[0]['id']
    return state,report


def inspect_incoming(root, ident):
    with verified_incoming(root,ident) as tree:
        return inspect_tree(root,ident,tree)


def adopt(root, ident, review_path):
    """Explicit reviewed data promotion only. Resume/ownership remain separate."""
    with verified_incoming(root,ident) as tree:
        return _adopt_verified(root,ident,review_path,tree)


def _adopt_verified(root,ident,review_path,incoming):
    import router
    state, report = inspect_tree(root, ident, incoming)
    review = cp.read(review_path)
    binding, store = cp.config(root)
    if cp.git_text(root, 'rev-parse', 'HEAD') != report['source_revision']:
        raise cp.Fault('Review exact source revision first')
    if (review.get('checkpoint_id') != ident or review.get('current_fingerprint') != report['current_fingerprint']
        or not 0 <= cp.age(review.get('observed_at')) <= 300
        or review.get('authorization', {}).get('confirmed') is not True
        or not review['authorization'].get('scope') or not review['authorization'].get('source')
        or not review.get('destination_reconciliation')):
        raise cp.Fault('Fresh adoption review and explicit destination reconciliation required')
    # Source ownership must already be released. No receipt is ever imported.
    with router.exclusive_store(root), cp.lock(store):
        owner = cp.Ownership(root, binding, store)
        if owner.value(owner.tip()).get('owner'):
            raise cp.Fault('Task still owned; never steal or expire the existing claim')
        transaction_path=store/('adoption-transaction-'+ident+'.json')
        transaction=cp.read(transaction_path) if transaction_path.exists() else None
        imported=cp.read(incoming/'router-state.json') if (incoming/'router-state.json').exists() else None
        if imported and imported.get('active'):imported['active']['status']='uncertain'
        same_transaction = transaction and transaction.get('manifest_sha256') == cp.sha(cp.content(incoming/'bundle.json'))
        if router.state(root).get('active') is not None and not (same_transaction and router.state(root)==imported):
            raise cp.Fault('Reconcile local uncertain worker before adoption')
        if cp.repo(root)['fingerprint'] != report['current_fingerprint']:
            raise cp.Fault('Destination changed during review')
        if (store/'latest.json').exists():
            old = cp.read(store/'latest.json'); cp.check_generation(store, old)
        else:
            old = None
        if same_transaction and transaction.get('phase')=='promoted':
            if old and old['id']==ident:
                return {'adopted':ident,'deduplicated':True,'worker_started':False,'owner_acquired':False}
            raise cp.Fault('Already adopted checkpoint; destination has newer work, preserve both')
        if old and old['id'] != report.get('destination_checkpoint'):
            raise cp.Fault('Destination checkpoint changed during adoption review')
        if transaction and not same_transaction:
            raise cp.Fault('Conflicting adoption transaction; preserve and reconcile')
        previous_local=transaction['previous'] if same_transaction else old
        cp.atomic(transaction_path,cp.encoded({'phase':'installing','checkpoint_id':ident,
            'manifest_sha256':cp.sha(cp.content(incoming/'bundle.json')),'previous':previous_local,'at':cp.now()}))
        pointer = cp.read(incoming/'latest.json')
        pointers = [pointer] + ([pointer['previous']] if pointer.get('previous') else [])
        for ptr in pointers:
            cp.check_generation(incoming, ptr)
            dest = store/'snapshots'/ptr['id']
            dest.parent.mkdir(exist_ok=True)
            if dest.exists():
                cp.check_generation(store, ptr)
            else:
                with tempfile.TemporaryDirectory(prefix='.incoming-',dir=dest.parent) as d:
                    staged = Path(d)/ptr['id'];shutil.copytree(incoming/'snapshots'/ptr['id'], staged)
                    os.rename(staged, dest)
        if (incoming/'router-state.json').exists():
            incoming_journal=cp.read(incoming/'router-state.json')
            local=router.state(root)
            existing={h['id']:h for h in local['history']}
            imported={h['id']:h for h in incoming_journal['history']}
            if any(k not in imported or imported[k]!=v for k,v in existing.items()):
                raise cp.Fault('Divergent/newer destination router history; preserve both and reconcile explicitly')
            if incoming_journal.get('active'):
                incoming_journal['active']['status']='uncertain'
            for result in (incoming/'router-runs').glob('*/result.txt') if (incoming/'router-runs').exists() else []:
                dest=store/'router-runs'/result.parent.name/'result.txt'
                if dest.exists() and cp.content(dest)!=cp.content(result):
                    raise cp.Fault('Conflicting worker result; preserve both')
            # Only observational execution facts move; authorization stays local.
        else:
            incoming_journal=None
        if previous_local and previous_local['id'] != ident:
            pointer['previous'] = previous_local
        # Preserve stops and retire prior device-local execution approvals before
        # pointer promotion. A crash cannot expose a promoted low snapshot unstopped.
        if (incoming/'stop.json').exists():
            transferred = cp.read(incoming/'stop.json')
            stop_path = store/'automatic-stop.json'
            marker = cp.read(stop_path) if stop_path.exists() else {}
            marker.update(schema_version=1,project_id=binding['project_id'],task_id=binding['task_id'],
                checkpoint_status=transferred.get('checkpoint_status','pending'),checkpoint_id=ident,automatic_resume=False,requested_at=cp.now(),
                low_kinds=sorted(set(marker.get('low_kinds',[]))|set(transferred['low_kinds'])),
                resource_accounts=sorted(set(marker.get('resource_accounts',[]))|set(transferred.get('resource_accounts',[]))))
            cp.atomic(stop_path,cp.encoded(marker))
        retired=store/'adoption-retired'/ident;retired.mkdir(parents=True,exist_ok=True)
        for name in ('plan-approval.json','router-authorization.json','router-schedule.json','resume.json','input.json'):
            path=store/name
            if path.exists():
                dest=retired/name
                already_installed = name=='input.json' and (incoming/'semantic-input.json').exists() and cp.content(path)==cp.content(incoming/'semantic-input.json')
                if dest.exists() and cp.content(dest)!=cp.content(path) and not already_installed:
                    raise cp.Fault('Conflicting retired local state; preserve and review')
                if not dest.exists():cp.atomic(dest,cp.content(path))
                path.unlink()
        if incoming_journal is not None:
            for result in (incoming/'router-runs').glob('*/result.txt') if (incoming/'router-runs').exists() else []:
                dest=store/'router-runs'/result.parent.name/'result.txt'
                cp.atomic(dest,cp.content(result))
            cp.atomic(store/'router.json',cp.encoded(incoming_journal))
        if (incoming/'semantic-input.json').exists():
            cp.atomic(store/'input.json',cp.content(incoming/'semantic-input.json'))
        cp.atomic(store/('adoption-'+ident+'.json'),cp.encoded({'review':cp.redact(review),'at':cp.now(),'previous':old}))
        cp.atomic(store/'latest.json',cp.encoded(pointer))
        cp.atomic(transaction_path,cp.encoded({'phase':'promoted','checkpoint_id':ident,
            'manifest_sha256':cp.sha(cp.content(incoming/'bundle.json')),'previous':previous_local,'at':cp.now()}))
    return {'adopted':ident,'worker_started':False,'owner_acquired':False,'next':'checkpoint.py inspect, fresh reviewed resume; never restore over the working tree'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    sub=p.add_subparsers(dest='command',required=True)
    pack=sub.add_parser('package');pack.add_argument('--output',type=Path,required=True)
    pub=sub.add_parser('publish');pub.add_argument('--repository',required=True)
    get=sub.add_parser('receive');get.add_argument('--repository',required=True);get.add_argument('--tag',required=True);get.add_argument('--asset',required=True);get.add_argument('--revision',required=True)
    latest=sub.add_parser('receive-latest');latest.add_argument('--repository',required=True)
    inspect=sub.add_parser('inspect-incoming');inspect.add_argument('--id',required=True)
    adopt_parser=sub.add_parser('adopt');adopt_parser.add_argument('--id',required=True);adopt_parser.add_argument('--review',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve()
    if a.command=='receive-latest':result=receive_latest(root,a.repository)
    elif a.command=='inspect-incoming':result=inspect_incoming(root,a.id)[1]
    elif a.command=='adopt':result=adopt(root,a.id,a.review)
    else:result=package(root,a.output) if a.command=='package' else publish(root,a.repository) if a.command=='publish' else receive(root,a.repository,a.tag,a.asset,a.revision)
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (cp.Fault,OSError,ValueError,KeyError,zipfile.BadZipFile,subprocess.SubprocessError) as exc:
        print(json.dumps({'ok':False,'error':str(exc),'retry':'Repeat same immutable transfer after inspecting outcome; no execution permission restored'}),file=sys.stderr);sys.exit(2)
