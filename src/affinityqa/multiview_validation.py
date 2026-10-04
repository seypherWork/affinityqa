"""Seal unseen agent and repair outputs before separate evaluator capture."""
import copy
import hashlib
import json
import time
from pathlib import Path

from .agents import validate_response
from .errors import AffinityQAError,SchemaError
from .evidence import fingerprint,utc_now
from .film_protocol import calibrate_reference
from .graph_bridge import evaluate_graph
from .local_suite import normalize_request
from .models import parse_entities,resolve_seed,context_issues,normalized_name
from .multiview_repair import build_capture
from .qloo import QlooClient


def load_policy(root,study):
    directory=root/'runs'/study['training_run']
    training=json.loads((directory/'multiview-training-report.json').read_text(encoding='utf-8'))
    policy=json.loads((directory/'frozen-multiview-policy.json').read_text(encoding='utf-8'))
    if (policy.get('policy_sha256')!=fingerprint({k:v for k,v in policy.items() if k!='policy_sha256'})
            or policy['policy_sha256']!=study['policy_sha256'] or training['policy_sha256']!=policy['policy_sha256']
            or training['training_gate']!='DEVELOPMENT_CONTROLS_PASS' or policy['reserved_cases_seen']!=0
            or policy['source_module_sha256']!=hashlib.sha256((root/'src/affinityqa/multiview_repair.py').read_bytes()).hexdigest()):
        raise SchemaError('Successful frozen development policy is required unchanged.')
    plan=json.loads((directory/'multiview-training-plan.json').read_text(encoding='utf-8'))
    if plan['plan_sha256']!=policy['training_plan_sha256'] or plan['plan_sha256']!=fingerprint({k:v for k,v in plan.items() if k!='plan_sha256'}):
        raise SchemaError('Training provenance changed.')
    for run,files in plan['source_artifact_sha256'].items():
        for name,expected in files.items():
            path=root/'runs'/run/name
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise SchemaError('Training graph evidence changed.')
    source=root/'runs'/plan['study']['source_movie_graph_run']/'graph-inputs.json'
    catalog=next(iter(json.loads(source.read_text(encoding='utf-8')).values()))['catalog']
    # Training fingerprint includes the previously verified catalog type field.
    if fingerprint([{**e,'types':['urn:entity:movie']} for e in catalog])!=policy['catalog_sha256']:
        raise SchemaError('Reserved catalog differs from training.')
    split=json.loads((root/'evals/context-study-v1.json').read_text(encoding='utf-8'))['reserved_v2']
    if len(split)!=6 or len({p['id'] for p in split})!=6:
        raise SchemaError('All six previously untouched pairs are required.')
    return policy,catalog,split


