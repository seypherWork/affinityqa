"""A sealed six-pair validation of value-sensitive, disjoint-movie repair."""
import hashlib,json,time
from .agents import validate_response
from .affinity_refinement import refined_fuse
from .errors import AffinityQAError,SchemaError
from .evidence import fingerprint,utc_now
from .film_protocol import calibrate_reference
from .graph_bridge import evaluate_graph
from .local_suite import normalize_request
from .models import parse_entities,resolve_seed,context_issues,normalized_name
from .qloo import QlooClient

TRAINING='20261003T235341Z-03694edc'

def load_policy(root):
    directory=root/'runs'/TRAINING
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    plan=read(directory/'affinity-refinement-plan.json');policy=read(directory/'frozen-refined-policy.json')
    result=read(directory/'affinity-refinement-report.json');selected=read(directory/'selected-result.json')
    if (result['training_gate']!='DEVELOPMENT_CONTROLS_PASS' or len(selected['cases'])!=8
            or not all(all(c['checks'].values()) for c in selected['cases'])
            or policy['policy_sha256']!=fingerprint({k:v for k,v in policy.items() if k!='policy_sha256'})
            or plan['plan_sha256']!=fingerprint({k:v for k,v in plan.items() if k!='plan_sha256'})
            or policy['training_plan_sha256']!=plan['plan_sha256'] or policy['policy_sha256']!=result['policy_sha256']
            or policy['power']!=.875 or policy['graph_weight']!=.5 or policy['movie_weight']!=1):
        raise SchemaError('The unchanged eight-case passing policy is required.')
    for name,h in policy['source_sha256'].items():
        if hashlib.sha256((root/'src/affinityqa'/name).read_bytes()).hexdigest()!=h:raise SchemaError('Frozen repair code changed.')
    source=read(root/'runs/20261003T214623Z-c7e44e6e/graph-inputs.json')
    catalog=next(iter(source.values()))['catalog']
    if fingerprint([{**e,'types':['urn:entity:movie']} for e in catalog])!=policy['catalog_sha256']:
        raise SchemaError('Frozen catalog changed.')
    pairs=plan['study']['reserved_v3']
    if len(pairs)!=6 or len({p['id'] for p in pairs})!=6 or len({normalized_name(p[s]) for p in pairs for s in ('A','B')})!=12:
        raise SchemaError('All six unique protected pairs are mandatory.')
    old=read(root/'evals/film-suite.json')
    exposed=read(root/'runs/20261003T220331Z-a2ec2896/reserved-validation-plan.json')['reserved_pairs']
    used={normalized_name(p[s]) for p in exposed for s in ('A','B')}
    used|={normalized_name(v['name']) for p in old['pairs'] for s in ('A','B') for v in p[s]}
    if used&{normalized_name(p[s]) for p in pairs for s in ('A','B')}:raise SchemaError('Protected original profiles overlap exposed inputs.')
    return policy,catalog,pairs

