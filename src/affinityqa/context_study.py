"""Development-only ablation; Qloo input examples are disjoint from test movies."""
from __future__ import annotations

import copy
from itertools import product
from statistics import median
import time

from .agents import AgentError, validate_response
from .errors import AffinityQAError, SchemaError
from .evidence import fingerprint, utc_now
from .film_protocol import calibrate_reference
from .local_suite import noise_and_effect, requests_for_pair
from .metrics import ndcg_at_k
from .models import context_issues, normalized_name, parse_entities, resolve_seed
from .reserved_reference import prepare_plan

VARIANTS = ['original', 'instructions_only', 'qloo_context', 'swapped_context']


def validate_study(study, suite):
    if (study.get('schema_version') != 1 or study.get('study_id') != 'disjoint-context-v1'
            or study.get('development_pair_ids') != ['mutation-01','mutation-03']
            or study.get('context_movies') != 5 or study.get('reference_repeats') != 3
            or study.get('agent_repeats') != 3 or study.get('request_cap') != 21
            or study.get('inference_cap') != 48 or study.get('variants') != VARIANTS
            or study.get('practical_tolerance') != 0 or not study.get('context_excludes_entire_evaluation_catalog')
            or not study.get('context_order_and_affinity_withheld')):
        raise SchemaError('Unsupported predeclared context-study contract.')
    known = {normalized_name(seed['name']) for p in suite['pairs'] for seed in p['A'] + p['B']}
    reserved = study.get('reserved_v2', [])
    names = [normalized_name(p[label]) for p in reserved for label in ('A','B')]
    if len(reserved) != 6 or len(set(names)) != 12 or any(name in known for name in names):
        raise SchemaError('New reserved profiles must be unique and unseen in the earlier suite.')
    pairs = [p for p in suite['pairs'] if p['id'] in study['development_pair_ids']]
    if len(pairs) != 2 or any(p['split'] != 'development' or len(p['A']) != 1 or len(p['B']) != 1 for p in pairs):
        raise SchemaError('Context candidate selection can use only the two development pairs.')
    return pairs


