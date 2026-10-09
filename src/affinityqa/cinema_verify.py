"""Read-only coherence audit of cinema preferences; no provider calls or taste attestation."""
import copy
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re

from .agents import AgentError, strict_json, validate_response
from .causal_agent import context_from_sample, profile_hash
from .cinema_capture import SOURCES, validate_request
from .cinema_preferences import CINEMA_PROMPT, CINEMA_PROTOCOL, CINEMA_TASK, DELIVERY_POLICY, BASELINE_POLICY
from .errors import SchemaError
from .evidence import fingerprint, utc_now
from .individual_remote_verify import expected_manifest as artist_manifest, expected_pacing, verify_packet, engine_source
from .individual_verify import checked_path, inventory, read, instant, musical_identity, need, same, sha, write_receipt

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def expected_manifest(source):
    value = artist_manifest(source)
    value.update(prompt_version='cinema-preferences-v1', prompt_sha256=fingerprint(CINEMA_PROMPT),
                 tool_contract='qloo-context+explicit-cinema-preferences-v1', max_inference_calls=2)
    return value


def verify_plan(plan):
    request = validate_request(plan['request'])
    output = plan['output_directory']
    need(isinstance(output, str) and len(output) <= 4000
         and (PureWindowsPath(output).is_absolute() or PurePosixPath(output).is_absolute()), 'cinema output declaration')
    source = SOURCE_ROOT/'src/affinityqa'
    expected = {'schema_version': 4, 'protocol_version': 'cinema-preferences-v1', 'mode': 'cinema-preferences-capture',
        'request': request, 'output_directory': output, 'remote_operator': expected_manifest('remote-llm'),
        'execution_pacing': expected_pacing(plan['execution_pacing']['minimum_interval_seconds']),
        'source_sha256': {name: sha(source/name) for name in SOURCES},
        'driver_sha256': sha(source/'cinema_capture.py'), 'verification_driver_sha256': sha(source/'cinema_verify.py'),
        'dependencies_lock_sha256': sha(SOURCE_ROOT/'requirements-backend.lock.txt'),
        'maximum_qloo_requests': 4, 'maximum_attempts_per_request': 1, 'maximum_model_decisions': 2,
        'cache_checks_per_profile': 1, 'faults': [], 'new_model_metadata_requests': 0,
        'startup_model_metadata_requests': 0, 'runtime_model_metadata_requests': 0, 'model_load_requests': 0,
        'individual_demo_only': True, 'independent_validation_claim': False, 'cultural_gate': 'NOT_VALIDATED',
        'release_gate': 'BLOCKED', 'partial_failure_policy': 'Preserve all evidence, stop without retry or resume.'}
    expected['plan_sha256'] = fingerprint(expected)
    need(same(plan, expected), 'cinema plan or installed source binding differs')
    return request


def decision_request(request, profile, context, label, run_id):
    preferences = request['preferences'][label]
    value = {'schema_version': 2, 'task': CINEMA_TASK, 'top_k': 5, 'catalog': request['catalog'],
             'profile': profile, 'tool_context': context, 'request_nonce': 'cinema-' + run_id + '-' + label,
             'preferences': preferences, 'preferences_sha256': fingerprint(preferences),
             'intent_sha256': fingerprint({'profile': profile, 'preferences': preferences})}
    value['request_id'] = fingerprint(value)
    return value


def expected_payload(request):
    ids = [row['entity_id'] for row in request['catalog']]
    schema = {'type': 'object', 'properties': {'ordered_catalog_indices': {'type': 'array',
        'items': {'type': 'integer', 'enum': list(range(20))}, 'minItems': 20, 'maxItems': 20}},
        'required': ['ordered_catalog_indices'], 'additionalProperties': False}
    return {'task': request['task'], 'catalog': [{'index': i, 'name': row['name'], 'release_year': row['release_year']}
        for i, row in enumerate(request['catalog'])], 'profile': request['profile'],
        'provider_movie_context': [{'catalog_index': ids.index(row['entity_id']), 'affinity': row['affinity']}
            for row in request['tool_context']['ranked_entities']],
        'tool_notice': 'Qloo query-relative cultural context, consumed by this agent. Not independent evaluation or confidence.',
        'output_schema': schema, 'cinema_preferences': {'schema_version': 1,
            'favorite_catalog_indices': [ids.index(v) for v in request['preferences']['favorite_entity_ids']],
            'excluded_catalog_indices': [ids.index(v) for v in request['preferences']['excluded_entity_ids']],
            'favorites_scope': 'Soft explicit interests; no independent quality labels or mandatory inclusions.',
            'exclusions_scope': 'Hard top-five delivery constraints; separate visible eligible-first policy.'},
        'preferences_sha256': request['preferences_sha256'], 'intent_sha256': request['intent_sha256'],
        'cinema_protocol': 'cinema-preferences-v1'}