def run_validation(root,engine,transport,ledger,*,sleeper=time.sleep,progress=None):
    policy,catalog,pairs=load_policy(root)
    if engine.calls or engine.max_calls!=36:raise SchemaError('Fresh 36-decision local engine required.')
    ids=[e['entity_id'] for e in catalog];catalog_names={normalized_name(e['name']) for e in catalog}
    task=json.loads((root/'evals/film-suite.json').read_text(encoding='utf-8'))['task']
    modules=('value_validation.py','affinity_refinement.py','affinity_repair.py','ollama_agent.py','models.py','qloo.py','metrics.py','graph_bridge.py')
    hashes={name:hashlib.sha256((root/'src/affinityqa'/name).read_bytes()).hexdigest() for name in modules}
    study={'validation_id':'affinity-value-reserved-v1','development_pair_ids':[p['id'] for p in pairs],
           'denominator':6,'max_profile_drop':0,'minimum_mean_gain':.02,'minimum_mean_gain_over_swapped':.01,
           'model_call_cap':36,'qloo_request_cap':98,'repeats':3,'request_batches':[31,31,36],
           'interpretation':'One independent frozen sample; not population or human-preference certification.'}
    plan={'study':study,'created_utc':utc_now(),'policy':policy,'catalog':catalog,'reserved_pairs':pairs,
          'source_sha256':hashes,'model_manifest':engine.manifest,'reserved_inputs_executed':0,
          'oracle_boundary':'Model decisions precede all Qloo calls; all repair variants precede direct references.',
          'mechanism':'Normalize disjoint movie affinity to [0,1], exponent .875; equal fusion with local ordinal utility. No artist graph is used.',
          'controls':'Same power and weights; pooled control averages normalized movie scores; swapped control uses opposite context.',
          'provider_quota':'Unknown; self-imposed caps. No automatic retry.'}
    plan['plan_sha256']=fingerprint(plan);ledger.write('value-validation-plan.json',plan)
    ledger.record('value_plan_frozen',{'plan_sha256':plan['plan_sha256'],'model_calls':0,'qloo_calls':0})
    report={'status':'INCOMPLETE','error':None,'sample_gate':'INCONCLUSIVE','ci_gate':'NOT_VALIDATED',
            'release_approved':False,'denominator':6,'cases':[],'policy_sha256':policy['policy_sha256'],'plan_sha256':plan['plan_sha256']}
    baselines={};seeds={};graph_cases=[];last=None
    def get(client,path,params):
        nonlocal last
        if any(hashlib.sha256((root/'src/affinityqa'/n).read_bytes()).hexdigest()!=h for n,h in hashes.items()):raise SchemaError('Frozen validation implementation changed.')
        if ledger.live_requests>=98:raise SchemaError('Validation request budget exhausted.')
        if last is not None:sleeper(max(0,1-(time.monotonic()-last)))
        last=time.monotonic();return client.get(path,params,cache=False)
    def movie_rows(body):
        rows=parse_entities(body,insights=True)
        expected={e['entity_id']:e for e in catalog}
        if (len(rows)!=20 or {e.entity_id for e in rows}!=set(ids)
                or context_issues(rows,{'filter_type':'urn:entity:movie','filters':{}},set())
                or any(e.affinity is None or e.name!=expected[e.entity_id]['name'] or e.metadata.get('release_year')!=expected[e.entity_id]['release_year'] for e in rows)):
            raise SchemaError('Incomplete, untyped or changed movie graph/reference.')
        return rows
    try:
        ledger.write('model-readiness.json',engine.warmup())
        for pair in pairs:
            key=pair['id'];baselines[key]={'A':[],'B':[]}
            for r in range(3):
                for p in (('A','B') if r%2==0 else ('B','A')):
                    req=normalize_request({'schema_version':1,'task':task,'top_k':5,'catalog':catalog,'profile':[{'name':pair[p],'type':'urn:entity:artist'}]})
                    if progress:progress('model',key,p,engine.calls+1,36)
                    ranking=validate_response(req,engine.rank(req))
                    if len(ranking)!=20:raise SchemaError('Incomplete model permutation.')
                    baselines[key][p].append(ranking)
                    ledger.record('value_model_decision',{'pair_id':key,'profile':p,'repeat':r+1,'ranked_entity_ids':ranking,'request_sha256':fingerprint(req)})
        ledger.write('sealed-model-decisions.json',baselines);ledger.write('inference-observations.json',engine.observations)
        ledger.record('all_model_decisions_sealed',{'sha256':fingerprint(baselines),'model_calls':36,'qloo_calls':0})
        for batch in (0,1):
            client=QlooClient(transport,ledger,max_requests=31,max_attempts=1)
            rows=parse_entities(get(client,'/entities',{'entity_ids':','.join(ids)}),insights=False)
            expected={e['entity_id']:e for e in catalog}
            if (len(rows)!=20 or {e.entity_id for e in rows}!=set(ids)
                    or any(e.name!=expected[e.entity_id]['name'] or e.metadata.get('release_year')!=expected[e.entity_id]['release_year'] for e in rows)):
                raise SchemaError('Catalog metadata changed.')
            for pair in pairs[batch*3:batch*3+3]:
                key=pair['id'];seeds[key]={};anchors={}
                for p in ('A','B'):
                    name=pair[p];seed={'name':name,'accepted_names':[name],'accepted_types':['urn:entity:artist']}
                    rows=parse_entities(get(client,'/search',{'query':name,'types':'urn:entity:artist','take':5}),insights=False)
                    seeds[key][p]=resolve_seed(seed,rows,synthetic=False).entity_id
                if len(set(seeds[key].values()))!=2:raise SchemaError('Artist mutation collapsed.')
                for p in ('A','B'):
                    rows=parse_entities(get(client,'/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':5,
                         'signal.interests.entities':seeds[key][p],'filter.exclude.entities':','.join(ids)}),insights=True)
                    if (len(rows)!=5 or len({e.entity_id for e in rows})!=5 or any(e.entity_id in ids or normalized_name(e.name) in catalog_names for e in rows)
                            or context_issues(rows,{'filter_type':'urn:entity:movie','filters':{}},set(ids))):raise SchemaError('External anchors overlap or lack typed coverage.')
                    anchors[p]=sorted(e.entity_id for e in rows)
                    ledger.write(f'movie-anchors-{key}-{p}.json',[{'entity_id':e.entity_id,'name':e.name} for e in rows])
                values={'A':[],'B':[]}
                for r in range(3):
                    for p in (('A','B') if r%2==0 else ('B','A')):
                        if set(anchors[p])&set(seeds[key].values()):raise SchemaError('Original artist cannot enter repair query.')
                        if progress:progress('movie-graph',key,p,ledger.live_requests+1,98)
                        rows=movie_rows(get(client,'/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,
                            'signal.interests.entities':','.join(anchors[p]),'filter.results.entities':','.join(ids)}))
                        values[p].append({e.entity_id:e.affinity for e in rows})
                case={'pair_id':key,'baseline':baselines[key],'movie':values}
                ledger.write('value-graph-'+key+'.json',case);graph_cases.append(case)
        sealed={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan['plan_sha256'],'real_qloo_requests':ledger.live_requests,'cases':[]}
        for case in graph_cases:
            ranks={'baseline':case['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
            for r in range(3):
                for p in ('A','B'):
                    other='B' if p=='A' else 'A';b=case['baseline'][p][r];m=case['movie'][p][r];om=case['movie'][other][r]
                    ranks['qloo_graph'][p].append(refined_fuse(b,m,m,policy['power']))
                    ranks['neutral_graph'][p].append(refined_fuse(b,m,m,policy['power'],other_movie=om,other_artist=om))
                    ranks['swapped_graph'][p].append(refined_fuse(b,om,om,policy['power']))
            sealed['cases'].append({'pair_id':case['pair_id'],'rankings':ranks})
        ledger.write('sealed-repair-decisions.json',sealed)
        ledger.record('all_repairs_sealed_before_reference',{'sha256':fingerprint(sealed),'qloo_calls':ledger.live_requests,'reference_calls':0})
        evaluator={'catalog':catalog,'pairs':[]};client=QlooClient(transport,ledger,max_requests=36,max_attempts=1)
        for pair in pairs:
            key=pair['id'];rankings={'A':[],'B':[]}
            for r in range(3):
                for p in (('A','B') if r%2==0 else ('B','A')):
                    if progress:progress('reference',key,p,ledger.live_requests+1,98)
                    rows=movie_rows(get(client,'/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,
                        'signal.interests.entities':seeds[key][p],'filter.results.entities':','.join(ids)}))
                    rankings[p].append([e.entity_id for e in rows])
            row={'pair_id':key,'rankings':rankings,'reference_policy':calibrate_reference(rankings,ids,5,0)}
            ledger.write('reference-'+key+'.json',row);evaluator['pairs'].append(row)
        evaluation=evaluate_graph(sealed,evaluator,study,ledger)
        passing=sum(all(c['checks'].values()) for c in evaluation['cases'])
        report.update(status='COMPLETE_RESERVED_VALIDATION',cases=evaluation['cases'],passing_cases=passing,sample_gate='PASS' if passing==6 else 'FAIL')
    except AffinityQAError as exc:
        report['error']=str(exc);ledger.record('stopped',{'reason':str(exc),'model_calls':engine.calls,'qloo_calls':ledger.live_requests})
    report.update(model_calls=engine.calls,real_qloo_requests=ledger.live_requests,
                  missing_pair_ids=[p['id'] for p in pairs if p['id'] not in {c['pair_id'] for c in report['cases']}])
    ledger.write('value-validation-report.json',report);return report
