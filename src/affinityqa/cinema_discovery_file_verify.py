"""Read-only staged file audit; actual samples, never self-hashes alone.

This checks recorded coherence. It neither authenticates providers nor validates
human taste, causal repair, sustained capacity or permission to publish.
"""
import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

from .agents import AgentError
from .causal_agent import profile_hash, validate_catalog
from .cinema_discoveries import DISCOVERY_PROMPT
from .cinema_discovery_capture import SOURCES
from .cinema_discovery_verify import expected_manifest, expected_input, preferences, verify_context, verify_packet
from .cinema_identity_verify import _candidates, _events, _sample, selection_profiles
from .errors import SchemaError
from .evidence import fingerprint, utc_now
from .individual_remote_capture import validate_request as artist_request
from .individual_remote_verify import expected_pacing
from .individual_verify import checked_path, inventory, read, instant, need, same, sha
from .models import parse_entities

SOURCE_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = 'cinema-confirmed-discovery-v2'
SOURCE = 'qloo-tool+groq-remote-discovery-v2'
DELIVERY = 'stable-nonseed-exclusion-guard-top-five-v1'
BASELINE = 'qloo-discovery-order+same-exclusion-guard-v1'


def diagnostic_contract():
    return {'schema_version': 1, 'request_receipt': 'discovery-prepared-request-v1',
        'failure_receipt': 'discovery-http-enums-v1', 'maximum_error_body_bytes': 8192,
        'raw_message_or_generation_recorded': False, 'external_dispatch_attested': False}


def verify_http_failure(failure):
    diagnostic = failure['http_failure']
    classes = {'DiscoveryRateLimitError', 'DiscoveryCredentialsError',
               'DiscoveryRequestRejectedError', 'DiscoveryServiceError'}
    if diagnostic is None:
        need(failure['error_class'] not in classes, 'typed HTTP failure lost its diagnostic')
        return
    need(failure['stage'] == 'model_dispatch' and isinstance(diagnostic, dict)
         and set(diagnostic) == {'schema_version', 'http_status', 'provider_error_type', 'provider_error_code'}
         and type(diagnostic['schema_version']) is int and diagnostic['schema_version'] == 1
         and type(diagnostic['http_status']) is int and 100 <= diagnostic['http_status'] <= 599,
         'closed HTTP failure diagnostic')
    need(diagnostic['provider_error_type'] is None or diagnostic['provider_error_type'] in
         ('invalid_request_error', 'server_error', 'validation_error', 'api_error'), 'unknown HTTP error type')
    need(diagnostic['provider_error_code'] is None or diagnostic['provider_error_code'] in
         ('json_validate_failed', 'tool_use_failed', 'model_not_found', 'invalid_request_error',
          'context_length_exceeded', 'invalid_json_schema', 'json_schema_validation_failed',
          'invalid_schema', 'invalid_parameter', 'unsupported_model', 'model_error'), 'unknown HTTP error code')
    code = diagnostic['http_status']
    expected = ('DiscoveryRateLimitError' if code == 429 else
                'DiscoveryCredentialsError' if code in (401, 403) else
                'DiscoveryRequestRejectedError' if 400 <= code < 500 else 'DiscoveryServiceError')
    need(failure['error_class'] == expected and failure['prepared_receipt_sha256'] is not None,
         'HTTP failure class or prepared request differs')
    need(1 <= failure['model_attempts'] == failure['admitted_model_slots'],
         'HTTP failure lacks its consumed model attempt')


def verify_prepared_requests(prepared, request, profiles, contexts, manifest, run_id, source):
    for slot, event in enumerate(prepared, 1):
        label = ('A', 'B')[slot-1]
        context = contexts[tool_key(profiles[label], request['catalog'], request['preferences'][label])[0]]
        effective = decision_request(request, profiles[label], context, label, run_id)
        payload_input = expected_input(effective)
        payload = {'model': manifest['model'], 'messages': [
            {'role': 'system', 'content': DISCOVERY_PROMPT},
            {'role': 'user', 'content': json.dumps(payload_input, ensure_ascii=False, allow_nan=False)}],
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'affinityqa_discovery_rank_slots_v2', 'strict': True,
                'schema': payload_input['output_schema']}}, **manifest['options']}
        wire = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        expected = {'schema_version': 1, 'protocol': 'discovery-prepared-request-v1',
            'execution_source': source, 'run_id': run_id, 'slot': slot,
            'request_id': effective['request_id'], 'input_sha256': fingerprint(payload_input),
            'provider_request_sha256': fingerprint(payload), 'wire_sha256': hashlib.sha256(wire).hexdigest(),
            'request_bytes': len(wire), 'external_dispatch_attested': False}
        need(same(event['data'], expected), 'prepared request differs from independent exact-wire reconstruction')


def _request(value):
    need(isinstance(value, dict) and set(value) == {'schema_version', 'artists', 'catalog', 'model', 'preferences'}
         and type(value['schema_version']) is int and value['schema_version'] == 5, 'discovery capture request5')
    base = artist_request({k: copy.deepcopy(v) for k, v in value.items() if k != 'preferences'} | {'schema_version': 2})
    need(isinstance(value['preferences'], dict) and set(value['preferences']) == {'A', 'B'}, 'two preference sets')
    return {**base, 'schema_version': 5, 'preferences': {
        label: preferences(value['preferences'][label], base['catalog']) for label in ('A', 'B')}}


