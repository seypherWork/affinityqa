"""Independent semantic checks for saved Qloo inputs and supported repairs.

The caller must first verify the receipt, file bytes and selected capture. This
module checks their meaning; hashes and a live_network_request flag are not
external-service attestation. No producer context/payload builder is imported.
"""
from __future__ import annotations

import copy
import math
import re
import unicodedata
from functools import wraps
from uuid import UUID

from .errors import SchemaError
from .evidence import fingerprint

INPUT_CHECKS = ('raw_qloo_request_bound', 'raw_qloo_response_bound',
                'context_projection_bound', 'model_payload_bound', 'observed_trace_bound')
PROOF_CHECKS = (*INPUT_CHECKS, 'supported_transition_verified',
                'requested_context_restored', 'legitimate_cache_bound')
OPERATIONS = {
    'CACHE_OMITS_PROFILE': ('set-profile-cache', 'cache_scope', 'task', 'profile'),
    'STALE_PROFILE': ('restore-request-profile', 'request_profile_current', False, True),
    'WRONG_TOOL_PROFILE': ('bind-request-tool', 'qloo_profile_current', False, True),
    'NONE': ('none', 'none', None, None),
}
STATE_KEYS = {'cache_scope', 'request_profile_current', 'qloo_profile_current',
              'patch_count', 'cache_entries'}
PROFILE_KEYS = ('requested_profile_sha256', 'transmitted_profile_sha256',
                'tool_profile_sha256', 'output_profile_sha256')


def _need(condition, message):
    if not condition:
        raise SchemaError('Qloo evidence: ' + message)


