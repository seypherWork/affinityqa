"""Pure discovery-boundary audit with independent input/output reconstruction.

Does not authenticate an API or certify taste quality. A file verifier must bind
the supplied sample byte hash to its actual immutable artifact inventory.
"""
import copy
import json
import math
import re

from .causal_agent import profile_hash, validate_catalog
from .cinema_discoveries import DISCOVERY_PROMPT
from .errors import SchemaError
from .evidence import fingerprint
from .individual_remote_verify import expected_manifest as literal_remote_manifest
from .models import parse_entities

PROTOCOL = 'cinema-confirmed-discovery-v2'


def need(condition, message):
    if not condition:
        raise SchemaError('Discovery boundary audit: ' + message)


def same(a, b):
    try:
        return fingerprint(a) == fingerprint(b)
    except (TypeError, ValueError, RecursionError):
        raise SchemaError('Discovery boundary audit: invalid finite JSON.') from None


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def digest(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def preferences(value, catalog):
    ids = validate_catalog(catalog)
    need(isinstance(value, dict) and set(value) == {'schema_version', 'favorite_entity_ids', 'excluded_entity_ids'}
         and integer(value['schema_version'], 1, 1), 'closed preferences version1')
    for key, maximum in (('favorite_entity_ids', 5), ('excluded_entity_ids', 15)):
        rows = value[key]
        need(isinstance(rows, list) and len(rows) <= maximum
             and all(isinstance(v, str) and v in ids for v in rows)
             and len(set(rows)) == len(rows), 'known bounded unique preference IDs')
    f, x = sorted(value['favorite_entity_ids']), sorted(value['excluded_entity_ids'])
    need(not set(f) & set(x) and len(set(ids) - set(f) - set(x)) >= 5, 'five nonseed eligible movies')
    return {'schema_version': 1, 'favorite_entity_ids': f, 'excluded_entity_ids': x}


def expected_manifest(source, *, max_calls=2, timeout=120):
    need(source in ('remote-llm', 'test-double-only'), 'execution source')
    need(integer(max_calls, 1, 39) and type(timeout) in (int, float)
         and math.isfinite(timeout) and 1 <= timeout <= 120, 'model budget/timeout')
    value = literal_remote_manifest(source)
    value.update(prompt_version=PROTOCOL, prompt_sha256=fingerprint(DISCOVERY_PROMPT),
                 tool_contract='qloo-composite-signal+known-favorites+exact-discovery-universe-v1',
                 response_contract='groq-strict-discovery-rank-slots-v2-redacted-envelope',
                 output_universe='Reference catalog minus explicit known favorites; exact permutation, not padded to twenty.',
                 max_inference_calls=max_calls, inference_timeout_seconds=timeout)
    value['diagnostic_contract'] = {'schema_version':1,'request_receipt':'discovery-prepared-request-v1',
        'failure_receipt':'discovery-http-enums-v1','maximum_error_body_bytes':8192,
        'raw_message_or_generation_recorded':False,'external_dispatch_attested':False}
    return value


def verify_context(context, catalog, profile, prefs, sample, sample_sha256):
    """Reconstruct exact new context from recorded Qloo data, not core helpers."""
    ids, p = validate_catalog(catalog), preferences(prefs, catalog)
    identity = profile_hash(profile)
    need(profile['entity_id'] not in ids and digest(sample_sha256), 'artist/catalog separation and sample hash')
    positive = {'profile_sha256': identity, 'favorite_input_sha256': fingerprint(p['favorite_entity_ids']),
                'signal_entity_ids': sorted([profile['entity_id'], *p['favorite_entity_ids']])}
    discoveries = sorted(set(ids) - set(p['favorite_entity_ids']))
    request = {'method': 'GET', 'host': 'https://hackathon.api.qloo.com', 'path': '/v2/insights',
               'params': {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': len(discoveries),
                          'signal.interests.entities': ','.join(positive['signal_entity_ids']),
                          'filter.results.entities': ','.join(discoveries)}}
    need(isinstance(sample, dict) and same(sample.get('request'), request)
         and integer(sample.get('status'), 200, 200) and integer(sample.get('attempt'), 1, 1)
         and sample.get('live_network_request') is True, 'exact recorded single live GET')
    body = sample.get('response')
    need(sample.get('response_sha256') == fingerprint(body), 'recorded response hash')
    rows = parse_entities(body, insights=True)
    need(len(rows) == len(discoveries) and {r.entity_id for r in rows} == set(discoveries), 'exact nonseed coverage')
    metadata = {r['entity_id']: r for r in catalog}
    need(all('urn:entity:movie' in r.types and r.name == metadata[r.entity_id]['name']
             and type(r.metadata.get('release_year')) is int
             and r.metadata['release_year'] == metadata[r.entity_id]['release_year']
             and type(r.affinity) in (int, float) and math.isfinite(r.affinity) and 0 <= r.affinity <= 1
             for r in rows), 'actual movie metadata and affinity')
    value = {'schema_version': 2, 'tool_name': 'qloo-film-discovery-context-v1', 'profile': copy.deepcopy(profile),
             **positive, 'favorite_entity_ids': p['favorite_entity_ids'],
             'signal_sha256': fingerprint(positive), 'catalog_sha256': fingerprint(catalog),
             'discovery_entity_ids': discoveries, 'discovery_sha256': fingerprint(discoveries),
             'ranked_entities': [{'entity_id': r.entity_id, 'affinity': r.affinity} for r in rows],
             'request_sha256': fingerprint(request), 'response_sha256': fingerprint(body),
             'sample_sha256': sample_sha256}
    value['context_sha256'] = fingerprint(value)
    need(same(context, value), 'context does not reconstruct from the actual tool sample')
    return value


def expected_input(request):
    """Independently derive closed request constants, original indices and payload."""
    ids, p = validate_catalog(request['catalog']), preferences(request['preferences'], request['catalog'])
    profile, context = request['profile'], request['tool_context']
    identity = profile_hash(profile)
    positive = {'profile_sha256': identity, 'favorite_input_sha256': fingerprint(p['favorite_entity_ids']),
                'signal_entity_ids': sorted([profile['entity_id'], *p['favorite_entity_ids']])}
    signal = fingerprint(positive)
    d = [i for i, v in enumerate(ids) if v not in p['favorite_entity_ids']]
    e = [i for i in d if ids[i] not in p['excluded_entity_ids']]
    intent = fingerprint({'protocol': PROTOCOL, 'catalog_sha256': fingerprint(request['catalog']),
                          'profile_sha256': identity, 'signal_sha256': signal, 'preferences': p})
    need(isinstance(request['request_nonce'], str) and 1 <= len(request['request_nonce']) <= 120, 'bounded nonce')
    value = {'schema_version': 3, 'protocol': PROTOCOL,
             'task': 'Recommend five new discoveries using known interests and the fixed reference catalog.',
             'top_k': 5, 'catalog': request['catalog'], 'profile': profile, 'tool_context': context,
             'request_nonce': request['request_nonce'], 'preferences': p, 'profile_sha256': identity,
             'signal_sha256': signal, 'preferences_sha256': fingerprint(p), 'intent_sha256': intent,
             'discovery_catalog_indices': d, 'eligible_catalog_indices': e}
    value['request_id'] = fingerprint(value)
    need(same(request, value) and profile == context['profile'], 'request identity/constants/intent')
    ranks = [f'rank_{position:02d}' for position in range(1, len(d) + 1)]
    schema = {'type': 'object', 'properties': {'ordered_catalog_indices': {
        'type': 'object', 'properties': {rank: {'type': 'integer', 'enum': list(d)} for rank in ranks},
        'required': ranks, 'additionalProperties': False}},
        'required': ['ordered_catalog_indices'], 'additionalProperties': False}
    return {'cinema_protocol': PROTOCOL, 'task': value['task'],
            'catalog': [{'index': i, **r} for i, r in enumerate(request['catalog'])], 'profile': profile,
            'known_favorite_movies': [{'catalog_index': ids.index(v), **request['catalog'][ids.index(v)]}
                                     for v in p['favorite_entity_ids']],
            'discovery_catalog_indices': d, 'eligible_catalog_indices': e,
            'provider_movie_context': [{'catalog_index': ids.index(r['entity_id']), 'affinity': r['affinity']}
                                       for r in context['ranked_entities']],
            'cinema_preferences': {'schema_version': 1, 'favorite_catalog_indices': [ids.index(v) for v in p['favorite_entity_ids']],
                'excluded_catalog_indices': [ids.index(v) for v in p['excluded_entity_ids']],
                'favorites_scope': 'Known positive inputs, excluded from ranking and delivery; no seed affinities.',
                'exclusions_scope': 'Hard delivery constraints; not Qloo positive signals.'},
            'profile_sha256': identity, 'signal_sha256': signal, 'preferences_sha256': fingerprint(p),
            'intent_sha256': intent,
            'tool_notice': 'Actual composite Qloo discovery context; query-relative affinities, no independent quality labels.',
            'output_schema': schema}


def verify_packet(packet, manifest, source, sample, sample_sha256):
    """Check a full successful observation; partial attempts are never successes."""
    try:
        need(isinstance(packet, dict) and set(packet) == {'execution_id', 'effective_request', 'model_payload', 'response', 'observation'}, 'packet schema')
        need(same(manifest, expected_manifest(source, max_calls=manifest['max_inference_calls'],
                                           timeout=manifest['inference_timeout_seconds'])), 'closed model manifest')
        request, obs = packet['effective_request'], packet['observation']
        verify_context(request['tool_context'], request['catalog'], request['profile'], request['preferences'], sample, sample_sha256)
        payload = expected_input(request)
        need(same(packet['model_payload'], payload), 'actual model payload')
        envelope = obs['provider_envelope']
        need(isinstance(envelope, dict) and set(envelope) == {'schema_version', 'discovery_protocol', 'execution_source', 'provider', 'object', 'model', 'id', 'created', 'system_fingerprint', 'choice', 'usage'}, 'redacted envelope schema')
        need(integer(envelope['schema_version'], 3, 3) and envelope['discovery_protocol'] == PROTOCOL
             and envelope['execution_source'] == source and envelope['provider'] == 'groq'
             and envelope['model'] == manifest['model'] and envelope['object'] == 'chat.completion', 'envelope identity/source')
        need(isinstance(envelope['id'], str) and re.fullmatch(r'[!-~]{1,160}', envelope['id'])
             and integer(envelope['created'], 1, 2**63 - 1), 'completion identity/time')
        fp = envelope['system_fingerprint']
        need(fp is None or isinstance(fp, str) and re.fullmatch(r'[!-~]{1,128}', fp), 'deployment fingerprint')
        choice = envelope['choice']
        need(isinstance(choice, dict) and set(choice) == {'index', 'finish_reason', 'role', 'ordered_catalog_indices'}
             and integer(choice['index'], 0, 0) and choice['finish_reason'] == 'stop' and choice['role'] == 'assistant', 'complete choice')
        slots, allowed = choice['ordered_catalog_indices'], request['discovery_catalog_indices']
        rank_names = [f'rank_{position:02d}' for position in range(1, len(allowed) + 1)]
        need(isinstance(slots, dict) and set(slots) == set(rank_names), 'closed complete rank slots')
        indices = [slots[rank] for rank in rank_names]
        need(all(type(i) is int for i in indices) and set(indices) == set(allowed), 'exact nonseed permutation')
        ranking = [request['catalog'][i]['entity_id'] for i in indices]
        need(same(packet['response'], {'schema_version': 1, 'request_id': request['request_id'], 'ranked_entity_ids': ranking}), 'response binding')
        usage = envelope['usage']
        need(isinstance(usage, dict) and set(usage) == {'prompt_tokens', 'completion_tokens', 'total_tokens', 'reasoning_tokens'}
             and integer(usage['prompt_tokens'], 1, 8192) and integer(usage['completion_tokens'], 1, 1024)
             and type(usage['total_tokens']) is int and usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens']
             and (usage['reasoning_tokens'] is None or integer(usage['reasoning_tokens'], 0, usage['completion_tokens'])), 'typed usage bounds')
        need(type(obs['elapsed_ms']) in (int, float) and math.isfinite(obs['elapsed_ms']) and obs['elapsed_ms'] >= 0
             and integer(obs['call'], 1, manifest['max_inference_calls']) and digest(obs['provider_response_sha256']), 'observation attempt/hash/time')
        wire = {'model': manifest['model'], 'messages': [
            {'role': 'system', 'content': DISCOVERY_PROMPT},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False, allow_nan=False)}],
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'affinityqa_discovery_rank_slots_v2',
                'strict': True, 'schema': payload['output_schema']}}, **manifest['options']}
        expected = {'call': obs['call'], 'input_sha256': fingerprint(payload), 'output_sha256': fingerprint(ranking),
            'elapsed_ms': obs['elapsed_ms'], 'prompt_eval_count': usage['prompt_tokens'], 'eval_count': usage['completion_tokens'],
            'private_thinking_recorded': False, 'done': True, 'done_reason': 'stop', 'provider': 'groq',
            'model': manifest['model'], 'completion_id': envelope['id'], 'provider_created': envelope['created'],
            'system_fingerprint': fp, 'provider_response_sha256': obs['provider_response_sha256'],
            'provider_response_hash_scope': 'Full parsed response observation; not reconstructible from the redacted envelope.',
            'provider_request_sha256': fingerprint(wire), 'provider_envelope': envelope,
            'provider_envelope_sha256': fingerprint(envelope), 'total_tokens': usage['total_tokens'],
            'reasoning_tokens': usage['reasoning_tokens'], 'model_revision_attested': False, 'execution_source': source,
            'discovery_protocol': PROTOCOL, 'reference_catalog_count': 20, 'raw_discovery_count': len(indices)}
        need(same(obs, expected) and len(json.dumps(wire, ensure_ascii=False, allow_nan=False).encode()) <= 65536,
             'observation or exact transmitted request differs')
        need(isinstance(packet['execution_id'], str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}/[1-9][0-9]?', packet['execution_id'])
             and packet['execution_id'].endswith('/' + str(obs['call'])), 'execution identity')
        delivered = [v for v in ranking if v not in request['preferences']['excluded_entity_ids']][:5]
        return {'raw_ranking': ranking, 'delivered_entity_ids': delivered,
                'baseline_delivered_entity_ids': [r['entity_id'] for r in request['tool_context']['ranked_entities']
                    if r['entity_id'] not in request['preferences']['excluded_entity_ids']][:5],
                'completion_id': envelope['id'], 'system_fingerprint': fp,
                'quality_validated': False, 'external_service_attested': False}
    except SchemaError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, RecursionError) as exc:
        raise SchemaError('Discovery boundary audit: malformed or inconsistent packet.') from exc


def verify_complete_packet_set(packets, manifest, source, samples):
    """Exact full successful budget, unique completions and one run; no partial GO."""
    try:
        need(isinstance(packets, list) and len(packets) == manifest['max_inference_calls']
             and isinstance(samples, dict), 'complete declared packet denominator')
        results, ids, run_id = [], set(), None
        for call, packet in enumerate(packets, 1):
            need(integer(packet['observation']['call'], call, call), 'packet sequence')
            current = packet['execution_id'].rsplit('/', 1)[0]
            need(run_id is None or current == run_id, 'packet from a different run')
            run_id = current
            sample_sha = packet['effective_request']['tool_context']['sample_sha256']
            need(sample_sha in samples, 'missing packet tool sample')
            verified = verify_packet(packet, manifest, source, samples[sample_sha], sample_sha)
            need(verified['completion_id'] not in ids, 'duplicate completion identity in complete packet set')
            ids.add(verified['completion_id'])
            results.append(verified)
        return results
    except SchemaError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        raise SchemaError('Discovery boundary audit: malformed packet set.') from exc
