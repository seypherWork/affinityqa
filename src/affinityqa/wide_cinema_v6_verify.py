"""Independent reconstruction from raw pages, immutable prefixes and model envelopes."""
import copy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit

from .agents import strict_json
from .evidence import fingerprint, utc_now
from .errors import SchemaError
from .individual_verify import checked_path, inventory, sha
from .individual_remote_verify import expected_manifest as base_manifest
from .models import canonical_id, normalized_name, parse_entities
from .wide_cinema_v6_compat import PROTOCOL, CONTEXT_PROTOCOL, SOURCE, PROMPT, legacy_source_sha, validate_frozen_sources

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
    'wide_cinema_v5_source/wide_cinema_capture.py','wide_cinema_v5_source/wide_cinema_verify.py')
DATA = ('requirements-backend.lock.txt','requirements-repeatable.lock.txt','assets/tokenizers/o200k_base.tiktoken')


def need(value,message):
    if not value:raise SchemaError('Wide verification: '+message)


def same(a,b):
    try:return fingerprint(a) == fingerprint(b)
    except (ValueError,TypeError,RecursionError):return False


def read(path):
    wrapped = strict_json(b'{"artifact":'+path.read_bytes()+b'}')
    need(set(wrapped) == {'artifact'},'one strict artifact value')
    return wrapped['artifact']


def _text(value,minimum,maximum):
    need(isinstance(value,str) and not any(unicodedata.category(c).startswith('C') for c in value),'printable bounded text')
    result = ' '.join(unicodedata.normalize('NFKC',value).split())
    need(value == result and minimum <= len(value) <= maximum,'normalized bounded text')
    return value


def _movie(value):
    need(isinstance(value,dict) and set(value) == {'entity_id','name','type','release_year'},'closed movie identity')
    need(isinstance(value['entity_id'],str) and canonical_id(value['entity_id']) == value['entity_id'] and value['type'] == 'urn:entity:movie'
         and type(value['release_year']) is int and 1888 <= value['release_year'] <= 2100,'actual movie ID/type/year')
    _text(value['name'],1,300)
    return copy.deepcopy(value)


def _request(value):
    need(isinstance(value,dict) and set(value) == {'schema_version','mode','seed_query','favorite_movie_query','intent_text','excluded_entity_ids','model'}
         and type(value['schema_version']) is int and value['schema_version'] == 9 and value['mode'] in ('movie','music'),'closed normalized request9')
    _text(value['seed_query'],1,200);_text(value['intent_text'],0,600)
    if value['favorite_movie_query'] is not None:
        need(value['mode'] == 'music','favorite only in music');_text(value['favorite_movie_query'],1,200)
    excluded = value['excluded_entity_ids']
    need(isinstance(excluded,list) and len(excluded) <= 15 and all(isinstance(v,str) and canonical_id(v) == v for v in excluded)
         and excluded == sorted(set(excluded)) and same(value['model'],{'provider':'groq','name':'openai/gpt-oss-20b'}),'owner model and canonical exclusions')
    return copy.deepcopy(value)


def expected_manifest(source):
    validate_frozen_sources()
    value = base_manifest(source)
    value.update(max_inference_calls=1,prompt_version=PROTOCOL,prompt_sha256=fingerprint(PROMPT),tool_contract='wide-real-film-pool-v1',
        response_contract='wide-five-ordered-identity-choices-normalized-v6',
        provider_response_format={'type':'json_object'},
        maximum_token_reservation=8000,
        decision_scope='one-wide-profile-one-five-choice-decision',prompt_cache_discount_reserved=False)
    return value


def _queries(request):
    rows = [('seed',{'query':request['seed_query'],'types':'urn:entity:movie' if request['mode'] == 'movie' else 'urn:entity:artist,urn:entity:person','take':5})]
    if request['favorite_movie_query'] is not None:rows.append(('favorite',{'query':request['favorite_movie_query'],'types':'urn:entity:movie','take':5}))
    return rows


