"""Evaluator-only repair contracts and a fail-closed local promotion decision.

References never enter the repair adapter. A sample PASS is not production
certification. Rejecting a patch retains the whole baseline, not selected cases.
"""
from __future__ import annotations

import copy
import hashlib
import json
from itertools import product
from pathlib import Path
from statistics import median

from .errors import SchemaError
from .evidence import fingerprint
from .film_protocol import calibrate_reference
from .metrics import ndcg_at_k, max_repeat_jitter
from .regression_pack import validate_decisions
from .store import RUN_ID

VARIANTS = ('baseline', 'neutral_graph', 'swapped_graph')
CHECKS = ('reference_informative', 'no_profile_loss', 'benefit_beyond_baseline',
          'benefit_beyond_neutral', 'beats_swapped_context', 'stable')
RECEIPT = 'MULTIVIEW-VALIDATION-V1-20261004.json'


def validate_contract(contract):
    if (not isinstance(contract, dict) or contract.get('schema_version') != 1
            or contract.get('kind') != 'affinityqa-repair-contract'
            or contract.get('contract_sha256') != fingerprint({k:v for k,v in contract.items() if k != 'contract_sha256'})
            or contract.get('top_k') != 5 or contract.get('repeats') != 3
            or contract.get('criteria') != {'max_profile_drop':0, 'minimum_mean_gain':.02,
                                           'minimum_mean_gain_over_swapped':.01}):
        raise SchemaError('Invalid, changed or unsupported frozen repair contract.')
    cases = contract.get('cases')
    catalog = contract.get('catalog')
    if not isinstance(cases, list) or len(cases) != 6 or not isinstance(catalog, list):
        raise SchemaError('The full six-case denominator is required.')
    ids = [e.get('entity_id') for e in catalog if isinstance(e, dict)]
    if len(ids) != 20 or any(not isinstance(i,str) for i in ids) or len(set(ids)) != 20:
        raise SchemaError('The independently selected twenty-movie catalog is required.')
    names=[]
    for case in cases:
        if (not isinstance(case,dict) or set(case) != {'id','artists','reference','controls'}
                or not isinstance(case['id'],str) or not case['id']
                or not isinstance(case['artists'],dict) or set(case['artists']) != {'A','B'}
                or any(not isinstance(n,str) or not n for n in case['artists'].values())
                or not isinstance(case['controls'],dict) or set(case['controls']) != set(VARIANTS)):
            raise SchemaError('Malformed repair case or incomplete controls.')
        names.append(case['id'])
        validate_decisions(case['reference'], ids)
        for variant in VARIANTS:
            validate_decisions(case['controls'][variant], ids)
    if len(set(names)) != 6:
        raise SchemaError('Repeated repair cases cannot pass.')
    return contract


def evaluate_repair(contract, decisions):
    """Recompute every control from rankings; never trust an imported PASS flag."""
    validate_contract(contract)
    if not isinstance(decisions,dict) or set(decisions) != {c['id'] for c in contract['cases']}:
        raise SchemaError('Supply all six independently produced cases; no filtering or substitution.')
    ids=[e['entity_id'] for e in contract['catalog']]
    results=[]
    for case in contract['cases']:
        actual=decisions[case['id']]
        validate_decisions(actual,ids)
        comparisons={}
        means={}
        for variant in VARIANTS:
            profiles={}
            for p in ('A','B'):
                deltas=[ndcg_at_k(a,r,5)-ndcg_at_k(b,r,5)
                        for a,b,r in product(actual[p],case['controls'][variant][p],case['reference'][p])]
                profiles[p]={'min':min(deltas),'median':median(deltas),'max':max(deltas)}
            comparisons[variant]=profiles
            means[variant]=(profiles['A']['min']+profiles['B']['min'])/2
        informative=calibrate_reference(case['reference'],ids,5,0)['informative']
        checks={'reference_informative':informative,
                'no_profile_loss':all(comparisons[v][p]['min'] >= -1e-12
                                      for v in ('baseline','neutral_graph') for p in ('A','B')),
                'benefit_beyond_baseline':means['baseline'] >= .02,
                'benefit_beyond_neutral':means['neutral_graph'] >= .02,
                'beats_swapped_context':means['swapped_graph'] >= .01,
                'stable':all(max_repeat_jitter(actual[p],5) <= 1e-12 for p in ('A','B'))}
        results.append({'id':case['id'],'checks':checks,'comparisons':comparisons,
                        'minimum_pair_mean_delta':means,
                        'sample_gate':'PASS' if all(checks.values()) else 'FAIL',
                        'failed_checks':[k for k in CHECKS if not checks[k]]})
    passed=sum(c['sample_gate']=='PASS' for c in results)
    gate='PASS' if passed==6 else 'FAIL'
    return {'schema_version':1,'contract_sha256':contract['contract_sha256'],
            'decisions_sha256':fingerprint(decisions),'sample_gate':gate,'cases':results,
            'passing_cases':passed,'denominator':6,
            'promotion':'ELIGIBLE_FOR_SAMPLE_REVIEW' if gate=='PASS' else 'BLOCKED',
            'retained_version':'candidate' if gate=='PASS' else 'baseline',
            'selected_decisions':copy.deepcopy(decisions if gate=='PASS' else
                {c['id']:c['controls']['baseline'] for c in contract['cases']}),
            'ci_gate':'NOT_VALIDATED','release_approved':False,
            'new_qloo_requests':0,'new_model_calls':0,
            'notice':'Exposed sample replay. Imported decisions do not prove live execution. '
                     'No deployment occurs; paired comparisons are not independent trials.'}


