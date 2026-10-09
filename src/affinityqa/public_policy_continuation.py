"""Explicit stopped-store continuity. No startup migration or admission refunds."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from .evidence import fingerprint
from .individual_jobs import ACTIVE,need,read
from .individual_capture import LOCK_MARKER,execution_lease,safe_directory_path,sha

MARKER='public-policy-continuation.json'
PREFIX='public-policy-continuation-v2-'
NAME=re.compile(r'^public-policy-continuation-v2-(\d{6})\.json$')
SHA=re.compile(r'^[a-f0-9]{64}$')
MAX_RECORDS=64
MAX_BYTES=4096
SOURCE_FIELDS={'controller_sha256','manager_sha256','policy_sha256'}
BASE_FIELDS={'schema_version','policy','origin','template_sha256','execution_pacing',*SOURCE_FIELDS}


def _pair(value):
    result={k:value[k] for k in ('controller_sha256','manager_sha256')}
    need(all(isinstance(v,str) and SHA.fullmatch(v) for v in result.values()),'Invalid source pair.')
    return result


def _base(previous,current=None):
    need(isinstance(previous,dict) and set(previous)==BASE_FIELDS
         and type(previous['schema_version']) is int and previous['schema_version']==1,'Public policy fields differ.')
    _pair(previous)
    need(isinstance(previous['template_sha256'],str) and SHA.fullmatch(previous['template_sha256'])
         and previous['policy_sha256']==fingerprint({k:v for k,v in previous.items() if k!='policy_sha256'}),
         'Previous public policy seal differs.')
    from .public_cases import public_policy
    from .public_demo import canonical_origin
    from .remote_pacing import pacing_policy
    policy=previous['policy'];cadence=previous['execution_pacing']
    keys=('maximum_sessions','maximum_plans','maximum_executions','plans_per_session','executions_per_session','session_hours')
    need(isinstance(policy,dict) and all(k in policy for k in keys) and isinstance(cadence,dict),'Policy or pacing differs.')
    need(fingerprint(policy)==fingerprint(public_policy(**{k:policy[k] for k in keys}))
         and previous['origin']==canonical_origin(previous['origin']) and cadence.get('configured') is True
         and fingerprint(cadence)==fingerprint(pacing_policy(cadence.get('minimum_interval_seconds'))),'Policy or pacing contract differs.')
    if current is not None:
        need(isinstance(current,dict) and set(current)==BASE_FIELDS,'Public policy fields differ.')
        _pair(current)
        need({k:v for k,v in previous.items() if k not in SOURCE_FIELDS}==
             {k:v for k,v in current.items() if k not in SOURCE_FIELDS},'Continuation cannot change template, origin, pacing or budgets.')
        need(current['policy_sha256']==fingerprint({k:v for k,v in current.items() if k!='policy_sha256'}),'Current policy seal differs.')


def validate_continuation(previous,current,marker):
    """Legacy v1 stays an immutable supported anchor."""
    _base(previous,current)
    expected={'schema_version':1,'previous_binding_sha256':fingerprint(previous),
              'current_controller_sha256':current['controller_sha256'],
              'current_manager_sha256':current['manager_sha256'],'admissions_reset':False}
    need(fingerprint(marker)==fingerprint(expected),'Reviewed legacy source continuation differs.')
    return expected


def _record(path):
    safe_directory_path(path)
    need(path.is_file() and 0<path.stat().st_size<=MAX_BYTES,'Unsafe or oversized continuation record.')
    return read(path)


def validate_chain(root,previous,current=None):
    """Pure closed-chain validation: installed pair must be the exact final tail."""
    root=safe_directory_path(Path(root));_base(previous,current)
    need(read(root/'public-policy.json')==previous,'Base policy changed.')
    files={'public-policy.json':sha(root/'public-policy.json')};tail=_pair(previous)
    if (root/MARKER).exists() or (root/MARKER).is_symlink():
        anchor=_record(root/MARKER);need(isinstance(anchor,dict),'Legacy record differs.')
        legacy={**previous,'controller_sha256':anchor.get('current_controller_sha256'),
                'manager_sha256':anchor.get('current_manager_sha256')}
        legacy['policy_sha256']=fingerprint({k:v for k,v in legacy.items() if k!='policy_sha256'})
        validate_continuation(previous,legacy,anchor)
        tail=_pair(legacy);files[MARKER]=sha(root/MARKER)
    previous_sha=files.get(MARKER,files['public-policy.json'])
    paths=sorted(p for p in root.iterdir() if p.name.startswith(PREFIX))
    need(len(paths)<=MAX_RECORDS,'Continuation chain exceeds its bound.')
    for index,path in enumerate(paths,1):
        match=NAME.fullmatch(path.name)
        need(match is not None and int(match[1])==index,'Continuation names or sequence differ.')
        value=_record(path)
        need(isinstance(value,dict) and set(value)=={'schema_version','sequence','base_binding_sha256',
             'previous_record_sha256','from_source','to_source','admissions_reset'},'Continuation fields differ.')
        need(type(value['schema_version']) is int and value['schema_version']==2
             and type(value['sequence']) is int and value['sequence']==index and value['admissions_reset'] is False
             and value['base_binding_sha256']==fingerprint(previous) and value['previous_record_sha256']==previous_sha
             and isinstance(value['from_source'],dict) and set(value['from_source'])==set(tail)
             and isinstance(value['to_source'],dict) and set(value['to_source'])==set(tail)
             and value['from_source']==tail,'Continuation links or admission contract differ.')
        new_tail=_pair(value['to_source']);need(new_tail!=tail,'Continuation must change installed sources.')
        tail=new_tail;previous_sha=sha(path);files[path.name]=previous_sha
    need(current is None or tail==_pair(current),'Public source changed; explicitly review the next stopped-store continuation.')
    return {'files_sha256':files,'tail_source':tail,'tail_record_sha256':previous_sha,'sequence':len(paths)}


def _stopped_root(root):
    root=safe_directory_path(Path(root));need(root.is_dir(),'Existing stopped storage required.')
    root=root.resolve(strict=True)
    for directory in ('jobs','sessions','ownership'):
        path=safe_directory_path(root/directory);need(path.is_dir(),'Recognized storage directories required.')
    lock=safe_directory_path(root/'jobs'/'.affinityqa-individual.lock')
    need(lock.is_file() and stat.S_ISREG(lock.stat().st_mode),'Existing retained lock required.')
    chain=validate_chain(root,read(root/'public-policy.json'))
    need({p.name for p in root.iterdir()}==set(chain['files_sha256'])|{'jobs','sessions','ownership'},'Unknown storage entry; inspect it.')
    return root


def _inventory(root):
    files={};sizes={}
    for path in sorted(root.rglob('*')):
        safe_directory_path(path);need(path.is_file() or path.is_dir(),'Unknown storage object.')
        if path.is_file():
            name=path.relative_to(root).as_posix();sizes[name]=path.stat().st_size
            # A held lease validates these bytes; Windows locks their first byte.
            files[name]=hashlib.sha256(LOCK_MARKER).hexdigest() if name=='jobs/.affinityqa-individual.lock' else sha(path)
    for job in (root/'jobs').iterdir():
        if job.is_dir():
            events=sorted(job.glob('event-*.json'))
            need(not events or read(events[-1]).get('status') not in ACTIVE,'Interrupted active work needs inspection before continuation.')
    return files,sizes


def _propose_held(root):
    previous=read(root/'public-policy.json');chain=validate_chain(root,previous)
    source=Path(__file__).resolve().parent
    target={'controller_sha256':sha(source/'public_cases.py'),'manager_sha256':sha(source/'individual_jobs.py')}
    need(chain['tail_source']!=target,'Installed sources already match the continuation tail.')
    need(chain['sequence']<MAX_RECORDS,'Continuation chain reached its bound.')
    index=chain['sequence']+1
    marker={'schema_version':2,'sequence':index,'base_binding_sha256':fingerprint(previous),
            'previous_record_sha256':chain['tail_record_sha256'],'from_source':chain['tail_source'],
            'to_source':target,'admissions_reset':False}
    files,sizes=_inventory(root)
    result={'schema_version':2,'storage':str(root),'marker_name':f'{PREFIX}{index:06d}.json',
            'marker':marker,'previous_chain':chain,'preserved_files_sha256':files,'preserved_files_bytes':sizes,
            'scope':'One append-only source record; policies, cases, expiry and admissions unchanged.'}
    result['proposal_sha256']=fingerprint(result)
    return result


def propose(root):
    root=_stopped_root(root)
    with execution_lease(root/'jobs'):return _propose_held(root)


def _flush_directory(path):
    if os.name=='nt':return  # Windows flushes published-file metadata below.
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try:os.fsync(fd)
    finally:os.close(fd)


def _publish(root,name,value):
    """No-replace publication of a sealed NEW inode. Staging remains retained."""
    stage=safe_directory_path(root.parent/('.affinityqa-continuation-'+uuid4().hex));stage.mkdir(mode=0o700)
    payload=stage/'record.json'
    data=(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf8')
    need(len(data)<=MAX_BYTES,'Continuation payload exceeds its bound.')
    fd=os.open(payload,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'wb') as stream:
        need(stream.write(data)==len(data),'Staging write incomplete.')
        stream.flush();os.fsync(stream.fileno())
    need(payload.read_bytes()==data and payload.stat().st_dev==root.stat().st_dev,'Staging differs or filesystem not shared.')
    _flush_directory(stage);_flush_directory(root.parent)
    destination=safe_directory_path(root/name)
    os.link(payload,destination)  # atomic no-replace; never hardlink an original
    # NTFS caches file metadata too. Flush with a write-capable handle, without
    # writing any bytes after publication. POSIX also flushes the directory.
    fd=os.open(destination,os.O_RDWR|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0))
    try:os.fsync(fd)
    finally:os.close(fd)
    _flush_directory(root)
    need(destination.read_bytes()==data,'Published continuation differs; inspect it.')
    return {'staging':str(stage),'published_record_sha256':sha(destination),
            'durability_method':'sealed-file-fsync+exclusive-link+published-file-fsync'+
                ('+directory-fsync' if os.name!='nt' else '+Windows-file-metadata-flush'),'power_loss_tested':False}


def execute(root,expected_proposal_sha256):
    root=_stopped_root(root)
    with execution_lease(root/'jobs'):
        proposal=_propose_held(root)
        need(proposal['proposal_sha256']==expected_proposal_sha256,'Reviewed inventory or source changed.')
        commit=_publish(root,proposal['marker_name'],proposal['marker'])
        files,sizes=_inventory(root)
        expected={**proposal['preserved_files_sha256'],proposal['marker_name']:commit['published_record_sha256']}
        need(files==expected and all(sizes[name]==size for name,size in proposal['preserved_files_bytes'].items()),
             'Original records changed; stop and inspect.')
        current={**read(root/'public-policy.json'),**proposal['marker']['to_source']}
        current['policy_sha256']=fingerprint({k:v for k,v in current.items() if k!='policy_sha256'})
        validate_chain(root,read(root/'public-policy.json'),current)
        return {**proposal,'commit':commit}