def _plan(value):
    request = _request(value['request'])
    output = value['output_directory']
    need(isinstance(output, str) and len(output) <= 4000 and
         (PureWindowsPath(output).is_absolute() or PurePosixPath(output).is_absolute()), 'discovery output path')
    source = SOURCE_ROOT/'src/affinityqa'
    expected = {'schema_version': 6, 'protocol_version': PROTOCOL, 'mode': 'cinema-confirmed-discovery-capture',
        'request': request, 'output_directory': output, 'remote_operator': expected_manifest('remote-llm'),
        'diagnostic_contract': diagnostic_contract(),
        'execution_pacing': expected_pacing(value['execution_pacing']['minimum_interval_seconds']),
        'source_sha256': {name: sha(source/name) for name in SOURCES},
        'driver_sha256': sha(source/'cinema_discovery_capture.py'),
        'verification_driver_sha256': sha(source/'cinema_discovery_file_verify.py'),
        'dependencies_lock_sha256': sha(SOURCE_ROOT/'requirements-backend.lock.txt'),
        'maximum_qloo_requests': 4, 'maximum_identity_search_requests': 2, 'maximum_insights_requests': 2,
        'maximum_attempts_per_request': 1, 'maximum_model_decisions': 2, 'cache_checks_per_profile': 1,
        'faults': [], 'explicit_identity_confirmation_required': True,
        'new_model_metadata_requests': 0, 'startup_model_metadata_requests': 0,
        'runtime_model_metadata_requests': 0, 'model_load_requests': 0,
        'individual_demo_only': True, 'independent_validation_claim': False,
        'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
        'partial_failure_policy': 'Preserve all evidence, stop without retry or resume; only a successful identity search may continue after explicit confirmation.'}
    expected['plan_sha256'] = fingerprint(expected)
    need(same(value, expected), 'discovery plan, source or lock changed')
    return request


def _base_report(report, plan, directory, phase):
    common = {'schema_version', 'created_utc', 'run_id', 'mode', 'phase', 'source', 'status', 'plan_sha256',
        'identity_queries', 'qloo_attempts', 'model_attempts', 'model_load_attempts', 'error_class',
        'causal_gate', 'behavioral_gate', 'integration_gate', 'preference_gate', 'cultural_gate', 'release_gate',
        'release_approved', 'independent_validation_claim', 'partial_evidence_preserved', 'diagnostic_contract'}
    extra = {'identity_candidates'} if phase == 'IDENTITY_SEARCH' else {
        'chosen_identities', 'independent_verification', 'admitted_model_slots', 'requested_profiles',
        'successful_profiles', 'failed_model_attempts', 'terminal_failure', 'unattempted_profiles', 'cinema_results'}
    need(set(report) == common | extra, 'closed discovery report fields')
    need(type(report['schema_version']) is int and report['schema_version'] == 6 and report['run_id'] == directory.name
         and report['mode'] == plan['mode'] and report['plan_sha256'] == plan['plan_sha256'] and report['phase'] == phase,
         'discovery report/plan binding')
    instant(report['created_utc'])
    need(same(report['diagnostic_contract'], diagnostic_contract()), 'discovery diagnostic contract changed')
    need(report['source'] in (SOURCE, 'test-double-only')
         and report['causal_gate'] == report['behavioral_gate'] == report['integration_gate'] == 'NOT_EVALUATED'
         and report['cultural_gate'] == 'NOT_VALIDATED' and report['release_gate'] == 'BLOCKED'
         and report['release_approved'] is False and report['independent_validation_claim'] is False
         and report['partial_evidence_preserved'] is True, 'unsupported discovery quality/release claim')
    need(type(report['model_load_attempts']) is int and report['model_load_attempts'] == 0, 'local model load claim')