def load_recorded_validation(root: Path):
    """Hash-bound private source, then portable contract and sealed decisions."""
    receipt_path=root/'evidence'/RECEIPT
    if receipt_path.is_symlink():raise SchemaError('Unsafe repair receipt.')
    receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
    run_id=receipt.get('run_id','')
    if not RUN_ID.fullmatch(run_id):raise SchemaError('Invalid repair validation run.')
    directory=root/'runs'/run_id
    if directory.is_symlink() or directory.resolve().parent != (root/'runs').resolve():
        raise SchemaError('Unsafe validation directory.')
    artifacts={}
    for name,sha in receipt['run_artifact_sha256'].items():
        if Path(name).name != name:raise SchemaError('Unsafe validation artifact name.')
        path=directory/name
        if path.is_symlink() or path.stat().st_size > 4_000_000:raise SchemaError('Unsafe validation artifact.')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=sha:
            raise SchemaError('Repair evidence changed; no verified result is available.')
        if name.endswith('.json'):artifacts[name]=json.loads(data)
    plan=artifacts['reserved-validation-plan.json']
    sealed=artifacts['sealed-repair-decisions.json']
    original=artifacts['reserved-validation-report.json']
    model=artifacts['sealed-model-decisions.json']
    if (sealed['status']!='COMPLETE_GRAPH_CAPTURE'
            or sealed['plan_sha256']!=plan['plan_sha256']
            or original['status']!='COMPLETE_RESERVED_VALIDATION'
            or len(plan['reserved_pairs'])!=6
            or [c['pair_id'] for c in sealed['cases']] != [p['id'] for p in plan['reserved_pairs']]
            or set(model)!={p['id'] for p in plan['reserved_pairs']}):
        raise SchemaError('Incomplete or mismatched sealed validation evidence.')
    cases=[];decisions={}
    for pair,case in zip(plan['reserved_pairs'],sealed['cases'],strict=True):
        key=pair['id'];ranks=case['rankings']
        if ranks['baseline']!=model[key]:raise SchemaError('Sealed original model decisions changed.')
        cases.append({'id':key,'artists':{p:pair[p] for p in ('A','B')},
                      'reference':artifacts['reference-'+key+'.json']['rankings'],
                      'controls':{v:ranks[v] for v in VARIANTS}})
        decisions[key]=ranks['qloo_graph']
    study=plan['study']
    contract={'schema_version':1,'kind':'affinityqa-repair-contract','top_k':5,'repeats':3,
              'source_run_id':run_id,'policy_sha256':plan['policy']['policy_sha256'],
              'criteria':{k:study[k] for k in ('max_profile_drop','minimum_mean_gain','minimum_mean_gain_over_swapped')},
              'catalog':plan['catalog'],'cases':cases,
              'scope':'All six previously untouched validation cases, now exposed; evaluator-only references.'}
    contract['contract_sha256']=fingerprint(contract)
    report=evaluate_repair(contract,decisions)
    if (report['sample_gate']!=original['sample_gate'] or report['passing_cases']!=original['passing_cases']
            or any(c['checks']!=o['checks'] or c['comparisons']!=o['comparisons']
                   or c['minimum_pair_mean_delta']!=o['minimum_pair_mean_delta']
                   for c,o in zip(report['cases'],original['cases'],strict=True))):
        raise SchemaError('Recomputed controls disagree with the sealed validation report.')
    return contract,decisions,report,receipt


def validation_snapshot(root: Path):
    contract,decisions,report,receipt=load_recorded_validation(root)
    movies={e['entity_id']:{'id':e['entity_id'],'title':e['name'],'year':e['release_year']} for e in contract['catalog']}
    cases=[]
    for source,result in zip(contract['cases'],report['cases'],strict=True):
        views=[]
        for repeat in range(3):
            profiles={}
            for p in ('A','B'):
                variants={v:source['controls'][v][p][repeat] for v in VARIANTS}
                variants['repaired']=decisions[source['id']][p][repeat]
                profiles[p]={'artist':source['artists'][p],
                    'rankings':{v:[movies[i] for i in ranks[:5]] for v,ranks in variants.items()},
                    'agreement':{v:median(ndcg_at_k(ranks,r,5) for r in source['reference'][p])
                                 for v,ranks in variants.items()}}
            views.append({'repeat':repeat+1,'profiles':profiles})
        cases.append({**{k:v for k,v in result.items() if k!='comparisons'},
                      'artists':source['artists'],'comparisons':result['comparisons'],'views':views})
    return {'run_id':receipt['run_id'],'verified_utc':receipt['verified_utc'],
            'sample_gate':report['sample_gate'],'promotion':report['promotion'],
            'passing_cases':report['passing_cases'],'denominator':6,'cases':cases,
            'model_calls':receipt['model_calls'],'reference_calls':receipt['real_qloo_requests'],
            'policy_sha256':contract['policy_sha256'],'contract_sha256':contract['contract_sha256'],
            'criteria':contract['criteria'],'retained_version':report['retained_version'],
            'release_approved':False,'ci_gate':'NOT_VALIDATED','new_live_calls':0,
            'mechanism':'Fixed global fusion of the model ranking, disjoint movies and related artists.',
            'scope':'Frozen policy, six new profile pairs tested before adaptation; all are now exposed.'}
