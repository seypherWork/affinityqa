"""Independent raw-sample, event-prefix and model-envelope verification."""
import copy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

from .agents import strict_json
from .evidence import fingerprint, utc_now
from .errors import SchemaError
from .individual_verify import checked_path, inventory, sha
from .individual_remote_verify import expected_manifest as base_manifest
from .models import canonical_id, normalized_name, parse_entities
from .open_movie_discovery import PROTOCOL, SOURCE, CONTEXT_PROTOCOL, PROMPT

SOURCES = ('open_movie_discovery.py', 'open_movie_discovery_agent.py', 'open_movie_discovery_capture.py',
           'open_movie_discovery_verify.py', 'qloo.py', 'models.py', 'evidence.py', 'errors.py', 'agents.py',
           'groq_agent.py', 'individual_capture.py', 'provider_runtime.py', 'provider_scheduler.py', 'qloo_cache.py')


def need(condition, message):
    if not condition:raise SchemaError('Open verification: ' + message)


def read(path):
    # The shared strict codec accepts objects only. A fixed wrapper retains its
    # UTF-8/duplicate/nonfinite checks for the saved candidate array as well.
    wrapped = strict_json(b'{"artifact":' + path.read_bytes() + b'}')
    need(set(wrapped) == {'artifact'}, 'one strict artifact value')
    return wrapped['artifact']


def same(a, b):
    try:return fingerprint(a) == fingerprint(b)
    except (TypeError, ValueError, RecursionError):return False


def _request(value):
    need(isinstance(value, dict) and set(value) == {'schema_version', 'movie_query', 'intent_text', 'excluded_entity_ids', 'model'}
        and type(value['schema_version']) is int and value['schema_version'] == 8, 'closed normalized request8')
    from .open_movie_discovery import text
    need(value['movie_query'] == text(value['movie_query'], 1, 200) and value['intent_text'] == text(value['intent_text'], 0, 600), 'canonical query/intention')
    x = value['excluded_entity_ids']
    need(isinstance(x, list) and len(x) <= 15 and all(isinstance(v, str) and canonical_id(v) == v for v in x)
         and x == sorted(set(x)), 'canonical exclusion set')
    need(same(value['model'], {'provider': 'groq', 'name': 'openai/gpt-oss-20b'}), 'owner model')
    return copy.deepcopy(value)


def _movie(value):
    from .open_movie_discovery import text
    need(isinstance(value, dict) and set(value) == {'entity_id', 'name', 'release_year', 'type'}, 'closed movie identity')
    need(isinstance(value['entity_id'], str) and value['entity_id'] == canonical_id(value['entity_id'])
        and value['type'] == 'urn:entity:movie' and value['name'] == text(value['name'], 1, 300)
        and type(value['release_year']) is int and 1888 <= value['release_year'] <= 2100, 'actual title/year/type')
    return copy.deepcopy(value)


def expected_manifest(source):
    value = base_manifest(source)
    value.update(max_inference_calls=1, prompt_version=PROTOCOL, prompt_sha256=fingerprint(PROMPT),
        tool_contract='open-real-movie-pool-v1', response_contract='open-movie-ranking-and-closed-interpretations-v1',
        maximum_token_reservation=8000, decision_scope='one-movie-one-observed-decision', prompt_cache_discount_reserved=False)
    return value


def _plan(directory):
    actual = read(directory / 'open-plan.json'); request = _request(actual['request']); source = Path(__file__).resolve().parent
    expected = {'schema_version': 10, 'protocol_version': PROTOCOL, 'mode': 'open-movie-discovery', 'request': request,
        'output_directory': str(directory.parent), 'source_sha256': {n: sha(source / n) for n in SOURCES},
        'driver_sha256': sha(source / 'open_movie_discovery_capture.py'), 'verification_driver_sha256': sha(source / 'open_movie_discovery_verify.py'),
        'dependencies_lock_sha256': sha(source.parents[1] / 'requirements-backend.lock.txt'),
        'remote_operator': expected_manifest('remote-llm'), 'maximum_qloo_requests': 2, 'maximum_identity_search_requests': 1,
        'maximum_insights_requests': 1, 'maximum_model_decisions': 1, 'maximum_attempts_per_request': 1,
        'maximum_model_load_requests': 0, 'maximum_model_metadata_requests': 0,
        'candidate_policy': {'minimum': 5, 'maximum': 20, 'source': 'exact-recorded-open-qloo-response',
                             'all_rows_typed_with_integer_year': True, 'fixed_catalog_fallback': False},
        'identity_candidate_contract': 'qloo-open-movie-title-year-slot-v1', 'faults': [],
        'execution_pacing': {'strategy': 'one-model-send-shared-provider-scheduler', 'minimum_interval_seconds': 0},
        'maximum_token_reservation': 8000, 'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED'}
    expected['plan_sha256'] = fingerprint(expected)
    need(same(actual, expected), 'source, plan, operator, parameters or budgets changed')
    return actual


