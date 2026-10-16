"""Independent paired input, shared completion and immutable file reconstruction."""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
from .errors import SchemaError
from .evidence import fingerprint, utc_now
from .individual_verify import checked_path, inventory, read, sha, same, need, instant
from .individual_remote_verify import expected_manifest as remote_manifest
from .cinema_identity_verify import selection_profiles, _sample
from .cinema_discovery_v4_boundary_verify import expected_input, verify_context
from .cinema_discovery_v4_verify import selection_movies as movie_selection, _effective_preferences, delivery, reference
from .fast_pair import PROMPT

PROTOCOL = 'cinema-paired-discovery-v1'
SOURCE = 'qloo-tool+groq-paired-discovery-v1'

def expected_manifest(source):
    value = remote_manifest(source)
    value.update(max_inference_calls=1,prompt_version=PROTOCOL,prompt_sha256=fingerprint(PROMPT),
        tool_contract='paired-confirmed-cinema-context-v1',response_contract='groq-paired-exact-discovery-arrays-v1',
        decision_scope='one-shared-call-two-correlated-projections',maximum_token_reservation=8000,
        prompt_cache_discount_reserved=False)
    return value

def selection_movies(receipt, selected_movie_entity_ids):
    need(isinstance(selected_movie_entity_ids,dict) and set(selected_movie_entity_ids)=={'A','B'},'explicit paired movie groups')
    if not any(receipt['movie_queries'].values()):
        need(same(selected_movie_entity_ids,{'A':[],'B':[]}),'zero-query confirmation must remain explicitly empty')
        return {'A':[],'B':[]}
    return movie_selection(receipt,selected_movie_entity_ids)

