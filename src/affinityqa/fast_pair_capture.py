"""Confirmed identities followed by one joint inference; no legacy file rewritten."""
import copy
from pathlib import Path
from .agents import strict_json
from .errors import AffinityQAError
from .evidence import Ledger, fingerprint, utc_now
from .individual_capture import safe_directory_path, validate_capture_paths, execution_lease, sha
from .groq_agent import contains_secret
from .cinema_identity_verify import selection_profiles
from .cinema_movie_inputs import compile_preferences
from .cinema_discoveries_v4 import qloo_request, context_from_sample, make_request, deliver, baseline
from .cinema_discovery_v4_capture import SOURCES as SEALED
from .qloo import QlooClient, LiveTransport
from .fast_pair import PROTOCOL, SOURCE, need, validate_request, child_request, pair_request, cache_key
from .fast_pair_agent import FastPairMovieAgent, model_manifest

SOURCES = (*SEALED, 'fast_pair.py','fast_pair_agent.py','fast_pair_capture.py','fast_pair_verify.py')

def identity_functions(request):
    if any(request['movie_queries'].values()):
        from .cinema_discovery_v4_capture import prepare_plan, search_identities
    else:
        from .cinema_discovery_v3_capture import prepare_plan, search_identities
    return prepare_plan, search_identities