def run_validation(root,study,engine,transport,ledger,*,sleeper=time.sleep,progress=None):
    policy,catalog,pairs=load_policy(root,study)
    if (engine.calls or engine.max_calls!=36 or study['max_total_qloo_requests']!=146
            or study['capture_batches']!=[55,55,36] or study['denominator']!=6
            or study['max_profile_drop']!=0 or study['minimum_mean_gain']!=.02
            or study['minimum_mean_gain_over_swapped']!=.01):
        raise SchemaError('Unchanged six-case validation needs the declared inference and request budgets.')
    ids=[e['entity_id'] for e in catalog];names={normalized_name(e['name']) for e in catalog}
    original_suite=json.loads((root/'evals/film-suite.json').read_text(encoding='utf-8'))
    modules=('multiview_repair.py','multiview_validation.py','ollama_agent.py','models.py','qloo.py','metrics.py','graph_bridge.py')
    hashes={name:hashlib.sha256((root/'src/affinityqa'/name).read_bytes()).hexdigest() for name in modules}
    plan={'study':study,'study_sha256':fingerprint(study),'created_utc':utc_now(),'policy':policy,
          'model_manifest':engine.manifest,'catalog':catalog,'reserved_pairs':pairs,
          'source_sha256':hashes,'model_calls':0,'qloo_calls':0,'reserved_cases_seen':0}
    plan['plan_sha256']=fingerprint(plan);ledger.write('reserved-validation-plan.json',plan)
    ledger.record('reserved_plan_frozen',{'plan_sha256':plan['plan_sha256'],'reserved_cases_seen':0})
    report={'status':'INCOMPLETE','error':None,'denominator':6,'cases':[],'sample_gate':'INCONCLUSIVE',
            'ci_gate':'NOT_VALIDATED','release_approved':False,'policy_sha256':policy['policy_sha256'],
            'plan_sha256':plan['plan_sha256'],'model_calls':0,'real_qloo_requests':0}
    baselines={};seeds={};movie_source={'status':'COMPLETE_GRAPH_CAPTURE','cases':[]};artist_source={'status':'COMPLETE_GRAPH_CAPTURE','cases':[]}
    last=None
    def unchanged():
        if any(hashlib.sha256((root/'src/affinityqa'/name).read_bytes()).hexdigest()!=expected for name,expected in hashes.items()):
            raise SchemaError('Implementation changed after reserved freeze; stop.')
    def get(client,path,params):
        nonlocal last
        unchanged()
        if ledger.live_requests>=146:raise SchemaError('Total validation network budget exhausted.')
        if last is not None:sleeper(max(0,1-(time.monotonic()-last)))
        last=time.monotonic()
        return client.get(path,params,cache=False)
    def movie_rows(body):
        rows=parse_entities(body,insights=True)
        if (len(rows)!=20 or {e.entity_id for e in rows}!=set(ids)
                or context_issues(rows,{'filter_type':'urn:entity:movie','filters':{}},set())
                or any(e.affinity is None for e in rows)):
            raise SchemaError('A reserved movie ranking lacks complete typed coverage or affinities.')
        return [e.entity_id for e in rows]
    try:
        ledger.write('model-readiness.json',engine.warmup())
        for pair in pairs:
            baselines[pair['id']]={'A':[],'B':[]}
            for repeat in range(3):
                for p in (('A','B') if repeat%2==0 else ('B','A')):
                    req=normalize_request({'schema_version':1,'task':original_suite['task'],'top_k':5,'catalog':catalog,
                        'profile':[{'name':pair[p],'type':'urn:entity:artist'}]})
                    if progress:progress('model',pair['id'],p,engine.calls+1,36)
                    ranking=validate_response(req,engine.rank(req))
                    if len(ranking)!=20:raise SchemaError('Reserved model omitted a ranking tail.')
                    baselines[pair['id']][p].append(ranking)
                    ledger.record('reserved_model_decision',{'pair_id':pair['id'],'profile':p,'repeat':repeat+1,
                        'ranked_entity_ids':ranking,'request_sha256':fingerprint(req),'inference_call':engine.calls})
        ledger.write('sealed-model-decisions.json',baselines)
        ledger.write('inference-observations.json',engine.observations)
        ledger.record('all_model_decisions_sealed',{'sha256':fingerprint(baselines),'model_calls':engine.calls,'qloo_calls':0})
        for batch in (0,1):
            client=QlooClient(transport,ledger,max_requests=55,max_attempts=1)
            metadata=parse_entities(get(client,'/entities',{'entity_ids':','.join(ids)}),insights=False)
            expected={e['entity_id']:e for e in catalog}
            if (len(metadata)!=20 or {e.entity_id for e in metadata}!=set(ids)
                    or any(e.name!=expected[e.entity_id]['name'] or e.metadata.get('release_year')!=expected[e.entity_id]['release_year'] for e in metadata)):
                raise SchemaError('Reserved catalog identity changed.')
            for pair in pairs[batch*3:batch*3+3]:
                key=pair['id'];seeds[key]={};ma={};aa={}
                for p in ('A','B'):
                    name=pair[p];seed={'name':name,'accepted_names':[name],'accepted_types':['urn:entity:artist']}
                    rows=parse_entities(get(client,'/search',{'query':name,'types':'urn:entity:artist','take':5}),insights=False)
                    seeds[key][p]=resolve_seed(seed,rows,synthetic=False).entity_id
                if seeds[key]['A']==seeds[key]['B']:raise SchemaError('Reserved artist mutation collapsed on lookup.')
                for p in ('A','B'):
                    rows=parse_entities(get(client,'/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':5,
                        'signal.interests.entities':seeds[key][p],'filter.exclude.entities':','.join(ids)}),insights=True)
                    if (len(rows)!=5 or any(e.entity_id in ids or normalized_name(e.name) in names for e in rows)
                            or context_issues(rows,{'filter_type':'urn:entity:movie','filters':{}},set(ids))):
                        raise SchemaError('Reserved movie anchors overlap the evaluation catalog or violate type.')
                    ma[p]=sorted(e.entity_id for e in rows)
                    ledger.write(f'movie-anchors-{key}-{p}.json',sorted([{'entity_id':e.entity_id,'name':e.name} for e in rows],key=lambda e:e['entity_id']))
                for p in ('A','B'):
                    rows=parse_entities(get(client,'/v2/insights',{'filter.type':'urn:entity:artist','bias.trends':'off','take':5,
                        'signal.interests.entities':seeds[key][p],'filter.exclude.entities':','.join(sorted(seeds[key].values()))}),insights=True)
                    if len(rows)!=5 or context_issues(rows,{'filter_type':'urn:entity:artist','filters':{}},set(seeds[key].values())):
                        raise SchemaError('Reserved artist anchors overlap original interests or violate type.')
                    aa[p]=sorted(e.entity_id for e in rows)
                    ledger.write(f'artist-anchors-{key}-{p}.json',sorted([{'entity_id':e.entity_id,'name':e.name} for e in rows],key=lambda e:e['entity_id']))
                for view,anchors,target in (('movie',ma,movie_source),('artist',aa,artist_source)):
                    graphs={'A':[],'B':[]}
                    for repeat in range(3):
                        for p in (('A','B') if repeat%2==0 else ('B','A')):
                            if set(anchors[p])&set(seeds[key].values()):raise SchemaError('Original artist entered a repair movie query.')
                            if progress:progress(view+'-graph',key,p,ledger.live_requests+1,146)
                            graphs[p].append(movie_rows(get(client,'/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,
                                'signal.interests.entities':','.join(anchors[p]),'filter.results.entities':','.join(ids)})))
                    row={'pair_id':key,'graphs':graphs,'rankings':{'baseline':baselines[key]}}
                    ledger.write(view+'-graph-'+key+'.json',row);target['cases'].append(row)
        sealed=build_capture(movie_source,artist_source,policy['graph_weight'],policy['movie_view_weight'],plan['plan_sha256'])
        sealed['real_qloo_requests']=ledger.live_requests
        ledger.write('sealed-repair-decisions.json',sealed)
        ledger.record('all_repairs_sealed_before_reference',{'sha256':fingerprint(sealed),'qloo_calls':ledger.live_requests,'reference_calls':0})
        evaluator={'catalog':catalog,'pairs':[]}
        client=QlooClient(transport,ledger,max_requests=36,max_attempts=1)
        for pair in pairs:
            key=pair['id'];rankings={'A':[],'B':[]}
            for repeat in range(3):
                for p in (('A','B') if repeat%2==0 else ('B','A')):
                    if progress:progress('reference',key,p,ledger.live_requests+1,146)
                    rankings[p].append(movie_rows(get(client,'/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,
                        'signal.interests.entities':seeds[key][p],'filter.results.entities':','.join(ids)})))
            row={'pair_id':key,'rankings':rankings,'reference_policy':calibrate_reference(rankings,ids,5,0)}
            ledger.write('reference-'+key+'.json',row);evaluator['pairs'].append(row)
        evaluation_study={**study,'development_pair_ids':[p['id'] for p in pairs],
                          'interpretation':study['ci_interpretation']}
        evaluated=evaluate_graph(sealed,evaluator,evaluation_study,ledger)
        report.update(status='COMPLETE_RESERVED_VALIDATION',cases=evaluated['cases'],
            sample_gate='PASS' if evaluated['candidate_gate']=='PROMISING_DEVELOPMENT_CANDIDATE' else 'FAIL',
            passing_cases=sum(all(c['checks'].values()) for c in evaluated['cases']))
    except AffinityQAError as exc:
        report['error']=str(exc);ledger.record('stopped',{'reason':str(exc),'model_calls':engine.calls,'qloo_calls':ledger.live_requests})
    report.update(model_calls=engine.calls,real_qloo_requests=ledger.live_requests,
                  missing_pair_ids=[p['id'] for p in pairs if p['id'] not in {c['pair_id'] for c in report['cases']}])
    ledger.write('reserved-validation-report.json',report)
    return report