def _events(directory):
    raw = (directory / 'ledger.jsonl').read_bytes(); events = [strict_json(row) for row in raw.splitlines()]
    need(1 <= len(events) <= 20, 'bounded nonempty event prefix')
    for i, event in enumerate(events, 1):
        need(set(event) == {'sequence', 'timestamp_utc', 'source', 'kind', 'data'} and type(event['sequence']) is int
             and event['sequence'] == i and event['source'] in (SOURCE, 'test-double-only') and isinstance(event['data'], dict), 'closed event sequence')
        instant = datetime.fromisoformat(event['timestamp_utc']); need(instant.utcoffset() is not None, 'timestamp timezone')
        if i > 1:need(event['source'] == events[0]['source'] and instant >= datetime.fromisoformat(events[i-2]['timestamp_utc']), 'monotonic event observations')
    return raw, events


def _sample(directory, event, expected_request):
    name = event['data'].get('sample')
    need(name == f'http-{event["sequence"]:04d}.json', 'sample event filename')
    value = read(directory / name)
    keys = {'source', 'request', 'status', 'response', 'response_sha256', 'response_headers', 'elapsed_ms', 'attempt', 'live_network_request'}
    need(set(value) == keys and value['source'] == event['source'] and same(value['request'], expected_request)
         and type(value['attempt']) is int and value['attempt'] == 1
         and type(value['status']) is int and 100 <= value['status'] <= 599
         and value['live_network_request'] is (value['source'] != 'test-double-only'), 'exact actual request/provenance/attempt')
    need(same(event['data'], {'sample': name, **{k: v for k, v in value.items() if k != 'response'}}), 'sample/ledger binding')
    need(type(value['elapsed_ms']) in (int, float) and math.isfinite(value['elapsed_ms']) and value['elapsed_ms'] >= 0
         and isinstance(value['response_headers'], dict) and value['response_sha256'] == fingerprint(value['response']), 'HTTP observation/hash')
    return value, name


def _choices(body):
    rows = parse_entities(body, insights=False); need(1 <= len(rows) <= 5, 'bounded search choices')
    result = []
    for r in rows:
        need('urn:entity:movie' in r.types, 'search movie category')
        result.append(_movie({'entity_id': r.entity_id, 'name': r.name, 'release_year': r.metadata.get('release_year'), 'type': 'urn:entity:movie'}))
    need(len({r['entity_id'] for r in result}) == len(result), 'unique search choices')
    return result


def _transport_failure(data, request):
    ordinary = {'request': request, 'attempt': 1}
    return same(data, ordinary) or same(data, {**ordinary, 'outcome': 'UNKNOWN', 'automatic_retry': False})