def capture_context_study(client, local_values, study, *, sleeper=time.sleep, progress=None):
    local, policy, suite, manifest, catalog = local_values
    prepare_plan(*local_values)
    pairs = validate_study(study, suite)
    if client.max_requests != 21 or client.max_attempts != 1 or client.requests:
        raise SchemaError('Development context capture needs a fresh 21-request/no-retry client.')
    ledger = client.ledger
    ids = [e['entity_id'] for e in catalog]
    names = {normalized_name(e['name']) for e in catalog}
    plan = {'study':study,'study_sha256':fingerprint(study),'suite_sha256':fingerprint(suite),
            'catalog_sha256':fingerprint(catalog),'local_report_sha256':fingerprint(local),
            'created_utc':utc_now(),'request_cap':21,'provider_quota':'UNKNOWN',
            'reserved_inputs_executed':0,'retry_attempts':1,'minimum_interval_seconds':1}
    plan['plan_sha256'] = fingerprint(plan)
    ledger.write('capture-plan.json',plan)
    ledger.write('study.json',study)
    ledger.write('suite.json',suite)
    ledger.record('context_plan_frozen',{'plan_sha256':plan['plan_sha256'],'requests':0})
    bundle = {'schema_version':1,'source':ledger.source,'plan_sha256':plan['plan_sha256'],
              'study_sha256':fingerprint(study),'catalog':catalog,'pairs':[]}
    report = {'source':ledger.source,'status':'INCOMPLETE','error':None,'reserved_inputs_executed':0,'ci_gate':'NOT_VALIDATED'}
    last = None
    def get(path,params):
        nonlocal last
        if last is not None:sleeper(max(0,1-(time.monotonic()-last)))
        last=time.monotonic()
        return client.get(path,params,cache=False)
    try:
        entities=parse_entities(get('/entities',{'entity_ids':','.join(ids)}),insights=False,synthetic=client.synthetic)
        if len(entities)!=20 or {e.entity_id for e in entities}!=set(ids):
            raise SchemaError('Context study catalog coverage changed.')
        for entity in entities:
            expected=next(row for row in catalog if row['entity_id']==entity.entity_id)
            if entity.name!=expected['name'] or entity.metadata.get('release_year')!=expected['release_year']:
                raise SchemaError('Context study catalog identity changed.')
        for pair in pairs:
            if progress:progress(pair['id'],client.requests)
            personas={}
            contexts={}
            for label in ('A','B'):
                seed=pair[label][0]
                entity=resolve_seed(seed,parse_entities(get('/search',{'query':seed['query'],'types':seed['search_type'],'take':5}),
                    insights=False,synthetic=client.synthetic),synthetic=client.synthetic)
                personas[label]=entity.entity_id
                rows=parse_entities(get('/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':5,
                    'filter.exclude.entities':','.join(ids),'signal.interests.entities':entity.entity_id}),
                    insights=True,synthetic=client.synthetic)
                if (len(rows)!=5 or any(e.entity_id in ids or normalized_name(e.name) in names for e in rows)
                        or context_issues(rows,{'filter_type':'urn:entity:movie','filters':{}},set(ids))):
                    raise SchemaError('Context must contain five movies outside the evaluation catalog; no overlap is filtered away silently.')
                if any(type(e.metadata.get('release_year')) is not int for e in rows):
                    raise SchemaError('Qloo context lacks movie release years.')
                contexts[label]=sorted([{'entity_id':e.entity_id,'name':e.name,'release_year':e.metadata['release_year']} for e in rows],key=lambda e:normalized_name(e['name']))
                ledger.record('disjoint_context_captured',{'pair_id':pair['id'],'profile':label,'context_sha256':fingerprint(contexts[label]),'excluded_catalog_count':20})
            if personas['A']==personas['B']:raise SchemaError('Artist mutation resolved to an unchanged identity.')
            ranks={'A':[],'B':[]}
            for repeat in range(3):
                for label in (('A','B') if repeat%2==0 else ('B','A')):
                    rows=parse_entities(get('/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,
                        'filter.results.entities':','.join(ids),'signal.interests.entities':personas[label]}),insights=True,synthetic=client.synthetic)
                    if len(rows)!=20 or {e.entity_id for e in rows}!=set(ids) or context_issues(rows,{'filter_type':'urn:entity:movie','filters':{}},set(personas.values())):
                        raise SchemaError('Context study reference is incomplete or violates the movie contract.')
                    ranks[label].append([e.entity_id for e in rows])
            row={'pair_id':pair['id'],'split':'development','personas':personas,'contexts':contexts,'rankings':ranks,
                 'reference_policy':calibrate_reference(ranks,ids,5,0)}
            ledger.write('development-'+pair['id']+'.json',row)
            bundle['pairs'].append(row)
        bundle['bundle_sha256']=fingerprint(bundle)
        ledger.write('context-bundle.json',bundle)
        report['status']='COMPLETE_SYNTHETIC' if client.synthetic else 'COMPLETE_CONTEXT_CAPTURE'
        report['bundle_sha256']=bundle['bundle_sha256']
    except AffinityQAError as exc:
        report['error']=str(exc)
        ledger.record('stopped',{'reason':str(exc)})
    report.update(real_qloo_requests=ledger.live_requests,transport_attempts=client.requests,completed_pairs=len(bundle['pairs']))
    ledger.write('capture-report.json',report)
    return report


def summarize_deltas(candidate, baseline, references, k):
    values=[ndcg_at_k(c,r,k)-ndcg_at_k(b,r,k) for c,b,r in product(candidate,baseline,references)]
    return {'min':min(values),'median':median(values),'max':max(values),'paired_combinations':len(values)}