def verify_pacing(plan, events, report, observed, frozen):
    """Check the discovery source explicitly; legacy source names stay closed."""
    need(report['source'] in (SOURCE, 'test-double-only'), 'discovery pacing provenance')
    execution_source = 'remote-llm' if report['source'] == SOURCE else 'test-double-only'
    policy = plan['execution_pacing']
    need(same(policy, expected_pacing(policy['minimum_interval_seconds'])), 'discovery pacing contract')
    need(report['source'] == 'test-double-only' or policy['configured'] is True, 'discovery unconfigured real cadence')
    slots = [event for event in events if event['kind'] == 'remote_model_attempt_admitted']
    need(report['admitted_model_slots'] == len(slots) <= 2
         and report['model_attempts'] <= len(slots) <= report['model_attempts'] + 1
         and len(slots) - len(observed) <= 1, 'discovery admitted slots/accounting')
    need(not slots or len(frozen) == 1 and frozen[0]['sequence'] < slots[0]['sequence'], 'discovery slot before input seal')
    interval, previous = policy['minimum_interval_seconds'] or 0.0, None
    for i, event in enumerate(slots, 1):
        data = event['data']
        need(set(data) == {'schema_version', 'execution_source', 'slot', 'adapter_calls_before_dispatch',
             'relative_start_seconds', 'scheduled_wait_seconds', 'minimum_interval_seconds', 'external_completion_attested'}, 'discovery slot schema')
        need(type(data['schema_version']) is int and data['schema_version'] == 1 and type(data['slot']) is int and data['slot'] == i
             and type(data['adapter_calls_before_dispatch']) is int and data['adapter_calls_before_dispatch'] == i-1
             and data['execution_source'] == execution_source
             and type(data['minimum_interval_seconds']) is float and data['minimum_interval_seconds'] == interval
             and data['external_completion_attested'] is False, 'discovery slot identity')
        start, wait = data['relative_start_seconds'], data['scheduled_wait_seconds']
        need(type(start) in (int, float) and math.isfinite(start) and 0 <= start <= 1e12
             and type(wait) in (int, float) and math.isfinite(wait) and 0 <= wait <= 70, 'discovery pacing values')
        need(start == 0 if previous is None else start - previous >= interval - 1e-8, 'discovery pacing interval')
        need(i > len(observed) or event['sequence'] < observed[i-1]['sequence'], 'discovery slot not durable before completion')
        need(i == 1 or i-2 >= len(observed) or observed[i-2]['sequence'] < event['sequence'], 'discovery dispatch before prior completion')
        previous = start
    need(report['status'] != 'COMPLETE' or len(slots) == 2, 'discovery complete pacing coverage')


def tool_key(profile, catalog, prefs):
    p = preferences(prefs, catalog)
    need(profile['entity_id'] not in validate_catalog(catalog), 'musical identity overlaps film catalog')
    positive = {'profile_sha256': profile_hash(profile), 'favorite_input_sha256': fingerprint(p['favorite_entity_ids']),
                'signal_entity_ids': sorted([profile['entity_id'], *p['favorite_entity_ids']])}
    d = sorted(set(validate_catalog(catalog)) - set(p['favorite_entity_ids']))
    query = {'method': 'GET', 'host': 'https://hackathon.api.qloo.com', 'path': '/v2/insights',
             'params': {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': len(d),
                        'signal.interests.entities': ','.join(positive['signal_entity_ids']),
                        'filter.results.entities': ','.join(d)}}
    return fingerprint({'tool_contract': 'qloo-film-discovery-context-v1', 'catalog_sha256': fingerprint(catalog),
                        'profile_sha256': profile_hash(profile), 'signal_sha256': fingerprint(positive), 'request': query}), query


def _prior_valid_insight(sample, catalog, prefs):
    """A later attempt implies the producer accepted every earlier context."""
    need(sample is not None and type(sample['status']) is int and sample['status'] == 200, 'query after failed insight')
    rows = parse_entities(sample['response'], insights=True)
    expected = set(validate_catalog(catalog)) - set(prefs['favorite_entity_ids'])
    metadata = {r['entity_id']: r for r in catalog}
    need(len(rows) == len(expected) and {r.entity_id for r in rows} == expected, 'query after incomplete nonseed coverage')
    need(all('urn:entity:movie' in r.types and r.name == metadata[r.entity_id]['name']
             and type(r.metadata.get('release_year')) is int and r.metadata['release_year'] == metadata[r.entity_id]['release_year']
             and type(r.affinity) in (int, float) and math.isfinite(r.affinity) and 0 <= r.affinity <= 1 for r in rows),
         'query after invalid movie metadata or affinity')


def decision_request(request, profile, context, label, run_id, *, cached=False):
    catalog, p = request['catalog'], request['preferences'][label]
    ids, identity = validate_catalog(catalog), profile_hash(profile)
    positive = {'profile_sha256': identity, 'favorite_input_sha256': fingerprint(p['favorite_entity_ids']),
                'signal_entity_ids': sorted([profile['entity_id'], *p['favorite_entity_ids']])}
    signal = fingerprint(positive)
    d = [i for i, v in enumerate(ids) if v not in p['favorite_entity_ids']]
    value = {'schema_version': 3, 'protocol': PROTOCOL,
        'task': 'Recommend five new discoveries using known interests and the fixed reference catalog.',
        'top_k': 5, 'catalog': catalog, 'profile': profile, 'tool_context': context,
        'request_nonce': ('discovery-cache-' if cached else 'discovery-') + run_id + '-' + label,
        'preferences': p, 'profile_sha256': identity, 'signal_sha256': signal, 'preferences_sha256': fingerprint(p),
        'intent_sha256': fingerprint({'protocol': PROTOCOL, 'catalog_sha256': fingerprint(catalog),
            'profile_sha256': identity, 'signal_sha256': signal, 'preferences': p}),
        'discovery_catalog_indices': d, 'eligible_catalog_indices': [i for i in d if ids[i] not in p['excluded_entity_ids']]}
    value['request_id'] = fingerprint(value)
    expected_input(value)
    return value