def _search(directory, *, continuing=False):
    before = inventory(directory); plan = _plan(directory); raw, all_events = _events(directory)
    prefix = (directory / 'identity-ledger.jsonl').read_bytes()
    need(raw.startswith(prefix), 'immutable identity ledger prefix changed')
    events = [strict_json(row) for row in prefix.splitlines()]
    need(events == all_events[:len(events)] and 1 <= len(events) <= 4, 'closed search prefix')
    if not continuing:need(raw == prefix, 'unexpected work before explicit confirmation')
    report = read(directory / 'open-search-report.json')
    keys = {'schema_version', 'protocol_version', 'run_id', 'phase', 'plan_sha256', 'status', 'source', 'movie_query',
            'movie_candidates', 'qloo_attempts', 'model_attempts', 'error_class', 'cultural_gate', 'release_gate'}
    need(set(report) == keys and type(report['schema_version']) is int and report['schema_version'] == 10
         and report['protocol_version'] == PROTOCOL and report['run_id'] == directory.name and report['phase'] == 'MOVIE_SEARCH'
         and report['plan_sha256'] == plan['plan_sha256'] and report['source'] == events[0]['source']
         and report['movie_query'] == plan['request']['movie_query'] and type(report['model_attempts']) is int and report['model_attempts'] == 0
         and report['cultural_gate'] == 'NOT_VALIDATED' and report['release_gate'] == 'BLOCKED', 'closed search report')
    params = {'query': plan['request']['movie_query'], 'types': 'urn:entity:movie', 'take': 5}
    expected_request = {'method': 'GET', 'host': 'https://hackathon.api.qloo.com', 'path': '/search', 'params': params}
    index = 0; observed = 0; choices = None; sample_names = []
    if events[0]['kind'] == 'open_search_admitted':
        need(same(events[0]['data'], {'params': params}), 'exact search admission'); index += 1
        if index < len(events) and events[index]['kind'] == 'tool_call':
            sample, name = _sample(directory, events[index], expected_request); sample_names.append(name); observed = 1; index += 1
            if sample['status'] == 200:
                try:choices = _choices(sample['response'])
                except SchemaError:choices = None
        elif index < len(events) and events[index]['kind'] == 'transport_failure':
            need(_transport_failure(events[index]['data'], expected_request), 'search transport boundary')
            observed = 1; index += 1
    if index < len(events) and events[index]['kind'] == 'open_search_candidates_recorded':
        need(choices is not None and same(read(directory / 'open-movie-candidates.json'), choices)
             and same(events[index]['data'], {'sha256': sha(directory / 'open-movie-candidates.json')}), 'actual candidate projection')
        index += 1
    success = index == len(events) and choices is not None and events[-1]['kind'] == 'open_search_candidates_recorded'
    if not success:
        need(index == len(events) - 1 and events[index]['kind'] == 'open_search_stopped'
             and same(events[index]['data'], {'error_class': report['error_class']})
             and isinstance(report['error_class'], str) and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,99}', report['error_class']), 'terminal partial search prefix')
    need(type(report['qloo_attempts']) is int and observed <= report['qloo_attempts'] <= (1 if events[0]['kind'] == 'open_search_admitted' else 0), 'search attempt accounting')
    need(report['status'] == ('AWAITING_IDENTITY_CONFIRMATION' if success else 'INCOMPLETE')
         and same(report['movie_candidates'], choices if success else []) and (report['error_class'] is None) == success, 'search outcome')
    initial_names = {'open-plan.json', 'open-search-report.json', 'identity-ledger.jsonl', 'ledger.jsonl', *sample_names}
    if 'open-movie-candidates.json' in before:
        need(choices is not None and same(read(directory / 'open-movie-candidates.json'), choices), 'partial candidate file')
        initial_names.add('open-movie-candidates.json')
    initial = {name: before[name] for name in initial_names}
    initial['ledger.jsonl'] = hashlib.sha256(prefix).hexdigest()
    if not continuing:need(set(before) == initial_names, 'unknown identity artifacts')
    receipt = {'schema_version': 1, 'verified_utc': utc_now(), 'protocol_version': PROTOCOL,
        'mode': 'open-movie-discovery', 'run_id': directory.name, 'plan_sha256': plan['plan_sha256'],
        'status': report['status'], 'source': report['source'], 'provenance': 'SIMULATION_ONLY' if report['source'] == 'test-double-only' else 'RECORDED_REMOTE_EXECUTION',
        'verification_status': 'VERIFIED_IDENTITY_SEARCH' if success else 'VERIFIED_PARTIAL',
        'movie_query': report['movie_query'], 'movie_candidates': copy.deepcopy(choices if success else []),
        'qloo_attempts': report['qloo_attempts'], 'model_attempts': 0, 'error_class': report['error_class'],
        'artifact_sha256': initial, 'causal_gate': 'NOT_EVALUATED', 'behavioral_gate': 'NOT_EVALUATED',
        'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED', 'external_service_attested': False}
    return receipt, plan, all_events, len(events), before


def verify_identity_search(directory):
    directory = checked_path(Path(directory)); return _search(directory)[0]