def delivery(raw, catalog, prefs):
    ids = {row['entity_id'] for row in catalog}
    need(isinstance(raw, list) and len(raw) == len(set(raw)) == 20 and set(raw) == ids, 'cinema raw permutation')
    eligible = [v for v in raw if v not in prefs['excluded_entity_ids']]
    rejected = [v for v in raw if v in prefs['excluded_entity_ids']]
    final = eligible[:5]
    need(len(final) == 5 and not set(final) & set(prefs['excluded_entity_ids']), 'cinema incomplete or excluded delivery')
    return {'schema_version': 1, 'policy': DELIVERY_POLICY, 'catalog_sha256': fingerprint(catalog),
        'preferences_sha256': fingerprint(prefs), 'raw_ranked_entity_ids': raw,
        'raw_output_sha256': fingerprint(raw), 'guarded_ranked_entity_ids': eligible + rejected,
        'guarded_output_sha256': fingerprint(eligible + rejected), 'delivered_entity_ids': final,
        'delivered_output_sha256': fingerprint(final), 'excluded_entity_ids': rejected,
        'selection_changed': raw[:5] != final, 'eligible_movies': len(eligible), 'preferences_gate': 'PASS',
        'complete_output': True, 'human_quality_validated': False, 'satisfaction_score': None}


def baseline(context, catalog, prefs):
    raw = [row['entity_id'] for row in context['ranked_entities']]
    informed = [v for v in raw if v in prefs['favorite_entity_ids']] + [v for v in raw if v not in prefs['favorite_entity_ids']]
    return {'schema_version': 1, 'information_policy': BASELINE_POLICY, 'qloo_raw_ranked_entity_ids': raw,
        'qloo_raw_output_sha256': fingerprint(raw), 'preferences_aware_ranked_entity_ids': informed,
        'delivery': delivery(informed, catalog, prefs)}


def boundary(request, packet, manifest, guard, *, hit):
    effective, payload = packet['effective_request'], packet['model_payload']
    key = fingerprint({'task': request['task'], 'catalog': request['catalog'], 'profile': request['profile'],
        'preferences': request['preferences'], 'intent_sha256': request['intent_sha256'],
        'tool_context': request['tool_context'], 'model_manifest': manifest})
    return {'requested_profile_sha256': profile_hash(request['profile']),
        'transmitted_profile_sha256': profile_hash(payload['profile']),
        'tool_profile_sha256': profile_hash(effective['tool_context']['profile']),
        'output_profile_sha256': profile_hash(payload['profile']),
        'requested_preferences_sha256': request['preferences_sha256'],
        'transmitted_preferences_sha256': payload['preferences_sha256'],
        'delivered_preferences_sha256': guard['preferences_sha256'],
        'requested_intent_sha256': request['intent_sha256'], 'transmitted_intent_sha256': payload['intent_sha256'],
        'cache_hit': hit, 'cache_key_sha256': key, 'execution_id': packet['execution_id'], 'call': packet['observation']['call'],
        'payload_sha256': fingerprint(payload), 'context_response_sha256': effective['tool_context']['response_sha256'],
        'requested_request_sha256': fingerprint(request), 'execution_request_sha256': fingerprint(effective),
        'raw_output_sha256': fingerprint(packet['response']['ranked_entity_ids']),
        'delivered_output_sha256': guard['delivered_output_sha256'], 'delivery_policy': DELIVERY_POLICY,
        'qloo_preferences_scope': 'Qloo consumes the artist only; preferences are not attested by tool_profile_sha256.'}


def projection(profile, prefs, request, guard, reference):
    return {'profile': profile, 'preferences': prefs, 'preferences_sha256': request['preferences_sha256'],
        'intent_sha256': request['intent_sha256'], 'raw_ranking': guard['raw_ranked_entity_ids'],
        'delivered': guard['delivered_entity_ids'], 'baseline_delivered': reference['delivery']['delivered_entity_ids'],
        'delivery_sha256': guard['delivered_output_sha256'], 'raw_ranking_sha256': guard['raw_output_sha256'],
        'eligible_count': guard['eligible_movies'], 'excluded_removed': guard['excluded_entity_ids'],
        'preference_gate': 'PASS', 'delivery_policy': DELIVERY_POLICY, 'selection_changed': guard['selection_changed'],
        'baseline_information_policy': BASELINE_POLICY, 'baseline_delivery_sha256': reference['delivery']['delivered_output_sha256'],
        'human_quality_validated': False, 'satisfaction_score': None}