def delivery(raw, catalog, prefs):
    ids, p = validate_catalog(catalog), preferences(prefs, catalog)
    d = sorted(set(ids) - set(p['favorite_entity_ids']))
    e = sorted(set(d) - set(p['excluded_entity_ids']))
    need(isinstance(raw, list) and len(raw) == len(d) and set(raw) == set(d), 'raw discovery permutation')
    eligible, rejected = [v for v in raw if v in e], [v for v in raw if v not in e]
    guard, delivered = eligible + rejected, eligible[:5]
    return {'schema_version': 2, 'protocol': PROTOCOL, 'policy': DELIVERY,
        'catalog_sha256': fingerprint(catalog), 'preferences_sha256': fingerprint(p),
        'discovery_sha256': fingerprint(d), 'eligible_sha256': fingerprint(e),
        'delivery_intent_sha256': fingerprint({'protocol': PROTOCOL, 'policy': DELIVERY,
            'catalog_sha256': fingerprint(catalog), 'preferences': p}),
        'raw_ranked_entity_ids': raw, 'raw_output_sha256': fingerprint(raw),
        'guarded_ranked_entity_ids': guard, 'guarded_output_sha256': fingerprint(guard),
        'delivered_entity_ids': delivered, 'delivered_output_sha256': fingerprint(delivered),
        'excluded_entity_ids': rejected, 'known_favorite_entity_ids': p['favorite_entity_ids'],
        'reference_catalog_count': 20, 'known_favorite_count': len(p['favorite_entity_ids']),
        'discovery_movies': len(d), 'eligible_movies': len(e), 'delivered_movies': 5,
        'selection_changed': raw[:5] != delivered, 'preferences_gate': 'PASS', 'complete_output': True,
        'human_quality_validated': False, 'satisfaction_score': None}


def reference(context, catalog, prefs):
    raw = [r['entity_id'] for r in context['ranked_entities']]
    return {'schema_version': 2, 'information_policy': BASELINE, 'context_sha256': context['context_sha256'],
        'signal_sha256': context['signal_sha256'], 'preferences_sha256': fingerprint(prefs),
        'qloo_raw_ranked_entity_ids': raw, 'qloo_raw_output_sha256': fingerprint(raw), 'delivery': delivery(raw, catalog, prefs)}


def boundary(request, packet, manifest, guard, *, hit):
    effective, payload = packet['effective_request'], packet['model_payload']
    key = fingerprint({'protocol': PROTOCOL, 'task': request['task'], 'catalog': request['catalog'],
        'profile': request['profile'], 'signal_sha256': request['signal_sha256'], 'preferences': request['preferences'],
        'intent_sha256': request['intent_sha256'], 'tool_context': request['tool_context'], 'model_manifest': manifest})
    return {
        'requested_profile_sha256': request['profile_sha256'], 'transmitted_profile_sha256': payload['profile_sha256'],
        'tool_profile_sha256': effective['tool_context']['profile_sha256'],
        'requested_signal_sha256': request['signal_sha256'], 'transmitted_signal_sha256': payload['signal_sha256'],
        'tool_signal_sha256': effective['tool_context']['signal_sha256'],
        'requested_preferences_sha256': request['preferences_sha256'], 'transmitted_preferences_sha256': payload['preferences_sha256'],
        'delivered_preferences_sha256': guard['preferences_sha256'],
        'requested_intent_sha256': request['intent_sha256'], 'transmitted_intent_sha256': payload['intent_sha256'],
        'cache_hit': hit, 'cache_key_sha256': key, 'execution_id': packet['execution_id'], 'call': packet['observation']['call'],
        'payload_sha256': fingerprint(payload), 'requested_request_sha256': fingerprint(request),
        'execution_request_sha256': fingerprint(effective), 'context_response_sha256': effective['tool_context']['response_sha256'],
        'raw_output_sha256': guard['raw_output_sha256'], 'delivered_output_sha256': guard['delivered_output_sha256'],
        'delivery_policy': DELIVERY, 'qloo_signal_scope': 'Confirmed musical identity and known favorite IDs; exclusions are delivery-only.'}


def projection(profile, prefs, request, guard, baseline):
    return {'profile': profile, 'preferences': prefs, 'preferences_sha256': request['preferences_sha256'],
        'intent_sha256': request['intent_sha256'], 'raw_ranking': guard['raw_ranked_entity_ids'],
        'delivered': guard['delivered_entity_ids'], 'baseline_delivered': baseline['delivery']['delivered_entity_ids'],
        'delivery_sha256': guard['delivered_output_sha256'], 'raw_ranking_sha256': guard['raw_output_sha256'],
        'eligible_count': guard['eligible_movies'], 'discovery_count': guard['discovery_movies'],
        'known_favorite_count': guard['known_favorite_count'], 'excluded_removed': guard['excluded_entity_ids'],
        'preference_gate': 'PASS', 'delivery_policy': DELIVERY, 'selection_changed': guard['selection_changed'],
        'baseline_information_policy': BASELINE, 'baseline_delivery_sha256': baseline['delivery']['delivered_output_sha256'],
        'human_quality_validated': False, 'satisfaction_score': None}


