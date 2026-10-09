"""Independent staged identity/cinema file audit; never chooses an identity or calls APIs."""
import copy
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import unicodedata

from .agents import AgentError, strict_json, validate_response
from .causal_agent import context_from_sample, profile_hash
from .cinema_capture import validate_request as cinema_request
from .cinema_identity_capture import SOURCES
from .cinema_preferences import CINEMA_PROMPT
from .cinema_verify import expected_manifest, expected_payload, decision_request, delivery, baseline, boundary, projection, verify_pacing
from .errors import SchemaError
from .evidence import fingerprint, utc_now
from .individual_remote_verify import expected_pacing, verify_packet
from .individual_verify import checked_path, inventory, read, instant, need, same, sha
from .models import parse_entities

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _request(value):
    need(type(value.get('schema_version')) is int and value['schema_version'] == 4, 'confirmed cinema request version')
    result = cinema_request({**value, 'schema_version': 3})
    result['schema_version'] = 4
    return result


def _plan(value):
    request = _request(value['request'])
    output = value['output_directory']
    need(isinstance(output, str) and len(output) <= 4000 and (PureWindowsPath(output).is_absolute() or PurePosixPath(output).is_absolute()), 'confirmed output path')
    source = SOURCE_ROOT/'src/affinityqa'
    expected = {'schema_version': 5, 'protocol_version': 'cinema-confirmed-identity-v1', 'mode': 'cinema-confirmed-identity-capture',
        'request': request, 'output_directory': output, 'remote_operator': expected_manifest('remote-llm'),
        'execution_pacing': expected_pacing(value['execution_pacing']['minimum_interval_seconds']),
        'source_sha256': {name: sha(source/name) for name in SOURCES},
        'driver_sha256': sha(source/'cinema_identity_capture.py'), 'verification_driver_sha256': sha(source/'cinema_identity_verify.py'),
        'dependencies_lock_sha256': sha(SOURCE_ROOT/'requirements-backend.lock.txt'),
        'maximum_qloo_requests': 4, 'maximum_identity_search_requests': 2, 'maximum_insights_requests': 2,
        'maximum_attempts_per_request': 1, 'maximum_model_decisions': 2, 'cache_checks_per_profile': 1,
        'faults': [], 'explicit_identity_confirmation_required': True,
        'new_model_metadata_requests': 0, 'startup_model_metadata_requests': 0,
        'runtime_model_metadata_requests': 0, 'model_load_requests': 0,
        'individual_demo_only': True, 'independent_validation_claim': False, 'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
        'partial_failure_policy': 'Preserve all evidence, stop without retry or resume; only a successful identity search may continue after explicit confirmation.'}
    expected['plan_sha256'] = fingerprint(expected)
    need(same(value, expected), 'confirmed plan or installed source binding differs')
    return request


def _candidates(body):
    """Rebuild candidate names, types and musical eligibility from recorded rows."""
    rows = parse_entities(body, insights=False)
    need(len(rows) <= 5, 'identity response bound')
    result = []
    allowed = {'musician', 'singer', 'singer songwriter', 'songwriter', 'rapper', 'composer',
               'pianist', 'guitarist', 'harpist', 'record producer', 'music producer'}
    for row in rows:
        kind = None
        if 'urn:entity:artist' in row.types:
            kind = 'urn:entity:artist'
        elif 'urn:entity:person' in row.types:
            occupations = row.metadata.get('occupations', row.metadata.get('occupation', []))
            occupations = [occupations] if isinstance(occupations, str) else occupations
            musical = isinstance(occupations, list) and any(isinstance(v, str)
                and ' '.join(unicodedata.normalize('NFKC', re.sub(r'[_-]', ' ', v)).casefold().split()) in allowed for v in occupations)
            externals = row.metadata.get('external', {})
            service = isinstance(externals, dict) and any(isinstance(externals.get(k), dict) and bool(externals[k].get('id'))
                                                         for k in ('musicbrainz', 'lastfm', 'spotify'))
            if musical or service:
                kind = 'urn:entity:person'
        if kind is not None:
            need(row.name == ' '.join(unicodedata.normalize('NFKC', row.name).split())
                 and not any(unicodedata.category(c).startswith('C') for c in row.name), 'canonical provider candidate name')
            profile = {'entity_id': row.entity_id, 'name': row.name, 'type': kind}
            profile_hash(profile)
            result.append(profile)
    need(result, 'no verified music candidates')
    return result


