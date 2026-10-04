"""Search observations amendment only; frozen causal modules remain unchanged."""
from continue_causal_validation import (
    argparse, copy, time, unicodedata, Path, ROOT, SOURCES, FRESH, DIGEST,
    read, sha, PROTOCOL, ToolContextMovieAgent, profile_hash, context_from_sample,
    capture_pair, Settings, LiveTransport, QlooClient, parse_entities, Ledger,
    fingerprint, utc_now, AffinityQAError, SchemaError, json,
    PARENT, INTERRUPTED, RULE, exact, resolve_musical, checked_inputs)
from affinityqa.models import validate_response_envelope

SECOND_STOP='20261004T122943Z-c400e1fb'
SEARCH_RULE=('Validate every raw search observation independently. Exact raw '
    'duplicates collapse with audit. Same UUID with conflicting normalized name '
    'or overlapping types and differing metadata stops. Disjoint-type observations '
    'remain separate; no metadata fusion; apply unchanged exact musical selector. '
    'Never apply this adapter to Insights rankings.')

def search_observations(body):
    validate_response_envelope(body,insights=False)
    entities=[];seen=[];audit=[]
    for index,row in enumerate(body['results']):
        parsed=parse_entities({'results':[row]},insights=False)[0]
        duplicate=False
        for previous_index,previous_raw,previous in seen:
            if previous.entity_id!=parsed.entity_id:continue
            if previous_raw==row:
                audit.append({'row':index,'same_as_row':previous_index,'entity_id':parsed.entity_id,'action':'exact_duplicate_collapsed'})
                duplicate=True;break
            if exact(previous.name)!=exact(parsed.name):raise SchemaError('Search UUID has conflicting names.')
            if set(previous.types)&set(parsed.types):raise SchemaError('Search UUID has conflicting same-type observations.')
            audit.append({'row':index,'same_as_row':previous_index,'entity_id':parsed.entity_id,'action':'disjoint_type_observations_preserved'})
        if not duplicate:seen.append((index,row,parsed));entities.append(parsed)
    return entities,audit