def _identity(directory, before, *, continuing=False):
    plan = read(directory/'individual-plan.json')
    request = _plan(plan)
    need(str(directory.parent) == plan['output_directory'], 'search left its declared output')
    report = read(directory/'identity-report.json')
    _base_report(report, plan, directory, 'IDENTITY_SEARCH')
    complete = report['status'] == 'AWAITING_IDENTITY_CONFIRMATION'
    need(report['status'] in ('AWAITING_IDENTITY_CONFIRMATION', 'INCOMPLETE')
         and report['preference_gate'] == 'NOT_EVALUATED', 'identity search state')
    need(report['error_class'] is None if complete else isinstance(report['error_class'], str) and bool(report['error_class']), 'identity search error state')
    need(type(report['model_attempts']) is int and report['model_attempts'] == 0, 'inference before explicit identity confirmation')
    snapshot = directory/'identity-ledger.jsonl'
    events = _events(snapshot, report['source'])
    raw, current = snapshot.read_bytes(), (directory/'ledger.jsonl').read_bytes()
    need(current.startswith(raw) if continuing else current == raw, 'identity snapshot is not the original ledger prefix')
    need(events[0]['kind'] == 'individual_plan_frozen'
         and same(events[0]['data'], {'plan_sha256': plan['plan_sha256'], 'model_calls': 0, 'qloo_calls': 0}), 'identity plan not first')
    active = events if complete else events[:-1]
    if not complete:
        need(events[-1]['kind'] == 'stopped_without_retry' and same(events[-1]['data'], {'error_class': report['error_class']}), 'identity terminal stop')
    expected_kinds = ['individual_plan_frozen', 'tool_call', 'identity_candidates_recorded',
                      'tool_call', 'identity_candidates_recorded', 'identity_search_complete']
    kinds = ['tool_call' if e['kind'] == 'transport_failure' else e['kind'] for e in active]
    need(len(kinds) <= 6 and kinds == expected_kinds[:len(kinds)] and (not complete or len(kinds) == 6), 'identity search legal event prefix')
    candidates, samples, attempts = {}, [], 0
    for index, label in ((1, 'A'), (3, 'B')):
        if len(active) <= index:
            continue
        event = active[index]
        attempts += 1
        sample, name = _sample(directory, event, report['source'], '/search', {'query': request['artists'][label], 'take': 5,
            'types': 'urn:entity:artist,urn:entity:person'})
        if name:
            samples.append(name)
        candidate_event = active[index+1] if len(active) > index+1 else None
        if sample is None or sample['status'] != 200:
            need(not complete and event == active[-1] and candidate_event is None
                 and report['error_class'] == 'TransportError', 'identity provider failure was not terminal')
            continue
        if candidate_event is not None:
            members = _candidates(sample['response'])
            need(same(candidate_event['data'], {'label': label, 'query': request['artists'][label],
                 'sample_sha256': before[name], 'candidates_sha256': fingerprint(members)}), 'identity candidate projection differs')
            candidates[label] = members
    need(same(report['identity_candidates'], candidates) and same(report['identity_queries'], request['artists'])
         and type(report['qloo_attempts']) is int and report['qloo_attempts'] == attempts <= 2, 'identity candidates/counters')
    if complete:
        need(set(candidates) == {'A', 'B'} and attempts == 2 and same(events[-1]['data'], {'plan_sha256': plan['plan_sha256'],
             'identity_candidates_sha256': fingerprint(candidates), 'qloo_calls': 2, 'model_calls': 0}), 'identity search completion')
    initial_names = {'individual-plan.json', 'identity-report.json', 'ledger.jsonl', 'identity-ledger.jsonl'} | set(samples)
    initial = {name: before[name] for name in initial_names}
    initial['ledger.jsonl'] = before['identity-ledger.jsonl']
    if not continuing:
        need(set(before) == initial_names, 'identity unknown artifact/inference before confirmation')
    receipt = {**report, 'verified_utc': utc_now(), 'verification_status': 'VERIFIED_IDENTITY_SEARCH' if complete else 'VERIFIED_PARTIAL',
        'provenance': 'SIMULATION_ONLY' if report['source'] == 'test-double-only' else 'RECORDED_REMOTE_EXECUTION',
        'external_service_attested': False, 'artifact_sha256': initial, 'verified_provider_samples': len(samples),
        'verified_model_packets': 0, 'capture_source_sha256': plan['source_sha256'], 'capture_driver_sha256': plan['driver_sha256'],
        'dependencies_lock_sha256': plan['dependencies_lock_sha256'],
        'verification_boundary': 'Recorded typed music candidates and immutable identity-search prefix; no automatic selection, inference, service attestation or cultural quality.'}
    return receipt, plan, request, events, samples


def verify_discovery_search(directory):
    try:
        directory = checked_path(directory)
        need(re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}', directory.name), 'identity run ID')
        before = inventory(directory)
        receipt, *_ = _identity(directory, before)
        need(inventory(directory) == before, 'identity artifacts changed during verification')
        return receipt
    except SchemaError:
        raise
    except (AgentError, KeyError, TypeError, ValueError, IndexError, StopIteration, OSError) as exc:
        raise SchemaError('Identity audit: missing, malformed or inconsistent evidence') from exc