def _closed(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            raise SchemaError('Qloo evidence: malformed input; no repair approved.') from None
    return checked


def _same(left, right):
    # JSON fingerprints distinguish True/1 and reject nonfinite values.
    return fingerprint(left) == fingerprint(right)


def _uuid(value):
    _need(type(value) is str and str(UUID(value)) == value, 'noncanonical identity.')
    return value


def _profile(profile):
    _need(type(profile) is dict and set(profile) == {'entity_id', 'name', 'type'}, 'invalid profile.')
    _uuid(profile['entity_id'])
    _need(type(profile['name']) is str and 0 < len(profile['name']) <= 300
          and profile['name'] == ' '.join(unicodedata.normalize('NFKC', profile['name']).split()), 'invalid profile name.')
    _need(profile['type'] in ('urn:entity:artist', 'urn:entity:person'), 'invalid profile type.')
    return fingerprint(profile)


def _catalog(catalog):
    _need(type(catalog) is list and len(catalog) == 20, 'twenty-film capture required.')
    rows = {}
    for row in catalog:
        _need(type(row) is dict and set(row) == {'entity_id', 'name', 'release_year'}, 'invalid catalog.')
        identity = _uuid(row['entity_id'])
        _need(identity not in rows and type(row['name']) is str and bool(row['name'].strip())
              and type(row['release_year']) is int and 1888 <= row['release_year'] <= 2030,
              'invalid or repeated catalog film.')
        rows[identity] = row
    return rows


def _bound_contexts(catalog, profiles, contexts, samples):
    movies = _catalog(catalog)
    _need(type(profiles) is dict and set(profiles) == {'A', 'B'}, 'two explicit profiles required.')
    hashes = {_profile(profile) for profile in profiles.values()}
    _need(len(hashes) == 2 and type(contexts) is dict and set(contexts) == hashes,
          'frozen profile coverage differs.')
    _need(type(samples) is dict, 'verified samples missing.')
    for profile in profiles.values():
        context = contexts[_profile(profile)]
        digest = context['sample_sha256']
        _need(type(digest) is str and re.fullmatch('[a-f0-9]{64}', digest), 'invalid sample binding.')
        sample = samples[digest]
        request = {'method': 'GET', 'host': 'https://hackathon.api.qloo.com', 'path': '/v2/insights',
                   'params': {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': 20,
                              'signal.interests.entities': profile['entity_id'],
                              'filter.results.entities': ','.join(sorted(movies))}}
        _need(_same(sample['request'], request) and type(sample['status']) is int
              and sample['status'] == 200 and type(sample['attempt']) is int
              and sample['attempt'] == 1 and sample['live_network_request'] is True,
              'raw request is not bound to its explicit interest and catalog.')
        body = sample['response']
        _need(type(body) is dict and body.get('success') is True
              and not {'error', 'errors'}.intersection(body), 'unsuccessful raw response.')
        _need(sample['response_sha256'] == fingerprint(body), 'raw response fingerprint differs.')
        raw = body['results']['entities']
        _need(type(raw) is list and len(raw) == 20, 'incomplete raw movie context.')
        ranked, seen = [], set()
        for row in raw:
            identity = str(UUID(row['entity_id']))
            _need(identity in movies and identity not in seen, 'wrong or duplicate raw movie.')
            seen.add(identity)
            types = row.get('types', [])
            _need(type(types) is list and all(type(t) is str for t in types), 'invalid raw types.')
            categories = set(types) | {row.get('type'), row.get('subtype')}
            query, properties = row.get('query', {}), row.get('properties', {})
            _need(type(query) is dict and type(properties) is dict, 'invalid raw movie metadata.')
            affinity = query.get('affinity', row.get('affinity'))
            _need(type(affinity) in (int, float) and math.isfinite(affinity) and 0 <= affinity <= 1,
                  'invalid raw affinity.')
            year = row.get('release_year', properties.get('release_year'))
            _need('urn:entity:movie' in categories and type(row['name']) is str
                  and row['name'].strip() == movies[identity]['name']
                  and type(year) is int and year == movies[identity]['release_year'],
                  'raw movie identity differs from the catalog.')
            ranked.append({'entity_id': identity, 'affinity': affinity})
        expected = {'schema_version': 1, 'tool_name': 'qloo-movie-context-v1',
                    'profile': profile, 'catalog_sha256': fingerprint(catalog),
                    'ranked_entities': ranked, 'request_sha256': fingerprint(request),
                    'response_sha256': fingerprint(body), 'sample_sha256': digest}
        expected['context_sha256'] = fingerprint(expected)
        _need(_same(context, expected), 'derived context differs from its raw source.')
    return hashes


def _request(value, catalog, hashes, contexts):
    keys = {'schema_version', 'task', 'top_k', 'catalog', 'profile', 'tool_context',
            'request_nonce', 'request_id'}
    _need(type(value) is dict and set(value) == keys and type(value['schema_version']) is int
          and value['schema_version'] == 1 and type(value['top_k']) is int and value['top_k'] == 5,
          'invalid effective request.')
    _need(_same(value['catalog'], catalog) and _profile(value['profile']) in hashes,
          'effective catalog or profile differs.')
    _need(type(value['task']) is str and 0 < len(value['task']) <= 600
          and bool(value['task'].strip()) and type(value['request_nonce']) is str
          and 0 < len(value['request_nonce']) <= 120, 'invalid task or nonce.')
    context = value['tool_context']
    _need(_same(context, contexts[_profile(context['profile'])]), 'unsealed effective context.')
    _need(value['request_id'] == fingerprint({k: v for k, v in value.items() if k != 'request_id'}),
          'effective request fingerprint differs.')


@_closed
def inspect_decision(requested, decision, packets, *, profiles, contexts, samples):
    """Bind observed semantics without assuming the requested profile was used."""
    catalog = requested['catalog']
    hashes = _bound_contexts(catalog, profiles, contexts, samples)
    _request(requested, catalog, hashes, contexts)
    wanted = _profile(requested['profile'])
    _need(_same(requested['tool_context'], contexts[wanted]), 'caller context is not its requested profile.')
    trace = decision['trace']
    _need(type(trace.get('execution_id')) is str and bool(trace['execution_id']), 'invalid execution identity.')
    _need(type(trace) is dict and type(trace['cache_hit']) is bool, 'invalid observed cache flag.')
    matches = [p for p in packets if p['execution_id'] == trace['execution_id']]
    _need(len(matches) == 1, 'one observed execution packet is required.')
    packet = matches[0]
    effective, payload, response, observation = (packet[k] for k in
        ('effective_request', 'model_payload', 'response', 'observation'))
    _request(effective, catalog, hashes, contexts)
    _need(effective['task'] == requested['task'], 'cached task differs from this request.')
    context = effective['tool_context']
    indices = {row['entity_id']: i for i, row in enumerate(catalog)}
    schema = {'type': 'object', 'properties': {'ordered_catalog_indices': {'type': 'array',
              'items': {'type': 'integer', 'enum': list(range(20))}, 'minItems': 20, 'maxItems': 20}},
              'required': ['ordered_catalog_indices'], 'additionalProperties': False}
    expected_payload = {'task': effective['task'],
        'catalog': [{'index': i, 'name': row['name'], 'release_year': row['release_year']}
                    for i, row in enumerate(catalog)], 'profile': effective['profile'],
        'provider_movie_context': [{'catalog_index': indices[row['entity_id']], 'affinity': row['affinity']}
                                   for row in context['ranked_entities']],
        'tool_notice': 'Qloo query-relative cultural context, consumed by this agent. Not independent evaluation or confidence.',
        'output_schema': schema}
    _need(_same(payload, expected_payload), 'model payload does not contain the bound Qloo context.')
    _need(type(response) is dict and set(response) == {'schema_version', 'request_id', 'ranked_entity_ids'}
          and type(response['schema_version']) is int and response['schema_version'] == 1
          and response['request_id'] == effective['request_id'], 'response belongs to another request.')
    ranking = response['ranked_entity_ids']
    _need(type(ranking) is list and len(ranking) == 20 and all(type(i) is str for i in ranking)
          and set(ranking) == set(indices) and _same(decision['ranking'], ranking), 'output permutation differs.')
    sent, tool = _profile(payload['profile']), _profile(context['profile'])
    expected_trace = {'requested_profile_sha256': wanted, 'transmitted_profile_sha256': sent,
        'tool_profile_sha256': tool, 'output_profile_sha256': sent,
        'payload_sha256': fingerprint(payload), 'context_response_sha256': context['response_sha256'],
        'requested_request_sha256': fingerprint(requested),
        'execution_request_sha256': fingerprint(effective), 'output_sha256': fingerprint(ranking)}
    _need(all(trace.get(k) == v for k, v in expected_trace.items()), 'observed trace differs from its packet.')
    _need(type(observation['call']) is int and observation['call'] > 0
          and type(trace['call']) is int and trace['call'] == observation['call']
          and observation['input_sha256'] == fingerprint(payload)
          and observation['output_sha256'] == fingerprint(ranking), 'model observation differs.')
    cause = 'UNSUPPORTED'
    if wanted == sent == tool:
        cause = 'NONE'
    elif trace['cache_hit'] and wanted != sent and sent == tool:
        cause = 'CACHE_OMITS_PROFILE'
    elif not trace['cache_hit'] and wanted != sent and sent == tool:
        cause = 'STALE_PROFILE'
    elif not trace['cache_hit'] and wanted == sent and wanted != tool:
        cause = 'WRONG_TOOL_PROFILE'
    return {'diagnosis': cause, 'operation': OPERATIONS.get(cause, ('none',))[0],
            'requested_profile_sha256': wanted, 'tool_profile_sha256': tool,
            'checks': dict.fromkeys(INPUT_CHECKS, True)}


def session_state(session):
    return {'cache_scope': session.scope, 'request_profile_current': session.route_current,
            'qloo_profile_current': session.bind_current, 'patch_count': session.patches,
            'cache_entries': len(session.cache)}


def _state(state):
    _need(type(state) is dict and set(state) == STATE_KEYS and state['cache_scope'] in ('task', 'profile')
          and type(state['request_profile_current']) is bool and type(state['qloo_profile_current']) is bool
          and type(state['patch_count']) is int and state['patch_count'] >= 0
          and type(state['cache_entries']) is int and state['cache_entries'] >= 0, 'invalid adapter state.')


@_closed
def plan_repair(observation, state):
    """A supported single change requires semantic evidence and one faulty setting."""
    _state(state)
    _need(type(observation['checks']) is dict and set(observation['checks']) == set(INPUT_CHECKS)
          and all(v is True for v in observation['checks'].values()), 'semantic checks are not complete.')
    cause = observation['diagnosis']
    _need(cause in OPERATIONS, 'unsupported profile divergence; no repair planned.')
    operation, setting, before, after = OPERATIONS[cause]
    _need(observation['operation'] == operation and (cause == 'NONE' or state['patch_count'] == 0), 'unapproved repair operation or repeat.')
    expected = {'cache_scope': 'profile', 'request_profile_current': True, 'qloo_profile_current': True,
                'patch_count': state['patch_count'] if cause == 'NONE' else 0, 'cache_entries': state['cache_entries']}
    if cause != 'NONE':
        expected[setting] = before
    _need(_same(state, expected), 'state does not match one supported incident.')
    return {'diagnosis': cause, 'operation': operation, 'setting': setting, 'before': before, 'after': after}


@_closed
def verify_repair_transition(plan, before_state, after_state):
    _state(before_state)
    _state(after_state)
    _need(type(plan) is dict and set(plan) == {'diagnosis', 'operation', 'setting', 'before', 'after'},
          'invalid repair plan.')
    cause = plan['diagnosis']
    _need(cause in OPERATIONS, 'unsupported repair transition.')
    operation, setting, before, after = OPERATIONS[cause]
    _need(_same(plan, {'diagnosis': cause, 'operation': operation, 'setting': setting,
                      'before': before, 'after': after}), 'repair plan changed.')
    expected_plan = plan_repair({'diagnosis': cause, 'operation': operation, 'checks': dict.fromkeys(INPUT_CHECKS, True)}, before_state)
    _need(_same(plan, expected_plan), 'repair preconditions differ.')
    expected = copy.deepcopy(before_state)
    if cause != 'NONE':
        _need(before_state['patch_count'] == 0 and _same(before_state[setting], before), 'repair precondition differs.')
        expected.update({setting: after, 'patch_count': 1, 'cache_entries': 0})
    _need(_same(after_state, expected), 'repair changed another setting or failed to clear affected state.')


@_closed
def verify_captured_packets(catalog, profiles, contexts, samples, packets, *, execution_prefix, expected_count=39):
    """Independently inspect the original packets, not just reconstructed replay data.

    An effective request may deliberately contain another profile's tool input.
    Reconstructing a caller handle here checks packet semantics; the actual
    requested profile and diagnosis are separately checked by inspect_decision.
    """
    _need(type(packets) is list and type(expected_count) is int and expected_count == 39
          and len(packets) == expected_count, 'complete captured packet set required.')
    _need(type(execution_prefix) is str and execution_prefix.endswith('/'), 'execution prefix required.')
    ids, calls = set(), set()
    for packet in packets:
        effective = packet['effective_request']
        observation = packet['observation']
        call, identity = observation['call'], packet['execution_id']
        _need(type(call) is int and 1 <= call <= expected_count
              and identity == execution_prefix + str(call) and identity not in ids and call not in calls,
              'captured execution identity differs or repeats.')
        ids.add(identity)
        calls.add(call)
        sent = _profile(effective['profile'])
        context = effective['tool_context']
        caller = copy.deepcopy(effective)
        caller['tool_context'] = copy.deepcopy(contexts[sent])
        caller['request_id'] = fingerprint({k: v for k, v in caller.items() if k != 'request_id'})
        ranking = packet['response']['ranked_entity_ids']
        trace = {'requested_profile_sha256': sent, 'transmitted_profile_sha256': sent,
                 'tool_profile_sha256': _profile(context['profile']), 'output_profile_sha256': sent,
                 'cache_hit': False, 'execution_id': identity, 'call': call,
                 'payload_sha256': fingerprint(packet['model_payload']),
                 'context_response_sha256': context['response_sha256'],
                 'requested_request_sha256': fingerprint(caller),
                 'execution_request_sha256': fingerprint(effective), 'output_sha256': fingerprint(ranking)}
        inspect_decision(caller, {'ranking': ranking, 'trace': trace}, [packet],
                         profiles=profiles, contexts=contexts, samples=samples)
    return {'status': 'VERIFIED', 'captured_packets_checked': expected_count}
