"""Read-only, minimal browser projection of verified real experiment records."""
from pathlib import Path
import hashlib
import json
from statistics import median

from .errors import SchemaError
from .metrics import ndcg_at_k
from .store import RUN_ID


def review_snapshot(root: Path):
    receipt_path=root/'evidence/AUDIT-BUILD-PHASE3-20261003.json'
    if receipt_path.is_symlink():raise SchemaError('Unsafe evidence receipt.')
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    run_id=receipt.get('run_id','')
    if not RUN_ID.fullmatch(run_id):raise SchemaError('Invalid verified run identifier.')
    directory=root/'runs'/run_id
    if directory.is_symlink() or directory.resolve().parent!=(root/'runs').resolve():raise SchemaError('Unsafe review evidence location.')
    def read(name):
        path=directory/name
        if path.is_symlink() or path.stat().st_size>2_000_000:raise SchemaError('Unsafe review artifact.')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=receipt.get('run_artifact_sha256',{}).get(name):
            raise SchemaError('Evidence changed; the review cannot display a verified result.')
        return json.loads(data.decode('utf-8'))
    report=read('reserved-comparison.json');local=read('local-decisions.json')
    suite=read('suite.json');catalog=read('catalog.json');policy=read('model-policy.json')
    if report.get('status')!='COMPLETE_RESERVED_COMPARISON' or len(report.get('cases',[]))!=6:
        raise SchemaError('The review requires the complete six-case comparison.')
    movies={e['entity_id']:{'id':e['entity_id'],'title':e['name'],'year':e['release_year']} for e in catalog}
    cases=[]
    for result in report['cases']:
        pair=next(p for p in suite['pairs'] if p['id']==result['pair_id'])
        decisions=next(r for r in local['reserved'] if r['pair_id']==result['pair_id'])
        ref=read('reference-'+result['pair_id']+'.json')
        views=[]
        for repeat in range(3):
            profiles={}
            for label in ('A','B'):
                profiles[label]={'artist':pair[label][0]['name'],
                    'before':[movies[i] for i in decisions['candidate'][label][repeat][:5]],
                    'reference':[movies[i] for i in ref['rankings'][label][0][:5]],
                    'after':[movies[i] for i in decisions['repaired'][label][repeat][:5]],
                    'before_agreement':median(ndcg_at_k(decisions['candidate'][label][repeat],r,5) for r in ref['rankings'][label]),
                    'after_agreement':median(ndcg_at_k(decisions['repaired'][label][repeat],r,5) for r in ref['rankings'][label])}
            views.append({'repeat':repeat+1,'order':'AB' if repeat%2==0 else 'BA','profiles':profiles})
        cases.append({'id':result['pair_id'],'artists':{p:pair[p][0]['name'] for p in ('A','B')},
                      'outcome':result['outcome'],'delta':result['paired_agreement_delta'],
                      'reference_noise':ref['calibration_policy']['reference_noise_max'],
                      'structural_gate':decisions['structural_gate'],'views':views,
                      'reference_hash':ref['reference_sha256']})
    snapshot={'project':'AffinityQA','mode':'recorded-evidence','run_id':run_id,
        'verified_utc':receipt['verified_utc'],'cases':cases,'counts':report['outcome_counts'],
        'case_count':6,'reference_calls':49,'model_calls':98,'ci_gate':'NOT_VALIDATED',
        'policy_hash':policy['policy_sha256'],'model':'qwen38:cyber-32k','new_live_calls':0,
        'fault':'Declared injected cache defect: profile omitted from cache key',
        'repair':'Cache key includes the profile; old entries are cleared',
        'limitations':['Observed six-case comparison, not population certification',
                       'Qloo agreement is not human preference truth','No validated production release threshold']}
    context_receipt_path = root / 'evidence/CONTEXT-DEVELOPMENT-20261003.json'
    if context_receipt_path.exists():
        if context_receipt_path.is_symlink():
            raise SchemaError('Unsafe context evidence receipt.')
        context_receipt = json.loads(context_receipt_path.read_text(encoding='utf-8'))
        candidates = []
        for candidate in context_receipt['candidates']:
            candidate_id = candidate['run_id']
            if not RUN_ID.fullmatch(candidate_id):
                raise SchemaError('Invalid context run identifier.')
            context_run = root / 'runs' / candidate_id
            context_path = context_run / 'context-ablation.json'
            if context_run.is_symlink() or context_path.is_symlink() or context_path.stat().st_size > 2_000_000:
                raise SchemaError('Unsafe context evidence artifact.')
            content = context_path.read_bytes()
            if hashlib.sha256(content).hexdigest() != context_receipt['run_artifact_sha256'][candidate_id]['context-ablation.json']:
                raise SchemaError('Context evidence changed; review is unavailable.')
            observed = json.loads(content)
            candidates.append({'index': candidate['index'], 'run_id': candidate_id,
                'candidate_gate': observed['candidate_gate'],
                'cases': [{'pair_id': case['pair_id'], 'checks': case['checks']} for case in observed['cases']]})
        snapshot['context_study'] = {'candidates': candidates,
            'model_calls': context_receipt['model_calls'], 'reference_calls': context_receipt['real_qloo_requests'],
            'reserved_inputs_executed': context_receipt['reserved_inputs_executed']}
    semantic_receipt_path=root/'evidence/SEMANTIC-DEVELOPMENT-20261003.json'
    if semantic_receipt_path.exists():
        if semantic_receipt_path.is_symlink():raise SchemaError('Unsafe semantic receipt.')
        receipt=json.loads(semantic_receipt_path.read_text(encoding='utf-8'))
        run=receipt['run_id']
        if not RUN_ID.fullmatch(run):raise SchemaError('Invalid semantic run identifier.')
        directory=root/'runs'/run;path=directory/'semantic-development.json'
        if directory.is_symlink() or path.is_symlink() or path.stat().st_size>2_000_000:raise SchemaError('Unsafe semantic evidence.')
        content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=receipt['run_artifact_sha256']['semantic-development.json']:
            raise SchemaError('Semantic evidence changed; review is unavailable.')
        observed=json.loads(content)
        snapshot['semantic_study']={'run_id':run,'candidate_gate':observed['candidate_gate'],
            'embedding_calls':observed['embedding_calls'],'new_qloo_requests':0,'reserved_inputs_executed':0,
            'cases':[{'pair_id':p['pair_id'],'checks':p['checks'],'delta':p['minimum_pair_mean_delta']} for p in observed['cases']]}
    if (root/'evidence/MULTIVIEW-VALIDATION-V1-20261004.json').exists():
        from .repair_gate import validation_snapshot
        repair=validation_snapshot(root)
        snapshot['repair_study']={k:repair[k] for k in ('run_id','sample_gate','passing_cases','denominator',
                                  'model_calls','reference_calls','policy_sha256','promotion')}
    if (root/'evidence/VALUE-VALIDATION-V1-20261004.json').exists():
        from .value_review import value_snapshot
        value=value_snapshot(root)
        snapshot['value_study']={k:value[k] for k in ('run_id','sample_gate','passing_cases','denominator',
            'model_calls','reference_calls','policy_sha256','promotion','development_passes','development_denominator')}
    if (root/'evidence/ORDERING-DEVELOPMENT-20261004.json').exists():
        from .ordering_review import ordering_snapshot
        snapshot['ordering_development']=ordering_snapshot(root)
    if (root/'evidence/INDIVIDUAL-CONTEXT-20261004.json').exists():
        from .individual_review import individual_snapshot
        clean=individual_snapshot(root)
        snapshot['individual_development']=clean
        qualification={k:clean[k] for k in ('historical_integrity_status','integrity_notice','identity_findings')}
        if 'ordering_development' in snapshot:snapshot['ordering_development']['integrity_qualification']=qualification
        if 'repair_study' in snapshot:snapshot['repair_study']['integrity_qualification']=qualification
    if (root/'evidence/REPAIR-LEARNING-20261004.json').exists():
        from .learning_review import learning_snapshot
        snapshot['repair_learning']=learning_snapshot(root)
    if (root/'evidence/CONTEXT-EXTENSIONS-20261004.json').exists():
        from .extension_review import extension_snapshot
        snapshot['context_extensions']=extension_snapshot(root)
    from .metadata_review import RECEIPT as metadata_receipt
    if (root/'evidence'/metadata_receipt).exists():
        from .metadata_review import metadata_snapshot
        snapshot['metadata_development']=metadata_snapshot(root)
    return snapshot