def _plan(directory):
    actual = read(directory/'wide-plan.json');request = _request(actual['request']);source = Path(__file__).resolve().parent;n = len(_queries(request))
    expected = {'schema_version':14,'protocol_version':PROTOCOL,'mode':'wide-cinema-discovery','request':request,
        'output_directory':str(directory.parent),'source_sha256':{v:legacy_source_sha(source/v) for v in SOURCES},
        'data_sha256':{v:sha(source.parents[1]/v) for v in DATA},'driver_sha256':legacy_source_sha(source/'wide_cinema_capture.py'),
        'verification_driver_sha256':legacy_source_sha(source/'wide_cinema_verify.py'),'remote_operator':expected_manifest('remote-llm'),
        'maximum_qloo_requests':n+2,'maximum_identity_search_requests':n,'maximum_insights_requests':2,'maximum_model_decisions':1,
        'maximum_attempts_per_request':1,'maximum_model_load_requests':0,'maximum_model_metadata_requests':0,
        'retrieval_policy':{'pages':[1,2],'take':50,'maximum_raw_rows':100,'maximum_candidates':100,'minimum_eligible':5,
            'fixed_catalog_fallback':False,'missing_year':'reject-row-with-source-position','conflicting_identity':'stop',
            'deduplication':'first-observed-consistent-UUID','seed_returned':'stop'},
        'identity_candidate_contract':'qloo-wide-confirmed-seed-and-optional-favorite-v1',
        'priority_policy':'explicit-taste-first-then-seed-interpretation-then-provider-order-v1',
        'model_output_policy':'five-ordered-identity-choices-normalized-local-validated-json-object-v6',
        'faults':[],'execution_pacing':{'strategy':'shared-durable-provider-scheduler','minimum_interval_seconds':0},
        'maximum_token_reservation':8000,'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}
    expected['plan_sha256'] = fingerprint(expected);need(same(actual,expected),'source/data/plan/operator/budget changed')
    return actual


def _events(directory):
    raw = (directory/'ledger.jsonl').read_bytes();events = [strict_json(v) for v in raw.splitlines()]
    need(1 <= len(events) <= 32,'bounded observed event prefix')
    for i,event in enumerate(events,1):
        need(set(event) == {'sequence','timestamp_utc','source','kind','data'} and type(event['sequence']) is int and event['sequence'] == i
             and event['source'] in (SOURCE,'test-double-only') and isinstance(event['data'],dict),'closed event sequence')
        instant = datetime.fromisoformat(event['timestamp_utc']);need(instant.utcoffset() is not None,'timezone-aware observation')
        if i > 1:need(event['source'] == events[0]['source'] and instant >= datetime.fromisoformat(events[i-2]['timestamp_utc']),'monotonic observations')
    return raw,events


def _sample(directory,event,request):
    name = event['data'].get('sample');need(name == f'http-{event["sequence"]:04d}.json','sample event filename')
    sample = read(directory/name)
    need(set(sample) == {'source','request','status','response','response_sha256','response_headers','elapsed_ms','attempt','live_network_request'}
        and sample['source'] == event['source'] and same(sample['request'],request) and type(sample['attempt']) is int and sample['attempt'] == 1
        and type(sample['status']) is int and 100 <= sample['status'] <= 599
        and sample['live_network_request'] is (sample['source'] != 'test-double-only'),'actual exact first-attempt request/provenance')
    need(same(event['data'],{'sample':name,**{k:v for k,v in sample.items() if k != 'response'}})
         and sample['response_sha256'] == fingerprint(sample['response']) and isinstance(sample['response_headers'],dict)
         and type(sample['elapsed_ms']) in (int,float) and math.isfinite(sample['elapsed_ms']) and sample['elapsed_ms'] >= 0,'raw sample hash/time binding')
    return sample,name


def _failure(data,request):
    plain = {'request':request,'attempt':1}
    return same(data,plain) or same(data,{**plain,'outcome':'UNKNOWN','automatic_retry':False})


def _choices(body,music):
    need(isinstance(body,dict) and isinstance(body.get('results'),list) and 1 <= len(body['results']) <= 5,'bounded raw choices')
    result = [];seen = {}
    occupations = {'musician','singer','singer songwriter','songwriter','rapper','composer','pianist','guitarist','harpist','record producer','music producer'}
    norm = lambda v:' '.join(unicodedata.normalize('NFKC',v).casefold().split())
    for raw in body['results']:
        row = parse_entities({**body,'results':[raw]},insights=False)[0]
        if not music:
            need('urn:entity:movie' in row.types,'movie choices cannot be albums/people')
            value = _movie({'entity_id':row.entity_id,'name':row.name,'type':'urn:entity:movie','release_year':row.metadata.get('release_year')})
        else:
            kind = 'urn:entity:artist' if 'urn:entity:artist' in row.types else None
            if kind is None and 'urn:entity:person' in row.types:
                raw_occupations = row.metadata.get('occupations',row.metadata.get('occupation',[]))
                raw_occupations = [raw_occupations] if isinstance(raw_occupations,str) else raw_occupations
                musical = isinstance(raw_occupations,list) and any(isinstance(v,str) and norm(re.sub(r'[_-]',' ',v)) in occupations for v in raw_occupations)
                ext = row.metadata.get('external',{})
                service = isinstance(ext,dict) and any(isinstance(ext.get(v),dict) and bool(ext[v].get('id')) for v in ('musicbrainz','lastfm','spotify'))
                if musical or service:kind = 'urn:entity:person'
            if kind is None:continue
            _text(row.name,1,300);value = {'entity_id':row.entity_id,'name':row.name,'type':kind}
        previous = seen.get(value['entity_id']);need(previous is None or music and same(previous,value),'conflicting or repeated movie choices')
        if previous is None:seen[value['entity_id']] = value;result.append(value)
    need(result,'at least one real selectable identity')
    return result


def _search(directory,continuing=False):
    before = inventory(directory);plan = _plan(directory);raw,all_events = _events(directory)
    prefix = (directory/'identity-ledger.jsonl').read_bytes();events = [strict_json(v) for v in prefix.splitlines()]
    need(raw.startswith(prefix) and events == all_events[:len(events)] and len(events) <= 8,'immutable identity prefix')
    if not continuing:need(raw == prefix,'no work before explicit confirmation')
    report = read(directory/'wide-search-report.json');request = plan['request'];i = 0;observed = 0;admitted = 0;names = []
    found = {'seed_candidates':[],'favorite_movie_candidates':[]};all_choices = True
    for slot,params in _queries(request):
        if i >= len(events) or events[i]['kind'] != 'wide_search_admitted':all_choices = False;break
        need(same(events[i]['data'],{'slot':slot,'params':params}),'exact search slot admission');i += 1;admitted += 1
        http = {'method':'GET','host':'https://hackathon.api.qloo.com','path':'/search','params':params};choices = None
        if i < len(events) and events[i]['kind'] == 'tool_call':
            sample,name = _sample(directory,events[i],http);names.append(name);i += 1;observed += 1
            if sample['status'] == 200:
                try:choices = _choices(sample['response'],slot == 'seed' and request['mode'] == 'music')
                except SchemaError:choices = None
        elif i < len(events) and events[i]['kind'] == 'transport_failure':
            need(_failure(events[i]['data'],http),'search transport failure');i += 1;observed += 1
        if i < len(events) and events[i]['kind'] == 'wide_search_choices_recorded':
            need(choices is not None and same(events[i]['data'],{'slot':slot,'choices_sha256':fingerprint(choices)}),'successful exact choice projection');i += 1
            found['seed_candidates' if slot == 'seed' else 'favorite_movie_candidates'] = choices
        else:all_choices = False;break
    success = all_choices and i < len(events) and events[i]['kind'] == 'wide_search_complete'
    if success:
        need(i == len(events)-1 and same(read(directory/'wide-candidates.json'),found)
             and same(events[i]['data'],{'sha256':before['wide-candidates.json']}),'closed completed search')
    else:
        need(i == len(events)-1 and events[i]['kind'] == 'wide_search_stopped'
             and same(events[i]['data'],{'error_class':report['error_class']}) and isinstance(report['error_class'],str)
             and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,99}',report['error_class']),'terminal partial search; no later lookup')
    expected = {'schema_version':14,'protocol_version':PROTOCOL,'run_id':directory.name,'phase':'IDENTITY_SEARCH','plan_sha256':plan['plan_sha256'],
        'status':'AWAITING_IDENTITY_CONFIRMATION' if success else 'INCOMPLETE','source':events[0]['source'],'mode':request['mode'],
        'seed_query':request['seed_query'],'favorite_movie_query':request['favorite_movie_query'],
        **(found if success else {'seed_candidates':[],'favorite_movie_candidates':[]}),
        'qloo_attempts':report.get('qloo_attempts'),'model_attempts':0,'error_class':None if success else report['error_class'],
        'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}
    need(type(report.get('qloo_attempts')) is int and observed <= report['qloo_attempts'] <= admitted
         and same(report,expected),'closed search report/accounting')
    initial_names = {'wide-plan.json','wide-search-report.json','identity-ledger.jsonl','ledger.jsonl',*names}
    if 'wide-candidates.json' in before:
        need(all_choices and same(read(directory/'wide-candidates.json'),found),'partial candidate file');initial_names.add('wide-candidates.json')
    initial = {n:before[n] for n in initial_names};initial['ledger.jsonl'] = hashlib.sha256(prefix).hexdigest()
    if not continuing:need(set(before) == initial_names,'unknown search artifacts')
    receipt = {'schema_version':1,'verified_utc':utc_now(),'protocol_version':PROTOCOL,'mode':request['mode'],'run_id':directory.name,
        'plan_sha256':plan['plan_sha256'],'status':expected['status'],'verification_status':'VERIFIED_IDENTITY_SEARCH' if success else 'VERIFIED_PARTIAL',
        'seed_query':request['seed_query'],'favorite_movie_query':request['favorite_movie_query'],
        'seed_candidates':copy.deepcopy(expected['seed_candidates']),'favorite_movie_candidates':copy.deepcopy(expected['favorite_movie_candidates']),
        'qloo_attempts':report['qloo_attempts'],'model_attempts':0,'error_class':expected['error_class'],'source':expected['source'],
        'provenance':'SIMULATION_ONLY' if expected['source'] == 'test-double-only' else 'RECORDED_REMOTE_EXECUTION','artifact_sha256':initial,
        'causal_gate':'NOT_EVALUATED','behavioral_gate':'NOT_EVALUATED','cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED','external_service_attested':False}
    return receipt,plan,all_events,len(events),before


def verify_identity_search(directory, *, original_output_directory=None):
    directory = checked_path(Path(directory))
    if read(directory/'wide-plan.json').get('protocol_version') == 'qloo-wide-cinema-discovery-v3':
        from .wide_cinema_v3_verify import verify_identity_search as verify_v3
        return verify_v3(directory,original_output_directory=original_output_directory)
    if read(directory/'wide-plan.json').get('protocol_version') == 'qloo-wide-cinema-discovery-v4':
        from .wide_cinema_v4_verify import verify_identity_search as verify_v4
        return verify_v4(directory,original_output_directory=original_output_directory)
    if read(directory/'wide-plan.json').get('protocol_version') == 'qloo-wide-cinema-discovery-v5':
        from .wide_cinema_v5_verify import verify_identity_search as verify_v5
        return verify_v5(directory,original_output_directory=original_output_directory)
    need(original_output_directory is None,'explicit relocation is read-only historical v3 only')
    return _search(directory)[0]


def _http(mode,seed,favorite,page):
    signal = sorted([seed['entity_id']]+([favorite['entity_id']] if favorite else []))
    known = ([seed['entity_id']] if mode == 'movie' else [])+([favorite['entity_id']] if favorite else [])
    params = {'filter.type':'urn:entity:movie','bias.trends':'off','take':50,'page':page,'signal.interests.entities':','.join(signal)}
    if known:params['filter.exclude.entities'] = ','.join(sorted(known))
    return {'method':'GET','host':'https://hackathon.api.qloo.com','path':'/v2/insights','params':params}


def _page(mode,seed,favorite,sample):
    need(sample['status'] == 200,'successful page required')
    rows = parse_entities(sample['response'],insights=True);need(len(rows) <= 50,'page bound')
    known = [seed] if mode == 'movie' else []
    if favorite:known.append(favorite)
    for row in rows:
        need('urn:entity:movie' in row.types and row.affinity is not None,'actual movie affinity')
        need(row.entity_id != seed['entity_id'] and row.entity_id not in [v['entity_id'] for v in known],'known seed returned')
        year = row.metadata.get('release_year')
        if type(year) is int and 1888 <= year <= 2100:
            _movie({'entity_id':row.entity_id,'name':row.name,'type':'urn:entity:movie','release_year':year})
            need(all((normalized_name(row.name),year) != (normalized_name(v['name']),v['release_year']) for v in known),'known movie alias')
    return rows


def _asset(row,sample_sha):
    image = row.metadata.get('image');url = image.get('url') if isinstance(image,dict) else None
    if not isinstance(url,str) or not 1 <= len(url) <= 2048 or any(not 33 <= ord(c) <= 126 for c in url):return None
    try:
        p = urlsplit(url);m = re.fullmatch(r'/i/([a-fA-F0-9-]{36})-[1-9][0-9]{0,3}x-(?:auto|[1-9][0-9]{0,3})\.(?:jpg|jpeg|png|webp)',p.path)
        if not (p.scheme == 'https' and p.netloc == 'images.qloo.com' and not p.query and not p.fragment and m and canonical_id(m[1]) == row.entity_id):return None
    except (ValueError,SchemaError):return None
    identity = {'entity_id':row.entity_id,'name':row.name,'release_year':row.metadata['release_year']}
    return {'entity_id':row.entity_id,'identity_sha256':fingerprint(identity),'url':url,'source':'QLOO_OBSERVED','sample_sha256':sample_sha}


def _context(mode,seed,favorite,samples):
    catalog = {};order = [];observations = [];rejected = [];duplicates = [];assets = {};pages = [];raw_identities = {}
    for page,(sample,sample_sha,rows) in enumerate(samples,1):
        pages.append({'page':page,'row_count':len(rows),'request_sha256':fingerprint(sample['request']),
            'response_sha256':sample['response_sha256'],'sample_sha256':sample_sha})
        for position,row in enumerate(rows):
            year = row.metadata.get('release_year')
            previous = raw_identities.get(row.entity_id)
            if previous is not None:
                need(previous[0] == row.name and (type(previous[1]) is not int or type(year) is not int or previous[1] == year),'conflicting raw identity even if a prior year was missing')
            else:raw_identities[row.entity_id] = (row.name,year)
            if type(year) is not int or not 1888 <= year <= 2100:
                rejected.append({'page':page,'position':position,'entity_id':row.entity_id,'reason':'MISSING_OR_INVALID_INTEGER_YEAR'});continue
            identity = {'entity_id':row.entity_id,'name':row.name,'release_year':year}
            if row.entity_id in catalog:
                need(same(catalog[row.entity_id],identity),'conflicting identity across pages')
                duplicates.append({'page':page,'position':position,'entity_id':row.entity_id})
            else:catalog[row.entity_id] = identity;order.append(row.entity_id)
            observations.append({'page':page,'position':position,'entity_id':row.entity_id,'affinity':row.affinity})
            asset = _asset(row,sample_sha)
            if asset is not None and row.entity_id not in assets:assets[row.entity_id] = asset
    ordered = [catalog[v] for v in sorted(catalog)]
    need(5 <= len(ordered) <= 100 and len({(normalized_name(v['name']),v['release_year']) for v in ordered}) == len(ordered),'valid unique bounded universe')
    value = {'schema_version':1,'protocol':CONTEXT_PROTOCOL,'source':samples[0][0]['source'],'mode':mode,'seed_identity':seed,
        'known_favorite_movie':favorite,'positive_signal_sha256':fingerprint({'seed':seed,'favorite':favorite}),'pages':pages,
        'candidate_catalog':ordered,'catalog_sha256':fingerprint(ordered),'raw_provider_order':order,'provider_observations':observations,
        'rejected_rows':rejected,'duplicate_rows':duplicates,'presentation_assets':[assets[v] for v in sorted(assets)]}
    value['context_sha256'] = fingerprint(value)
    return value


def _decision(request,context,run_id):
    eligible = [i for i,v in enumerate(context['candidate_catalog']) if v['entity_id'] not in request['excluded_entity_ids']]
    need(len(eligible) >= 5,'five eligible complete films before model')
    value = {'schema_version':1,'protocol':PROTOCOL,'request':request,'context':context,'eligible_catalog_indices':eligible,
        'input_binding_sha256':fingerprint({'request':request,'context_sha256':context['context_sha256']}),'request_nonce':'wide-'+run_id}
    value['request_id'] = fingerprint(value)
    return value


def _input_schema(decision):
    context = decision['context'];request = decision['request'];allowed = decision['eligible_catalog_indices']
    seed = {k:v for k,v in context['seed_identity'].items() if k != 'entity_id'}
    favorite = context['known_favorite_movie'];favorite = {k:v for k,v in favorite.items() if k != 'entity_id'} if favorite else None
    first = {}
    for row in context['provider_observations']:first.setdefault(row['entity_id'],row['affinity'])
    order = {v:i for i,v in enumerate(context['raw_provider_order'])}
    payload = {'protocol':PROTOCOL,'input_binding_sha256':decision['input_binding_sha256'],'mode':request['mode'],'seed':seed,
        'known_favorite_movie':favorite,'intent_text':request['intent_text'],
        'priority':'stated taste first, then seed interpretation, then provider affinity/order; no forced divergence',
        'candidates':[{'catalog_index':i,'title':v['name'],'release_year':v['release_year'],
            'observed_affinity':first[v['entity_id']],'provider_order':order[v['entity_id']]}
            for i,v in enumerate(context['candidate_catalog']) if i in allowed],
        'information_notice':'Only the model receives extra text and may use NOT_FACT_CHECKED cinematic knowledge; cross-page affinity calibration is not attested.'}
    schema = {'type':'object','properties':{'ordered_catalog_indices':{'type':'array','items':{'type':'object',
        'properties':{'catalog_index':{'type':'integer','enum':allowed},
            'title':{'type':'string','minLength':1,'maxLength':300},
            'release_year':{'type':'integer','minimum':1888,'maximum':2100},
            'text':{'type':'string','minLength':40,'maxLength':240}},
        'required':['catalog_index','title','release_year','text'],'additionalProperties':False},'minItems':5,'maxItems':5}},
        'required':['ordered_catalog_indices'],'additionalProperties':False}
    payload['output_contract'] = copy.deepcopy(schema)
    return payload,schema


def _wire(decision,manifest):
    if decision.get('protocol') == 'qloo-wide-cinema-discovery-v3':
        from .wide_cinema_v3_verify import _wire as wire_v3
        return wire_v3(decision,manifest)
    if decision.get('protocol') == 'qloo-wide-cinema-discovery-v4':
        from .wide_cinema_v4_verify import _wire as wire_v4
        return wire_v4(decision,manifest)
    if decision.get('protocol') == 'qloo-wide-cinema-discovery-v5':
        from .wide_cinema_v5_verify import _wire as wire_v5
        return wire_v5(decision,manifest)
    need(decision.get('protocol') == PROTOCOL,'current strict transport protocol')
    response_format = {'type':'json_object'}
    need(same(manifest.get('provider_response_format'),response_format),'fixed JSON object transport')
    payload,schema = _input_schema(decision)
    return {'model':manifest['model'],'messages':[{'role':'system','content':PROMPT},
        {'role':'user','content':json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False)}],
        'response_format':response_format,**manifest['options']}


def _reason(value):
    need(isinstance(value,str) and len(value) <= 1024
         and not any(unicodedata.category(c).startswith('C') and c not in '\t\r\n' for c in value),'bounded reason with no unsafe controls')
    normalized=' '.join(unicodedata.normalize('NFKC',value).split())
    need(40 <= len(normalized) <= 240 and value == normalized,'persisted normalized reason length')
    return normalized


def verify_packet(packet,manifest,decision):
    if decision.get('protocol') == 'qloo-wide-cinema-discovery-v3':
        from .wide_cinema_v3_verify import verify_packet as verify_v3
        return verify_v3(packet,manifest,decision)
    if decision.get('protocol') == 'qloo-wide-cinema-discovery-v4':
        from .wide_cinema_v4_verify import verify_packet as verify_v4
        return verify_v4(packet,manifest,decision)
    if decision.get('protocol') == 'qloo-wide-cinema-discovery-v5':
        from .wide_cinema_v5_verify import verify_packet as verify_v5
        return verify_v5(packet,manifest,decision)
    need(decision.get('protocol') == PROTOCOL,'current strict packet protocol')
    need(isinstance(packet,dict) and set(packet) == {'execution_id','effective_request','model_payload','response','observation','cache_key_sha256'},'closed model packet')
    need(packet['execution_id'] == decision['request_nonce'][5:]+'/1' and same(packet['effective_request'],decision),'exact effective request')
    payload,_ = _input_schema(decision);need(same(packet['model_payload'],payload),'compact independently reconstructed input')
    obs = packet['observation'];env = obs['provider_envelope'];source = 'test-double-only' if decision['context']['source'] == 'test-double-only' else 'remote-llm'
    need(same(manifest,expected_manifest(source)) and set(env) == {'schema_version','execution_source','provider','object','model','id','created','system_fingerprint','choice','usage'}
         and type(env['schema_version']) is int and env['schema_version'] == 1 and env['execution_source'] == source and env['provider'] == 'groq'
         and env['object'] == 'chat.completion' and env['model'] == manifest['model'],'closed completion manifest/envelope')
    need(isinstance(env['id'],str) and re.fullmatch(r'[!-~]{1,160}',env['id']) and type(env['created']) is int and 1 <= env['created'] <= 2**63-1,'completion identity/time')
    sf = env['system_fingerprint'];need(sf is None or isinstance(sf,str) and re.fullmatch(r'[!-~]{1,128}',sf),'provider fingerprint')
    choice = env['choice'];need(set(choice) == {'index','finish_reason','role','ordered_catalog_indices'} and type(choice['index']) is int and choice['index'] == 0
        and choice['finish_reason'] == 'stop' and choice['role'] == 'assistant','complete final choice')
    block = choice['ordered_catalog_indices'];need(isinstance(block,list) and len(block) == 5,'single five-choice array')
    reasons=[]
    for row in block:
        need(isinstance(row,dict) and set(row) == {'catalog_index','title','release_year','text'}
            and type(row['catalog_index']) is int and row['catalog_index'] in decision['eligible_catalog_indices'],'closed eligible identity choice')
        target=decision['context']['candidate_catalog'][row['catalog_index']]
        need(isinstance(row['title'],str) and row['title'] == target['name']
            and type(row['release_year']) is int and row['release_year'] == target['release_year'],'exact indexed title and year')
        text=_reason(row['text'])
        prefix=' '.join(unicodedata.normalize('NFKC',f"{target['name']} ({target['release_year']}):").split())+' '
        need(text.startswith(prefix),'literal indexed title/year text prefix')
        reasons.append({'catalog_index':row['catalog_index'],'text':text})
    order=[r['catalog_index'] for r in block];need(len(set(order)) == 5,'five distinct original indices')
    ids = [v['entity_id'] for v in decision['context']['candidate_catalog']];checked = {'ranking':[ids[i] for i in order],'reasons':reasons}
    key = fingerprint({'protocol':PROTOCOL,'request':decision['request'],'context':decision['context'],'manifest':manifest})
    need(packet['cache_key_sha256'] == key and same(packet['response'],{'schema_version':1,'request_id':decision['request_id'],
        'ranked_entity_ids':checked['ranking'],'reasons':reasons,'output_sha256':fingerprint(checked),'cache_key_sha256':key}),'model result/cache binding')
    usage = env['usage'];need(set(usage) == {'prompt_tokens','completion_tokens','total_tokens','reasoning_tokens'}
        and type(usage['prompt_tokens']) is int and 1 <= usage['prompt_tokens'] <= 8192 and type(usage['completion_tokens']) is int and 1 <= usage['completion_tokens'] <= 1024
        and type(usage['total_tokens']) is int and usage['total_tokens'] == usage['prompt_tokens']+usage['completion_tokens']
        and (usage['reasoning_tokens'] is None or type(usage['reasoning_tokens']) is int and 0 <= usage['reasoning_tokens'] <= usage['completion_tokens']),'typed token usage')
    need(type(obs['elapsed_ms']) in (int,float) and math.isfinite(obs['elapsed_ms']) and obs['elapsed_ms'] >= 0
         and isinstance(obs['provider_response_sha256'],str) and re.fullmatch('[a-f0-9]{64}',obs['provider_response_sha256']),'response hash/time observation')
    expected = {'call':1,'input_sha256':fingerprint(payload),'output_sha256':fingerprint(checked),'elapsed_ms':obs['elapsed_ms'],
        'prompt_eval_count':usage['prompt_tokens'],'eval_count':usage['completion_tokens'],'private_thinking_recorded':False,'done':True,'done_reason':'stop',
        'provider':'groq','model':manifest['model'],'completion_id':env['id'],'provider_created':env['created'],'system_fingerprint':sf,
        'provider_response_sha256':obs['provider_response_sha256'],'provider_response_hash_scope':'Full parsed response observation; not reconstructible from the redacted envelope.',
        'provider_request_sha256':fingerprint(_wire(decision,manifest)),'provider_envelope':env,'provider_envelope_sha256':fingerprint(env),
        'total_tokens':usage['total_tokens'],'reasoning_tokens':usage['reasoning_tokens'],'model_revision_attested':False,'execution_source':source}
    need(same(obs,expected),'complete model observation boundaries')
    return checked


def _rejection(value,decision,prepared):
    keys={'schema_version','protocol','request_id','provider_request_sha256','stage','code','accepted','scope','rejected_text_recorded',
        'body_parsed','provider_response_sha256','finish_reason','reported_usage','completion_choice_count','output_choices_count',
        'indices','indices_unique','indices_eligible','reason_lengths','reason_normalized_lengths','reason_canonical','reason_controls'}
    need(isinstance(value,dict) and set(value) == keys and type(value['schema_version']) is int and value['schema_version'] == 1
        and value['protocol'] == PROTOCOL and value['request_id'] == decision['request_id']
        and value['provider_request_sha256'] == prepared['provider_request_sha256'] and value['accepted'] is False
        and value['scope'] == 'SAFE_FAILURE_PROJECTION_NO_RAW_RESPONSE' and value['rejected_text_recorded'] is False,'closed non-acceptance diagnostic binding')
    codes={'COMPLETION':{'COMPLETION_REJECTED'},'ENVELOPE':{'ENVELOPE_IDENTITY','COMPLETION_IDENTITY','CHOICE_SHAPE','FINISH_REASON','FINAL_MESSAGE'},
        'OUTPUT':{'OUTPUT_JSON','OUTPUT_VALIDATION','OUTPUT_TOP_LEVEL','OUTPUT_COUNT','OUTPUT_CHOICE_SHAPE','OUTPUT_INDEX_TYPE','OUTPUT_INDEX_ELIGIBILITY',
            'OUTPUT_INDEX_DUPLICATE','OUTPUT_TEXT_TYPE','OUTPUT_TEXT_RAW_LENGTH','OUTPUT_TEXT_CONTROL','OUTPUT_TEXT_LENGTH',
            'OUTPUT_IDENTITY_TITLE','OUTPUT_IDENTITY_YEAR','OUTPUT_TEXT_TARGET'},
        'USAGE':{'USAGE_SHAPE','USAGE_RESERVATION','USAGE_REASONING','PROVIDER_FINGERPRINT'}}
    need(isinstance(value['stage'],str) and value['stage'] in codes and isinstance(value['code'],str)
         and value['code'] in codes[value['stage']],'closed diagnostic stage/code')
    need(type(value['body_parsed']) is bool and value['finish_reason'] in ('NOT_OBSERVED','STOP','LENGTH','CONTENT_FILTER','TOOL_CALLS','FUNCTION_CALL','MISSING','OTHER'),'closed response termination projection')
    response_hash=value['provider_response_sha256']
    need(response_hash is None or isinstance(response_hash,str) and re.fullmatch('[a-f0-9]{64}',response_hash),'safe optional response hash')
    if not value['body_parsed']:need(value['finish_reason'] == 'NOT_OBSERVED' and response_hash is None,'no invented response observation')
    else:need(response_hash is not None and value['finish_reason'] != 'NOT_OBSERVED','parsed response hash')
    usage=value['reported_usage']
    if usage is not None:
        need(value['body_parsed'] and isinstance(usage,dict) and set(usage) == {'prompt_tokens','completion_tokens','total_tokens','reasoning_tokens'}
            and all(type(usage[k]) is int and 0 <= usage[k] <= 2**31 for k in ('prompt_tokens','completion_tokens','total_tokens'))
            and usage['total_tokens'] == usage['prompt_tokens']+usage['completion_tokens']
            and (usage['reasoning_tokens'] is None or type(usage['reasoning_tokens']) is int and 0 <= usage['reasoning_tokens'] <= usage['completion_tokens']),'typed numeric reported usage, no accepted-usage claim')
    for key in ('completion_choice_count','output_choices_count'):
        need(value[key] is None or type(value[key]) is int and 0 <= value[key] <= 262144,'bounded optional counts')
    indices=value['indices'];need(isinstance(indices,list) and len(indices) <= 5 and all(v is None or type(v) is int and abs(v) <= 2**31 for v in indices),'bounded numeric indices only')
    need(len(indices) == (min(value['output_choices_count'],5) if value['output_choices_count'] is not None else 0),'projection covers the first at most five returned choices')
    for key in ('indices_eligible','reason_lengths','reason_normalized_lengths','reason_canonical','reason_controls'):
        need(isinstance(value[key],list) and len(value[key]) == len(indices),'aligned bounded diagnostic projections')
    for key in ('reason_lengths','reason_normalized_lengths'):
        need(all(v is None or type(v) is int and 0 <= v <= 2**31 for v in value[key]),'finite numeric reason lengths')
    for key in ('reason_canonical','reason_controls'):
        need(all(v is None or type(v) is bool for v in value[key]),'reason flags without text')
    expected_unique=len(set(indices)) == len(indices) if indices and None not in indices else None
    need(value['indices_unique'] is expected_unique and all(type(v) is bool for v in value['indices_eligible'])
         and value['indices_eligible'] == [v in decision['eligible_catalog_indices'] if v is not None else False for v in indices],'recomputed index constraints')
    if not value['body_parsed']:need(usage is None and value['completion_choice_count'] is None and value['output_choices_count'] is None and not indices,'no derived data without a parsed response')
    return value


def _result(decision,checked):
    context,request = decision['context'],decision['request'];chosen = checked['ranking']
    baseline = [v for v in context['raw_provider_order'] if v not in request['excluded_entity_ids']][:5]
    reasons = [{'catalog_index':r['catalog_index'],'entity_id':context['candidate_catalog'][r['catalog_index']]['entity_id'],
        'kind':'MODEL_INTERPRETATION','verification':'NOT_FACT_CHECKED','text':r['text'],'provider_cause_verified':False} for r in checked['reasons']]
    return {'schema_version':1,'protocol':PROTOCOL,'mode':request['mode'],'seed_identity':context['seed_identity'],
        'known_favorite_movie':context['known_favorite_movie'],'candidate_catalog':context['candidate_catalog'],'candidate_count':len(context['candidate_catalog']),
        'raw_selection':chosen,'delivered':list(chosen),'baseline_delivered':baseline,'reasons':reasons,'intent_text':request['intent_text'],
        'excluded_entity_ids':request['excluded_entity_ids'],'eligible_count':len(decision['eligible_catalog_indices']),
        'information_policy':{'intent_text_sent_to_qloo':False,'intent_text_sent_to_model':bool(request['intent_text']),'stated_taste_first_when_present':True,
            'same_explicit_information':not bool(request['intent_text']),'model_cinematic_knowledge_allowed':True,'model_knowledge_fact_checked':False,
            'same_total_information_attested':False,'baseline':'provider-page-order-with-same-identity-exclusion-guard','comparison_is_quality_metric':False,'taste_quality_gate':'NOT_VALIDATED'},
        'boundaries':{'positive_signal_sha256':context['positive_signal_sha256'],'context_sha256':context['context_sha256'],'catalog_sha256':context['catalog_sha256'],
            'input_binding_sha256':decision['input_binding_sha256'],'raw_selection_sha256':fingerprint(chosen),'delivery_sha256':fingerprint(chosen),
            'baseline_delivery_sha256':fingerprint(baseline),'reasons_sha256':fingerprint(reasons),'presentation_sha256':fingerprint(context['presentation_assets'])},
        'provider_rows_count':sum(v['row_count'] for v in context['pages']),'rejected_rows_count':len(context['rejected_rows']),
        'deduplicated_rows_count':len(context['duplicate_rows']),'presentation_assets':context['presentation_assets'],
        'preference_gate':'PASS','cultural_quality':'NOT_VALIDATED','satisfaction_score':None}


def verify_discoveries(directory, *, original_output_directory=None):
    directory = checked_path(Path(directory))
    if read(directory/'wide-plan.json').get('protocol_version') == 'qloo-wide-cinema-discovery-v3':
        from .wide_cinema_v3_verify import verify_discoveries as verify_v3
        return verify_v3(directory,original_output_directory=original_output_directory)
    if read(directory/'wide-plan.json').get('protocol_version') == 'qloo-wide-cinema-discovery-v4':
        from .wide_cinema_v4_verify import verify_discoveries as verify_v4
        return verify_v4(directory,original_output_directory=original_output_directory)
    if read(directory/'wide-plan.json').get('protocol_version') == 'qloo-wide-cinema-discovery-v5':
        from .wide_cinema_v5_verify import verify_discoveries as verify_v5
        return verify_v5(directory,original_output_directory=original_output_directory)
    need(original_output_directory is None,'explicit relocation is read-only historical v3 only')
    if not (directory/'wide-confirmation.json').exists():return verify_identity_search(directory)
    receipt,plan,events,offset,before = _search(directory,continuing=True)
    need(receipt['verification_status'] == 'VERIFIED_IDENTITY_SEARCH','capture only after successful search')
    confirmation = read(directory/'wide-confirmation.json');request = plan['request']
    need(set(confirmation) == {'schema_version','protocol','plan_sha256','identity_receipt','selected_seed_entity_id','selected_favorite_movie_entity_id','seed_identity','known_favorite_movie'}
         and type(confirmation['schema_version']) is int and confirmation['schema_version'] == 1 and confirmation['protocol'] == PROTOCOL
         and confirmation['plan_sha256'] == plan['plan_sha256'],'closed confirmation')
    clean = lambda r:{k:v for k,v in r.items() if k != 'verified_utc'}
    need(same(clean(confirmation['identity_receipt']),clean(receipt)),'original identity receipt inventory')
    seeds = [v for v in receipt['seed_candidates'] if v['entity_id'] == confirmation['selected_seed_entity_id']]
    need(len(seeds) == 1 and same(seeds[0],confirmation['seed_identity']),'original explicit seed selection');seed = seeds[0];favorite = None
    if request['favorite_movie_query'] is not None:
        movies = [v for v in receipt['favorite_movie_candidates'] if v['entity_id'] == confirmation['selected_favorite_movie_entity_id']]
        need(len(movies) == 1 and same(movies[0],confirmation['known_favorite_movie']) and movies[0]['entity_id'] != seed['entity_id'],'original explicit favorite selection');favorite = movies[0]
    else:need(confirmation['known_favorite_movie'] is None and confirmation['selected_favorite_movie_entity_id'] is None,'no invented favorite')
    tail = events[offset:];need(tail and tail[0]['kind'] == 'wide_confirmed' and same(tail[0]['data'],{'sha256':before['wide-confirmation.json']}),'confirmation before retrieval')
    report = read(directory/'wide-report.json');i = 1;observed = receipt['qloo_attempts'];admitted = 0;samples = [];names = []
    for page in (1,2):
        if i >= len(tail) or tail[i]['kind'] != 'wide_page_admitted':break
        http = _http(request['mode'],seed,favorite,page)
        need(same(tail[i]['data'],{'page':page,'params':http['params']}),'exact next page, no whitelist');i += 1;admitted += 1;rows = None
        if i < len(tail) and tail[i]['kind'] == 'tool_call':
            sample,name = _sample(directory,tail[i],http);names.append(name);i += 1;observed += 1
            try:rows = _page(request['mode'],seed,favorite,sample)
            except SchemaError:rows = None
        elif i < len(tail) and tail[i]['kind'] == 'transport_failure':
            need(_failure(tail[i]['data'],http),'page transport boundary');i += 1;observed += 1
        if i < len(tail) and tail[i]['kind'] == 'wide_page_accepted':
            need(rows is not None and same(tail[i]['data'],{'page':page,'sample_sha256':before[name],'row_count':len(rows)}),'semantic page success before next page');i += 1
            samples.append((sample,before[name],rows))
        else:break
    context = None
    if len(samples) == 2:
        try:context = _context(request['mode'],seed,favorite,samples)
        except SchemaError:context = None
    decision = None
    if i < len(tail) and tail[i]['kind'] == 'wide_context_frozen':
        need(context is not None and same(read(directory/'wide-context.json'),context) and same(tail[i]['data'],{'sha256':before['wide-context.json']}),'independently reconstructed frozen universe');i += 1
        try:decision = _decision(request,context,directory.name)
        except SchemaError:decision = None
    prepared = manifest = None
    if i < len(tail) and tail[i]['kind'] == 'wide_model_attempt_prepared':
        need(decision is not None,'no model before valid eligible universe');manifest = read(directory/'wide-model-manifest.json')
        need(same(manifest,expected_manifest('test-double-only' if receipt['source'] == 'test-double-only' else 'remote-llm')),'closed manifest')
        prepared = tail[i]['data'];i += 1;wire = _wire(decision,manifest);encoded = json.dumps(wire,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        need(set(prepared) == {'request_id','input_sha256','provider_request_sha256','wire_sha256','request_bytes','reservation'},'closed preparation')
        costs = prepared['reservation'];need(isinstance(costs,dict) and set(costs) == {'tokens','input_tokens','output_tokens'} and all(type(v) is int for v in costs.values())
            and costs['output_tokens'] == 1024 and costs['input_tokens'] >= 1024 and costs['tokens'] == costs['input_tokens']+1024 and costs['tokens'] <= 8000,'bounded full-wire reservation')
        need(len(encoded) <= 65536 and same({k:v for k,v in prepared.items() if k != 'reservation'},
            {'request_id':decision['request_id'],'input_sha256':fingerprint(_input_schema(decision)[0]),'provider_request_sha256':fingerprint(wire),
             'wire_sha256':hashlib.sha256(encoded).hexdigest(),'request_bytes':len(encoded)}),'prepared input/wire binding')
    diagnostic=None;diagnostic_present='wide-model-rejection.json' in before
    if i < len(tail) and tail[i]['kind'] == 'wide_model_rejected':
        need(prepared is not None and decision is not None and diagnostic_present
             and report['model_attempts'] == 1 and 'wide-execution-001.json' not in before,'rejection after one prepared decision, never an accepted packet')
        diagnostic=_rejection(read(directory/'wide-model-rejection.json'),decision,prepared)
        need(same(tail[i]['data'],{'sha256':before['wide-model-rejection.json'],'stage':diagnostic['stage'],'code':diagnostic['code']}),'hash-bound rejection projection')
        i+=1
    else:need(not diagnostic_present,'no orphaned rejection diagnostic')
    packet_present = 'wide-execution-001.json' in before;checked = None;model_recorded = result_recorded = False
    if packet_present:
        need(prepared is not None,'packet after admitted preparation only');packet = read(directory/'wide-execution-001.json')
        checked = verify_packet(packet,manifest,decision)
        need(packet['observation']['prompt_eval_count'] <= prepared['reservation']['input_tokens'],'observed usage within reservation')
    if i < len(tail) and tail[i]['kind'] == 'wide_execution_recorded':
        need(packet_present and same(tail[i]['data'],{'sha256':before['wide-execution-001.json']}),'recorded accepted packet');i += 1;model_recorded = True
    result = _result(decision,checked) if checked is not None else None
    if 'wide-result.json' in before:need(result is not None and same(read(directory/'wide-result.json'),result),'independent selection/baseline/presentation projection')
    if i < len(tail) and tail[i]['kind'] == 'wide_result_recorded':
        need(model_recorded and result is not None and 'wide-result.json' in before and same(tail[i]['data'],{'sha256':before['wide-result.json']}),'result after recorded model');i += 1;result_recorded = True
    complete = i < len(tail) and tail[i]['kind'] == 'wide_complete'
    if complete:need(diagnostic is None and result_recorded and i == len(tail)-1 and same(tail[i]['data'],{'candidate_count':len(context['candidate_catalog']),'delivered_count':5}),'closed completed terminal')
    else:need(i == len(tail)-1 and tail[i]['kind'] == 'wide_capture_stopped' and same(tail[i]['data'],{'error_class':report['error_class']})
        and isinstance(report['error_class'],str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,99}',report['error_class']),'terminal partial prefix, no later work')
    expected = {'schema_version':14,'protocol_version':PROTOCOL,'run_id':directory.name,'phase':'CONFIRMED_DISCOVERIES','plan_sha256':plan['plan_sha256'],
        'status':'COMPLETE' if complete else 'INCOMPLETE','source':receipt['source'],'qloo_attempts':report.get('qloo_attempts'),'model_attempts':report.get('model_attempts'),
        'error_class':None if complete else report['error_class'],'wide_cinema_results':result if complete else None,'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}
    need(same(report,expected) and type(report['qloo_attempts']) is int and observed <= report['qloo_attempts'] <= receipt['qloo_attempts']+admitted
         and type(report['model_attempts']) is int and int(packet_present) <= report['model_attempts'] <= int(prepared is not None),'closed final report and all attempted operations')
    if complete:need(report['qloo_attempts'] == plan['maximum_qloo_requests'] and report['model_attempts'] == 1,'exact complete3/4Q and1G')
    required = set(receipt['artifact_sha256']) | {'wide-confirmation.json','wide-report.json',*names}
    optional = {'wide-context.json','wide-model-manifest.json','wide-execution-001.json','wide-result.json','wide-model-rejection.json'}
    need(required <= set(before) <= required | optional,'closed artifact inventory')
    if 'wide-context.json' in before:need(context is not None and same(read(directory/'wide-context.json'),context),'partial context integrity')
    if 'wide-model-manifest.json' in before:need(decision is not None and same(read(directory/'wide-model-manifest.json'),expected_manifest('test-double-only' if receipt['source'] == 'test-double-only' else 'remote-llm')),'partial operator integrity')
    return {**receipt,'verified_utc':utc_now(),'verification_status':'VERIFIED_COMPLETE' if complete else 'VERIFIED_PARTIAL','status':report['status'],
        'artifact_sha256':before,'qloo_attempts':report['qloo_attempts'],'model_attempts':report['model_attempts'],'error_class':report['error_class'],
        'seed_identity':seed,'known_favorite_movie':favorite,'wide_cinema_results':result if complete else None,
        'model_rejection':diagnostic,
        'verified_provider_samples':len(list(directory.glob('http-*.json'))),'verified_model_packets':int(packet_present),
        'preference_gate':'PASS' if complete else 'NOT_EVALUATED','integration_gate':'OBSERVED_COMPLETE' if complete else 'INCOMPLETE',
        'causal_gate':'NOT_EVALUATED','behavioral_gate':'NOT_EVALUATED','cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED','external_service_attested':False}
