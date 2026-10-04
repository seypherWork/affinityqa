"""Read-only checked projection of two rejected context-extension experiments."""
import hashlib,json
from pathlib import Path
from .errors import SchemaError
from .store import RUN_ID
from .learning_review import learning_snapshot

RECEIPT='CONTEXT-EXTENSIONS-20261004.json'


def extension_snapshot(root):
    def raw(path):
        if path.is_symlink() or path.stat().st_size>5_000_000:raise SchemaError('Unsafe extension artifact.')
        return path.read_bytes()
    data=json.loads(raw(root/'evidence'/RECEIPT));parent=root/'evidence/REPAIR-LEARNING-20261004.json'
    if hashlib.sha256(raw(parent)).hexdigest()!=data['parent_receipt_sha256']:raise SchemaError('Extension parent changed.')
    previous=learning_snapshot(root);labels={c['pair_id']:c['artists'] for c in previous['cases']['full']};documents={};runs=data['studies']
    if set(runs)!={'capture','broad','interaction'} or len(set(runs.values()))!=3 or set(data['run_artifact_sha256'])!=set(runs.values()):raise SchemaError('Incomplete extension studies.')
    for run,files in data['run_artifact_sha256'].items():
        if not RUN_ID.fullmatch(run) or (root/'runs'/run).is_symlink():raise SchemaError('Unsafe extension run.')
        for name,h in files.items():
            if name!=Path(name).name:raise SchemaError('Unsafe extension path.')
            content=raw(root/'runs'/run/name)
            if hashlib.sha256(content).hexdigest()!=h:raise SchemaError('Extension evidence changed.')
            if name.endswith('.json'):documents[(run,name)]=json.loads(content)
    def document(kind,name):
        try:return documents[(runs[kind],name)]
        except KeyError as exc:raise SchemaError('Missing extension evidence.') from exc
    capture=document('capture','broad-movie-report.json')
    if (data['status']!='REJECTED_DEVELOPMENT' or data['denominator']!=14 or data['fits_verified']!=90 or data['score_reports_verified']!=13
        or data['release_approved'] is not False or data['new_qloo_requests']!=57 or any(data[k]!=0 for k in ('new_model_calls','new_reference_calls','new_validation_pairs'))
        or capture['status']!='COMPLETE' or capture['real_qloo_requests']!=57
        or len([n for n in data['run_artifact_sha256'][runs['capture']] if n.startswith('http-') and n.endswith('.json')])!=57):raise SchemaError('Extension summary differs from evidence.')
    experiments=[]
    def case_report(kind,prefix,summary):
        report=document(kind,prefix+'-graph-development.json');cases=report['cases']
        if len(cases)!=14 or {c['pair_id'] for c in cases}!=set(labels):raise SchemaError('Complete extension denominator required.')
        failures={c['pair_id']:[k for k,v in c['checks'].items() if not v] for c in cases if not all(c['checks'].values())}
        if summary!={'passes':14-len(failures),'failures':failures}:raise SchemaError('Extension case counts differ.')
        return {'passes':14-len(failures),'cases':[{**c,'artists':labels[c['pair_id']],'passing':all(c['checks'].values())} for c in cases]}
    for kind,stem,title in (('broad','broad-training','20-film context'),('interaction','interaction-repair','Numeric interactions')):
        report=document(kind,stem+'-report.json');plan=document(kind,stem+'-plan.json')
        if report['training_gate']!='REJECTED' or report['release_approved'] is not False or report['fits']!=45 or len(report['candidates'])!=3 or plan['regularization']!=[.001,.01,.1]:raise SchemaError('Extension candidate budget changed.')
        if kind=='broad':
            experiments.append({'id':'broad-fixed','label':'20-film context · previous coefficients','kind':'fixed','regularization':None,'full':case_report(kind,'fixed',report['fixed_previous_coefficients']),'held':None})
        for row in report['candidates']:
            n=row['candidate'];prefix=f'candidate-{n:02d}'
            if n not in (1,2,3) or row['regularization']!=plan['regularization'][n-1]:raise SchemaError('Unexpected extension candidate.')
            fits=document(kind,prefix+'-fits.json')
            if len(fits['folds'])!=14 or {f['held_pair_id'] for f in fits['folds']}!=set(labels):raise SchemaError('Incomplete extension folds.')
            for fold in fits['folds']:
                if len(fold['training_pair_ids'])!=13 or set(fold['training_pair_ids'])!=set(labels)-{fold['held_pair_id']}:raise SchemaError('Excluded pair entered extension fit.')
            experiments.append({'id':f'{kind}-{n}','label':f'{title} · regularization {row["regularization"]}','kind':kind,'regularization':row['regularization'],
                'full':case_report(kind,prefix+'-full',row['full_fit']),'held':case_report(kind,prefix+'-held',row['leave_one_pair_out'])})
    if len({e['id'] for e in experiments})!=7:raise SchemaError('Missing extension candidate.')
    return {**{k:data[k] for k in ('verified_utc','status','denominator','fits_verified','score_reports_verified','new_qloo_requests','new_model_calls','new_reference_calls','new_validation_pairs','release_approved','boundary','diagnostic')},'experiments':experiments,
            'previous_best':{'full':previous['full_fit_passes'],'held':previous['resampled_passes'],'denominator':previous['denominator']}}
