"""Single reviewed identity amendment. Dry-run by default; no core changes."""
import argparse
import copy
import re
import time
import unicodedata
from pathlib import Path

from run_causal_repair import (ROOT, SOURCES, FRESH, DIGEST, read, sha, inputs,
    PROTOCOL, FAULTS, ToolContextMovieAgent, profile_hash, context_from_sample,
    capture_pair, Settings, LiveTransport, QlooClient, parse_entities,
    Ledger, fingerprint, utc_now, AffinityQAError, SchemaError, json)

PARENT='20261004T114624Z-a1722335'
INTERRUPTED='20261004T122430Z-3986e92d'
RULE=('NFKC casefold whitespace exact name; unique artist preferred; otherwise '
      'unique person with explicit musical occupation or music-service identity; '
      'same-type ambiguity stops, with no substitution or retry.')

def exact(value):
    return ' '.join(unicodedata.normalize('NFKC',value).casefold().split())

def resolve_musical(name, entities):
    matches=[e for e in entities if exact(e.name)==exact(name)]
    artists=[e for e in matches if 'urn:entity:artist' in e.types]
    if len(artists)>1:raise SchemaError('Multiple exact artist identities: '+name)
    if artists:return artists[0]
    persons=[e for e in matches if 'urn:entity:person' in e.types]
    if len(persons)!=1:raise SchemaError('No unique exact musical person: '+name)
    e=persons[0];m=e.metadata
    occupations=m.get('occupations',m.get('occupation',[]))
    if isinstance(occupations,str):occupations=[occupations]
    if not isinstance(occupations,list):occupations=[]
    accepted={'musician','singer','singer songwriter','songwriter','rapper','composer','pianist','guitarist','harpist','record producer','music producer'}
    musical=any(isinstance(v,str) and ' '.join(re.sub(r'[_-]',' ',v.casefold()).split()) in accepted for v in occupations)
    external=m.get('external',{})
    service=isinstance(external,dict) and any(isinstance(external.get(k),dict) and bool(external[k].get('id')) for k in ('musicbrainz','lastfm','spotify'))
    if not (musical or service):raise SchemaError('Person lacks explicit musical identity evidence: '+name)
    return e

