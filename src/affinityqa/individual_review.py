"""Read-only hash-bound identity-clean development and historical qualification."""
import hashlib,json
from pathlib import Path
from .errors import SchemaError
from .store import RUN_ID

RECEIPT='INDIVIDUAL-CONTEXT-20261004.json'

def individual_snapshot(root):
    path=root/'evidence'/RECEIPT
    if path.is_symlink():raise SchemaError('Unsafe individual-context receipt.')
    data=json.loads(path.read_text(encoding='utf8'));documents={}
    def verify(run,name,h):
        if not RUN_ID.fullmatch(run) or name!=Path(name).name:raise SchemaError('Unsafe individual-context artifact path.')
        directory=root/'runs'/run;p=directory/name
        if directory.is_symlink() or p.is_symlink() or p.stat().st_size>5_000_000:raise SchemaError('Unsafe individual-context artifact.')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h:raise SchemaError('Individual-context evidence changed.')
        if name.endswith('.json'):documents[(run,name)]=json.loads(raw)
    for run,files in data['run_artifact_sha256'].items():
        for name,h in files.items():verify(run,name,h)
    for relative,h in data['source_artifact_sha256'].items():
        parts=relative.split('/')
        if len(parts)!=2:raise SchemaError('Unsafe context source path.')
        verify(*parts,h)
    runs=data['studies'];report=documents[(runs['training'],'individual-training-report.json')]
    coverage=documents[(runs['coverage'],'context-coverage-report.json')];plan=documents[(runs['coverage'],'context-coverage-plan.json')]
    old=documents[(runs['stopped'],'individual-context-report.json')];audit=documents[(runs['coverage'],'identity-context-audit.json')]
    available=sum(v['status']=='AVAILABLE' for v in coverage['projections'].values())
    best=max(c['passing_cases'] for c in report['candidates']);example=next(c for c in report['candidates'] if c['passing_cases']==best)
    recorded=documents[(runs['training'],f'candidate-{example["candidate"]:02d}-graph-development.json')]
    unavailable=[{'entity_id':k,'name':plan['unique_entities'][k]} for k,v in coverage['projections'].items() if v['status']=='UNAVAILABLE']
    if (report['training_gate']!='REJECTED' or report['release_approved'] is not False or data['release_approved'] is not False
        or old['status']!='INCOMPLETE' or old['real_qloo_requests']!=7 or coverage['status']!='COMPLETE_COVERAGE_AUDIT'
        or coverage['new_qloo_requests']!=61 or coverage['total_qloo_requests']!=68 or data['new_qloo_requests']!=68
        or data['new_model_calls']!=0 or data['new_reference_calls']!=0 or data['new_validation_pairs']!=0
        or len(report['candidates'])!=28 or data['candidate_count']!=28 or best!=12 or data['best_passes']!=best
        or data['denominator']!=14 or len(recorded['cases'])!=14 or available!=67 or data['available_projections']!=available
        or len(coverage['projections'])!=68 or data['total_projections']!=68 or data['unavailable']!=unavailable
        or data['profile_coverage']!=coverage['profile_coverage'] or data['example_candidate']!=example
        or data['identity_findings']!=[r for r in audit if r['own_profile_overlap']] or data['excluded_entries']!=len(audit)
        or data['historical_integrity_status']!='QUALIFIED_ALIAS_OVERLAP' or not data['integrity_notice']
        or data['amendment']!=plan['amendment'] or data['context_snapshot']!=plan['context_snapshot']):
        raise SchemaError('Individual-context summary differs from recorded evidence.')
    if len(data['cases'])!=14:raise SchemaError('Full fourteen-case denominator required.')
    for actual,display in zip(recorded['cases'],data['cases'],strict=True):
        if any(display[k]!=v for k,v in actual.items()) or display['passing']!=all(actual['checks'].values()):raise SchemaError('Individual-context case changed.')
    if sum(c['passing'] for c in data['cases'])!=12:raise SchemaError('Individual-context pass count changed.')
    return {k:v for k,v in data.items() if k not in ('run_artifact_sha256','source_artifact_sha256')}

def historical_qualification(root):
    data=individual_snapshot(root)
    return {'status':data['historical_integrity_status'],'notice':data['integrity_notice'],'finding':data['identity_findings'][0],
            'latest_clean_development':{'passing_cases':data['best_passes'],'denominator':data['denominator'],'release_approved':False}}