def evaluate_context_study(original, contextual, ledger, bundle, suite, study, *, progress=None, candidate_index=1):
    pairs=validate_study(study,suite)
    if candidate_index not in (1,2) or (candidate_index==2 and contextual.manifest.get('baseline_contract')!='agent-own-first-ranking-no-oracle'):
        raise SchemaError('Only the two predeclared candidate attempts are supported.')
    if (bundle.get('bundle_sha256')!=fingerprint({k:v for k,v in bundle.items() if k!='bundle_sha256'})
            or bundle.get('study_sha256')!=fingerprint(study)
            or [p['pair_id'] for p in bundle.get('pairs',[])]!=[p['id'] for p in pairs]
            or bundle.get('source')!='qloo-live-context-development' or ledger.source!='qloo-context+local-llm'):
        raise SchemaError('Context evaluation requires complete genuine development evidence bound to the frozen study.')
    if original.max_calls-original.calls<12 or contextual.max_calls-contextual.calls<36:
        raise SchemaError('Ablation requires 12 original and 36 contextual inference attempts.')
    catalog=bundle['catalog'];ids=[e['entity_id'] for e in catalog]
    for row in bundle['pairs']:
        if row['reference_policy']!=calibrate_reference(row['rankings'],ids,5,0):
            raise SchemaError('Development reference policy changed.')
    plan={'study_sha256':fingerprint(study),'bundle_sha256':bundle['bundle_sha256'],
          'original_manifest':original.manifest,'contextual_manifest':contextual.manifest,
          'selection_rule':study['selection_rule'],'reserved_inputs_executed':0,'inference_cap':48,
          'candidate_index':candidate_index,'created_utc':utc_now()}
    plan['plan_sha256']=fingerprint(plan)
    ledger.write('model-plan.json',plan)
    ledger.write('study.json',study)
    ledger.record('model_plan_frozen',{'plan_sha256':plan['plan_sha256']})
    report={'status':'INCOMPLETE','source':ledger.source,'cases':[],'error':None,'candidate_gate':'NOT_VALIDATED',
            'ci_gate':'NOT_VALIDATED','reserved_inputs_executed':0,'new_qloo_requests':0,'plan_sha256':plan['plan_sha256']}
    template={'schema_version':1,'task':suite['task'],'top_k':5,'catalog':catalog}
    try:
        ledger.write('model-readiness.json',original.warmup())
        for pair in pairs:
            ref=next(r for r in bundle['pairs'] if r['pair_id']==pair['id'])
            inputs=requests_for_pair(template,pair)
            ranks={v:{'A':[],'B':[]} for v in VARIANTS}
            for repeat in range(3):
                # Rotate conditions and alternate profiles to expose order effects.
                variants=VARIANTS[repeat:]+VARIANTS[:repeat]
                for label in (('A','B') if repeat%2==0 else ('B','A')):
                    for variant in variants:
                        req=copy.deepcopy(inputs[label])
                        if variant in ('qloo_context','swapped_context'):
                            source_label=label if variant=='qloo_context' else ('B' if label=='A' else 'A')
                            req['cultural_context']=ref['contexts'][source_label]
                        engine=original if variant=='original' else contextual
                        if candidate_index==2 and variant!='original':
                            req['baseline_ranked_entity_ids']=ranks['original'][label][0]
                        if progress:progress(pair['id'],variant,original.calls+contextual.calls+1)
                        output=validate_response(req,engine.rank(req))
                        if len(output)!=20:raise AgentError('Ablation output must rank all twenty movies.')
                        ranks[variant][label].append(output)
                        ledger.record('model_decision',{'pair_id':pair['id'],'profile':label,'variant':variant,'repeat':repeat+1,
                            'request_sha256':fingerprint(req),'context_sha256':fingerprint(req.get('cultural_context')),
                            'ranked_entity_ids':output,'total_inference_calls':original.calls+contextual.calls})
            baseline_noise=noise_and_effect(ranks['original'],5)['noise_max']
            measures={v:noise_and_effect(rows,5) for v,rows in ranks.items()}
            comparisons={}
            for other in ('original','instructions_only','swapped_context'):
                comparisons[other]={label:summarize_deltas(ranks['qloo_context'][label],ranks[other][label],ref['rankings'][label],5) for label in ('A','B')}
            no_loss=all(comparisons[v][p]['min']>=-baseline_noise-1e-12 for v in ('original','instructions_only') for p in ('A','B'))
            added_value=any(comparisons['instructions_only'][p]['min']>baseline_noise+1e-12 for p in ('A','B'))
            beats_swapped=sum(comparisons['swapped_context'][p]['median'] for p in ('A','B'))>1e-12
            stable=measures['qloo_context']['noise_max']<=baseline_noise+1e-12
            passed=ref['reference_policy']['informative'] and no_loss and added_value and beats_swapped and stable
            row={'pair_id':pair['id'],'rankings':ranks,'noise_barrier':baseline_noise,'measurements':measures,
                 'comparisons':comparisons,'checks':{'reference_informative':ref['reference_policy']['informative'],
                 'no_profile_loss':no_loss,'benefit_beyond_instructions':added_value,'beats_swapped_context':beats_swapped,'stable':stable},
                 'candidate_gate':'PROMISING_DEVELOPMENT_CANDIDATE' if passed else 'REJECTED_DEVELOPMENT_CANDIDATE'}
            ledger.write('ablation-'+pair['id']+'.json',row);report['cases'].append(row)
        report['status']='COMPLETE_CONTEXT_ABLATION'
        report['candidate_gate']='PROMISING_DEVELOPMENT_CANDIDATE' if all(r['candidate_gate']=='PROMISING_DEVELOPMENT_CANDIDATE' for r in report['cases']) else 'REJECTED_DEVELOPMENT_CANDIDATE'
    except AffinityQAError as exc:
        report['error']=str(exc);ledger.record('stopped',{'reason':str(exc)})
    report['local_inference_attempts']=original.calls+contextual.calls
    ledger.write('inference-observations.json',{'original':original.observations,'contextual':contextual.observations})
    ledger.write('context-ablation.json',report)
    return report