def _context(seed, sample, sample_sha):
    need(sample['status'] == 200, 'successful candidate response')
    rows = parse_entities(sample['response'], insights=True); need(5 <= len(rows) <= 20, 'five to twenty actual rows')
    catalog = []
    for r in rows:
        need('urn:entity:movie' in r.types and r.affinity is not None, 'typed actual affinity')
        movie = _movie({'entity_id': r.entity_id, 'name': r.name, 'release_year': r.metadata.get('release_year'), 'type': 'urn:entity:movie'})
        need(movie['entity_id'] != seed['entity_id'] and (normalized_name(movie['name']), movie['release_year']) !=
             (normalized_name(seed['name']), seed['release_year']), 'seed or alternate seed returned')
        catalog.append({k: movie[k] for k in ('entity_id', 'name', 'release_year')})
    catalog.sort(key=lambda r: r['entity_id'])
    need(len({(normalized_name(r['name']), r['release_year']) for r in catalog}) == len(catalog), 'duplicate movie aliases')
    value = {'schema_version': 1, 'protocol': CONTEXT_PROTOCOL, 'source': sample['source'], 'seed_movie': seed,
        'seed_sha256': fingerprint(seed), 'candidate_catalog': catalog, 'catalog_sha256': fingerprint(catalog),
        'raw_provider_ranking': [r.entity_id for r in rows], 'provider_affinities': [{'entity_id': r.entity_id, 'affinity': r.affinity} for r in rows],
        'request_sha256': fingerprint(sample['request']), 'response_sha256': sample['response_sha256'], 'sample_sha256': sample_sha}
    value['context_sha256'] = fingerprint(value); return value


def _decision(request, context, run_id):
    eligible = [i for i, row in enumerate(context['candidate_catalog']) if row['entity_id'] not in request['excluded_entity_ids']]
    need(len(eligible) >= 5, 'at least five actual eligible movies')
    value = {'schema_version': 1, 'protocol': PROTOCOL, 'request': request, 'context': context,
        'eligible_catalog_indices': eligible, 'request_nonce': 'open-' + run_id,
        'provider_intent_sha256': fingerprint(context['seed_movie']),
        'application_intent_sha256': fingerprint({'seed_movie': context['seed_movie'], 'intent_text': request['intent_text'],
            'excluded_entity_ids': request['excluded_entity_ids'], 'catalog_sha256': context['catalog_sha256']})}
    value['request_id'] = fingerprint(value); return value


def _input_and_schema(decision):
    context, request = decision['context'], decision['request']; catalog = context['candidate_catalog']; ids = [r['entity_id'] for r in catalog]
    indices = list(range(len(ids)))
    schema = {'type': 'object', 'properties': {'ordered_catalog_indices': {'type': 'object', 'properties': {
        'ranking': {'type': 'array', 'items': {'type': 'integer', 'enum': indices}, 'minItems': len(indices), 'maxItems': len(indices)},
        'reasons': {'type': 'array', 'items': {'type': 'object', 'properties': {'catalog_index': {'type': 'integer', 'enum': indices},
            'text': {'type': 'string', 'minLength': 40, 'maxLength': 240}}, 'required': ['catalog_index', 'text'], 'additionalProperties': False}, 'minItems': 5, 'maxItems': 5}},
        'required': ['ranking', 'reasons'], 'additionalProperties': False}}, 'required': ['ordered_catalog_indices'], 'additionalProperties': False}
    payload = {'protocol': PROTOCOL, 'seed_movie': copy.deepcopy(context['seed_movie']),
        'catalog': [{'index': i, **copy.deepcopy(r)} for i, r in enumerate(catalog)],
        'provider_context': [{'catalog_index': ids.index(r['entity_id']), 'affinity': r['affinity']} for r in context['provider_affinities']],
        'intent_text': request['intent_text'], 'eligible_catalog_indices': list(decision['eligible_catalog_indices']),
        'intent_notice': 'Additional text goes only to this model; the Qloo baseline did not receive it.',
        'reason_notice': 'Individualized model interpretations may use cinematic model knowledge: NOT_FACT_CHECKED, never certified by Qloo.', 'output_schema': schema}
    return payload, schema, None


