"""Verified read-only display of the original-profile text experiment."""
import hashlib,json
from pathlib import Path
from .errors import SchemaError
from .store import RUN_ID
from .extension_review import extension_snapshot

RECEIPT='METADATA-TEXT-20261004T085651Z-3b742376.json'


def metadata_snapshot(root):
    def readraw(path):
        if path.is_symlink() or path.stat().st_size>5_000_000:raise SchemaError('Unsafe metadata review artifact.')
        return path.read_bytes()
    receipt=json.loads(readraw(root/'evidence'/RECEIPT));run=receipt['run_id']
    if not RUN_ID.fullmatch(run) or (root/'runs'/run).is_symlink():raise SchemaError('Unsafe metadata run.')
    parent=root/'evidence/CONTEXT-EXTENSIONS-20261004.json'
    if hashlib.sha256(readraw(parent)).hexdigest()!=receipt['parent_receipt_sha256']:raise SchemaError('Metadata parent evidence changed.')
    extension_snapshot(root);documents={}
    for name,h in receipt['artifact_sha256'].items():
        if name!=Path(name).name:raise SchemaError('Unsafe metadata artifact name.')
        raw=readraw(root/'runs'/run/name)
        if hashlib.sha256(raw).hexdigest()!=h:raise SchemaError('Metadata evidence changed.')
        if name.endswith('.json'):documents[name]=json.loads(raw)
    def document(name):
        if name not in documents:raise SchemaError('Missing metadata evidence.')
        return documents[name]
    report=document('metadata-text-report.json');plan=document('metadata-text-plan.json');decisions=document('metadata-text-decisions.json')
    for name,h in plan['source_artifact_sha256'].items():
        parts=Path(name).parts
        if len(parts)!=3 or parts[0]!='runs' or not RUN_ID.fullmatch(parts[1]) or '..' in parts:raise SchemaError('Unsafe metadata source path.')
        if hashlib.sha256(readraw(root/name)).hexdigest()!=h:raise SchemaError('Metadata source changed.')
    for key in ('status','model_calls','new_qloo_requests','new_reference_calls','new_validation_pairs','denominator','release_approved','error','training_gate'):
        if receipt[key]!=report[key]:raise SchemaError('Metadata summary differs from recorded report.')
    if any(report[k]!=0 for k in ('new_qloo_requests','new_reference_calls','new_validation_pairs')) or report['release_approved'] is not False:raise SchemaError('Unsupported metadata release claim.')
    if report['status']=='COMPLETE_GRAPH_CAPTURE':
        cases=document('graph-development.json')['cases'];shown=receipt['cases'];expected=set(plan['study']['development_pair_ids'])
        if len(cases)!=14 or len(shown)!=14 or {c['pair_id'] for c in cases}!=expected or len(decisions['cases'])!=14:raise SchemaError('Complete metadata denominator required.')
        for a,b in zip(cases,shown,strict=True):
            if any(b.get(k)!=v for k,v in a.items()):raise SchemaError('Metadata case result changed.')
        if sum(all(c['checks'].values()) for c in cases)!=report['passes'] or receipt['passes']!=report['passes']:raise SchemaError('Metadata pass count differs.')
        outputs=[n for n in documents if n.startswith('metadata-output-')]
        if len(outputs)!=252 or report['model_calls']!=252 or receipt['verified_outputs']!=252:raise SchemaError('Incomplete metadata execution evidence.')
    elif report['training_gate']!='NOT_EVALUATED' or receipt['cases'] or receipt['passes'] is not None:raise SchemaError('Incomplete metadata capture cannot be scored.')
    amendment=plan['technical_amendment'];original=root/'runs'/amendment['original_run']
    if not RUN_ID.fullmatch(amendment['original_run']) or original.is_symlink():raise SchemaError('Unsafe original metadata run.')
    for name,key in (('metadata-text-plan.json','original_plan_sha256'),('metadata-text-report.json','original_report_sha256')):
        if hashlib.sha256(readraw(original/name)).hexdigest()!=amendment[key]:raise SchemaError('Original stopped metadata evidence changed.')
    if receipt['cumulative_model_calls_including_stopped_attempt']!=report['model_calls']+1:raise SchemaError('Stopped metadata attempt omitted.')
    return {k:v for k,v in receipt.items() if k not in ('artifact_sha256','parent_receipt_sha256')}