def _events(path, source):
    need(path.stat().st_size <= 2_000_000, 'identity ledger read bound')
    events = [strict_json(line) for line in path.read_bytes().splitlines() if line.strip()]
    need(events and all(set(e) == {'sequence', 'timestamp_utc', 'source', 'kind', 'data'}
         and type(e['sequence']) is int and e['sequence'] == i and e['source'] == source for i, e in enumerate(events, 1)), 'identity event sequence/source')
    times = [instant(e['timestamp_utc']) for e in events]
    need(times == sorted(times), 'identity event time reversal')
    return events


def _sample(directory, event, source, path, params):
    data = event['data']
    expected = {'method': 'GET', 'host': 'https://hackathon.api.qloo.com', 'path': path, 'params': params}
    need(same(data['request'], expected) and type(data['attempt']) is int and data['attempt'] == 1, 'identity/cinema provider request binding')
    if event['kind'] == 'transport_failure':
        need(set(data) == {'request', 'attempt'}, 'identity transport failure fields')
        return None, None
    need(event['kind'] == 'tool_call', 'identity expected provider event')
    name = data['sample']
    need(name == f'http-{event["sequence"]:04d}.json', 'identity sample sequence')
    sample = read(directory/name)
    need(sample['source'] == source and same(sample['request'], expected)
         and type(sample['attempt']) is int and sample['attempt'] == 1 and sample['live_network_request'] is True
         and type(sample['status']) is int and 100 <= sample['status'] <= 599
         and sample['response_sha256'] == fingerprint(sample['response'])
         and same(data, {'sample': name, **{k: v for k, v in sample.items() if k != 'response'}}), 'identity sample/hash/ledger binding')
    return sample, name


def _base_report(report, plan, directory, phase):
    need(type(report['schema_version']) is int and report['schema_version'] == 5 and report['run_id'] == directory.name
         and report['mode'] == plan['mode'] and report['plan_sha256'] == plan['plan_sha256'] and report['phase'] == phase,
         'staged report/plan binding')
    instant(report['created_utc'])
    need(report['source'] in ('qloo-tool+groq-remote-llm', 'test-double-only')
         and report['causal_gate'] == report['behavioral_gate'] == report['integration_gate'] == 'NOT_EVALUATED'
         and report['cultural_gate'] == 'NOT_VALIDATED' and report['release_gate'] == 'BLOCKED'
         and report['release_approved'] is False and report['independent_validation_claim'] is False
         and report['partial_evidence_preserved'] is True, 'unapproved staged quality/release claim')
    need(type(report['model_load_attempts']) is int and report['model_load_attempts'] == 0, 'staged local model loading')


def _identity(directory, before, *, continuing=False):
    plan = read(directory/'individual-plan.json')
    request = _plan(plan)
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


def selection_profiles(receipt, selected_entity_ids):
    need(isinstance(receipt, dict) and receipt.get('verification_status') == 'VERIFIED_IDENTITY_SEARCH'
         and receipt.get('status') == 'AWAITING_IDENTITY_CONFIRMATION', 'Only a verified successful identity search may be confirmed.')
    need(isinstance(selected_entity_ids, dict) and set(selected_entity_ids) == {'A', 'B'}, 'Explicit selection is required for both profiles; no default choice.')
    profiles = {}
    for label in ('A', 'B'):
        selected = selected_entity_ids[label]
        need(isinstance(selected, str), 'A selected identity must be a canonical candidate ID.')
        members = receipt['identity_candidates'][label]
        need(isinstance(members, list) and 1 <= len(members) <= 5, 'Bounded verified candidates required.')
        for row in members:
            profile_hash(row)
        matches = [row for row in members if row['entity_id'] == selected]
        need(len(matches) == 1 and len({row['entity_id'] for row in members}) == len(members), 'Selection is outside the verified candidate set.')
        profiles[label] = copy.deepcopy(matches[0])
    need(profiles['A']['entity_id'] != profiles['B']['entity_id'], 'Two distinct confirmed musical identities are required.')
    return profiles