def verify_packet(packet, manifest, context, request, run_id):
    need(isinstance(packet, dict) and set(packet) == {'execution_id', 'effective_request', 'model_payload', 'response', 'observation', 'cache_key_sha256'}, 'closed packet')
    decision = _decision(request, context, run_id); need(same(packet['effective_request'], decision) and packet['execution_id'] == run_id + '/1', 'exact effective decision')
    source = 'test-double-only' if context['source'] == 'test-double-only' else 'remote-llm'
    need(same(manifest, expected_manifest(source)), 'closed model manifest')
    payload, schema, texts = _input_and_schema(decision); need(same(packet['model_payload'], payload), 'independently reconstructed payload')
    wire = {'model': manifest['model'], 'messages': [{'role': 'system', 'content': PROMPT},
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)}],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'affinityqa_open_movies_v1', 'strict': True, 'schema': schema}}, **manifest['options']}
    obs = packet['observation']; envelope = obs['provider_envelope']
    need(set(envelope) == {'schema_version', 'execution_source', 'provider', 'object', 'model', 'id', 'created', 'system_fingerprint', 'choice', 'usage'}
         and type(envelope['schema_version']) is int and envelope['schema_version'] == 1 and envelope['execution_source'] == source
         and envelope['provider'] == 'groq' and envelope['object'] == 'chat.completion' and envelope['model'] == manifest['model'], 'model envelope')
    need(isinstance(envelope['id'], str) and re.fullmatch(r'[!-~]{1,160}', envelope['id'])
         and type(envelope['created']) is int and 1 <= envelope['created'] <= 2**63 - 1, 'completion ID/time')
    system_fp = envelope['system_fingerprint']; need(system_fp is None or isinstance(system_fp, str) and re.fullmatch(r'[!-~]{1,128}', system_fp), 'system fingerprint')
    choice = envelope['choice']; need(set(choice) == {'index', 'finish_reason', 'role', 'ordered_catalog_indices'}
         and type(choice['index']) is int and choice['index'] == 0 and choice['finish_reason'] == 'stop' and choice['role'] == 'assistant', 'complete choice')
    block = choice['ordered_catalog_indices']; need(isinstance(block, dict) and set(block) == {'ranking', 'reasons'}, 'conserved nested ranking and reasons')
    n = len(context['candidate_catalog']); order = block['ranking']
    need(isinstance(order, list) and len(order) == n and all(type(i) is int for i in order) and set(order) == set(range(n)), 'complete real-candidate permutation')
    delivered_indices = [i for i in order if i in decision['eligible_catalog_indices']][:5]
    from .open_movie_discovery import text
    reasons = block['reasons']; need(isinstance(reasons, list) and len(reasons) == 5 and all(isinstance(r, dict)
         and set(r) == {'catalog_index', 'text'} and type(r['catalog_index']) is int
         and isinstance(r['text'], str) and 40 <= len(r['text']) <= 240 and r['text'] == text(r['text'], 40, 240) for r in reasons)
         and [r['catalog_index'] for r in reasons] == delivered_indices, 'closed interpretations for delivered indices')
    ids = [r['entity_id'] for r in context['candidate_catalog']]; checked = {'ranking': [ids[i] for i in order], 'reasons': reasons}
    key = fingerprint({'protocol': PROTOCOL, 'request': request, 'context': context, 'manifest': manifest})
    need(packet['cache_key_sha256'] == key and same(packet['response'], {'schema_version': 1, 'request_id': decision['request_id'],
         'ranked_entity_ids': checked['ranking'], 'reasons': reasons, 'output_sha256': fingerprint(checked), 'cache_key_sha256': key}), 'response/key binding')
    usage = envelope['usage']; need(set(usage) == {'prompt_tokens', 'completion_tokens', 'total_tokens', 'reasoning_tokens'}
         and type(usage['prompt_tokens']) is int and 1 <= usage['prompt_tokens'] <= 8192
         and type(usage['completion_tokens']) is int and 1 <= usage['completion_tokens'] <= 1024
         and type(usage['total_tokens']) is int and usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
         and (usage['reasoning_tokens'] is None or type(usage['reasoning_tokens']) is int and 0 <= usage['reasoning_tokens'] <= usage['completion_tokens']), 'usage bounds')
    need(type(obs['elapsed_ms']) in (int, float) and math.isfinite(obs['elapsed_ms']) and obs['elapsed_ms'] >= 0
         and isinstance(obs['provider_response_sha256'], str) and re.fullmatch('[a-f0-9]{64}', obs['provider_response_sha256']), 'observed response hash/time')
    expected = {'call': 1, 'input_sha256': fingerprint(payload), 'output_sha256': fingerprint(checked), 'elapsed_ms': obs['elapsed_ms'],
        'prompt_eval_count': usage['prompt_tokens'], 'eval_count': usage['completion_tokens'], 'private_thinking_recorded': False,
        'done': True, 'done_reason': 'stop', 'provider': 'groq', 'model': manifest['model'], 'completion_id': envelope['id'],
        'provider_created': envelope['created'], 'system_fingerprint': system_fp, 'provider_response_sha256': obs['provider_response_sha256'],
        'provider_response_hash_scope': 'Full parsed response observation; not reconstructible from the redacted envelope.',
        'provider_request_sha256': fingerprint(wire), 'provider_envelope': envelope, 'provider_envelope_sha256': fingerprint(envelope),
        'total_tokens': usage['total_tokens'], 'reasoning_tokens': usage['reasoning_tokens'], 'model_revision_attested': False, 'execution_source': source}
    need(same(obs, expected), 'complete observation boundaries')
    return decision, checked, wire


