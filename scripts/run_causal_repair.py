"""Explicit bounded causal study. No retries, evaluation-answer copying or publishing."""
import argparse,hashlib,json,sys,time,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from affinityqa.causal_agent import PROTOCOL,FAULTS,ToolContextMovieAgent,profile_hash,context_from_sample
from affinityqa.causal_runner import capture_pair,freeze_policy
from affinityqa.qloo import Settings,LiveTransport,QlooClient
from affinityqa.models import parse_entities,resolve_seed
from affinityqa.evidence import Ledger,fingerprint,utc_now
from affinityqa.errors import AffinityQAError,SchemaError

DIGEST='d9a13ce0551de860f380e7661ad70f01cf2e1f76cbab93aa5e32177dd9bcbda8'
SOURCES=('causal_agent.py','causal_runner.py','causal_evaluator.py','ollama_agent.py','qloo.py','models.py','metrics.py','evidence.py')
FRESH=(('Alice Coltrane','Lil Nas X'),('Kraftwerk','Halsey'),('Slowdive','Post Malone'),('Trent Reznor','Ice Spice'),('Autechre','Lana Del Rey'),('Mogwai','Kesha'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf8'))


def inputs():
    path=ROOT/'runs/20261004T082339Z-baec76ec/http-0002.json';sample=read(path)
    if sample['status']!=200 or fingerprint(sample['response'])!=sample['response_sha256']:raise SchemaError('Catalog provenance changed.')
    rows=parse_entities(sample['response'],insights=False)
    catalog=sorted([{'entity_id':r.entity_id,'name':r.name,'release_year':r.metadata['release_year']} for r in rows],key=lambda r:r['entity_id'])
    seedpath=ROOT/'runs/20261004T082339Z-baec76ec/broad-movie-plan.json';seed=read(seedpath)['seeds']['mutation-01']
    known={'A':{'entity_id':seed['A'],'name':'Brian Eno','type':'urn:entity:artist'},'B':{'entity_id':seed['B'],'name':'Bad Bunny','type':'urn:entity:artist'}}
    return catalog,known,{p.relative_to(ROOT).as_posix():sha(p) for p in (path,seedpath)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('development','validation'));parser.add_argument('--execute',action='store_true');parser.add_argument('--parent');parser.add_argument('--url',default='http://192.168.173.1:11434');args=parser.parse_args()
    catalog,known,origin=inputs();development=args.mode=='development';count=1 if development else 6
    pairs=[{'pair_id':'causal-development-01','artists':{'A':'Brian Eno','B':'Bad Bunny'},'split':'development'}] if development else [{'pair_id':f'causal-validation-{i:02d}','artists':{'A':a,'B':b},'split':'validation'} for i,(a,b) in enumerate(FRESH,1)]
    if not args.execute:print(json.dumps({'mode':args.mode,'pairs':pairs,'maximum_model_calls':39*count,'maximum_qloo_requests':2 if development else 24,'new_independent_cultural_references':0}));return 0
    if any(read(p).get('mode')==args.mode for p in (ROOT/'runs').glob('*/causal-plan.json')):raise SystemExit('This mode has already been attempted. No budget expansion or automatic rerun.')
    parent=None;policy=None
    if not development:
        from affinityqa.store import RUN_ID
        if not args.parent or not RUN_ID.fullmatch(args.parent):raise SchemaError('Validation needs an independently verified development run.')
        parent_path=ROOT/'evidence'/('CAUSAL-REPAIR-'+args.parent+'.json');parent=read(parent_path)
        if parent['status']!='COMPLETE' or parent['causal_gate']!='PASS' or parent['behavioral_gate']!='OBSERVED_RECOVERY':raise SchemaError('Development did not qualify for new validation.')
        if parent['driver_sha256']!=sha(Path(__file__)):raise SchemaError('Frozen experiment driver changed.')
        for name,h in parent['artifact_sha256'].items():
            if sha(ROOT/'runs'/args.parent/name)!=h:raise SchemaError('Development evidence changed.')
        policy=read(ROOT/'runs'/args.parent/'frozen-causal-policy.json')
        if policy['policy_sha256']!=fingerprint({k:v for k,v in policy.items() if k!='policy_sha256'}):raise SchemaError('Policy hash changed.')
        for name,h in policy['source_sha256'].items():
            if sha(ROOT/'src/affinityqa'/name)!=h:raise SchemaError('Frozen operator changed before validation.')
    engine=ToolContextMovieAgent(args.url,'qwen38:cyber-32k',timeout=45,max_calls=39)
    if engine.manifest['model_digest']!=DIGEST or (policy is not None and engine.manifest!=policy['model_manifest']):raise SchemaError('Model identity or options changed.')
    settings=Settings.from_environment(ROOT/'.env',use_process_environment=False);ledger=Ledger(ROOT/'runs','qloo-tool+local-llm',(settings.api_key,))
    plan={'schema_version':1,'protocol_version':PROTOCOL,'created_utc':utc_now(),'mode':args.mode,'pairs':pairs,'faults':list(FAULTS),'repeats':3,
          'maximum_model_calls':39*count,'maximum_qloo_requests':2 if development else 24,'maximum_attempts_per_request':1,'catalog':catalog,'catalog_sha256':fingerprint(catalog),'manifest':engine.manifest,
          'source_sha256':{n:sha(ROOT/'src/affinityqa'/n) for n in SOURCES},'driver_sha256':sha(Path(__file__)),'source_artifact_sha256':origin,
          'capture':'One untyped name lookup per fresh explicit interest; exactly one normalized exact artist/person match required. One complete direct Qloo movie snapshot per interest. No profile replacement, automatic retry, partial scores or direct quality-reference capture.',
          'model_accounting':'Per pair6healthy +3repeats*(cache1fault+2repair +stale2fault+2repair +tool2fault+2repair)=39. Three healthy equivalent-request controls and nine repaired equivalent-request controls use cache, not additional model calls.',
          'selection':'Every pair and every fault required. Healthy stability, trace-driven diagnosis, single supported patch, new model executions, profile integrity, no behavioral regression and no false alarm must all pass. Independent cultural quality NOT_VALIDATED; public release BLOCKED.',
          'behavioral_claim':'Only count recovery where faulty→healthy exceeds frozen noise and repaired→everyhealthy stays within it. Require at least one observed behavioral recovery in the declared cache fault in development before validation; do not count no-effect as recovery.',
          'boundary':'Public explicit musical interests and convenience fixed movie catalog. New original validation profiles after policy freeze; some appeared as indirect neighbors, and TrentReznor relates to prior NineInchNails. Not independent people, human preferences, population reliability, or provider-repeat stability.',
          'parent_run':args.parent,'parent_receipt_sha256':None if development else sha(parent_path),'new_independent_cultural_reference_calls':0,'release_approved':False}
    plan['plan_sha256']=fingerprint(plan);ledger.write('causal-plan.json',plan);ledger.record('plan_frozen',{'model_calls':0,'qloo_calls':0});print('RUN '+ledger.run_id,flush=True)
    client=QlooClient(LiveTransport(settings,timeout=120),ledger,max_requests=plan['maximum_qloo_requests'],max_attempts=1);last=None
    def get(path,params):
        nonlocal last
        if last is not None:time.sleep(max(0,1-(time.monotonic()-last)))
        last=time.monotonic();body=client.get(path,params,cache=False)
        event=next(e for e in reversed(ledger.events) if e['kind']=='tool_call');p=ledger.directory/event['data']['sample'];return body,read(p),sha(p)
    engines=[engine]
    result={'schema_version':1,'protocol_version':PROTOCOL,'status':'INCOMPLETE','run_id':ledger.run_id,'source':'qloo-tool+local-llm','mode':args.mode,
            'causal_gate':'NOT_EVALUATED','behavioral_gate':'NOT_EVALUATED','cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED','release_approved':False,'model_calls':0,'qloo_requests':0,'denominator':count*3,'passing':0,'pairs':[],'error':None,'plan_sha256':plan['plan_sha256']}
    try:
        captured={}
        # Resolve and collect the entire declared tool input set before inference.
        for pair in pairs:
            key=pair['pair_id'];profiles=known if development else {}
            if not development:
                for p,name in pair['artists'].items():
                    body,_,_=get('/search',{'query':name,'take':5});entity=resolve_seed({'name':name,'accepted_names':[name],'accepted_types':['urn:entity:artist','urn:entity:person']},parse_entities(body,insights=False),synthetic=False)
                    profiles[p]={'entity_id':entity.entity_id,'name':' '.join(unicodedata.normalize('NFKC',name).split()),'type':'urn:entity:artist' if 'urn:entity:artist' in entity.types else 'urn:entity:person'}
            if len({profile_hash(p) for p in profiles.values()})!=2:raise SchemaError('Profiles unexpectedly coincide.')
            contexts={}
            for p in ('A','B'):
                profile=profiles[p];_,sample,h=get('/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,'signal.interests.entities':profile['entity_id'],'filter.results.entities':','.join(sorted(r['entity_id'] for r in catalog))})
                context=context_from_sample(profile,catalog,sample,h);contexts[profile_hash(profile)]=context
            captured[key]={'profiles':profiles,'contexts':contexts};print(f'{key} tool inputs complete; Qloo{client.requests}/{plan["maximum_qloo_requests"]}',flush=True)
        ledger.write('causal-tool-inputs.json',captured);ledger.record('all_tool_inputs_frozen',{'sha256':fingerprint(captured),'model_calls':0,'qloo_calls':client.requests})
        def progress(key,phase,repeat,calls):print(f'{key} {phase} repeat{repeat}: {calls}/39 actual model calls',flush=True)
        for i,pair in enumerate(pairs):
            if i:
                engine=ToolContextMovieAgent(args.url,'qwen38:cyber-32k',timeout=45,max_calls=39);engines.append(engine)
            if engine.manifest!=plan['manifest']:raise SchemaError('Model options changed during execution.')
            # Every pair needs unique recorded IDs even though its engine counter
            # is bounded at39. Separate per-pair ledger stores actual executions.
            pair_ledger=Ledger(ledger.directory/'pair-executions','qloo-tool+local-llm',(settings.api_key,));ledger.write('causal-execution-binding-'+pair['pair_id']+'.json',{'pair_id':pair['pair_id'],'directory':pair_ledger.directory.relative_to(ledger.directory).as_posix()})
            pair_ledger.write('model-manifest.json',engine.manifest);pair_ledger.write('model-readiness.json',engine.warmup())
            def freeze(noise,healthy,controls):return freeze_policy(noise,healthy,controls,plan=plan,manifest=engine.manifest,ledger=ledger)
            entry=captured[pair['pair_id']];record,summary,policy=capture_pair(engine,pair_ledger,pair,catalog,entry['profiles'],entry['contexts'],policy=policy,freeze=freeze,progress=progress)
            ledger.write('causal-pair-'+pair['pair_id']+'.json',record);result['pairs'].append(summary);result['model_calls']+=engine.calls
        result['status']='COMPLETE';result['passing']=sum(c['passing'] for p in result['pairs'] for c in p['cases'])
        result['causal_gate']='PASS' if result['passing']==result['denominator'] else 'FAIL'
        observed=sum(c['behavioral_recovery_observed_repeats'] for p in result['pairs'] for c in p['cases'])
        cache_observed=sum(c['behavioral_recovery_observed_repeats'] for p in result['pairs'] for c in p['cases'] if c['fault']=='cache-omits-profile')
        result.update(behavioral_gate='OBSERVED_RECOVERY' if observed and cache_observed else 'INCONCLUSIVE',behavioral_recoveries_observed=observed,cache_behavioral_recoveries=cache_observed,policy_sha256=policy['policy_sha256'],noise_barrier=policy['noise_barrier'])
        if not development:ledger.write('frozen-causal-policy.json',policy)
    except AffinityQAError as exc:
        result['error']=str(exc);ledger.record('stopped',{'error_class':type(exc).__name__,'reason':str(exc)})
        # Count completed and current attempted model requests without losing partial evidence.
        result['model_calls']=sum(len(list(p.glob('causal-execution-*.json'))) for p in (ledger.directory/'pair-executions').glob('*'))
        result['model_attempts']=sum(e.calls for e in engines)
    result['qloo_requests']=client.requests;ledger.write('causal-report.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='pairs'},indent=2));return 0 if result['status']=='COMPLETE' and result['causal_gate']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
