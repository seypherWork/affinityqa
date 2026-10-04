"""Portable, offline cultural regression checks over a frozen local reference.

Reference data is evaluator-only. An exported pack stays local; a caller must
provide independently executed complete rankings, never an oracle-copy repair.
"""
from __future__ import annotations

import json
import math
from itertools import product
from pathlib import Path
from statistics import median

from .errors import SchemaError
from .evidence import fingerprint, utc_now
from .metrics import ndcg_at_k
from .review import review_snapshot


def validate_pack(pack):
    if (not isinstance(pack, dict) or pack.get('schema_version') != 1
            or pack.get('kind') != 'affinityqa-regression-pack'
            or pack.get('pack_sha256') != fingerprint({k:v for k,v in pack.items() if k != 'pack_sha256'})
            or pack.get('top_k') != 5 or pack.get('repeats') != 3):
        raise SchemaError('Invalid or changed regression pack.')
    tolerance = pack.get('max_profile_drop')
    if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or not 0 <= tolerance <= .1:
        raise SchemaError('Invalid predeclared regression tolerance.')
    cases = pack.get('cases')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 6 or len({c['id'] for c in cases}) != len(cases):
        raise SchemaError('Invalid regression denominator.')
    for case in cases:
        ids = [e['entity_id'] for e in case['catalog']]
        if len(ids) != 20 or len(set(ids)) != 20 or set(case['artists']) != {'A','B'}:
            raise SchemaError('A regression case needs the fixed twenty-movie catalog and two profiles.')
        for version in ('reference','baseline'):
            validate_decisions(case[version], ids)
    return pack


def validate_decisions(decisions, ids):
    if not isinstance(decisions, dict) or set(decisions) != {'A','B'}:
        raise SchemaError('Decisions need both profiles; a missing profile cannot pass.')
    for label in ('A','B'):
        ranks = decisions[label]
        if not isinstance(ranks, list) or len(ranks) != 3:
            raise SchemaError('Exactly three complete decisions per profile are required.')
        for ranking in ranks:
            if (not isinstance(ranking, list) or any(not isinstance(i,str) for i in ranking)
                    or len(ranking) != len(ids) or set(ranking) != set(ids)):
                raise SchemaError('Decision omitted, duplicated or invented a movie; no tail is supplied.')


def export_pack(root: Path, *, baseline='candidate', case_ids=None, max_profile_drop=0):
    snapshot = review_snapshot(root)  # Original artifact hashes must still match.
    if baseline not in ('candidate','repaired'):
        raise SchemaError('Choose a recorded baseline version.')
    run = root/'runs'/snapshot['run_id']
    def read(name):
        return json.loads((run/name).read_text(encoding='utf-8'))
    # review_snapshot has checked all of these decision/reference artifacts.
    local = read('local-decisions.json')
    catalog = read('catalog.json')
    selected = case_ids or [c['id'] for c in snapshot['cases']]
    if len(set(selected)) != len(selected) or not set(selected) <= {c['id'] for c in snapshot['cases']}:
        raise SchemaError('Unknown or repeated regression case.')
    cases=[]
    for view in snapshot['cases']:
        if view['id'] not in selected:
            continue
        decision = next(c for c in local['reserved'] if c['pair_id']==view['id'])
        ref = read('reference-'+view['id']+'.json')
        cases.append({'id':view['id'],'artists':view['artists'],'catalog':catalog,
                      'reference':ref['rankings'],'reference_informative':ref['calibration_policy']['informative'],
                      'baseline':decision[baseline],'reference_sha256':ref['reference_sha256']})
    pack={'schema_version':1,'kind':'affinityqa-regression-pack','created_utc':utc_now(),
          'source_run_id':snapshot['run_id'],'baseline_version':baseline,'top_k':5,'repeats':3,
          'max_profile_drop':max_profile_drop,'cases':cases,'ci_gate':'NOT_VALIDATED',
          'scope':'Previously exposed regression sample; reference agreement, not human satisfaction or an unseen test.',
          'privacy':'Evaluator-only local artifact; do not send reference rankings to the agent.'}
    pack['pack_sha256']=fingerprint(pack)
    return validate_pack(pack)


def evaluate_pack(pack, decisions):
    validate_pack(pack)
    if not isinstance(decisions, dict) or set(decisions) != {c['id'] for c in pack['cases']}:
        raise SchemaError('All regression cases must be supplied exactly once; no denominator filtering.')
    results=[]
    for case in pack['cases']:
        actual=decisions[case['id']]
        validate_decisions(actual,[e['entity_id'] for e in case['catalog']])
        profiles={}
        for label in ('A','B'):
            deltas=[ndcg_at_k(c,r,5)-ndcg_at_k(b,r,5)
                    for c,b,r in product(actual[label],case['baseline'][label],case['reference'][label])]
            profiles[label]={'artist':case['artists'][label],'min_delta':min(deltas),'median_delta':median(deltas),
                             'max_delta':max(deltas),'combinations':len(deltas),
                             'no_regression':min(deltas)>=-pack['max_profile_drop']-1e-12}
        gate=('INCONCLUSIVE' if not case['reference_informative'] else
              'PASS' if all(p['no_regression'] for p in profiles.values()) else 'FAIL')
        results.append({'id':case['id'],'profiles':profiles,'regression_gate':gate})
    gate='FAIL' if any(c['regression_gate']=='FAIL' for c in results) else (
        'INCONCLUSIVE' if any(c['regression_gate']=='INCONCLUSIVE' for c in results) else 'PASS')
    return {'schema_version':1,'pack_sha256':pack['pack_sha256'],'regression_gate':gate,
            'cases':results,'denominator':len(results),'new_qloo_requests':0,'new_model_calls':0,
            'ci_gate':'NOT_VALIDATED','notice':'Sample regression check only; paired combinations are not independent trials.'}