def verify_pacing(plan, events, report, observed, frozen):
    policy = plan['execution_pacing']
    need(same(policy, expected_pacing(policy['minimum_interval_seconds'])), 'cinema pacing contract')
    need(report['source'] == 'test-double-only' or policy['configured'] is True, 'cinema unconfigured real cadence')
    slots = [event for event in events if event['kind'] == 'remote_model_attempt_admitted']
    need(report['admitted_model_slots'] == len(slots) <= 2
         and report['model_attempts'] <= len(slots) <= report['model_attempts'] + 1
         and len(slots) - len(observed) <= 1, 'cinema admitted slots/accounting')
    need(not slots or len(frozen) == 1 and frozen[0]['sequence'] < slots[0]['sequence'], 'cinema slot before input seal')
    interval, previous = policy['minimum_interval_seconds'] or 0.0, None
    for i, event in enumerate(slots, 1):
        data = event['data']
        need(set(data) == {'schema_version', 'execution_source', 'slot', 'adapter_calls_before_dispatch',
             'relative_start_seconds', 'scheduled_wait_seconds', 'minimum_interval_seconds', 'external_completion_attested'}, 'cinema slot schema')
        need(type(data['schema_version']) is int and data['schema_version'] == 1 and type(data['slot']) is int and data['slot'] == i
             and type(data['adapter_calls_before_dispatch']) is int and data['adapter_calls_before_dispatch'] == i-1
             and data['execution_source'] == engine_source(report['source'])
             and type(data['minimum_interval_seconds']) is float and data['minimum_interval_seconds'] == interval
             and data['external_completion_attested'] is False, 'cinema slot identity')
        start, wait = data['relative_start_seconds'], data['scheduled_wait_seconds']
        need(type(start) in (int, float) and math.isfinite(start) and 0 <= start <= 1e12
             and type(wait) in (int, float) and math.isfinite(wait) and 0 <= wait <= 70, 'cinema pacing values')
        need(start == 0 if previous is None else start - previous >= interval - 1e-8, 'cinema pacing interval')
        need(i > len(observed) or event['sequence'] < observed[i-1]['sequence'], 'cinema slot not durable before completion')
        need(i == 1 or i-2 >= len(observed) or observed[i-2]['sequence'] < event['sequence'], 'cinema dispatch before prior completion')
        previous = start
    need(report['status'] != 'COMPLETE' or len(slots) == 2, 'cinema complete pacing coverage')


def verify_event_prefix(events, complete, artifact_names):
    """A stopped run is a prefix of this capture, never arbitrary coherent fragments."""
    execution = events if complete else events[:-1]
    kinds = ['tool_call' if e['kind'] == 'transport_failure' else e['kind'] for e in execution]
    full = ['individual_plan_frozen', *['tool_call']*4, 'all_tool_inputs_frozen',
            'remote_model_attempt_admitted', 'observed_model_execution',
            'observed_cinema_boundary', 'observed_cinema_boundary',
            'remote_model_attempt_admitted', 'observed_model_execution',
            'observed_cinema_boundary', 'observed_cinema_boundary']
    need(len(kinds) <= len(full) and kinds == full[:len(kinds)]
         and (not complete or kinds == full), 'cinema execution is not a legal sequential prefix')
    # The result file is written after both A boundaries and before admitting B.
    # File coherence does not attest disk timing, but a missing A result cannot
    # describe any legitimate dispatch of B, even in an interrupted capture.
    if len(execution) >= 11:
        need('cinema-result-A.json' in artifact_names, 'cinema B admitted before A result completed')
    failures = [e for e in execution if e['kind'] == 'transport_failure']
    need(not failures or not complete and len(failures) == 1 and failures[0] == execution[-1],
         'cinema transport failure was not terminal')