def _result(decision, checked):
    context, request = decision['context'], decision['request']; excluded = set(request['excluded_entity_ids'])
    raw = checked['ranking']; delivered = [v for v in raw if v not in excluded][:5]; baseline = [v for v in context['raw_provider_ranking'] if v not in excluded][:5]
    reasons = [{'catalog_index': r['catalog_index'], 'entity_id': context['candidate_catalog'][r['catalog_index']]['entity_id'],
        'kind': 'MODEL_INTERPRETATION', 'verification': 'NOT_FACT_CHECKED', 'text': r['text'], 'provider_cause_verified': False} for r in checked['reasons']]
    return {'schema_version': 1, 'protocol': PROTOCOL, 'seed_movie': context['seed_movie'], 'candidate_catalog': context['candidate_catalog'],
        'candidate_count': len(raw), 'raw_ranking': raw, 'delivered': delivered, 'baseline_delivered': baseline, 'reasons': reasons,
        'intent_text': request['intent_text'], 'excluded_entity_ids': request['excluded_entity_ids'],
        'information_policy': {'intent_text_sent_to_qloo': False, 'intent_text_sent_to_model': bool(request['intent_text']),
            'same_explicit_information': not bool(request['intent_text']), 'model_cinematic_knowledge_allowed': True,
            'model_knowledge_fact_checked': False, 'same_total_information_attested': False,
            'baseline': 'qloo-movie-affinity-with-same-local-exclusion-guard', 'comparison_is_quality_metric': False},
        'boundaries': {'seed_sha256': context['seed_sha256'], 'context_sha256': context['context_sha256'], 'catalog_sha256': context['catalog_sha256'],
            'provider_intent_sha256': decision['provider_intent_sha256'], 'application_intent_sha256': decision['application_intent_sha256'],
            'raw_ranking_sha256': fingerprint(raw), 'delivery_sha256': fingerprint(delivered), 'baseline_delivery_sha256': fingerprint(baseline), 'reasons_sha256': fingerprint(reasons)},
        'eligible_count': len(decision['eligible_catalog_indices']), 'seed_delivered': False, 'excluded_removed': [v for v in raw if v in excluded],
        'preference_gate': 'PASS', 'cultural_quality': 'NOT_VALIDATED', 'satisfaction_score': None}


