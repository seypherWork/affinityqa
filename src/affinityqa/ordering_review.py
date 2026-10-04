"""Hash-bound development result. It cannot supersede independent validation."""
import hashlib,json
from pathlib import Path
from .errors import SchemaError
from .store import RUN_ID

RECEIPT='ORDERING-DEVELOPMENT-20261004.json'

def ordering_snapshot(root):
    path=root/'evidence'/RECEIPT
    if path.is_symlink():raise SchemaError('Unsafe ordering receipt.')
    data=json.loads(path.read_text(encoding='utf8'));documents={}
    for run,files in data['run_artifact_sha256'].items():
        if not RUN_ID.fullmatch(run):raise SchemaError('Unsafe ordering run identifier.')
        directory=root/'runs'/run
        if directory.is_symlink():raise SchemaError('Unsafe ordering directory.')
        for name,h in files.items():
            p=directory/name
            if name!=Path(name).name or p.is_symlink() or p.stat().st_size>5_000_000:raise SchemaError('Unsafe ordering artifact.')
            raw=p.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=h:raise SchemaError('Ordering evidence changed.')
            if name.endswith('.json'):documents[(run,name)]=json.loads(raw)
    studies=data['studies'];best=data['example_candidate']
    source=documents[(best['run_id'],f'candidate-{best["candidate"]:02d}-graph-development.json')]
    counts=[len(documents[(studies[k],name)]['candidates']) for k,name in [('head','head-order-report.json'),('multi','multiview-value-report.json'),('two','two-stage-report.json')]]
    intervals=documents[(studies['interval'],'multiview-interval-report.json')]
    expansion=documents[(studies['expansion'],'artist-expansion-report.json')]
    if (counts!=[18,36,12] or len(intervals['intervals'])!=429 or intervals['passing_intervals'] or expansion['real_qloo_requests']!=48
        or data['discrete_candidates']!=66 or data['calibration_intervals']!=429 or data['new_qloo_requests']!=48
        or data['new_model_calls']!=0 or data['new_validation_pairs']!=0 or len(source['cases'])!=14
        or data['denominator']!=14 or data['best_passes']!=13 or data['release_approved'] is not False):
        raise SchemaError('Ordering summary differs from recorded studies.')
    for observed,display in zip(source['cases'],data['cases'],strict=True):
        if any(display[k]!=v for k,v in observed.items()) or display['passing']!=all(observed['checks'].values()):raise SchemaError('Ordering case differs from recorded result.')
    if sum(c['passing'] for c in data['cases'])!=13:raise SchemaError('Ordering pass count differs.')
    return {k:data[k] for k in ('verified_utc','status','best_passes','denominator','discrete_candidates','calibration_intervals',
        'new_qloo_requests','new_model_calls','new_validation_pairs','release_approved','example_candidate','cases','boundary')}