def verify_identity_search(directory):
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
    need(identity['verification_status'] == 'VERIFIED_IDENTITY_SEARCH', 'Failed identity search cannot continue')
    report = read(directory/'individual-report.json')
    _base_report(report, plan, directory, 'CONFIRMED_CINEMA')
    complete, source = report['status'] == 'COMPLETE', report['source']
    need(report['status'] in ('COMPLETE', 'INCOMPLETE') and source == identity['source']
         and same(report['identity_queries'], request['artists']) and report['independent_verification'] == 'PENDING', 'confirmed status/source/queries')
    need(report['error_class'] is None if complete else isinstance(report['error_class'], str) and bool(report['error_class']), 'confirmed error state')
    for key, minimum, maximum in (('model_attempts', 0, 2), ('qloo_attempts', 2, 4), ('admitted_model_slots', 0, 2)):
        need(type(report[key]) is int and minimum <= report[key] <= maximum, 'confirmed attempt budgets')
    events = _events(directory/'ledger.jsonl', source)
    need(same(events[:len(prefix)], prefix), 'confirmed ledger changed its search prefix')
    suffix = events[len(prefix):]
    need(suffix, 'missing confirmation phase event')
    if not complete:
        need(suffix[-1]['kind'] == 'stopped_without_retry' and same(suffix[-1]['data'], {'error_class': report['error_class']}), 'confirmed first-failure stop')
    active = suffix if complete else suffix[:-1]
    expected_kinds = ['identities_confirmed', 'tool_call', 'tool_call', 'all_tool_inputs_frozen',
        'remote_model_attempt_admitted', 'observed_model_execution', 'observed_cinema_boundary', 'observed_cinema_boundary',
        'remote_model_attempt_admitted', 'observed_model_execution', 'observed_cinema_boundary', 'observed_cinema_boundary']
    kinds = ['tool_call' if e['kind'] == 'transport_failure' else e['kind'] for e in active]
    need(len(kinds) <= len(expected_kinds) and kinds == expected_kinds[:len(kinds)]
         and (not complete or kinds == expected_kinds), 'confirmed legal sequential prefix')
    if len(active) >= 9:
        need('cinema-result-A.json' in before, 'confirmed B admitted before A result')
    confirmation = read(directory/'confirmation.json')
    need(set(confirmation) == {'schema_version', 'protocol_version', 'run_id', 'plan_sha256', 'identity_search_receipt',
        'identity_search_receipt_sha256', 'selected_entity_ids', 'selected_profiles'} and type(confirmation['schema_version']) is int
        and confirmation['schema_version'] == 1 and confirmation['protocol_version'] == 'cinema-confirmed-identity-v1'
        and confirmation['run_id'] == directory.name and confirmation['plan_sha256'] == plan['plan_sha256'], 'confirmation contract/binding')
    recorded_receipt = confirmation['identity_search_receipt']
    instant(recorded_receipt['verified_utc'])
    need(confirmation['identity_search_receipt_sha256'] == fingerprint(recorded_receipt)
         and same({k: v for k, v in recorded_receipt.items() if k != 'verified_utc'}, {k: v for k, v in identity.items() if k != 'verified_utc'}),
         'confirmation receipt belongs to different or changed search')
    profiles = selection_profiles(identity, confirmation['selected_entity_ids'])
    need(same(confirmation['selected_profiles'], profiles) and same(report['chosen_identities'], profiles), 'confirmed selection differs from actual candidates')
    if active:
        need(same(active[0]['data'], {'confirmation_sha256': before['confirmation.json'],
            'identity_search_receipt_sha256': fingerprint(recorded_receipt), 'selected_profiles_sha256': fingerprint(profiles)}), 'confirmation not recorded before inference')
    if 'individual-identities.json' in before:
        need(active and same(read(directory/'individual-identities.json'), profiles), 'confirmed identity file differs')
    attempts = [e for e in active if e['kind'] in ('tool_call', 'transport_failure')]
    need(len(attempts) + 2 == report['qloo_attempts'], 'confirmed cumulative Qloo accounting')
    samples, sample_names = {}, list(identity_samples)
    for i, event in enumerate(attempts):
        label = ('A', 'B')[i]
        params = {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': 20,
            'signal.interests.entities': profiles[label]['entity_id'],
            'filter.results.entities': ','.join(sorted(row['entity_id'] for row in request['catalog']))}
        sample, name = _sample(directory, event, source, '/v2/insights', params)
        if sample is None or sample['status'] != 200:
            need(not complete and event == active[-1] and report['error_class'] == 'TransportError', 'confirmed tool failure was not terminal')
        if name:
            sample_names.append(name)
            samples[before[name]] = sample
        if i < len(attempts)-1:
            need(sample is not None and sample['status'] == 200, 'confirmed request after failed insight')
            context_from_sample(profiles[label], request['catalog'], sample, before[name])
    need({n for n in before if n.startswith('http-')} == set(sample_names), 'confirmed orphan provider sample')
    manifest = read(directory/'model-manifest.json') if 'model-manifest.json' in before else None
    if manifest is not None:
        need(active and same(manifest, expected_manifest('test-double-only' if source == 'test-double-only' else 'remote-llm')), 'confirmed model contract')
    need(not attempts or manifest is not None and 'individual-identities.json' in before, 'insights before confirmed identities/model contract')
    contexts = read(directory/'individual-tool-inputs.json') if 'individual-tool-inputs.json' in before else None
    frozen = [e for e in active if e['kind'] == 'all_tool_inputs_frozen']
    if contexts is not None:
        need(set(contexts) == {profile_hash(p) for p in profiles.values()} and len(frozen) == 1 and len(attempts) == 2, 'confirmed context coverage')
        for profile in profiles.values():
            context = contexts[profile_hash(profile)]
            need(context['sample_sha256'] in samples and same(context, context_from_sample(profile, request['catalog'],
                 samples[context['sample_sha256']], context['sample_sha256'])), 'confirmed context differs from selected identity')
        need(same(frozen[0]['data'], {'sha256': fingerprint(contexts), 'model_calls': 0, 'qloo_calls': 4}), 'confirmed input seal')
    else:
        need(not frozen and not complete, 'missing confirmed sealed inputs')
    packet_names = sorted(n for n in before if n.startswith('cinema-execution-'))
    observed = [e for e in active if e['kind'] == 'observed_model_execution']
    need(len(packet_names) == len(observed) <= report['model_attempts'] <= 2
         and report['model_attempts'] - len(packet_names) <= 1, 'confirmed packet/attempt accounting')
    need(not report['model_attempts'] or contexts is not None and manifest is not None and len(attempts) == 2, 'model before confirmed complete tool preflight')
    verify_pacing(plan, events, report, observed, frozen)
    results, result_names, completion_ids, boundaries = {}, [], set(), []
    for i, name in enumerate(packet_names, 1):
        label = ('A', 'B')[i-1]
        effective = decision_request(request, profiles[label], contexts[profile_hash(profiles[label])], label, directory.name)
        packet = read(directory/name)
        need(set(packet) == {'execution_id', 'effective_request', 'model_payload', 'response', 'observation'}
             and name == f'cinema-execution-{i:03d}.json' and packet['execution_id'] == directory.name + '/' + str(i)
             and same(packet['effective_request'], effective), 'confirmed effective request sequence')
        ranking = validate_response(effective, packet['response'])
        payload, observation = expected_payload(effective), packet['observation']
        need(same(payload, packet['model_payload']) and type(observation['call']) is int and observation['call'] == i
             and observation['input_sha256'] == fingerprint(payload) and observation['output_sha256'] == fingerprint(ranking), 'confirmed preferences/artist/raw payload binding')
        verify_packet(packet, manifest, source, system_prompt=CINEMA_PROMPT)
        need(observation['completion_id'] not in completion_ids, 'confirmed duplicate completion')
        completion_ids.add(observation['completion_id'])
        need(same(observed[i-1]['data'], {'execution_id': packet['execution_id'], 'request_sha256': fingerprint(effective),
             'payload_sha256': fingerprint(payload), 'output_sha256': fingerprint(ranking)}), 'confirmed packet event')
        guard = delivery(ranking, request['catalog'], effective['preferences'])
        traces = [boundary(effective, packet, manifest, guard, hit=hit) for hit in (False, True)]
        available = [e for e in active if e['kind'] == 'observed_cinema_boundary' and e['data'].get('execution_id') == packet['execution_id']]
        need(len(available) <= 2 and (len(available) == 2 if complete else True), 'confirmed cache boundary coverage')
        for j, event in enumerate(available):
            need(same(event['data'], traces[j]), 'confirmed cache/preferences/intent boundary')
        boundaries.extend(available)
        result_name = 'cinema-result-' + label + '.json'
        if result_name in before:
            need(len(available) == 2, 'confirmed result before complete cache proof')
            result_names.append(result_name)
            reference = baseline(effective['tool_context'], request['catalog'], effective['preferences'])
            public = projection(profiles[label], effective['preferences'], effective, guard, reference)
            need(same(read(directory/result_name), {'schema_version': 1, 'label': label, 'effective_request': effective,
                'uncached_boundary': {'ranking': ranking, 'delivery': guard, 'trace': traces[0]},
                'cached_boundary': {'ranking': ranking, 'delivery': guard, 'trace': traces[1]}, 'baseline': reference, 'result': public}), 'confirmed raw/delivery/baseline differs')
            results[label] = public
    need(len(boundaries) == sum(e['kind'] == 'observed_cinema_boundary' for e in active), 'confirmed orphan boundary')
    need(same(report['cinema_results'], results) and type(report['successful_profiles']) is int and report['successful_profiles'] == len(results)
         and type(report['requested_profiles']) is int and report['requested_profiles'] == 2
         and type(report['failed_model_attempts']) is int and report['failed_model_attempts'] == report['model_attempts']-len(packet_names)
         and type(report['unattempted_profiles']) is int and report['unattempted_profiles'] == 2-report['model_attempts'], 'confirmed denominators/results')
    need(report['preference_gate'] == ('PASS' if complete else 'NOT_EVALUATED'), 'confirmed preference gate')
    if complete:
        need(len(results) == len(packet_names) == report['model_attempts'] == 2 and report['qloo_attempts'] == 4, 'confirmed complete budgets')
    allowed = set(identity['artifact_sha256']) | {'confirmation.json', 'individual-report.json', 'individual-identities.json',
        'model-manifest.json', 'individual-tool-inputs.json'} | set(sample_names) | set(packet_names) | set(result_names)
    need(set(before) <= allowed and inventory(directory) == before, 'confirmed unknown artifact or concurrent mutation')
    return {**report, 'verified_utc': utc_now(), 'verification_status': 'VERIFIED_COMPLETE' if complete else 'VERIFIED_PARTIAL',
        'identity_candidates': identity['identity_candidates'], 'provenance': identity['provenance'], 'external_service_attested': False,
        'artifact_sha256': before, 'verified_provider_samples': len(sample_names), 'verified_model_packets': len(packet_names),
        'capture_source_sha256': plan['source_sha256'], 'capture_driver_sha256': plan['driver_sha256'],
        'dependencies_lock_sha256': plan['dependencies_lock_sha256'], 'verifier_source_sha256': {'cinema_identity_verify.py': sha(Path(__file__))},
        'verification_boundary': 'Immutable search prefix, explicit candidate membership selection, cumulative budgets and independent cinema payload/cache/delivery verification; no service, cultural or causal attestation.'}


def verify_confirmed_cinema(directory):
    try:
        directory = checked_path(directory)
        if not (directory/'individual-report.json').exists():
            return verify_identity_search(directory)
        return _confirmed(directory)
    except SchemaError:
        raise
    except (AgentError, KeyError, TypeError, ValueError, IndexError, StopIteration, OSError) as exc:
        raise SchemaError('Confirmed cinema audit: missing, malformed or inconsistent evidence') from exc