def checked_inputs():
    original=Path(__file__).with_name('run_causal_repair.py')
    catalog,_,origin=inputs()
    receipts={}
    for run in (PARENT,INTERRUPTED):
        path=ROOT/'evidence'/('CAUSAL-REPAIR-'+run+'.json');receipt=read(path)
        if receipt['driver_sha256']!=sha(original):raise SchemaError('Original driver changed.')
        for name,h in receipt['artifact_sha256'].items():
            p=(ROOT/'runs'/run/name).resolve()
            if not p.is_relative_to((ROOT/'runs'/run).resolve()) or sha(p)!=h:raise SchemaError('Prior run evidence changed.')
            origin[p.relative_to(ROOT).as_posix()]=h
        origin[path.relative_to(ROOT).as_posix()]=sha(path);receipts[run]=receipt
    parent=receipts[PARENT];prior=receipts[INTERRUPTED]
    if parent['status']!='COMPLETE' or parent['causal_gate']!='PASS' or parent['behavioral_gate']!='OBSERVED_RECOVERY':raise SchemaError('Development not qualified.')
    if prior['status']!='INCOMPLETE' or prior['model_calls']!=0 or prior.get('model_attempts')!=0 or prior['qloo_requests']!=1 or prior['pairs']:raise SchemaError('Interrupted run is not the permitted pre-model failure.')
    policy=read(ROOT/'runs'/PARENT/'frozen-causal-policy.json')
    if policy['policy_sha256']!=fingerprint({k:v for k,v in policy.items() if k!='policy_sha256'}):raise SchemaError('Frozen policy hash changed.')
    oldplan=read(ROOT/'runs'/INTERRUPTED/'causal-plan.json')
    expected=[{'pair_id':f'causal-validation-{i:02d}','artists':{'A':a,'B':b},'split':'validation'} for i,(a,b) in enumerate(FRESH,1)]
    if oldplan['pairs']!=expected or oldplan['catalog']!=catalog or oldplan['parent_run']!=PARENT:raise SchemaError('Interrupted protocol mismatch.')
    for name in SOURCES:
        h=sha(ROOT/'src/affinityqa'/name)
        if policy['source_sha256'][name]!=h or oldplan['source_sha256'][name]!=h:raise SchemaError('Frozen core changed: '+name)
    samplepath=ROOT/'runs'/INTERRUPTED/'http-0002.json';sample=read(samplepath)
    if sample['status']!=200 or sample['request']['path']!='/search' or sample['request']['params']!={'query':'Alice Coltrane','take':5} or fingerprint(sample['response'])!=sample['response_sha256']:raise SchemaError('Reused lookup provenance changed.')
    resolve_musical('Alice Coltrane',parse_entities(sample['response'],insights=False))
    return catalog,policy,oldplan,sample,origin,{'interrupted_run':INTERRUPTED,'interrupted_receipt_sha256':sha(ROOT/'evidence'/('CAUSAL-REPAIR-'+INTERRUPTED+'.json')),'reused_sample':{'path':samplepath.relative_to(ROOT).as_posix(),'sha256':sha(samplepath)},'identity_resolution':RULE,'before_model_outputs':True}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--url',default='http://192.168.173.1:11434');args=parser.parse_args()
    catalog,policy,oldplan,sample,origin,amendment=checked_inputs()
    if not args.execute:
        print(json.dumps({'amendment':amendment,'pairs':oldplan['pairs'],'maximum_new_qloo_requests':23,'maximum_total_qloo_requests':24,'maximum_model_calls':234,'sequence':'reuse Alice; resolve11; freeze12 identities; capture12 insights; freeze inputs; run234 model calls','policy_sha256':policy['policy_sha256']},indent=2));return 0
    if any(read(p).get('amendment',{}).get('interrupted_run')==INTERRUPTED for p in (ROOT/'runs').glob('*/causal-plan.json')):raise SchemaError('This continuation has already been attempted.')
    engine=ToolContextMovieAgent(args.url,'qwen38:cyber-32k',timeout=45,max_calls=39)
    if engine.manifest['model_digest']!=DIGEST or engine.manifest!=policy['model_manifest']:raise SchemaError('Model identity or options changed.')
    settings=Settings.from_environment(ROOT/'.env',use_process_environment=False);ledger=Ledger(ROOT/'runs','qloo-tool+local-llm',(settings.api_key,))
    plan=copy.deepcopy(oldplan);plan.pop('plan_sha256')
    plan.update(schema_version=2,created_utc=utc_now(),maximum_qloo_requests=23,total_maximum_qloo_requests=24,
        original_driver_sha256=sha(Path(__file__).with_name('run_causal_repair.py')),driver_sha256=sha(Path(__file__)),
        source_artifact_sha256=origin,amendment=amendment,capture='Reuse prior Alice search; eleven fresh searches; seal every identity before twelve Insights calls; original causal operator and policy unchanged.')
    plan['plan_sha256']=fingerprint(plan);ledger.write('causal-plan.json',plan);ledger.record('plan_frozen',{'model_calls':0,'qloo_calls':0});print('RUN '+ledger.run_id,flush=True)
    client=QlooClient(LiveTransport(settings,timeout=120),ledger,max_requests=23,max_attempts=1);last=None
    def get(path,params):
        nonlocal last
        if last is not None:time.sleep(max(0,1-(time.monotonic()-last)))
        last=time.monotonic();body=client.get(path,params,cache=False)
        event=next(e for e in reversed(ledger.events) if e['kind']=='tool_call');p=ledger.directory/event['data']['sample'];return body,read(p),sha(p)
    engines=[engine];pairs=plan['pairs']
    result={'schema_version':2,'protocol_version':PROTOCOL,'status':'INCOMPLETE','run_id':ledger.run_id,'source':'qloo-tool+local-llm','mode':'validation','causal_gate':'NOT_EVALUATED','behavioral_gate':'NOT_EVALUATED','cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED','release_approved':False,'model_calls':0,'qloo_requests':0,'reused_qloo_requests':1,'total_qloo_requests':1,'denominator':18,'passing':0,'pairs':[],'error':None,'plan_sha256':plan['plan_sha256']}
    try:
        identities={}
        for pair in pairs:
            profiles={}
            for p,name in pair['artists'].items():
                body=sample['response'] if pair['pair_id']=='causal-validation-01' and p=='A' else get('/search',{'query':name,'take':5})[0]
                entity=resolve_musical(name,parse_entities(body,insights=False))
                profiles[p]={'entity_id':entity.entity_id,'name':' '.join(unicodedata.normalize('NFKC',name).split()),'type':'urn:entity:artist' if 'urn:entity:artist' in entity.types else 'urn:entity:person'}
            identities[pair['pair_id']]=profiles
        if len({v['entity_id'] for profiles in identities.values() for v in profiles.values()})!=12:raise SchemaError('Original identities coincide.')
        ledger.write('causal-identities.json',identities);ledger.record('all_identities_frozen',{'sha256':fingerprint(identities),'model_calls':0,'qloo_calls':client.requests})
        captured={}
        for pair in pairs:
            key=pair['pair_id'];profiles=identities[key];contexts={}
            for p in ('A','B'):
                profile=profiles[p];_,packet,h=get('/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,'signal.interests.entities':profile['entity_id'],'filter.results.entities':','.join(sorted(r['entity_id'] for r in catalog))})
                contexts[profile_hash(profile)]=context_from_sample(profile,catalog,packet,h)
            captured[key]={'profiles':profiles,'contexts':contexts};print(f'{key} tool inputs complete; new Qloo{client.requests}/23',flush=True)
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
    result['qloo_requests']=client.requests;result['total_qloo_requests']=client.requests+1;ledger.write('causal-report.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='pairs'},indent=2));return 0 if result['status']=='COMPLETE' and result['causal_gate']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