def _confirmed(directory):
    before = inventory(directory)
    identity, plan, request, prefix, identity_samples = _identity(directory, before, continuing=True)
    need(identity['verification_status'] == 'VERIFIED_IDENTITY_SEARCH', 'failed search cannot continue')
    need(str(directory.parent) == plan['output_directory'], 'discovery files left their declared output')
    report = read(directory/'individual-report.json')
    _base_report(report, plan, directory, 'CONFIRMED_DISCOVERIES')
    complete, source = report['status'] == 'COMPLETE', report['source']
    need(report['status'] in ('COMPLETE', 'INCOMPLETE') and source == identity['source']
         and same(report['identity_queries'], request['artists']) and report['independent_verification'] == 'PENDING',
         'discovery status/source/queries')
    need(report['error_class'] is None if complete else isinstance(report['error_class'], str) and bool(report['error_class']), 'error state')
    for key, minimum in (('model_attempts', 0), ('qloo_attempts', 2), ('admitted_model_slots', 0)):
        need(type(report[key]) is int and minimum <= report[key] <= (4 if key == 'qloo_attempts' else 2), 'discovery budgets')
    events = _events(directory/'ledger.jsonl', source)
    need(same(events[:len(prefix)], prefix), 'changed search ledger prefix')
    suffix = events[len(prefix):]
    need(suffix, 'missing confirmation phase')
    if not complete:
        need(suffix[-1]['kind'] == 'stopped_without_retry'
             and same(suffix[-1]['data'], {'error_class': report['error_class']}), 'failure must be terminal')
    active = suffix if complete else suffix[:-1]
    terminal = [e for e in active if e['kind'] == 'discovery_session_stopped']
    if terminal:
        need(not complete and len(terminal) == 1 and active[-1] == terminal[0], 'orphan or nonterminal session stop')
        failure = report['terminal_failure']
        need(isinstance(failure, dict) and set(failure) == {'schema_version', 'stage', 'error_class', 'model_attempts',
             'attempt_count_state', 'observed_successes', 'observation_count_state', 'recorded_successful_packets',
             'admitted_model_slots', 'admission_count_state', 'automatic_retry', 'external_service_attested', 'terminal_recording_state',
             'http_failure', 'prepared_receipt_sha256'}
             and failure.get('terminal_recording_state') == 'RECORDED'
             and same(terminal[0]['data'], {k: v for k, v in failure.items() if k != 'terminal_recording_state'}),
             'session failure receipt differs')
        need(failure['schema_version'] == 2 and type(failure['schema_version']) is int
             and failure['error_class'] == report['error_class'] and failure['automatic_retry'] is False
             and failure['external_service_attested'] is False
             and failure['stage'] in ('preflight', 'model_dispatch', 'cache_verification', 'packet_verification',
                 'packet_recording', 'execution_event_recording', 'delivery_boundary'), 'unsupported terminal claim')
        for key, counter in (('model_attempts', 'model_attempts'), ('admitted_model_slots', 'admitted_model_slots')):
            need(type(failure[key]) is int and failure[key] == report[counter], 'terminal consumed budget')
        need(failure['attempt_count_state'] == failure['admission_count_state'] == failure['observation_count_state'] == 'KNOWN',
             'unknown attempt state cannot be independently counted')
        need(type(failure['observed_successes']) is int and 0 <= failure['observed_successes'] <= report['model_attempts'], 'terminal observations')
        verify_http_failure(failure)
        active = active[:-1]
    else:
        need(report['terminal_failure'] is None, 'terminal receipt without event')
    prepared = [event for event in active if event['kind'] == 'discovery_request_prepared']
    for event in prepared:
        index = active.index(event)
        need(index > 0 and active[index-1]['kind'] == 'remote_model_attempt_admitted'
             and event['data'].get('slot') == active[index-1]['data']['slot'],
             'prepared request outside its durable admitted slot')
    need(len(prepared) <= report['admitted_model_slots'] <= 2, 'prepared request budget')
    if source == SOURCE or prepared:
        need(report['model_attempts'] <= len(prepared) <= report['model_attempts'] + 1,
             'attempt lacks its original prepared request')
    if terminal:
        digest = report['terminal_failure']['prepared_receipt_sha256']
        if digest is not None:
            need(report['terminal_failure']['stage'] == 'model_dispatch' and prepared
                 and prepared[-1]['data']['slot'] == report['admitted_model_slots']
                 and digest == fingerprint(prepared[-1]['data']), 'terminal failure bound to another prepared request')
    active = [event for event in active if event['kind'] != 'discovery_request_prepared']
    expected_kinds = ['identities_confirmed', 'tool_call', 'tool_call', 'all_tool_inputs_frozen',
        'remote_model_attempt_admitted', 'observed_discovery_execution', 'observed_discovery_boundary', 'observed_discovery_boundary',
        'remote_model_attempt_admitted', 'observed_discovery_execution', 'observed_discovery_boundary', 'observed_discovery_boundary']
    kinds = ['tool_call' if e['kind'] == 'transport_failure' else e['kind'] for e in active]
    need(kinds == expected_kinds[:len(kinds)] and (not complete or kinds == expected_kinds), 'illegal discovery execution prefix')
    if len(active) >= 9:
        need('cinema-result-A.json' in before, 'B admitted before A result')
    confirmation = read(directory/'confirmation.json')
    need(set(confirmation) == {'schema_version', 'protocol_version', 'run_id', 'plan_sha256', 'identity_search_receipt',
        'identity_search_receipt_sha256', 'selected_entity_ids', 'selected_profiles'}
        and type(confirmation['schema_version']) is int and confirmation['schema_version'] == 1
        and confirmation['protocol_version'] == PROTOCOL and confirmation['run_id'] == directory.name
        and confirmation['plan_sha256'] == plan['plan_sha256'], 'discovery confirmation contract')
    recorded_receipt = confirmation['identity_search_receipt']
    instant(recorded_receipt['verified_utc'])
    need(confirmation['identity_search_receipt_sha256'] == fingerprint(recorded_receipt)
         and same({k: v for k, v in recorded_receipt.items() if k != 'verified_utc'},
                  {k: v for k, v in identity.items() if k != 'verified_utc'}), 'confirmation search receipt')
    profiles = selection_profiles(identity, confirmation['selected_entity_ids'])
    need(same(confirmation['selected_profiles'], profiles) and same(report['chosen_identities'], profiles), 'selection outside actual candidates')
    if active:
        need(same(active[0]['data'], {'confirmation_sha256': before['confirmation.json'],
             'identity_search_receipt_sha256': fingerprint(recorded_receipt), 'selected_profiles_sha256': fingerprint(profiles)}), 'confirmation ordering')
    if 'individual-identities.json' in before:
        need(active and same(read(directory/'individual-identities.json'), profiles), 'chosen identity file')
    attempts = [e for e in active if e['kind'] in ('tool_call', 'transport_failure')]
    need(len(attempts) + 2 == report['qloo_attempts'], 'cumulative Qloo accounting')
    samples, sample_names = {}, list(identity_samples)
    for i, event in enumerate(attempts):
        label = ('A', 'B')[i]
        _, query = tool_key(profiles[label], request['catalog'], request['preferences'][label])
        sample, name = _sample(directory, event, source, '/v2/insights', query['params'])
        if sample is None or sample['status'] != 200:
            need(not complete and event == active[-1] and report['error_class'] == 'TransportError', 'tool failure not terminal')
        if name:
            sample_names.append(name)
            samples[before[name]] = sample
        if i < len(attempts)-1:
            _prior_valid_insight(sample, request['catalog'], request['preferences'][label])
    need({n for n in before if n.startswith('http-')} == set(sample_names), 'orphan provider sample')
    manifest = read(directory/'model-manifest.json') if 'model-manifest.json' in before else None
    engine_source = 'test-double-only' if source == 'test-double-only' else 'remote-llm'
    if manifest is not None:
        need(active and same(manifest, expected_manifest(engine_source)), 'discovery model contract')
    need(not attempts or manifest is not None and 'individual-identities.json' in before, 'insights before confirmation/manifest')
    contexts = read(directory/'individual-tool-inputs.json') if 'individual-tool-inputs.json' in before else None
    frozen = [e for e in active if e['kind'] == 'all_tool_inputs_frozen']
    if contexts is not None:
        need(set(contexts) == {tool_key(profiles[l], request['catalog'], request['preferences'][l])[0] for l in ('A', 'B')}
             and len(frozen) == 1 and len(attempts) == 2, 'discovery context coverage')
        for label in ('A', 'B'):
            context = contexts[tool_key(profiles[label], request['catalog'], request['preferences'][label])[0]]
            digest = context['sample_sha256']
            need(digest in samples, 'missing context sample bytes')
            verify_context(context, request['catalog'], profiles[label], request['preferences'][label], samples[digest], digest)
        need(same(frozen[0]['data'], {'sha256': fingerprint(contexts), 'model_calls': 0, 'qloo_calls': 4}), 'context seal')
    else:
        need(not frozen and not complete, 'missing sealed contexts')
    if prepared:
        need(contexts is not None and manifest is not None, 'request prepared before sealed model inputs')
        verify_prepared_requests(prepared, request, profiles, contexts, manifest, directory.name, engine_source)
    packet_names = sorted(n for n in before if n.startswith('discovery-execution-'))
    observed = [e for e in active if e['kind'] == 'observed_discovery_execution']
    need(len(packet_names) == len(observed) <= report['model_attempts'] <= 2
         and report['model_attempts'] - len(packet_names) <= 1, 'packet/attempt counts')
    need(not report['model_attempts'] or contexts is not None and manifest is not None, 'model before all tool inputs')
    verify_pacing(plan, events, report, observed, frozen)
    results, result_names, completion_ids, boundaries = {}, [], set(), []
    for i, name in enumerate(packet_names, 1):
        label = ('A', 'B')[i-1]
        context = contexts[tool_key(profiles[label], request['catalog'], request['preferences'][label])[0]]
        effective = decision_request(request, profiles[label], context, label, directory.name)
        cached_request = decision_request(request, profiles[label], context, label, directory.name, cached=True)
        packet = read(directory/name)
        need(name == f'discovery-execution-{i:03d}.json' and packet['execution_id'] == directory.name + '/' + str(i)
             and same(packet['effective_request'], effective) and type(packet['observation']['call']) is int
             and packet['observation']['call'] == i, 'discovery request/packet sequence')
        checked = verify_packet(packet, manifest, engine_source, samples[context['sample_sha256']], context['sample_sha256'])
        ranking, observation = checked['raw_ranking'], packet['observation']
        need(checked['completion_id'] not in completion_ids, 'duplicate completion')
        completion_ids.add(checked['completion_id'])
        need(same(observed[i-1]['data'], {'execution_id': packet['execution_id'], 'request_sha256': fingerprint(effective),
            'payload_sha256': fingerprint(packet['model_payload']), 'output_sha256': fingerprint(ranking)}), 'packet observation event')
        guard = delivery(ranking, request['catalog'], effective['preferences'])
        traces = [boundary(r, packet, manifest, guard, hit=hit) for r, hit in ((effective, False), (cached_request, True))]
        available = [e for e in active if e['kind'] == 'observed_discovery_boundary' and e['data'].get('execution_id') == packet['execution_id']]
        need(len(available) <= 2 and (not complete or len(available) == 2), 'cache boundary coverage')
        for j, event in enumerate(available):
            need(same(event['data'], traces[j]), 'wrong profile/signal/preferences/cache boundary')
        boundaries.extend(available)
        result_name = 'cinema-result-' + label + '.json'
        if result_name in before:
            need(len(available) == 2, 'result before cache check')
            result_names.append(result_name)
            baseline = reference(context, request['catalog'], effective['preferences'])
            public = projection(profiles[label], effective['preferences'], effective, guard, baseline)
            need(same(read(directory/result_name), {'schema_version': 1, 'label': label, 'effective_request': effective,
                'cache_request': cached_request, 'uncached_boundary': {'ranking': ranking, 'delivery': guard, 'trace': traces[0]},
                'cached_boundary': {'ranking': ranking, 'delivery': guard, 'trace': traces[1]}, 'baseline': baseline, 'result': public}),
                'raw ranking, delivery or fair baseline differs')
            results[label] = public
    need(len(boundaries) == sum(e['kind'] == 'observed_discovery_boundary' for e in active), 'orphan boundary')
    need(same(report['cinema_results'], results) and type(report['successful_profiles']) is int
         and report['successful_profiles'] == len(results) and type(report['requested_profiles']) is int
         and report['requested_profiles'] == 2 and type(report['failed_model_attempts']) is int
         and report['failed_model_attempts'] == report['model_attempts']-len(packet_names)
         and type(report['unattempted_profiles']) is int and report['unattempted_profiles'] == 2-report['model_attempts'], 'results/denominators')
    if terminal:
        need(type(report['terminal_failure']['recorded_successful_packets']) is int
             and report['terminal_failure']['recorded_successful_packets'] == len(packet_names), 'terminal packet count')
    need(report['preference_gate'] == ('PASS' if complete else 'NOT_EVALUATED'), 'preference gate')
    if complete:
        need(len(results) == len(packet_names) == report['model_attempts'] == 2 and report['qloo_attempts'] == 4, 'complete budgets')
    allowed = set(identity['artifact_sha256']) | {'confirmation.json', 'individual-report.json', 'individual-identities.json',
        'model-manifest.json', 'individual-tool-inputs.json'} | set(sample_names) | set(packet_names) | set(result_names)
    need(set(before) <= allowed and inventory(directory) == before, 'unknown artifacts or concurrent mutation')
    return {**report, 'verified_utc': utc_now(), 'verification_status': 'VERIFIED_COMPLETE' if complete else 'VERIFIED_PARTIAL',
        'identity_candidates': identity['identity_candidates'], 'provenance': identity['provenance'], 'external_service_attested': False,
        'artifact_sha256': before, 'verified_provider_samples': len(sample_names), 'verified_model_packets': len(packet_names),
        'capture_source_sha256': plan['source_sha256'], 'capture_driver_sha256': plan['driver_sha256'],
        'dependencies_lock_sha256': plan['dependencies_lock_sha256'],
        'verifier_source_sha256': {'cinema_discovery_file_verify.py': sha(Path(__file__))},
        'verification_boundary': 'Recorded typed candidates, exact selected membership, original search prefix, positive Qloo inputs, discovery payload/cache/delivery, consumed budgets. No service authentication, human or causal quality claim.'}


def verify_confirmed_discoveries(directory):
    try:
        directory = checked_path(directory)
        need(re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}', directory.name), 'discovery run ID')
        if not (directory/'individual-report.json').exists():
            return verify_discovery_search(directory)
        return _confirmed(directory)
    except SchemaError:
        raise
    except (AgentError, KeyError, TypeError, ValueError, IndexError, StopIteration, OSError) as exc:
        raise SchemaError('Discovery file audit: missing, malformed or inconsistent evidence') from exc

