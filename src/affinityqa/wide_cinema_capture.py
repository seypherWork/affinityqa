"""Bounded two-page capture using the unchanged durable provider dispatcher."""
import copy
import re
import unicodedata
from pathlib import Path

from .agents import strict_json
from .errors import AffinityQAError
from .evidence import Ledger, fingerprint
from .groq_agent import contains_secret
from .individual_capture import safe_directory_path, validate_capture_paths, execution_lease, sha
from .provider_runtime import current_runtime
from .qloo import QlooClient, LiveTransport
from .models import canonical_id, parse_entities
from .wide_cinema_discovery import (PROTOCOL, SOURCE, need, validate_request, search_queries, movie_candidates,
    seed_identity, select_identities, qloo_request, context_from_samples, make_decision, result_for, cache_key, validate_page, text)
from .wide_cinema_agent import WideCinemaAgent, model_manifest, validate_failure_projection

SOURCES = ('wide_cinema_discovery.py','wide_cinema_agent.py','wide_cinema_capture.py','wide_cinema_verify.py',
    'qloo.py','models.py','evidence.py','errors.py','agents.py','groq_agent.py','individual_capture.py',
    'individual_verify.py','individual_remote_verify.py','provider_runtime.py','provider_scheduler.py',
    'qloo_cache.py','search_music_candidates.py','cinema_identity_capture.py','causal_agent.py',
    'wide_cinema_v3_compat.py','wide_cinema_v3_verify.py',
    'wide_cinema_v3_source/wide_cinema_discovery.py','wide_cinema_v3_source/wide_cinema_agent.py',
    'wide_cinema_v3_source/wide_cinema_capture.py','wide_cinema_v3_source/wide_cinema_verify.py',
    'wide_cinema_v4_compat.py','wide_cinema_v4_verify.py',
    'wide_cinema_v4_source/wide_cinema_discovery.py','wide_cinema_v4_source/wide_cinema_agent.py',
    'wide_cinema_v4_source/wide_cinema_capture.py','wide_cinema_v4_source/wide_cinema_verify.py',
    'wide_cinema_v5_compat.py','wide_cinema_v5_verify.py',
    'wide_cinema_v5_source/wide_cinema_discovery.py','wide_cinema_v5_source/wide_cinema_agent.py',
    'wide_cinema_v5_source/wide_cinema_capture.py','wide_cinema_v5_source/wide_cinema_verify.py',
    'wide_cinema_v6_compat.py','wide_cinema_v6_verify.py',
    'wide_cinema_v6_source/wide_cinema_discovery.py','wide_cinema_v6_source/wide_cinema_agent.py',
    'wide_cinema_v6_source/wide_cinema_capture.py','wide_cinema_v6_source/wide_cinema_verify.py',
    'wide_cinema_v7_compat.py','wide_cinema_v7_verify.py',
    'wide_cinema_v7_source/wide_cinema_discovery.py','wide_cinema_v7_source/wide_cinema_agent.py',
    'wide_cinema_v7_source/wide_cinema_capture.py','wide_cinema_v7_source/wide_cinema_verify.py',
    'wide_cinema_tokens.py',
    'wide_cinema_v8_compat.py','wide_cinema_v8_verify.py',
    'wide_cinema_v8_source/wide_cinema_discovery.py','wide_cinema_v8_source/wide_cinema_agent.py',
    'wide_cinema_v8_source/wide_cinema_capture.py','wide_cinema_v8_source/wide_cinema_verify.py',
    'wide_cinema_grounding.py',
    'wide_cinema_v9_compat.py','wide_cinema_v9_verify.py',
    'wide_cinema_v9_source/wide_cinema_discovery.py','wide_cinema_v9_source/wide_cinema_agent.py',
    'wide_cinema_v9_source/wide_cinema_capture.py','wide_cinema_v9_source/wide_cinema_verify.py')
SOURCES = (*SOURCES,'wide_cinema_v10_compat.py','wide_cinema_v10_verify.py','wide_cinema_v10_source/wide_cinema_discovery.py','wide_cinema_v10_source/wide_cinema_agent.py','wide_cinema_v10_source/wide_cinema_capture.py','wide_cinema_v10_source/wide_cinema_verify.py')
SOURCES = (*SOURCES,'wide_cinema_v11_compat.py','wide_cinema_v11_verify.py','wide_cinema_v11_source/wide_cinema_discovery.py','wide_cinema_v11_source/wide_cinema_agent.py','wide_cinema_v11_source/wide_cinema_capture.py','wide_cinema_v11_source/wide_cinema_verify.py')
DATA = ('requirements-backend.lock.txt','requirements-repeatable.lock.txt','assets/tokenizers/o200k_base.tiktoken')


