"""Read-only review of supervised development; no independent-validation claim."""
import hashlib,json
from pathlib import Path
from .errors import SchemaError
from .store import RUN_ID
from .individual_review import individual_snapshot

RECEIPT='REPAIR-LEARNING-20261004.json'

def learning_snapshot(root):
    path=root/'evidence'/RECEIPT
    if path.is_symlink():raise SchemaError('Unsafe learning receipt.')
    data=json.loads(path.read_text(encoding='utf8'));parent=root/'evidence/INDIVIDUAL-CONTEXT-20261004.json'
    if parent.is_symlink() or hashlib.sha256(parent.read_bytes()).hexdigest()!=data['parent_receipt_sha256']:raise SchemaError('Learning parent evidence changed.')
    previous=individual_snapshot(root);labels={c['pair_id']:c['artists'] for c in previous['cases']};documents={}
    for run,files in data['run_artifact_sha256'].items():
        if not RUN_ID.fullmatch(run):raise SchemaError('Unsafe learning run.')
        directory=root/'runs'/run
        if directory.is_symlink():raise SchemaError('Unsafe learning directory.')
        for name,h in files.items():
            p=directory/name
            if name!=Path(name).name or p.is_symlink() or p.stat().st_size>5_000_000:raise SchemaError('Unsafe learning artifact.')
            raw=p.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=h:raise SchemaError('Learning evidence changed.')
            if name.endswith('.json'):documents[(run,name)]=json.loads(raw)
    runs=data['studies'];report=documents[(runs['learned'],'learned-repair-report.json')];risk=documents[(runs['disagreement'],'disagreement-report.json')]
    example=max(report['candidates'],key=lambda r:(min(r['full_fit']['passes'],r['leave_one_pair_out']['passes']),-r['candidate']))
    if (report['training_gate']!='REJECTED' or risk['training_gate']!='REJECTED' or report['release_approved'] is not False or data['release_approved'] is not False
        or data['status']!='REJECTED_DEVELOPMENT' or len(report['candidates'])!=3 or data['supervised_candidates']!=3
        or report['fits']!=45 or data['fits_verified']!=45 or len(risk['candidates'])!=9 or data['disagreement_candidates']!=9
        or max(r['passing_cases'] for r in risk['candidates'])!=data['disagreement_best'] or data['disagreement_best']!=12
        or data['full_fit_passes']!=13 or data['resampled_passes']!=13 or data['denominator']!=14 or data['example_candidate']!=example
        or any(data[k]!=0 for k in ('new_qloo_requests','new_model_calls','new_reference_calls','new_validation_pairs'))):
        raise SchemaError('Learning summary differs from recorded evidence.')
    for suffix in ('full','held'):
        actual=documents[(runs['learned'],f'candidate-{example["candidate"]:02d}-{suffix}-graph-development.json')]['cases'];display=data['cases'][suffix]
        if len(actual)!=14 or len(display)!=14:raise SchemaError('Full learning denominator required.')
        for a,d in zip(actual,display,strict=True):
            if any(d[k]!=v for k,v in a.items()) or d['artists']!=labels[a['pair_id']] or d['passing']!=all(a['checks'].values()):raise SchemaError('Learning case differs from recorded result.')
        if sum(c['passing'] for c in display)!=13:raise SchemaError('Learning case count differs.')
    for row in report['candidates']:
        fits=documents[(runs['learned'],f'candidate-{row["candidate"]:02d}-fits.json')]
        if len(fits['folds'])!=14 or {f['held_pair_id'] for f in fits['folds']}!=set(labels):raise SchemaError('Incomplete internal resampling.')
        for fold in fits['folds']:
            if set(fold['training_pair_ids'])!=set(labels)-{fold['held_pair_id']} or len(fold['training_pair_ids'])!=13:raise SchemaError('Held pair entered its own fit.')
    return {k:v for k,v in data.items() if k not in ('run_artifact_sha256','parent_receipt_sha256')}