def prepare_plan(request, output, *, minimum_model_interval_seconds=None):
    request = validate_request(request)
    output = safe_directory_path(Path(output)); validate_capture_paths(output)
    need(not output.exists() and output.parent.is_dir(),'new output and existing parent required')
    child = identity_functions(request)[0](child_request(request),output,minimum_model_interval_seconds=minimum_model_interval_seconds)
    source = Path(__file__).resolve().parent
    value = {'schema_version':9,'protocol_version':PROTOCOL,'mode':'cinema-paired-discovery-capture','request':request,
        'output_directory':str(output),'identity_plan':child,'remote_operator':model_manifest('remote-llm'),
        'source_sha256':{n:sha(source/n) for n in SOURCES},'driver_sha256':sha(source/'fast_pair_capture.py'),
        'verification_driver_sha256':sha(source/'fast_pair_verify.py'),
        'dependencies_lock_sha256':sha(source.parents[1]/'requirements-backend.lock.txt'),
        'maximum_qloo_requests':4+sum(map(len,request['movie_queries'].values())),
        'maximum_identity_search_requests':2,'maximum_movie_search_requests':sum(map(len,request['movie_queries'].values())),
        'maximum_insights_requests':2,'maximum_model_decisions':1,'maximum_attempts_per_request':1,
        'identity_candidate_contract':child['identity_candidate_contract'],
        'movie_candidate_contract':'qloo-confirmed-movie-title-year-v1','faults':[],
        'execution_pacing':{'strategy':'one-joint-send-no-intercall-wait','minimum_interval_seconds':0},
        'decision_scope':'one-shared-call-two-correlated-projections','maximum_token_reservation':8000,
        'independent_validation_claim':False,'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}
    value['plan_sha256'] = fingerprint(value)
    return value

def search_identities(request, output, expected_plan_hash, settings, *, minimum_model_interval_seconds=None, _test_adapters=None):
    plan = prepare_plan(request,output,minimum_model_interval_seconds=minimum_model_interval_seconds)
    need(plan['plan_sha256']==expected_plan_hash,'reviewed pair plan changed')
    old = plan['identity_plan']
    report, directory = identity_functions(plan['request'])[1](child_request(plan['request']),output,old['plan_sha256'],settings,
        minimum_model_interval_seconds=minimum_model_interval_seconds,_test_adapters=_test_adapters)
    with (directory/'pair-plan.json').open('x',encoding='utf-8') as handle:
        import json
        json.dump(plan,handle,ensure_ascii=False,allow_nan=False,indent=2)
    return {**report,'protocol_version':PROTOCOL,'plan_sha256':plan['plan_sha256']}, directory

def capture_confirmed(directory, selected_entity_ids, identity_receipt, settings, remote_key, *, selected_movie_entity_ids, _test_adapters=None, _test_pacing_clock=None):
    from .fast_pair_verify import verify_discovery_search, selection_movies
    directory = safe_directory_path(Path(directory))
    need(_test_pacing_clock is None,'paired protocol has no simulated or intercall pacing')
    with execution_lease(directory.parent.parent):
        current = verify_discovery_search(directory)
        clean = lambda r:{k:v for k,v in r.items() if k!='verified_utc'}
        need(fingerprint(clean(current))==fingerprint(clean(identity_receipt)),'identity receipt changed')
        profiles = selection_profiles(current,selected_entity_ids)
        movies = selection_movies(current,selected_movie_entity_ids)
        plan = strict_json((directory/'pair-plan.json').read_bytes()); request = plan['request']
        prefs = {k:compile_preferences(request['catalog'],request['preferences'][k],movies[k]) for k in ('A','B')}
        secrets = (settings.api_key,remote_key)
        need(all(isinstance(s,str) and len(s)>=20 for s in secrets),'private provider configuration required')
        need(not contains_secret((plan,identity_receipt,profiles,prefs),secrets),'private values in confirmed data')
        testing = _test_adapters is not None
        need(current['provenance']==('SIMULATION_ONLY' if testing else 'RECORDED_REMOTE_EXECUTION'),'mixed execution provenance')
        ledger = Ledger.__new__(Ledger)
        ledger.directory, ledger.run_id, ledger.source, ledger.secrets = directory,directory.name,'test-double-only' if testing else SOURCE,secrets
        ledger.events = [strict_json(x) for x in (directory/'ledger.jsonl').read_bytes().splitlines()]
        ledger.live_requests = current['qloo_attempts']
        confirmation = {'protocol':PROTOCOL,'plan_sha256':plan['plan_sha256'],'identity_receipt':copy.deepcopy(identity_receipt),
            'selected_entity_ids':copy.deepcopy(selected_entity_ids),'selected_movie_entity_ids':copy.deepcopy(selected_movie_entity_ids),
            'profiles':profiles,'movies':movies,'preferences':prefs}
        ledger.write('pair-confirmation.json',confirmation)
        ledger.record('pair_confirmed',{'confirmation_sha256':sha(directory/'pair-confirmation.json')})
        report = {'schema_version':9,'run_id':directory.name,'mode':plan['mode'],'protocol_version':PROTOCOL,'source':ledger.source,
            'phase':'CONFIRMED_DISCOVERIES','created_utc':utc_now(),'plan_sha256':plan['plan_sha256'],'status':'INCOMPLETE',
            'qloo_attempts':current['qloo_attempts'],'model_attempts':0,'error_class':None,'cinema_results':{},
            'preference_gate':'NOT_EVALUATED','cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED',
            'decision_scope':'one-shared-call-two-correlated-projections','independent_validation_claim':False}
        client = engine = None
        factories = _test_adapters or (lambda:FastPairMovieAgent(remote_key,forbidden_secrets=(settings.api_key,)),lambda:LiveTransport(settings,timeout=120))
        try:
            client = QlooClient(factories[1](),ledger,max_requests=plan['maximum_qloo_requests'],max_attempts=1)
            client.requests = current['qloo_attempts']
            contexts = {}
            for label in ('A','B'):
                client.get('/v2/insights',qloo_request(profiles[label],request['catalog'],prefs[label])['params'],cache=False)
                sample_path = directory/ledger.events[-1]['data']['sample']; sample = strict_json(sample_path.read_bytes())
                contexts[label] = context_from_sample(profiles[label],request['catalog'],prefs[label],sample,sha(sample_path))
            ledger.write('individual-tool-inputs.json',contexts)
            ledger.record('pair_inputs_frozen',{'sha256':fingerprint(contexts)})
            engine = factories[0]()
            need(engine.calls==0 and fingerprint(engine.manifest)==fingerprint(model_manifest('test-double-only' if testing else 'remote-llm')),'closed paired engine')
            engine.dispatch_ledger = ledger
            ledger.write('model-manifest.json',engine.manifest)
            effective = pair_request({k:make_request(request['catalog'],profiles[k],contexts[k],prefs[k],'pair-'+directory.name+'-'+k) for k in ('A','B')},'pair-'+directory.name)
            response = engine.rank(effective)
            packet = {'execution_id':directory.name+'/1','effective_request':effective,'model_payload':copy.deepcopy(engine.last_input),
                'response':response,'observation':copy.deepcopy(engine.observations[-1]),'joint_cache_key_sha256':cache_key(effective,engine.manifest)}
            from .fast_pair_verify import verify_packet
            checked = verify_packet(packet,engine.manifest,contexts)
            ledger.write('pair-execution-001.json',packet)
            ledger.record('pair_execution_recorded',{'packet_sha256':sha(directory/'pair-execution-001.json')})
            for label in ('A','B'):
                raw = checked[label]; guard = deliver(raw,request['catalog'],prefs[label]); ref = baseline(contexts[label],request['catalog'],prefs[label])
                result = {'profile':profiles[label],'preferences':prefs[label],'raw_ranking':raw,'delivered':guard['delivered_entity_ids'],
                    'baseline_delivered':ref['delivery']['delivered_entity_ids'],'discovery_count':len(raw),'eligible_count':guard['eligible_movies'],
                    'preferences_sha256':guard['preferences_sha256'],'intent_sha256':effective['profiles'][label]['intent_sha256'],
                    'raw_ranking_sha256':guard['raw_output_sha256'],'delivery_sha256':guard['delivered_output_sha256'],
                    'excluded_removed':guard['excluded_entity_ids'],'selection_changed':guard['selection_changed'],
                    'delivery_policy':guard['policy'],'baseline_information_policy':ref['information_policy'],
                    'baseline_delivery_sha256':ref['delivery']['delivered_output_sha256'],
                    'known_favorite_count':guard['known_favorite_count'],'preference_gate':'PASS',
                    'shared_execution_id':packet['execution_id'],'correlated_projection':True,'human_quality_validated':False,'satisfaction_score':None}
                ledger.write('cinema-result-'+label+'.json',result); report['cinema_results'][label] = result
            ledger.record('pair_projections_recorded',{'A':sha(directory/'cinema-result-A.json'),'B':sha(directory/'cinema-result-B.json')})
            report.update(status='COMPLETE',preference_gate='PASS')
        except BaseException as exc:
            report['error_class'] = type(exc).__name__
            ledger.record('stopped_without_retry',{'error_class':type(exc).__name__})
            if not isinstance(exc,(AffinityQAError,OSError)):
                raise
        finally:
            report['qloo_attempts'] = getattr(client,'requests',current['qloo_attempts'])
            report['model_attempts'] = getattr(engine,'calls',0)
            ledger.write('individual-report.json',report)
        return report,directory