def verify_discoveries(directory):
    directory = checked_path(Path(directory))
    if not (directory / 'open-confirmation.json').exists():return verify_identity_search(directory)
    receipt, plan, events, offset, before = _search(directory, continuing=True)
    need(receipt['verification_status'] == 'VERIFIED_IDENTITY_SEARCH', 'no capture after incomplete search')
    confirmation = read(directory / 'open-confirmation.json')
    need(set(confirmation) == {'schema_version', 'protocol', 'plan_sha256', 'identity_receipt', 'selected_movie_entity_id', 'seed_movie'}
         and type(confirmation['schema_version']) is int and confirmation['schema_version'] == 1 and confirmation['protocol'] == PROTOCOL
         and confirmation['plan_sha256'] == plan['plan_sha256'], 'closed explicit confirmation')
    clean = lambda r: {k: v for k, v in r.items() if k != 'verified_utc'}
    need(same(clean(confirmation['identity_receipt']), clean(receipt)), 'original identity receipt/inventory')
    selected = [r for r in receipt['movie_candidates'] if r['entity_id'] == confirmation['selected_movie_entity_id']]
    need(len(selected) == 1 and same(selected[0], confirmation['seed_movie']), 'explicit original UUID/title/year')
    seed = _movie(selected[0]); tail = events[offset:]; need(tail and tail[0]['kind'] == 'open_movie_confirmed'
         and same(tail[0]['data'], {'sha256': before['open-confirmation.json']}), 'confirmation precedes insights/model')
    request_http = {'method': 'GET', 'host': 'https://hackathon.api.qloo.com', 'path': '/v2/insights',
        'params': {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': 20,
                   'signal.interests.entities': seed['entity_id'], 'filter.exclude.entities': seed['entity_id']}}
    report = read(directory / 'open-report.json'); index = 1; context = None; checked = decision = None; sample_names = []
    observed_qloo = receipt['qloo_attempts']; admitted = False
    if index < len(tail) and tail[index]['kind'] == 'open_insights_admitted':
        admitted = True; need(same(tail[index]['data'], {'params': request_http['params']}), 'exact open query without fixed universe'); index += 1
        if index < len(tail) and tail[index]['kind'] == 'tool_call':
            sample, name = _sample(directory, tail[index], request_http); sample_names.append(name); observed_qloo += 1; index += 1
            try:context = _context(seed, sample, before[name])
            except SchemaError:context = None
        elif index < len(tail) and tail[index]['kind'] == 'transport_failure':
            need(_transport_failure(tail[index]['data'], request_http), 'open transport failure'); observed_qloo += 1; index += 1
    if index < len(tail) and tail[index]['kind'] == 'open_candidate_context_frozen':
        need(context is not None and same(read(directory / 'open-candidate-context.json'), context)
             and same(tail[index]['data'], {'sha256': before['open-candidate-context.json']}), 'actual frozen candidate universe'); index += 1
        try:decision = _decision(plan['request'], context, directory.name)
        except SchemaError:decision = None
    prepared = None; manifest = None
    if index < len(tail) and tail[index]['kind'] == 'open_model_attempt_prepared':
        need(decision is not None, 'no model after missing/invalid context or too few eligible candidates')
        manifest = read(directory / 'open-model-manifest.json'); need(same(manifest, expected_manifest('test-double-only' if receipt['source'] == 'test-double-only' else 'remote-llm')), 'actual model manifest')
        prepared = tail[index]['data']; index += 1
        need(set(prepared) == {'request_id', 'input_sha256', 'provider_request_sha256', 'wire_sha256', 'request_bytes', 'reservation'}, 'closed prepared boundary')
        payload, schema, _ = _input_and_schema(decision)
        wire = {'model': manifest['model'], 'messages': [{'role': 'system', 'content': PROMPT},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'affinityqa_open_movies_v1', 'strict': True, 'schema': schema}}, **manifest['options']}
        encoded = json.dumps(wire, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        costs = prepared['reservation']; need(isinstance(costs, dict) and set(costs) == {'tokens', 'input_tokens', 'output_tokens'}
            and all(type(v) is int for v in costs.values()) and costs['output_tokens'] == 1024 and costs['input_tokens'] >= 1024
            and costs['tokens'] == costs['input_tokens'] + 1024 and costs['tokens'] <= 8000, 'declared reservation bounds')
        need(same({k: v for k, v in prepared.items() if k != 'reservation'}, {'request_id': decision['request_id'], 'input_sha256': fingerprint(payload),
            'provider_request_sha256': fingerprint(wire), 'wire_sha256': hashlib.sha256(encoded).hexdigest(), 'request_bytes': len(encoded)}) and len(encoded) <= 65536, 'prepared wire/input hashes')
    packet_present = 'open-movie-execution-001.json' in before
    if packet_present:
        need(prepared is not None, 'packet without prepared model boundary')
        packet = read(directory / 'open-movie-execution-001.json')
        decision, checked, _ = verify_packet(packet, manifest, context, plan['request'], directory.name)
        need(packet['observation']['prompt_eval_count'] <= prepared['reservation']['input_tokens'], 'actual usage beyond reserved input')
    model_recorded = False
    if index < len(tail) and tail[index]['kind'] == 'open_model_execution_recorded':
        need(packet_present and same(tail[index]['data'], {'sha256': before['open-movie-execution-001.json']}), 'recorded accepted packet'); index += 1
        model_recorded = True
    result = _result(decision, checked) if checked is not None else None
    if 'open-movie-result.json' in before:
        need(result is not None and same(read(directory / 'open-movie-result.json'), result), 'independent raw/delivered/baseline/interpretation projection')
    result_recorded = False
    if index < len(tail) and tail[index]['kind'] == 'open_result_recorded':
        need(model_recorded and result is not None and 'open-movie-result.json' in before and same(tail[index]['data'], {'sha256': before['open-movie-result.json']}), 'result record'); index += 1
        result_recorded = True
    complete = index < len(tail) and tail[index]['kind'] == 'open_complete'
    if complete:
        need(index == len(tail) - 1 and result_recorded and result is not None and same(tail[index]['data'], {'candidate_count': len(result['candidate_catalog']), 'delivered_count': 5}), 'closed complete terminal')
    else:
        need(index == len(tail) - 1 and tail[index]['kind'] == 'open_capture_stopped'
             and same(tail[index]['data'], {'error_class': report['error_class']}) and isinstance(report['error_class'], str)
             and re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,99}', report['error_class']), 'closed partial terminal, no later work')
    keys = {'schema_version', 'protocol_version', 'run_id', 'phase', 'plan_sha256', 'status', 'source', 'qloo_attempts',
            'model_attempts', 'error_class', 'open_movie_results', 'cultural_gate', 'release_gate'}
    need(set(report) == keys and type(report['schema_version']) is int and report['schema_version'] == 10
         and report['protocol_version'] == PROTOCOL and report['run_id'] == directory.name and report['phase'] == 'CONFIRMED_OPEN_MOVIES'
         and report['source'] == receipt['source'] and report['plan_sha256'] == plan['plan_sha256']
         and report['status'] == ('COMPLETE' if complete else 'INCOMPLETE') and (report['error_class'] is None) == complete
         and report['cultural_gate'] == 'NOT_VALIDATED' and report['release_gate'] == 'BLOCKED', 'closed final report')
    need(type(report['qloo_attempts']) is int and observed_qloo <= report['qloo_attempts'] <= receipt['qloo_attempts'] + int(admitted)
         and type(report['model_attempts']) is int and int(packet_present) <= report['model_attempts'] <= int(prepared is not None), 'all bounded attempted operations')
    need(same(report['open_movie_results'], result if complete else None), 'report result/status binding')
    if complete:need(report['qloo_attempts'] == 2 and report['model_attempts'] == 1, 'complete exact2Qloo1Groq')
    allowed = set(receipt['artifact_sha256']) | {'open-confirmation.json', 'open-report.json', *sample_names}
    optional = {'open-candidate-context.json', 'open-model-manifest.json', 'open-movie-execution-001.json', 'open-movie-result.json'}
    need(set(before) <= allowed | optional and allowed <= set(before), 'closed complete/partial artifact inventory')
    if 'open-candidate-context.json' in before:need(context is not None and same(read(directory / 'open-candidate-context.json'), context), 'partial context integrity')
    if 'open-model-manifest.json' in before:need(decision is not None and same(read(directory / 'open-model-manifest.json'), expected_manifest('test-double-only' if receipt['source'] == 'test-double-only' else 'remote-llm')), 'partial manifest integrity')
    return {**receipt, 'verified_utc': utc_now(), 'status': report['status'], 'verification_status': 'VERIFIED_COMPLETE' if complete else 'VERIFIED_PARTIAL',
        'artifact_sha256': before, 'qloo_attempts': report['qloo_attempts'], 'model_attempts': report['model_attempts'],
        'error_class': report['error_class'], 'chosen_movie_input': seed, 'open_movie_results': result if complete else None,
        'candidate_catalog': copy.deepcopy(context['candidate_catalog']) if context is not None else [],
        'verified_provider_samples': len(list(directory.glob('http-*.json'))), 'verified_model_packets': int(packet_present),
        'preference_gate': 'PASS' if complete else 'NOT_EVALUATED', 'integration_gate': 'OBSERVED_COMPLETE' if complete else 'INCOMPLETE',
        'causal_gate': 'NOT_EVALUATED', 'behavioral_gate': 'NOT_EVALUATED', 'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
        'external_service_attested': False}