def resume_inputs():
    catalog,policy,original_plan,alice,origin,first_amendment=checked_inputs()
    receiptpath=ROOT/'evidence'/('CAUSAL-REPAIR-'+SECOND_STOP+'.json');receipt=read(receiptpath)
    driver=Path(__file__).with_name('continue_causal_validation.py')
    if receipt['driver_sha256']!=sha(driver):raise SchemaError('First continuation driver changed.')
    if receipt['status']!='INCOMPLETE' or receipt['model_calls']!=0 or receipt.get('model_attempts')!=0 or receipt['qloo_requests']!=4 or receipt['total_qloo_requests']!=5 or receipt['pairs']:raise SchemaError('Second stop is not the permitted pre-model state.')
    origin[driver.relative_to(ROOT).as_posix()]=sha(driver)
    origin[receiptpath.relative_to(ROOT).as_posix()]=sha(receiptpath)
    for name,h in receipt['artifact_sha256'].items():
        path=(ROOT/'runs'/SECOND_STOP/name).resolve()
        if not path.is_relative_to((ROOT/'runs'/SECOND_STOP).resolve()) or sha(path)!=h:raise SchemaError('Second stop evidence changed.')
        origin[path.relative_to(ROOT).as_posix()]=h
    oldplan=read(ROOT/'runs'/SECOND_STOP/'causal-plan.json')
    if oldplan['pairs']!=original_plan['pairs'] or oldplan['catalog']!=catalog or oldplan['source_sha256']!=original_plan['source_sha256'] or oldplan['manifest']!=original_plan['manifest'] or oldplan['parent_run']!=PARENT:raise SchemaError('Amendment chain protocol changed.')
    if oldplan['amendment']!=first_amendment:raise SchemaError('First amendment binding changed.')
    paths=[ROOT/'runs'/INTERRUPTED/'http-0002.json',*[ROOT/'runs'/SECOND_STOP/f'http-{n:04d}.json' for n in range(2,6)]]
    expected=['Alice Coltrane','Lil Nas X','Kraftwerk','Halsey','Slowdive'];reused={};bindings=[]
    for name,path in zip(expected,paths,strict=True):
        sample=read(path)
        if sample['status']!=200 or sample['request']!={'method':'GET','host':'https://hackathon.api.qloo.com','path':'/search','params':{'query':name,'take':5}} or sample.get('attempt')!=1 or sample.get('live_network_request') is not True or fingerprint(sample['response'])!=sample['response_sha256']:raise SchemaError('Reused search provenance changed.')
        resolve_musical(name,search_observations(sample['response'])[0]);reused[name]=sample
        bindings.append({'query':name,'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path)})
    amendment={'kind':'search-observations-v1','interrupted_run':SECOND_STOP,'interrupted_receipt_sha256':sha(receiptpath),'prior_amendment':first_amendment,'prior_driver_sha256':sha(driver),'reused_samples':bindings,'identity_resolution':RULE,'search_observation_rule':SEARCH_RULE,'before_model_outputs':True}
    return catalog,policy,oldplan,reused,origin,amendment


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--url',default='http://192.168.173.1:11434');args=parser.parse_args()
    catalog,policy,oldplan,reused,origin,amendment=resume_inputs()
    if not args.execute:
        print(json.dumps({'amendment':amendment,'pairs':oldplan['pairs'],'maximum_new_qloo_requests':19,'maximum_total_qloo_requests':24,'maximum_model_calls':234,'sequence':'reuse five recorded searches; resolve seven; freeze12 identities; capture12 insights; freeze inputs; run234 model calls','policy_sha256':policy['policy_sha256']},indent=2));return 0
    if any(read(p).get('amendment',{}).get('interrupted_run')==SECOND_STOP for p in (ROOT/'runs').glob('*/causal-plan.json')):raise SchemaError('This continuation has already been attempted.')
    engine=ToolContextMovieAgent(args.url,'qwen38:cyber-32k',timeout=45,max_calls=39)
    if engine.manifest['model_digest']!=DIGEST or engine.manifest!=policy['model_manifest']:raise SchemaError('Model identity or options changed.')
    settings=Settings.from_environment(ROOT/'.env',use_process_environment=False);ledger=Ledger(ROOT/'runs','qloo-tool+local-llm',(settings.api_key,))
    plan=copy.deepcopy(oldplan);plan.pop('plan_sha256')
    plan.update(schema_version=3,created_utc=utc_now(),maximum_qloo_requests=19,total_maximum_qloo_requests=24,
        original_driver_sha256=sha(Path(__file__).with_name('run_causal_repair.py')),driver_sha256=sha(Path(__file__)),
        source_artifact_sha256=origin,amendment=amendment,capture='Reuse five recorded searches; seven fresh searches; seal every identity before twelve Insights calls; original causal operator and policy unchanged.')
    plan['plan_sha256']=fingerprint(plan);ledger.write('causal-plan.json',plan);ledger.record('plan_frozen',{'model_calls':0,'qloo_calls':0});print('RUN '+ledger.run_id,flush=True)
    client=QlooClient(LiveTransport(settings,timeout=120),ledger,max_requests=19,max_attempts=1);last=None
    def get(path,params):
        nonlocal last
        if last is not None:time.sleep(max(0,1-(time.monotonic()-last)))
        last=time.monotonic();body=client.get(path,params,cache=False)
        event=next(e for e in reversed(ledger.events) if e['kind']=='tool_call');p=ledger.directory/event['data']['sample'];return body,read(p),sha(p)
    engines=[engine];pairs=plan['pairs']
    result={'schema_version':3,'protocol_version':PROTOCOL,'status':'INCOMPLETE','run_id':ledger.run_id,'source':'qloo-tool+local-llm','mode':'validation','causal_gate':'NOT_EVALUATED','behavioral_gate':'NOT_EVALUATED','cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED','release_approved':False,'model_calls':0,'qloo_requests':0,'reused_qloo_requests':5,'total_qloo_requests':5,'denominator':18,'passing':0,'pairs':[],'error':None,'plan_sha256':plan['plan_sha256']}
    try:
        identities={};search_audit={}
        for pair in pairs:
            profiles={}
            for p,name in pair['artists'].items():
                body=reused[name]['response'] if name in reused else get('/search',{'query':name,'take':5})[0]
                observations,audit=search_observations(body);search_audit[name]=audit
                entity=resolve_musical(name,observations)
                profiles[p]={'entity_id':entity.entity_id,'name':' '.join(unicodedata.normalize('NFKC',name).split()),'type':'urn:entity:artist' if 'urn:entity:artist' in entity.types else 'urn:entity:person'}
            identities[pair['pair_id']]=profiles
        if len({v['entity_id'] for profiles in identities.values() for v in profiles.values()})!=12:raise SchemaError('Original identities coincide.')
        ledger.write('causal-search-audit.json',search_audit);ledger.write('causal-identities.json',identities);ledger.record('all_identities_frozen',{'sha256':fingerprint(identities),'model_calls':0,'qloo_calls':client.requests})
        captured={}
        for pair in pairs:
            key=pair['pair_id'];profiles=identities[key];contexts={}
            for p in ('A','B'):
                profile=profiles[p];_,packet,h=get('/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,'signal.interests.entities':profile['entity_id'],'filter.results.entities':','.join(sorted(r['entity_id'] for r in catalog))})
                contexts[profile_hash(profile)]=context_from_sample(profile,catalog,packet,h)
            captured[key]={'profiles':profiles,'contexts':contexts};print(f'{key} tool inputs complete; new Qloo{client.requests}/19',flush=True)
        ledger.write('causal-tool-inputs.json',captured);ledger.record('all_tool_inputs_frozen',{'sha256':fingerprint(captured),'model_calls':0,'qloo_calls':client.requests})
        def progress(key,phase,repeat,calls):print(f'{key} {phase} repeat{repeat}: {calls}/39 actual model calls',flush=True)
        for i,pair in enumerate(pairs):
            if i:
                engine=ToolContextMovieAgent(args.url,'qwen38:cyber-32k',timeout=45,max_calls=39);engines.append(engine)
            if engine.manifest!=plan['manifest']:raise SchemaError('Model options changed during execution.')
            pair_ledger=Ledger(ledger.directory/'pair-executions','qloo-tool+local-llm',(settings.api_key,));ledger.write('causal-execution-binding-'+pair['pair_id']+'.json',{'pair_id':pair['pair_id'],'directory':pair_ledger.directory.relative_to(ledger.directory).as_posix()})
            pair_ledger.write('model-manifest.json',engine.manifest);pair_ledger.write('model-readiness.json',engine.warmup())
            def no_refreeze(*a,**k):raise SchemaError('Validation cannot recalibrate the frozen policy.')
            entry=captured[pair['pair_id']];record,summary,returned_policy=capture_pair(engine,pair_ledger,pair,catalog,entry['profiles'],entry['contexts'],policy=policy,freeze=no_refreeze,progress=progress)
            if returned_policy!=policy:raise SchemaError('Validation changed policy.')
            ledger.write('causal-pair-'+pair['pair_id']+'.json',record);result['pairs'].append(summary);result['model_calls']+=engine.calls
        result['status']='COMPLETE';result['passing']=sum(c['passing'] for p in result['pairs'] for c in p['cases'])
        result['causal_gate']='PASS' if result['passing']==18 else 'FAIL'
        observed=sum(c['behavioral_recovery_observed_repeats'] for p in result['pairs'] for c in p['cases'])
        cache_observed=sum(c['behavioral_recovery_observed_repeats'] for p in result['pairs'] for c in p['cases'] if c['fault']=='cache-omits-profile')
        result.update(behavioral_gate='OBSERVED_RECOVERY' if observed and cache_observed else 'INCONCLUSIVE',behavioral_recoveries_observed=observed,cache_behavioral_recoveries=cache_observed,policy_sha256=policy['policy_sha256'],noise_barrier=policy['noise_barrier'])
        ledger.write('frozen-causal-policy.json',policy)
    except AffinityQAError as exc:
        result['error']=str(exc);ledger.record('stopped',{'error_class':type(exc).__name__,'reason':str(exc)})
        result['model_calls']=sum(len(list(p.glob('causal-execution-*.json'))) for p in (ledger.directory/'pair-executions').glob('*'))
        result['model_attempts']=sum(e.calls for e in engines)
    result['qloo_requests']=client.requests;result['total_qloo_requests']=client.requests+5;ledger.write('causal-report.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='pairs'},indent=2));return 0 if result['status']=='COMPLETE' and result['causal_gate']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
