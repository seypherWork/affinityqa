"""Execute healthy, three controlled incidents, and real repaired reruns."""
import copy
from itertools import combinations
from .causal_agent import FAULTS,CausalMovieSession,ExecutionRecorder,diagnose,make_request,profile_hash
from .causal_evaluator import evaluate_pair
from .evidence import fingerprint,utc_now
from .metrics import rank_distance
from .errors import SchemaError

TASK='Rank the fixed twenty-movie catalog for a discovery feed tailored to the explicit musical interest and its cultural tool context.'


def capture_pair(engine,ledger,pair,catalog,profiles,contexts,*,policy=None,freeze=None,progress=None):
    recorder=ExecutionRecorder(engine,ledger);key=pair['pair_id']
    healthy={'A':[],'B':[]};controls=[]
    def request(p,nonce):return make_request(TASK,catalog,profiles[p],contexts[profile_hash(profiles[p])],nonce)
    def control(session,req,decision,expected):
        observed=diagnose(decision['trace']);patch=session.apply(observed)
        if observed['diagnosis']=='NONE' and patch!={'operation':'none','attempt':0,'applied':False}:raise SchemaError('Healthy control unexpectedly changed state.')
        return {**copy.deepcopy(decision),'diagnosis':observed,'expected_cache_hit':expected,'patch':patch}
    for repeat in range(1,4):
        session=CausalMovieSession(recorder,contexts);order=['A','B'] if repeat%2 else ['B','A']
        for p in order:
            req=request(p,f'{key}-healthy-{repeat}-{p}');out=session.rank(req);healthy[p].append(out);controls.append(control(session,req,out,False))
        req=request(order[0],f'{key}-healthy-equivalent-{repeat}');out=session.rank(req);controls.append(control(session,req,out,True))
        if progress:progress(key,'healthy',repeat,engine.calls)
    noise=max(rank_distance(a['ranking'],b['ranking'],5) for rows in healthy.values() for a,b in combinations(rows,2))
    if policy is None:
        if freeze is None:raise SchemaError('Development must seal a policy before incidents.')
        policy=freeze(noise,healthy,controls)
    barrier=policy['noise_barrier']
    ledger.record('pair_healthy_capture_complete',{'pair_id':key,'observed_noise':noise,'frozen_noise_barrier':barrier,'model_calls':engine.calls})
    record={'pair_id':key,'artists':pair['artists'],'split':pair['split'],'catalog':catalog,'profiles':profiles,'healthy':healthy,'healthy_controls':controls,'cases':[],
            'tool_signal_distance':rank_distance([r['entity_id'] for r in contexts[profile_hash(profiles['A'])]['ranked_entities']],
                                                [r['entity_id'] for r in contexts[profile_hash(profiles['B'])]['ranked_entities']],5),
            'observed_healthy_noise':noise,'policy_sha256':policy['policy_sha256']}
    for fault in FAULTS:
        case={'fault':fault,'repeats':[]}
        for repeat in range(1,4):
            order=['A','B'] if repeat%2 else ['B','A'];session=CausalMovieSession(recorder,contexts,fault=fault)
            before={p:session.rank(request(p,f'{key}-{fault}-before-{repeat}-{p}')) for p in order}
            diagnostic=diagnose(before[order[1]]['trace']);patch=session.apply(diagnostic)
            after={p:session.rank(request(p,f'{key}-{fault}-after-{repeat}-{p}')) for p in order}
            req=request(order[0],f'{key}-{fault}-after-equivalent-{repeat}');out=session.rank(req)
            ac=control(session,req,out,True)
            case['repeats'].append({'repeat':repeat,'order':order,'before':before,'after':after,'diagnosis':diagnostic,'patch':patch,'after_controls':[ac]})
            if progress:progress(key,fault,repeat,engine.calls)
        record['cases'].append(case)
    if engine.calls!=39:raise SchemaError('The declared thirty-nine-decision pair budget differs from actual execution.')
    ledger.write('causal-pair-'+key+'.json',record)
    summary=evaluate_pair(record,barrier);ledger.write('causal-summary-'+key+'.json',summary)
    return record,summary,policy


def freeze_policy(noise,healthy,controls,*,plan,manifest,ledger):
    policy={'schema_version':1,'protocol_version':'causal-profile-integrity-v1','created_utc':utc_now(),'noise_barrier':noise,'practical_tolerance':0,
            'noise_method':'maximum observed within-profile symmetric ordinal NDCG@5 distance over three fresh development decisions per profile',
            'calibration_sha256':fingerprint({'healthy':healthy,'controls':controls}),'model_manifest':manifest,'catalog_sha256':plan['catalog_sha256'],
            'source_sha256':plan['source_sha256'],'development_pair_id':plan['pairs'][0]['pair_id'],'reserved_pairs_seen':0,
            'causal_checks':['complete_repeats','correct_diagnosis','repair_applied','profile_integrity_restored','real_rerun','healthy_stable','no_behavioral_regression','no_false_alarm','legitimate_cache_reuse'],
            'quality_boundary':'Direct Qloo context is consumed. Agreement with that snapshot cannot independently certify cultural quality.',
            'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}
    policy['policy_sha256']=fingerprint(policy);ledger.write('frozen-causal-policy.json',policy)
    ledger.record('policy_frozen',{'policy_sha256':policy['policy_sha256'],'model_calls':6,'reserved_pairs_seen':0});return policy