def _search(directory, before, *, continuing=False):
    from .fast_pair_capture import SOURCES
    p = read(directory/'pair-plan.json'); r = p['request']; child = p['identity_plan']
    need(isinstance(r,dict) and set(r)=={'schema_version','artists','catalog','model','preferences','movie_queries'}
         and type(r['schema_version']) is int and r['schema_version']==7,'closed paired request7')
    queries = r['movie_queries']; need(isinstance(queries,dict) and set(queries)=={'A','B'},'movie query groups')
    if any(queries.values()):
        from .cinema_discovery_v4_verify import _identity, _request
        child_request = _request({**r,'schema_version':6})
    else:
        from .cinema_discovery_v3_verify import _identity, _request
        need(same(queries,{'A':[],'B':[]}),'empty movie slots')
        child_request = _request({k:v for k,v in r.items() if k!='movie_queries'} | {'schema_version':5})
    old, actual, *_ = _identity(directory,before,continuing=True)
    need(same(actual,child) and same(actual['request'],child_request),'identity driver/source/request translation differs')
    source = Path(__file__).resolve().parent
    expected = {'schema_version':9,'protocol_version':PROTOCOL,'mode':'cinema-paired-discovery-capture','request':r,
        'output_directory':str(directory.parent),'identity_plan':actual,'remote_operator':expected_manifest('remote-llm'),
        'source_sha256':{n:sha(source/n) for n in SOURCES},'driver_sha256':sha(source/'fast_pair_capture.py'),
        'verification_driver_sha256':sha(source/'fast_pair_verify.py'),
        'dependencies_lock_sha256':sha(source.parents[1]/'requirements-backend.lock.txt'),
        'maximum_qloo_requests':4+sum(map(len,queries.values())),'maximum_identity_search_requests':2,
        'maximum_movie_search_requests':sum(map(len,queries.values())),'maximum_insights_requests':2,
        'maximum_model_decisions':1,'maximum_attempts_per_request':1,
        'identity_candidate_contract':actual['identity_candidate_contract'],'movie_candidate_contract':'qloo-confirmed-movie-title-year-v1',
        'faults':[],'execution_pacing':{'strategy':'one-joint-send-no-intercall-wait','minimum_interval_seconds':0},
        'decision_scope':'one-shared-call-two-correlated-projections','maximum_token_reservation':8000,
        'independent_validation_claim':False,'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}
    expected['plan_sha256'] = fingerprint(expected)
    need(same(p,expected),'paired source, plan, manifest or drivers changed')
    initial = dict(old['artifact_sha256']); initial['pair-plan.json'] = before['pair-plan.json']
    if not continuing:
        need(set(before)==set(initial) and before==initial,'unknown search artifacts or mutation')
    receipt = {**old,'protocol_version':PROTOCOL,'mode':p['mode'],'plan_sha256':p['plan_sha256'],
        'movie_queries':copy.deepcopy(queries),'movie_candidates':copy.deepcopy(old.get('movie_candidates',{'A':[],'B':[]})),
        'artifact_sha256':initial,'capture_source_sha256':p['source_sha256'],'capture_driver_sha256':p['driver_sha256'],
        'maximum_model_decisions':1,'decision_scope':p['decision_scope']}
    return receipt,p

def _input(request):
    need(isinstance(request,dict) and set(request)=={'schema_version','protocol','profiles','request_nonce','request_id'}
         and type(request['schema_version']) is int and request['schema_version']==1 and request['protocol']==PROTOCOL,'closed joint request')
    need(isinstance(request['profiles'],dict) and set(request['profiles'])=={'A','B'},'both profile requests')
    need(isinstance(request['request_nonce'],str) and 1<=len(request['request_nonce'])<=120,'joint nonce')
    need(request['request_id']==fingerprint({k:v for k,v in request.items() if k!='request_id'}),'joint request ID')
    rows = {k:expected_input(request['profiles'][k]) for k in ('A','B')}
    need(rows['A']['catalog']==rows['B']['catalog'] and rows['A']['profile']['entity_id']!=rows['B']['profile']['entity_id'],'shared catalog/distinct profiles')
    fields = ('profile','known_favorite_movies','external_favorite_movies','discovery_catalog_indices','eligible_catalog_indices','provider_movie_context','cinema_preferences')
    return {'cinema_protocol':PROTOCOL,'task':'Rank the two explicit profiles separately using their own known interests and provider context.',
        'catalog':rows['A']['catalog'],'profiles':{k:{f:copy.deepcopy(rows[k][f]) for f in fields} for k in ('A','B')},
        'tool_notice':'Actual composite Qloo discovery context; query-relative affinities, no independent quality labels.'}

def _wire(request, manifest):
    indices = {k:request['profiles'][k]['discovery_catalog_indices'] for k in ('A','B')}
    props = {k:{'type':'array','items':{'type':'integer','enum':list(v)},'minItems':len(v),'maxItems':len(v)} for k,v in indices.items()}
    schema = {'type':'object','properties':{'ordered_catalog_indices':{'type':'object','properties':props,'required':['A','B'],
        'additionalProperties':False}},'required':['ordered_catalog_indices'],'additionalProperties':False}
    return {'model':manifest['model'],'messages':[{'role':'system','content':PROMPT},
        {'role':'user','content':json.dumps(_input(request),ensure_ascii=False,separators=(',',':'),allow_nan=False)}],
        'response_format':{'type':'json_schema','json_schema':{'name':'affinityqa_paired_discovery_v1','strict':True,'schema':schema}},**manifest['options']}

def verify_packet(packet, manifest, contexts):
    need(isinstance(packet,dict) and set(packet)=={'execution_id','effective_request','model_payload','response','observation','joint_cache_key_sha256'},'one closed shared packet')
    request,obs = packet['effective_request'],packet['observation']; payload = _input(request)
    source = obs['execution_source']; need(source in ('remote-llm','test-double-only') and same(manifest,expected_manifest(source)),'paired model contract/source')
    need(same(packet['model_payload'],payload),'independent paired model payload')
    need(set(contexts)=={'A','B'} and all(same(request['profiles'][k]['tool_context'],contexts[k]) for k in contexts),'profile/context routing')
    key = fingerprint({'protocol':PROTOCOL,'input':payload,'contexts':contexts,'manifest':manifest})
    need(packet['joint_cache_key_sha256']==key,'joint A+B+preferences+context+prompt cache binding')
    envelope = obs['provider_envelope']
    need(isinstance(envelope,dict) and set(envelope)=={'schema_version','execution_source','provider','object','model','id','created','system_fingerprint','choice','usage'},'closed shared envelope')
    need(type(envelope['schema_version']) is int and envelope['schema_version']==1 and envelope['execution_source']==source
         and envelope['provider']=='groq' and envelope['object']=='chat.completion' and envelope['model']==manifest['model'],'envelope identity')
    need(isinstance(envelope['id'],str) and re.fullmatch(r'[!-~]{1,160}',envelope['id']) and type(envelope['created']) is int and 1<=envelope['created']<=2**63-1,'provider completion identity/time')
    fp = envelope['system_fingerprint']; need(fp is None or isinstance(fp,str) and re.fullmatch(r'[!-~]{1,128}',fp),'provider fingerprint')
    choice = envelope['choice']; need(set(choice)=={'index','finish_reason','role','ordered_catalog_indices'} and type(choice['index']) is int
        and choice['index']==0 and choice['finish_reason']=='stop' and choice['role']=='assistant','one complete choice')
    indices = choice['ordered_catalog_indices']; need(isinstance(indices,dict) and set(indices)=={'A','B'},'two correlated outputs')
    result = {}
    for k in ('A','B'):
        rows, allowed = indices[k], request['profiles'][k]['discovery_catalog_indices']
        need(isinstance(rows,list) and len(rows)==len(allowed) and all(type(i) is int for i in rows) and set(rows)==set(allowed),'exact projected permutation')
        result[k] = [request['profiles'][k]['catalog'][i]['entity_id'] for i in rows]
    need(same(packet['response'],{'schema_version':1,'request_id':request['request_id'],'ranked_entity_ids':result}),'shared response binding')
    usage = envelope['usage']; need(set(usage)=={'prompt_tokens','completion_tokens','total_tokens','reasoning_tokens'},'closed token usage')
    need(type(usage['prompt_tokens']) is int and 1<=usage['prompt_tokens']<=8192 and type(usage['completion_tokens']) is int and 1<=usage['completion_tokens']<=1024
         and type(usage['total_tokens']) is int and usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens']
         and (usage['reasoning_tokens'] is None or type(usage['reasoning_tokens']) is int and 0<=usage['reasoning_tokens']<=usage['completion_tokens']),'token bounds')
    need(type(obs['elapsed_ms']) in (int,float) and math.isfinite(obs['elapsed_ms']) and obs['elapsed_ms']>=0
         and isinstance(obs['provider_response_sha256'],str) and re.fullmatch('[a-f0-9]{64}',obs['provider_response_sha256']),'observation time/hash')
    expected = {'call':1,'input_sha256':fingerprint(payload),'output_sha256':fingerprint(result),'elapsed_ms':obs['elapsed_ms'],
        'prompt_eval_count':usage['prompt_tokens'],'eval_count':usage['completion_tokens'],'private_thinking_recorded':False,
        'done':True,'done_reason':'stop','provider':'groq','model':manifest['model'],'completion_id':envelope['id'],
        'provider_created':envelope['created'],'system_fingerprint':fp,'provider_response_sha256':obs['provider_response_sha256'],
        'provider_response_hash_scope':'Full parsed response observation; not reconstructible from the redacted envelope.',
        'provider_request_sha256':fingerprint(_wire(request,manifest)),'provider_envelope':envelope,'provider_envelope_sha256':fingerprint(envelope),
        'total_tokens':usage['total_tokens'],'reasoning_tokens':usage['reasoning_tokens'],'model_revision_attested':False,'execution_source':source}
    need(same(obs,expected) and isinstance(packet['execution_id'],str) and re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}/1',packet['execution_id']),'single observation/execution')
    return result

def verify_discovery_search(directory):
    try:
        directory = checked_path(directory); before = inventory(directory)
        result,_ = _search(directory,before)
        need(inventory(directory)==before,'search changed during audit')
        return result
    except SchemaError: raise
    except (KeyError,ValueError,TypeError,OSError,IndexError,AttributeError) as exc:
        raise SchemaError('Paired search evidence invalid.') from exc

def _confirmed(directory):
    before = inventory(directory); identity,plan = _search(directory,before,continuing=True)
    need(identity['verification_status']=='VERIFIED_IDENTITY_SEARCH','successful immutable search required')
    request = plan['request']; c = read(directory/'pair-confirmation.json'); report = read(directory/'individual-report.json')
    need(set(c)=={'protocol','plan_sha256','identity_receipt','selected_entity_ids','selected_movie_entity_ids','profiles','movies','preferences'}
         and c['protocol']==PROTOCOL and c['plan_sha256']==plan['plan_sha256'],'closed joint confirmation')
    instant(c['identity_receipt']['verified_utc'])
    clean = lambda r:{k:v for k,v in r.items() if k!='verified_utc'}
    need(same(clean(identity),clean(c['identity_receipt'])),'confirmation search receipt changed')
    profiles = selection_profiles(identity,c['selected_entity_ids']); movies = selection_movies(identity,c['selected_movie_entity_ids'])
    prefs = {k:_effective_preferences(request['catalog'],request['preferences'][k],movies[k]) for k in ('A','B')}
    need(same(c['profiles'],profiles) and same(c['movies'],movies) and same(c['preferences'],prefs),'posted data substituted for verified choices')
    prefix = [json.loads(x) for x in (directory/'identity-ledger.jsonl').read_bytes().splitlines()]
    events = [json.loads(x) for x in (directory/'ledger.jsonl').read_bytes().splitlines()]
    need(same(events[:len(prefix)],prefix),'search prefix changed')
    source = 'test-double-only' if identity['provenance']=='SIMULATION_ONLY' else SOURCE
    suffix = events[len(prefix):]; complete = report['status']=='COMPLETE'
    for i,e in enumerate(suffix,len(prefix)+1):
        need(set(e)=={'sequence','timestamp_utc','source','kind','data'} and type(e['sequence']) is int and e['sequence']==i and e['source']==source,'event sequence/source')
        instant(e['timestamp_utc'])
    if not complete:
        need(suffix and suffix[-1]['kind']=='stopped_without_retry' and same(suffix[-1]['data'],{'error_class':report['error_class']}),'terminal stop')
        suffix = suffix[:-1]
    expected_kinds = ['pair_confirmed','tool_call','tool_call','pair_inputs_frozen','pair_model_attempt_prepared','pair_execution_recorded','pair_projections_recorded']
    kinds = ['tool_call' if e['kind']=='transport_failure' else e['kind'] for e in suffix]
    need(kinds==expected_kinds[:len(kinds)] and (not complete or kinds==expected_kinds),'legal joint execution prefix')
    need(suffix and same(suffix[0]['data'],{'confirmation_sha256':before['pair-confirmation.json']}),'confirmation file binding')
    samples = {}; sample_names = []
    for i,event in enumerate(suffix[1:3]):
        label = ('A','B')[i]; p = profiles[label]; prefs_row = prefs[label]
        ids = sorted(v['entity_id'] for v in request['catalog'] if v['entity_id'] not in prefs_row['favorite_entity_ids'])
        signals = sorted([p['entity_id'],*prefs_row['favorite_entity_ids'],*[v['entity_id'] for v in prefs_row['external_favorite_movies']]])
        params = {'filter.type':'urn:entity:movie','bias.trends':'off','take':len(ids),'signal.interests.entities':','.join(signals),'filter.results.entities':','.join(ids)}
        sample,name = _sample(directory,event,source,'/v2/insights',params)
        if name: sample_names.append(name); samples[label] = (sample,name)
    contexts = read(directory/'individual-tool-inputs.json') if 'individual-tool-inputs.json' in before else None
    if contexts is not None:
        need(set(contexts)=={'A','B'} and len(samples)==2 and len(suffix)>=4,'complete frozen contexts')
        for k in ('A','B'):
            sample,name = samples[k]; verify_context(contexts[k],request['catalog'],profiles[k],prefs[k],sample,before[name])
        need(same(suffix[3]['data'],{'sha256':fingerprint(contexts)}),'context seal')
    else: need(len(suffix)<4 and not complete,'missing contexts')
    manifest = read(directory/'model-manifest.json') if 'model-manifest.json' in before else None
    if manifest is not None: need(same(manifest,expected_manifest('test-double-only' if source=='test-double-only' else 'remote-llm')),'model manifest')
    results = {}; prepared = len(suffix)>=5; packet_present = 'pair-execution-001.json' in before
    if prepared:
        need(contexts is not None and manifest is not None,'model before frozen inputs')
        d = suffix[4]['data']; need(set(d)=={'request_id','input_sha256','provider_request_sha256','wire_sha256','request_bytes','reservation'},'prepared contract')
        from .provider_runtime import PinnedHarmonyTokenEstimator
        estimator = PinnedHarmonyTokenEstimator(Path(__file__).resolve().parents[2]/'assets/tokenizers/o200k_base.tiktoken')
        from .cinema_discovery_v4_verify import decision_request
        decisions = {k:decision_request(request|{'preferences':prefs},profiles[k],contexts[k],k,directory.name) for k in ('A','B')}
        # The new nonce spelling belongs to the new contract; old helper validates all other constants independently.
        for k in decisions:
            decisions[k]['request_nonce']='pair-'+directory.name+'-'+k
            decisions[k].pop('request_id'); decisions[k]['request_id']=fingerprint(decisions[k])
        effective = {'schema_version':1,'protocol':PROTOCOL,'profiles':decisions,'request_nonce':'pair-'+directory.name}
        effective['request_id']=fingerprint(effective)
        payload = _wire(effective,manifest); raw = json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        reservation = estimator.estimate(raw)
        need(reservation['tokens']<=8000 and len(raw)<=65536 and same(d,{'request_id':effective['request_id'],'input_sha256':fingerprint(_input(effective)),
            'provider_request_sha256':fingerprint(payload),'wire_sha256':hashlib.sha256(raw).hexdigest(),'request_bytes':len(raw),'reservation':reservation}),'exact offline token reservation/wire')
        if packet_present:
            need(len(suffix)>=6,'orphan joint packet'); packet = read(directory/'pair-execution-001.json')
            need(same(packet['effective_request'],effective) and packet['execution_id']==directory.name+'/1','joint effective selection binding')
            ranking = verify_packet(packet,manifest,contexts)
            need(same(suffix[5]['data'],{'packet_sha256':before['pair-execution-001.json']}),'joint packet artifact binding')
            for k in ('A','B'):
                guard = delivery(ranking[k],request['catalog'],prefs[k]); ref = reference(contexts[k],request['catalog'],prefs[k])
                result = {'profile':profiles[k],'preferences':prefs[k],'raw_ranking':ranking[k],'delivered':guard['delivered_entity_ids'],
                    'baseline_delivered':ref['delivery']['delivered_entity_ids'],'discovery_count':len(ranking[k]),'eligible_count':guard['eligible_movies'],
                    'preferences_sha256':guard['preferences_sha256'],'intent_sha256':effective['profiles'][k]['intent_sha256'],
                    'raw_ranking_sha256':guard['raw_output_sha256'],'delivery_sha256':guard['delivered_output_sha256'],
                    'excluded_removed':guard['excluded_entity_ids'],'selection_changed':guard['selection_changed'],
                    'delivery_policy':guard['policy'],'baseline_information_policy':ref['information_policy'],
                    'baseline_delivery_sha256':ref['delivery']['delivered_output_sha256'],
                    'known_favorite_count':guard['known_favorite_count'],'preference_gate':'PASS','shared_execution_id':packet['execution_id'],
                    'correlated_projection':True,'human_quality_validated':False,'satisfaction_score':None}
                name = 'cinema-result-'+k+'.json'
                if name in before: need(same(read(directory/name),result),'correlated projection differs'); results[k]=result
            if len(suffix)>=7: need(same(suffix[6]['data'],{k:before['cinema-result-'+k+'.json'] for k in ('A','B')}),'projection seals')
    else: need(not packet_present,'packet before admitted request')
    need(packet_present or not any('cinema-result-'+k+'.json' in before for k in ('A','B')),'projection without shared packet')
    need(set(report)=={'schema_version','run_id','mode','protocol_version','source','phase','created_utc','plan_sha256','status','qloo_attempts','model_attempts','error_class','cinema_results','preference_gate','cultural_gate','release_gate','decision_scope','independent_validation_claim'},'closed joint report')
    need(type(report['schema_version']) is int and report['schema_version']==9 and report['run_id']==directory.name and report['mode']==plan['mode']
         and report['protocol_version']==PROTOCOL and report['source']==source and report['phase']=='CONFIRMED_DISCOVERIES'
         and report['plan_sha256']==plan['plan_sha256'] and report['status'] in ('COMPLETE','INCOMPLETE')
         and report['decision_scope']==plan['decision_scope'] and report['independent_validation_claim'] is False
         and report['cultural_gate']=='NOT_VALIDATED' and report['release_gate']=='BLOCKED','joint report identity/claims')
    instant(report['created_utc'])
    need(type(report['qloo_attempts']) is int and report['qloo_attempts']==identity['qloo_attempts']+min(2,max(0,len(suffix)-1))
         and type(report['model_attempts']) is int and report['model_attempts']==int(prepared),'cumulative budgets')
    need(report['error_class'] is None if complete else isinstance(report['error_class'],str) and bool(report['error_class']),'stop class')
    need(same(report['cinema_results'],results) and report['preference_gate']==('PASS' if complete else 'NOT_EVALUATED')
         and (not complete or len(results)==2 and packet_present),'complete shared denominator')
    allowed = set(identity['artifact_sha256'])|{'pair-confirmation.json','individual-report.json','individual-tool-inputs.json','model-manifest.json','pair-execution-001.json',
        'cinema-result-A.json','cinema-result-B.json'}|set(sample_names)
    need(set(before)<=allowed and inventory(directory)==before,'unknown artifact or concurrent mutation')
    return {**report,'verified_utc':utc_now(),'verification_status':'VERIFIED_COMPLETE' if complete else 'VERIFIED_PARTIAL',
        'provenance':identity['provenance'],'artifact_sha256':before,'verified_provider_samples':identity['verified_provider_samples']+len(sample_names),
        'verified_model_packets':int(packet_present),'chosen_identities':profiles,'chosen_movie_inputs':movies,'movie_queries':request['movie_queries'],
        'movie_input_gate':'PASS' if complete else 'NOT_EVALUATED','shared_model_calls':int(packet_present),'correlated_projections':len(results),
        'independent_model_decisions':False,'external_service_attested':False,'causal_gate':'NOT_EVALUATED','behavioral_gate':'NOT_EVALUATED','integration_gate':'NOT_EVALUATED'}

def verify_confirmed_discoveries(directory):
    try: return _confirmed(checked_path(directory))
    except SchemaError: raise
    except (KeyError,ValueError,TypeError,OSError,IndexError,AttributeError) as exc:
        raise SchemaError('Paired capture evidence invalid.') from exc
