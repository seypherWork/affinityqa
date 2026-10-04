"""Read-only, hash-verified review of the newer value-sensitive validation."""
import hashlib,json
from pathlib import Path
from statistics import median
from .errors import SchemaError
from .evidence import fingerprint
from .metrics import ndcg_at_k
from .repair_gate import evaluate_repair,VARIANTS
from .store import RUN_ID

RECEIPT='VALUE-VALIDATION-V1-20261004.json'

def load_recorded_value(root):
    path=root/'evidence'/RECEIPT
    if path.is_symlink():raise SchemaError('Unsafe value validation receipt.')
    receipt=json.loads(path.read_text(encoding='utf-8'));run=receipt['run_id']
    if not RUN_ID.fullmatch(run):raise SchemaError('Invalid value validation run.')
    directory=root/'runs'/run
    if directory.is_symlink() or directory.resolve().parent!=(root/'runs').resolve():raise SchemaError('Unsafe value validation directory.')
    artifacts={}
    for name,sha in receipt['run_artifact_sha256'].items():
        if name!=Path(name).name:raise SchemaError('Unsafe value artifact name.')
        p=directory/name
        if p.is_symlink() or p.stat().st_size>4_000_000:raise SchemaError('Unsafe value artifact.')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise SchemaError('Value validation evidence changed.')
        if name.endswith('.json'):artifacts[name]=json.loads(raw)
    plan=artifacts['value-validation-plan.json'];sealed=artifacts['sealed-repair-decisions.json']
    original=artifacts['value-validation-report.json'];model=artifacts['sealed-model-decisions.json']
    for source,files in receipt['source_run_artifact_sha256'].items():
        if not RUN_ID.fullmatch(source):raise SchemaError('Unsafe source run.')
        source_dir=root/'runs'/source
        if source_dir.is_symlink():raise SchemaError('Unsafe source directory.')
        for name,h in files.items():
            p=source_dir/name
            if name!=Path(name).name or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:
                raise SchemaError('Value source evidence changed.')
    if (receipt['model_calls']!=original['model_calls'] or receipt['real_qloo_requests']!=original['real_qloo_requests']
            or plan['accounting']!={'imported_model_calls':36,'prior_qloo_requests':54,'identity_qloo_requests':3,'new_qloo_cap':44,'total_qloo_cap':101}
            or original['real_qloo_requests']!=101 or original['new_model_calls']!=0):
        raise SchemaError('Value execution accounting differs.')
    pairs=plan['reserved_pairs']
    if (plan['plan_sha256']!=fingerprint({k:v for k,v in plan.items() if k!='plan_sha256'})
            or sealed['plan_sha256']!=plan['plan_sha256'] or len(pairs)!=6
            or original['status']!='COMPLETE_RESERVED_VALIDATION' or sealed['status']!='COMPLETE_GRAPH_CAPTURE'
            or [c['pair_id'] for c in sealed['cases']]!=[p['id'] for p in pairs] or set(model)!={p['id'] for p in pairs}):
        raise SchemaError('Incomplete or mismatched value evidence.')
    cases=[];decisions={}
    for pair,case in zip(pairs,sealed['cases'],strict=True):
        key=pair['id'];ranks=case['rankings']
        if ranks['baseline']!=model[key]:raise SchemaError('Value baseline differs from sealed model decisions.')
        cases.append({'id':key,'artists':{p:pair[p] for p in ('A','B')},'reference':artifacts['reference-'+key+'.json']['rankings'],
                      'controls':{v:ranks[v] for v in VARIANTS}})
        decisions[key]=ranks['qloo_graph']
    contract={'schema_version':1,'kind':'affinityqa-repair-contract','top_k':5,'repeats':3,'source_run_id':run,
              'policy_sha256':plan['policy']['policy_sha256'],'catalog':plan['catalog'],'cases':cases,
              'criteria':{k:plan['study'][k] for k in ('max_profile_drop','minimum_mean_gain','minimum_mean_gain_over_swapped')},
              'identity_amendment':plan['identity_amendment'],'recovery_of':plan['recovery_of'],
              'scope':'Six predeclared v3 names, with a documented pre-reference identity-type amendment for Selena Gomez. Now exposed; references are evaluator-only.'}
    contract['contract_sha256']=fingerprint(contract);report=evaluate_repair(contract,decisions)
    if (report['sample_gate']!=original['sample_gate'] or report['passing_cases']!=original['passing_cases']
            or any(c['checks']!=o['checks'] or c['comparisons']!=o['comparisons'] or c['minimum_pair_mean_delta']!=o['minimum_pair_mean_delta']
                   for c,o in zip(report['cases'],original['cases'],strict=True))):raise SchemaError('Value evaluation differs from recorded report.')
    return contract,decisions,report,receipt

def value_snapshot(root):
    contract,decisions,report,receipt=load_recorded_value(root)
    movies={e['entity_id']:{'id':e['entity_id'],'title':e['name'],'year':e['release_year']} for e in contract['catalog']}
    cases=[]
    for source,result in zip(contract['cases'],report['cases'],strict=True):
        views=[]
        for repeat in range(3):
            profiles={}
            for p in ('A','B'):
                variants={v:source['controls'][v][p][repeat] for v in VARIANTS};variants['repaired']=decisions[source['id']][p][repeat]
                profiles[p]={'artist':source['artists'][p],
                    'rankings':{v:[movies[i] for i in ranks[:5]] for v,ranks in variants.items()},
                    'agreement':{v:median(ndcg_at_k(ranks,r,5) for r in source['reference'][p]) for v,ranks in variants.items()}}
            views.append({'repeat':repeat+1,'profiles':profiles})
        cases.append({**result,'artists':source['artists'],'views':views})
    return {'run_id':receipt['run_id'],'verified_utc':receipt['verified_utc'],'cases':cases,'denominator':6,
            **{k:report[k] for k in ('sample_gate','promotion','passing_cases','retained_version','release_approved','ci_gate')},
            'model_calls':receipt['model_calls'],'reference_calls':receipt['real_qloo_requests'],
            'policy_sha256':contract['policy_sha256'],'contract_sha256':contract['contract_sha256'],'criteria':contract['criteria'],
            'development_passes':8,'development_denominator':8,'development_candidates':30,'new_live_calls':0,
            'identity_amendment':contract['identity_amendment'],'recovery_of':contract['recovery_of'],
            'mechanism':'Value-sensitive disjoint movie affinity fused with the original local model ranking.'}