def _verify(directory):
    directory = checked_path(directory)
    need(re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}', directory.name), 'cinema run ID')
    before = inventory(directory)
    plan, report = read(directory/'individual-plan.json'), read(directory/'individual-report.json')
    request = verify_plan(plan)
    complete, source = report['status'] == 'COMPLETE', report['source']
    need(source in ('qloo-tool+groq-remote-llm', 'test-double-only') and report['status'] in ('COMPLETE', 'INCOMPLETE'), 'cinema source/status')
    need(type(report['schema_version']) is int and report['schema_version'] == 4 and report['run_id'] == directory.name
         and report['mode'] == plan['mode'] and report['plan_sha256'] == plan['plan_sha256'], 'cinema report binding')
    instant(report['created_utc'])
    need(report['causal_gate'] == report['behavioral_gate'] == report['integration_gate'] == 'NOT_EVALUATED'
         and report['cultural_gate'] == 'NOT_VALIDATED' and report['release_gate'] == 'BLOCKED'
         and report['release_approved'] is False and report['independent_validation_claim'] is False
         and report['independent_verification'] == 'PENDING' and report['partial_evidence_preserved'] is True,
         'cinema must not approve causal, cultural or release gates')
    for key, maximum in (('model_attempts', 2), ('qloo_attempts', 4), ('model_load_attempts', 0), ('admitted_model_slots', 2)):
        need(type(report[key]) is int and 0 <= report[key] <= maximum, 'cinema attempt counter')
    need(report['error_class'] is None if complete else isinstance(report['error_class'], str) and bool(report['error_class']), 'cinema complete/error state')
    need((directory/'ledger.jsonl').stat().st_size <= 2_000_000, 'cinema ledger bound')
    events = [strict_json(line) for line in (directory/'ledger.jsonl').read_bytes().splitlines() if line.strip()]
    allowed_kinds = {'individual_plan_frozen', 'tool_call', 'transport_failure', 'all_tool_inputs_frozen',
                     'remote_model_attempt_admitted', 'observed_model_execution', 'observed_cinema_boundary', 'stopped_without_retry'}
    need(events and all(type(e['sequence']) is int and e['sequence'] == i and e['source'] == source
         and set(e) == {'sequence', 'timestamp_utc', 'source', 'kind', 'data'} and e['kind'] in allowed_kinds
         for i, e in enumerate(events, 1)), 'cinema ledger schema/sequence/source')
    times = [instant(e['timestamp_utc']) for e in events]
    need(times == sorted(times), 'cinema ledger time reversal')
    need(events[0]['kind'] == 'individual_plan_frozen'
         and same(events[0]['data'], {'plan_sha256': plan['plan_sha256'], 'model_calls': 0, 'qloo_calls': 0}), 'cinema plan not first')
    stops = [e for e in events if e['kind'] == 'stopped_without_retry']
    need(not stops if complete else len(stops) == 1 and stops[0] == events[-1]
         and same(stops[0]['data'], {'error_class': report['error_class']}), 'cinema stop or retry state')
    verify_event_prefix(events, complete, before)
    attempts = [e for e in events if e['kind'] in ('tool_call', 'transport_failure')]
    need(len(attempts) == report['qloo_attempts'], 'cinema Qloo attempts')
    profiles = read(directory/'individual-identities.json') if 'individual-identities.json' in before else None
    sequence = [{'query': request['artists'][p], 'take': 5} for p in ('A', 'B')]
    if profiles is not None:
        need(isinstance(profiles, dict) and set(profiles) == {'A', 'B'} and len({p['entity_id'] for p in profiles.values()}) == 2, 'cinema artist identities')
        sequence += [{'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': 20,
            'signal.interests.entities': profiles[p]['entity_id'],
            'filter.results.entities': ','.join(sorted(row['entity_id'] for row in request['catalog']))} for p in ('A', 'B')]
    samples, sample_names = {}, []
    for i, event in enumerate(attempts):
        data = event['data']
        need(i < len(sequence) and data['request'] == {'method': 'GET', 'host': 'https://hackathon.api.qloo.com',
             'path': '/search' if i < 2 else '/v2/insights', 'params': sequence[i]}
             and type(data['attempt']) is int and data['attempt'] == 1, 'cinema provider request prefix')
        if event['kind'] == 'transport_failure':
            need(not complete and event == attempts[-1] and set(data) == {'request', 'attempt'}, 'cinema transport retried')
            continue
        name = data['sample']
        need(name == f'http-{event["sequence"]:04d}.json', 'cinema sample sequence')
        sample = read(directory/name)
        need(sample['source'] == source and same(sample['request'], data['request'])
             and type(sample['attempt']) is int and sample['attempt'] == 1 and sample['live_network_request'] is True
             and sample['response_sha256'] == fingerprint(sample['response'])
             and same(data, {'sample': name, **{k: v for k, v in sample.items() if k != 'response'}}), 'cinema sample/ledger binding')
        need(type(sample['status']) is int and 100 <= sample['status'] <= 599
             and (not complete or sample['status'] == 200), 'cinema HTTP status')
        if sample['status'] != 200:
            need(not complete and event == attempts[-1] and event == events[-2]
                 and report['error_class'] == 'TransportError', 'cinema non200 response was not terminal')
            need('individual-tool-inputs.json' not in before
                 and (i >= 2 or profiles is None), 'cinema advanced artifact after non200 response')
        # An earlier successful HTTP response must also have been usable before
        # the producer could issue the following request. A malformed terminal
        # response may still legitimately be preserved as partial evidence.
        if i < len(attempts)-1:
            need(sample['status'] == 200, 'cinema provider failure followed by another request')
            if i < 2:
                musical_identity(request['artists'][('A', 'B')[i]], sample['response'])
            else:
                need(profiles is not None, 'cinema insights without resolved artist')
                context_from_sample(profiles[('A', 'B')[i-2]], request['catalog'], sample, before[name])
        sample_names.append(name)
        samples[before[name]] = sample
    need({n for n in before if n.startswith('http-')} == set(sample_names), 'cinema orphan sample')
    if profiles is not None:
        for i, p in enumerate(('A', 'B')):
            need(len(sample_names) > i, 'cinema missing artist search')
            sample = read(directory/sample_names[i])
            need(sample['status'] == 200 and same(profiles[p], musical_identity(request['artists'][p], sample['response'])), 'cinema artist resolution')
    contexts = read(directory/'individual-tool-inputs.json') if 'individual-tool-inputs.json' in before else None
    frozen = [e for e in events if e['kind'] == 'all_tool_inputs_frozen']
    if contexts is not None:
        need(profiles is not None and set(contexts) == {profile_hash(p) for p in profiles.values()} and len(frozen) == 1, 'cinema context coverage')
        for profile in profiles.values():
            context = contexts[profile_hash(profile)]
            need(context['sample_sha256'] in samples and same(context, context_from_sample(profile, request['catalog'],
                samples[context['sample_sha256']], context['sample_sha256'])), 'cinema Qloo context provenance')
        need(len(attempts) == 4 and same(frozen[0]['data'], {'sha256': fingerprint(contexts), 'model_calls': 0, 'qloo_calls': 4})
             and attempts[-1]['sequence'] < frozen[0]['sequence'], 'cinema input seal')
    else:
        need(not complete and not frozen, 'cinema missing sealed input')
    manifest = read(directory/'model-manifest.json') if 'model-manifest.json' in before else None
    need(not attempts or manifest is not None, 'cinema Qloo request before recorded model contract')
    if manifest is not None:
        need(same(manifest, expected_manifest('test-double-only' if source == 'test-double-only' else 'remote-llm')), 'cinema manifest differs')
    observed = [e for e in events if e['kind'] == 'observed_model_execution']
    packet_names = sorted(n for n in before if n.startswith('cinema-execution-'))
    need(len(packet_names) == len(observed) <= report['model_attempts'] <= 2
         and report['model_attempts'] - len(packet_names) <= 1, 'cinema packets/attempts after first failure')
    need(not report['model_attempts'] or contexts is not None and manifest is not None and len(samples) == 4, 'cinema decision before complete preflight')
    verify_pacing(plan, events, report, observed, frozen)
    packets, trace_expectations, results = [], [], {}
    completed_ids = set()
    result_names = []
    for i, name in enumerate(packet_names, 1):
        label = ('A', 'B')[i-1]
        need(contexts is not None and manifest is not None and frozen[0]['sequence'] < observed[i-1]['sequence'], 'cinema unsealed decision')
        effective = decision_request(request, profiles[label], contexts[profile_hash(profiles[label])], label, directory.name)
        packet = read(directory/name)
        need(set(packet) == {'execution_id', 'effective_request', 'model_payload', 'response', 'observation'}
             and name == f'cinema-execution-{i:03d}.json' and packet['execution_id'] == directory.name + '/' + str(i)
             and same(packet['effective_request'], effective), 'cinema packet sequence/request')
        ranking = validate_response(effective, packet['response'])
        payload = expected_payload(effective)
        obs = packet['observation']
        need(type(obs['call']) is int and obs['call'] == i and same(packet['model_payload'], payload)
             and obs['input_sha256'] == fingerprint(payload) and obs['output_sha256'] == fingerprint(ranking), 'cinema effective payload/raw hash')
        verify_packet(packet, manifest, source, system_prompt=CINEMA_PROMPT)
        need(obs['completion_id'] not in completed_ids, 'cinema duplicate completion identity')
        completed_ids.add(obs['completion_id'])
        need(same(observed[i-1]['data'], {'execution_id': packet['execution_id'], 'request_sha256': fingerprint(effective),
             'payload_sha256': fingerprint(payload), 'output_sha256': fingerprint(ranking)}), 'cinema observed model event')
        guard = delivery(ranking, request['catalog'], request['preferences'][label])
        traces = [boundary(effective, packet, manifest, guard, hit=hit) for hit in (False, True)]
        available = [e for e in events if e['kind'] == 'observed_cinema_boundary' and e['data'].get('execution_id') == packet['execution_id']]
        need(len(available) <= 2 and (len(available) == 2 if complete else True), 'cinema boundary count')
        for j, event in enumerate(available):
            need(same(event['data'], traces[j]) and event['sequence'] > observed[i-1]['sequence'], 'cinema boundary/cache/intent differs')
        trace_expectations.extend(available)
        result_name = 'cinema-result-' + label + '.json'
        if result_name in before:
            need(len(available) == 2, 'cinema result without cache evidence')
            result_names.append(result_name)
            reference = baseline(effective['tool_context'], request['catalog'], effective['preferences'])
            public = projection(profiles[label], effective['preferences'], effective, guard, reference)
            expected = {'schema_version': 1, 'label': label, 'effective_request': effective,
                'uncached_boundary': {'ranking': ranking, 'delivery': guard, 'trace': traces[0]},
                'cached_boundary': {'ranking': ranking, 'delivery': guard, 'trace': traces[1]}, 'baseline': reference, 'result': public}
            need(same(read(directory/result_name), expected), 'cinema raw/delivery/baseline/result differs')
            results[label] = public
        packets.append(packet)
    need(len(trace_expectations) == sum(e['kind'] == 'observed_cinema_boundary' for e in events), 'cinema orphan boundary')
    need(same(report['cinema_results'], results) and type(report['successful_profiles']) is int
         and report['successful_profiles'] == len(results) and type(report['requested_profiles']) is int and report['requested_profiles'] == 2
         and type(report['failed_model_attempts']) is int and report['failed_model_attempts'] == report['model_attempts'] - len(packets)
         and type(report['unattempted_profiles']) is int and report['unattempted_profiles'] == 2 - report['model_attempts'], 'cinema denominator/accounting/result')
    need(report['preference_gate'] == ('PASS' if complete else 'NOT_EVALUATED'), 'cinema preference gate')
    if complete:
        need(len(packets) == report['model_attempts'] == len(results) == 2 and report['qloo_attempts'] == 4, 'cinema complete coverage')
    allowed = {'individual-plan.json', 'individual-report.json', 'ledger.jsonl', 'individual-identities.json',
               'individual-tool-inputs.json', 'model-manifest.json'} | set(sample_names) | set(packet_names) | set(result_names)
    need(set(before) <= allowed, 'cinema unknown artifact or local loading')
    need(inventory(directory) == before, 'cinema capture changed during verification')
    return {**report, 'verified_utc': utc_now(), 'verification_status': 'VERIFIED_COMPLETE' if complete else 'VERIFIED_PARTIAL',
        'recorded_source': source, 'provenance': 'SIMULATION_ONLY' if source == 'test-double-only' else 'RECORDED_REMOTE_EXECUTION',
        'external_service_attested': False, 'verified_model_packets': len(packets), 'verified_provider_samples': len(samples),
        'artifact_sha256': before, 'capture_source_sha256': plan['source_sha256'], 'capture_driver_sha256': plan['driver_sha256'],
        'dependencies_lock_sha256': plan['dependencies_lock_sha256'],
        'verifier_source_sha256': {'cinema_verify.py': sha(Path(__file__))},
        'verification_boundary': 'Recorded-file coherence, actual cinema payload bindings, cache and independent delivery/baseline recomputation. '
            'No new requests, external-service attestation, causal fault experiment, cultural satisfaction or population reliability.'}


def verify_cinema(directory):
    try:
        return _verify(directory)
    except SchemaError:
        raise
    except (AgentError, KeyError, TypeError, ValueError, IndexError, StopIteration, OSError) as exc:
        raise SchemaError('Cinema audit: missing, malformed or inconsistent evidence') from exc