class WideCinemaClient(QlooClient):
    """Only exact reviewed requests; never widen the sealed legacy validator."""
    def __init__(self, transport, ledger, requests, *, testing, maximum, initial=0):
        need(isinstance(requests,list) and 1 <= len(requests) <= 2
             and type(initial) is int and type(maximum) is int and maximum in (3,4), 'Closed wide request budget required.')
        for request in requests:
            need(isinstance(request,dict) and set(request) == {'method','host','path','params'}
                 and request['method'] == 'GET' and request['host'] == 'https://hackathon.api.qloo.com'
                 and isinstance(request['params'],dict), 'Closed Qloo host, method and parameter mapping required.')
        if requests[0]['path'] == '/search':
            need(initial == 0 and maximum == len(requests)+2, 'Search phase has one or two searches and two later pages.')
            for index,request in enumerate(requests):
                params=request['params']
                need(request['path'] == '/search' and set(params) == {'query','types','take'}
                     and type(params['take']) is int and params['take'] == 5
                     and params['query'] == text(params['query'],1,200)
                     and params['types'] in ('urn:entity:movie','urn:entity:artist,urn:entity:person'), 'Typed bounded search required.')
                if index == 1:
                    need(requests[0]['params']['types'] == 'urn:entity:artist,urn:entity:person'
                         and params['types'] == 'urn:entity:movie', 'Only a music seed can have one later favorite-film search.')
        else:
            need(len(requests) == 2 and initial in (1,2) and maximum == initial+2, 'Exactly two pages after the completed searches required.')
            first=None
            for page,request in enumerate(requests,1):
                params=request['params'];required={'filter.type','bias.trends','take','page','signal.interests.entities'}
                need(request['path'] == '/v2/insights' and required <= set(params) <= required | {'filter.exclude.entities'}
                     and params['filter.type'] == 'urn:entity:movie' and params['bias.trends'] == 'off'
                     and type(params['take']) is int and params['take'] == 50
                     and type(params['page']) is int and params['page'] == page, 'Exactly movie pages1 and2 of take50 required.')
                def ids(value):
                    need(isinstance(value,str), 'Canonical positive IDs required.')
                    values=value.split(',')
                    need(1 <= len(values) <= 2 and values == sorted(set(values))
                         and all(canonical_id(v) == v for v in values), 'One or two sorted canonical UUIDs required.')
                    return values
                signals=ids(params['signal.interests.entities'])
                excluded=ids(params['filter.exclude.entities']) if 'filter.exclude.entities' in params else []
                need(len(signals) == initial and set(excluded) <= set(signals)
                     and (initial == 1 and (not excluded or excluded == signals) or initial == 2 and len(excluded) == 1),
                     'Only the confirmed movie seed or favorite may be excluded from its positive signal.')
                shared={k:v for k,v in params.items() if k != 'page'}
                need(first is None or fingerprint(first) == fingerprint(shared), 'Both pages require the same confirmed positive signal.')
                first=shared
        super().__init__(transport, ledger, synthetic=testing, max_requests=maximum, max_attempts=1)
        self.requests = initial
        self._reviewed = copy.deepcopy(requests)
        self._ordinal = 0

    def get(self, path, params, *, cache=False):
        request = {'method':'GET','host':'https://hackathon.api.qloo.com','path':path,'params':params}
        need(cache is False and self._ordinal < len(self._reviewed)
             and fingerprint(request) == fingerprint(self._reviewed[self._ordinal]), 'Exact next reviewed wide query required.')
        runtime = current_runtime(); need(runtime is not None, 'An active durable dispatcher is mandatory; no uncoordinated send.')
        self._ordinal += 1
        return runtime.qloo_get(self, path, params, cache=False)


def prepare_plan(request, output, *, minimum_model_interval_seconds=None):
    request = validate_request(request); output = safe_directory_path(Path(output)); validate_capture_paths(output)
    need(not output.exists() and output.parent.is_dir(), 'New output path and existing parent required.')
    source = Path(__file__).resolve().parent; search_count = len(search_queries(request))
    value = {'schema_version':18,'protocol_version':PROTOCOL,'mode':'wide-cinema-discovery','request':request,
        'output_directory':str(output),'source_sha256':{n:sha(source/n) for n in SOURCES},
        'data_sha256':{n:sha(source.parents[1]/n) for n in DATA},
        'driver_sha256':sha(source/'wide_cinema_capture.py'),'verification_driver_sha256':sha(source/'wide_cinema_verify.py'),
        'remote_operator':model_manifest('remote-llm'),'maximum_qloo_requests':search_count+2,
        'maximum_identity_search_requests':search_count,'maximum_insights_requests':2,'maximum_model_decisions':1,
        'maximum_attempts_per_request':1,'maximum_model_load_requests':0,'maximum_model_metadata_requests':0,
        'retrieval_policy':{'pages':[1,2],'take':50,'maximum_raw_rows':100,'maximum_candidates':100,'minimum_eligible':5,
            'fixed_catalog_fallback':False,'missing_year':'reject-row-with-source-position','conflicting_identity':'stop',
            'deduplication':'first-observed-consistent-UUID','seed_returned':'stop','movie_titles':'bounded-original-source-v1'},
        'identity_candidate_contract':'qloo-wide-confirmed-seed-and-optional-favorite-v2-canonical-name-filter',
        'priority_policy':'explicit-taste-first-then-seed-interpretation-then-provider-order-v1',
        'model_output_policy':'five-ordered-catalog-indices-source-grounded-v10',
        'faults':[],'execution_pacing':{'strategy':'shared-durable-provider-scheduler','minimum_interval_seconds':0},
        'maximum_token_reservation':8000,'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}
    value['plan_sha256'] = fingerprint(value)
    return value


def _search_music_profiles(body):
    # Validate every raw row before excluding an unusable display name. Never
    # hide malformed IDs/metadata or contradictory musical identities.
    need(isinstance(body,dict) and isinstance(body.get('results'),list)
         and 1 <= len(body['results']) <= 5, 'Bounded search results required.')
    rows=[parse_entities({**body,'results':[raw]},insights=False)[0] for raw in body['results']]
    occupations={'musician','singer','singer songwriter','songwriter','rapper','composer',
                 'pianist','guitarist','harpist','record producer','music producer'}
    seen={};choices=[]
    for row in rows:
        kind='urn:entity:artist' if 'urn:entity:artist' in row.types else None
        if kind is None and 'urn:entity:person' in row.types:
            raw=row.metadata.get('occupations',row.metadata.get('occupation',[]))
            raw=[raw] if isinstance(raw,str) else raw
            musical=isinstance(raw,list) and any(isinstance(v,str) and
                ' '.join(unicodedata.normalize('NFKC',re.sub(r'[_-]',' ',v)).casefold().split()) in occupations for v in raw)
            external=row.metadata.get('external',{})
            service=isinstance(external,dict) and any(isinstance(external.get(k),dict) and bool(external[k].get('id'))
                for k in ('musicbrainz','lastfm','spotify'))
            if musical or service:kind='urn:entity:person'
        if kind is None:continue
        profile={'entity_id':row.entity_id,'name':row.name,'type':kind}
        previous=seen.get(row.entity_id)
        need(previous is None or previous==profile,'Conflicting musical profiles share one search entity ID.')
        if previous is not None:continue
        seen[row.entity_id]=profile
        canonical=' '.join(unicodedata.normalize('NFKC',row.name).split())
        if not (1 <= len(row.name) <= 300 and row.name==canonical
                and not any(unicodedata.category(c).startswith('C') for c in row.name)):
            continue
        choices.append(seed_identity(profile,'music'))
    need(choices,'No verified musical identity candidates were returned; no substitution.')
    return choices


def search_identities(request, output, expected_plan_hash, settings, *, minimum_model_interval_seconds=None, _test_adapters=None):
    plan = prepare_plan(request,output,minimum_model_interval_seconds=minimum_model_interval_seconds)
    need(plan['plan_sha256'] == expected_plan_hash and current_runtime() is not None, 'Frozen plan and active dispatcher required before keys/network.')
    need(isinstance(settings.api_key,str) and len(settings.api_key) >= 20 and not contains_secret(plan,(settings.api_key,)), 'Private Qloo configuration must remain outside evidence.')
    testing = _test_adapters is not None; output = Path(output); output.mkdir(mode=0o700)
    ledger = Ledger(output,'test-double-only' if testing else SOURCE,secrets=(settings.api_key,))
    ledger.write('wide-plan.json',plan)
    report = {'schema_version':18,'protocol_version':PROTOCOL,'run_id':ledger.run_id,'phase':'IDENTITY_SEARCH',
        'plan_sha256':plan['plan_sha256'],'status':'INCOMPLETE','source':ledger.source,'mode':plan['request']['mode'],
        'seed_query':plan['request']['seed_query'],'favorite_movie_query':plan['request']['favorite_movie_query'],
        'seed_candidates':[],'favorite_movie_candidates':[],'qloo_attempts':0,'model_attempts':0,'error_class':None,
        'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}
    client = None
    try:
        queries = search_queries(plan['request'])
        requests = [{'method':'GET','host':'https://hackathon.api.qloo.com','path':'/search','params':p} for _,p in queries]
        transport = _test_adapters[1]() if testing else LiveTransport(settings,timeout=120)
        client = WideCinemaClient(transport,ledger,requests,testing=testing,maximum=plan['maximum_qloo_requests'])
        found = {'seed_candidates':[],'favorite_movie_candidates':[]}
        for slot, params in queries:
            ledger.record('wide_search_admitted',{'slot':slot,'params':params})
            body = client.get('/search',params,cache=False)
            choices = _search_music_profiles(body) if slot == 'seed' and plan['request']['mode'] == 'music' else movie_candidates(body)
            found['seed_candidates' if slot == 'seed' else 'favorite_movie_candidates'] = choices
            ledger.record('wide_search_choices_recorded',{'slot':slot,'choices_sha256':fingerprint(choices)})
        ledger.write('wide-candidates.json',found)
        ledger.record('wide_search_complete',{'sha256':sha(ledger.directory/'wide-candidates.json')})
        report.update(status='AWAITING_IDENTITY_CONFIRMATION',**found)
    except BaseException as exc:
        report['error_class'] = type(exc).__name__; ledger.record('wide_search_stopped',{'error_class':type(exc).__name__})
        if not isinstance(exc,(AffinityQAError,OSError)):raise
    finally:
        report['qloo_attempts'] = getattr(client,'requests',0)
        ledger.write('wide-search-report.json',report)
        with (ledger.directory/'identity-ledger.jsonl').open('xb') as handle:handle.write((ledger.directory/'ledger.jsonl').read_bytes())
    return report, ledger.directory


def capture_confirmed(directory, selected_seed_entity_id, identity_receipt, settings, remote_key, *,
                      selected_favorite_movie_entity_id=None, _test_adapters=None, _test_pacing_clock=None):
    from .wide_cinema_verify import verify_identity_search
    directory = safe_directory_path(Path(directory))
    reviewed_plan = strict_json((directory/'wide-plan.json').read_bytes())
    need(isinstance(reviewed_plan,dict) and reviewed_plan.get('protocol_version') == PROTOCOL,
         'Historical wide captures are read-only; prepare a new v12 plan.')
    need(_test_pacing_clock is None and current_runtime() is not None, 'Actual durable dispatcher required.')
    with execution_lease(directory.parent.parent):
        current = verify_identity_search(directory)
        clean = lambda r:{k:v for k,v in r.items() if k != 'verified_utc'}
        need(fingerprint(clean(current)) == fingerprint(clean(identity_receipt)), 'Original identity receipt changed.')
        plan = strict_json((directory/'wide-plan.json').read_bytes()); request = plan['request']
        need(fingerprint(plan) == fingerprint(reviewed_plan), 'Reviewed wide plan changed before confirmation.')
        seed,favorite = select_identities(request,current,selected_seed_entity_id,selected_favorite_movie_entity_id)
        testing = _test_adapters is not None
        need(current['provenance'] == ('SIMULATION_ONLY' if testing else 'RECORDED_REMOTE_EXECUTION'), 'Mixed provenance.')
        secrets = (settings.api_key,remote_key)
        need(all(isinstance(s,str) and len(s) >= 20 for s in secrets) and not contains_secret([plan,identity_receipt,seed,favorite],secrets), 'Provider secrets must remain private.')
        ledger = Ledger.__new__(Ledger); ledger.directory,ledger.run_id,ledger.source,ledger.secrets = directory,directory.name,current['source'],secrets
        ledger.events = [strict_json(row) for row in (directory/'ledger.jsonl').read_bytes().splitlines()]
        ledger.live_requests = current['qloo_attempts'] if not testing else 0
        confirmation = {'schema_version':1,'protocol':PROTOCOL,'plan_sha256':plan['plan_sha256'],'identity_receipt':copy.deepcopy(identity_receipt),
            'selected_seed_entity_id':selected_seed_entity_id,'selected_favorite_movie_entity_id':selected_favorite_movie_entity_id,
            'seed_identity':seed,'known_favorite_movie':favorite}
        ledger.write('wide-confirmation.json',confirmation); ledger.record('wide_confirmed',{'sha256':sha(directory/'wide-confirmation.json')})
        report = {'schema_version':18,'protocol_version':PROTOCOL,'run_id':directory.name,'phase':'CONFIRMED_DISCOVERIES',
            'plan_sha256':plan['plan_sha256'],'status':'INCOMPLETE','source':ledger.source,'qloo_attempts':current['qloo_attempts'],
            'model_attempts':0,'error_class':None,'wide_cinema_results':None,'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}
        client = engine = None
        try:
            requests = [qloo_request(request['mode'],seed,favorite,page) for page in (1,2)]
            transport = _test_adapters[1]() if testing else LiveTransport(settings,timeout=120)
            client = WideCinemaClient(transport,ledger,requests,testing=testing,maximum=plan['maximum_qloo_requests'],initial=current['qloo_attempts'])
            samples = []
            for page, http in enumerate(requests,1):
                ledger.record('wide_page_admitted',{'page':page,'params':http['params']})
                client.get('/v2/insights',http['params'],cache=False)
                path = directory/ledger.events[-1]['data']['sample']; sample = strict_json(path.read_bytes())
                rows = validate_page(request['mode'],seed,favorite,sample,sha(path),page)
                samples.append({'sample':sample,'sample_sha256':sha(path)})
                ledger.record('wide_page_accepted',{'page':page,'sample_sha256':sha(path),'row_count':len(rows)})
            context = context_from_samples(request['mode'],seed,favorite,samples)
            ledger.write('wide-context.json',context); ledger.record('wide_context_frozen',{'sha256':sha(directory/'wide-context.json')})
            decision = make_decision(request,context,'wide-'+directory.name)
            engine = _test_adapters[0]() if testing else WideCinemaAgent(remote_key,forbidden_secrets=(settings.api_key,))
            need(engine.calls == 0 and fingerprint(engine.manifest) == fingerprint(model_manifest('test-double-only' if testing else 'remote-llm')), 'Frozen unused operator required.')
            engine.dispatch_ledger = ledger; ledger.write('wide-model-manifest.json',engine.manifest)
            response = engine.rank(decision)
            packet = {'execution_id':directory.name+'/1','effective_request':decision,'model_payload':copy.deepcopy(engine.last_input),
                'response':copy.deepcopy(response),'observation':copy.deepcopy(engine.observations[-1]),'cache_key_sha256':cache_key(decision,engine.manifest)}
            ledger.write('wide-execution-001.json',packet); ledger.record('wide_execution_recorded',{'sha256':sha(directory/'wide-execution-001.json')})
            output = {'ordered_catalog_indices':packet['observation']['provider_envelope']['choice']['ordered_catalog_indices']}
            result = result_for(decision,output)
            need(response['ranked_entity_ids'] == result['raw_selection'], 'Observed response differs from selected result.')
            ledger.write('wide-result.json',result); ledger.record('wide_result_recorded',{'sha256':sha(directory/'wide-result.json')})
            ledger.record('wide_complete',{'candidate_count':len(context['candidate_catalog']),'delivered_count':5})
            report.update(status='COMPLETE',wide_cinema_results=result)
        except BaseException as exc:
            report.update(status='INCOMPLETE',wide_cinema_results=None,error_class=type(exc).__name__)
            diagnostic=getattr(engine,'last_rejection',None)
            if diagnostic is not None:
                try:
                    diagnostic=validate_failure_projection(diagnostic,decision,engine.last_prepared)
                    need(not contains_secret(diagnostic,secrets),'Private content cannot enter a rejection diagnostic.')
                except AffinityQAError:diagnostic=None
            if diagnostic is not None:
                ledger.write('wide-model-rejection.json',diagnostic)
                ledger.record('wide_model_rejected',{'sha256':sha(directory/'wide-model-rejection.json'),
                    'stage':diagnostic['stage'],'code':diagnostic['code']})
            ledger.record('wide_capture_stopped',{'error_class':type(exc).__name__})
            if not isinstance(exc,(AffinityQAError,OSError)):raise
        finally:
            report['qloo_attempts'] = getattr(client,'requests',current['qloo_attempts']); report['model_attempts'] = getattr(engine,'calls',0)
            ledger.write('wide-report.json',report)
        return report,directory
