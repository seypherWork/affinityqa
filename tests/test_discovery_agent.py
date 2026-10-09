"""Denied-network synthetic transport tests; no service or human validation."""
from email.message import Message
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src')]
from affinityqa.agents import AgentError
from affinityqa.cinema_discoveries import context_from_sample, make_request, deliver
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent, model_manifest
from affinityqa.evidence import fingerprint
from affinityqa.groq_agent import GroqToolContextMovieAgent, MODEL, ENDPOINT

TEST_SECRET = 'synthetic-discovery-private-credential-only'
OTHER_SECRET = 'synthetic-discovery-other-credential-only'


def rank_slots(indices):
    return {f'rank_{position:02d}': index for position, index in enumerate(indices, 1)}


def fixture_request(favorite_count=1):
    catalog = [{'entity_id': f'aaaaaaaa-0000-4000-8000-{i:012d}',
                'name': f'Synthetic discovery movie {i}', 'release_year': 2000 + i}
               for i in range(20)]
    profile = {'entity_id': 'bbbbbbbb-0000-4000-8000-000000000001',
               'name': 'Synthetic discovery artist', 'type': 'urn:entity:artist'}
    prefs = {'schema_version': 1,
             'favorite_entity_ids': [r['entity_id'] for r in catalog[:favorite_count]],
             'excluded_entity_ids': [catalog[19]['entity_id']]}
    discovery = catalog[favorite_count:]
    signal = sorted([profile['entity_id']] + prefs['favorite_entity_ids'])
    request = {'method': 'GET', 'host': 'https://hackathon.api.qloo.com', 'path': '/v2/insights',
               'params': {'filter.type': 'urn:entity:movie', 'bias.trends': 'off',
                          'take': len(discovery), 'signal.interests.entities': ','.join(signal),
                          'filter.results.entities': ','.join(sorted(r['entity_id'] for r in discovery))}}
    body = {'success': True, 'results': {'entities': [
        {'entity_id': r['entity_id'], 'name': r['name'], 'types': ['urn:entity:movie'],
         'properties': {'release_year': r['release_year']}, 'query': {'affinity': (i + 1) / 20}}
        for i, r in enumerate(reversed(discovery))]}}
    sample = {'fixture_provenance': 'SYNTHETIC_UNIT_ONLY_NOT_LIVE_EVIDENCE',
              'request': request, 'status': 200, 'attempt': 1, 'live_network_request': True,
              'response': body, 'response_sha256': fingerprint(body)}
    context = context_from_sample(profile, catalog, prefs, sample, fingerprint(sample))
    return make_request(catalog, profile, context, prefs, 'synthetic-discovery-unit')


class Response(io.BytesIO):
    def __init__(self, raw):
        super().__init__(raw)
        self.status = 200
        self.headers = Message()
        self.headers['Content-Type'] = 'application/json'


class Opener:
    def __init__(self, *, mutation=None, failure=None):
        self.calls = []
        self.mutation, self.failure = mutation, failure

    def open(self, request, timeout):
        payload = json.loads(request.data)
        self.calls.append((request, payload, timeout))
        if self.failure is not None:
            raise self.failure
        data = json.loads(payload['messages'][1]['content'])
        indices = [r['catalog_index'] for r in data['provider_movie_context']]
        body = {'id': 'synthetic-discovery-' + str(len(self.calls)), 'object': 'chat.completion',
                'created': 1791560410, 'model': MODEL, 'system_fingerprint': 'synthetic-provider-revision',
                'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {
                    'role': 'assistant', 'content': json.dumps({'ordered_catalog_indices': rank_slots(indices)})}}],
                'usage': {'prompt_tokens': 1200, 'completion_tokens': 150, 'total_tokens': 1350,
                          'completion_tokens_details': {'reasoning_tokens': 40}}}
        if self.mutation:
            self.mutation(body)
        return Response(json.dumps(body).encode())


class DiscoveryAgentTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network and DNS denied for synthetic tests'))
            guard.start()
            self.addCleanup(guard.stop)

    def agent(self, **kwargs):
        opener = kwargs.pop('opener', None) or Opener()
        return DiscoveryMovieAgent(TEST_SECRET, _test_opener=opener, **kwargs), opener

    def test_zero_one_five_known_favorites_have_exact_dynamic_schema_and_output(self):
        for favorites in (0, 1, 5):
            with self.subTest(favorites=favorites):
                request = fixture_request(favorites)
                engine, opener = self.agent(max_calls=1)
                self.assertEqual(engine.calls, 0)
                self.assertEqual(opener.calls, [])
                response = engine.rank(request)
                expected = [r['entity_id'] for r in reversed(request['catalog'][favorites:])]
                self.assertEqual(response['ranked_entity_ids'], expected)
                self.assertEqual(len(response['ranked_entity_ids']), 20 - favorites)
                transport, payload, timeout = opener.calls[0]
                self.assertEqual(transport.full_url, ENDPOINT)
                self.assertEqual(transport.method, 'POST')
                self.assertEqual(timeout, 120)
                schema = payload['response_format']['json_schema']['schema']['properties']['ordered_catalog_indices']
                self.assertEqual(schema['type'], 'object')
                self.assertEqual(len(schema['required']), 20 - favorites)
                self.assertEqual(set(schema['required']), set(schema['properties']))
                self.assertFalse(schema['additionalProperties'])
                self.assertTrue(all(set(field['enum']) == set(range(favorites, 20))
                                    for field in schema['properties'].values()))
                self.assertEqual(engine.observations[0]['raw_discovery_count'], 20 - favorites)
                self.assertEqual(engine.observations[0]['provider_envelope']['schema_version'], 3)
                self.assertEqual(engine.observations[0]['input_sha256'], fingerprint(engine.last_input))
                self.assertEqual(engine.observations[0]['output_sha256'], fingerprint(expected))
                self.assertFalse(engine.observations[0]['model_revision_attested'])
                delivery = deliver(expected, request['catalog'], request['preferences'])
                self.assertEqual(delivery['delivered_entity_ids'], expected[1:6])
                self.assertNotIn(TEST_SECRET, json.dumps(engine.observations) + json.dumps(engine.last_input))

    def test_legacy_twenty_contract_does_not_accept_new_request(self):
        opener = Opener()
        engine = GroqToolContextMovieAgent(TEST_SECRET, _test_opener=opener)
        with self.assertRaises(AgentError):
            engine.rank(fixture_request())
        self.assertEqual(engine.calls, 0)
        self.assertEqual(opener.calls, [])

    def test_known_favorite_partial_duplicate_bool_or_unknown_index_rejected(self):
        bad_outputs = ([0] + list(range(1, 19)), list(range(1, 19)),
                       [1] + list(range(1, 19)), [True] + list(range(2, 20)),
                       list(range(1, 19)) + [20])
        for indices in bad_outputs:
            def mutation(body):
                body['choices'][0]['message']['content'] = json.dumps({'ordered_catalog_indices': rank_slots(indices)})
            with self.subTest(indices=indices):
                engine, opener = self.agent(opener=Opener(mutation=mutation))
                with self.assertRaises(AgentError):
                    engine.rank(fixture_request())
                self.assertEqual(engine.calls, 1)
                self.assertEqual(len(opener.calls), 1)
                self.assertEqual(engine.observations, [])

    def test_malformed_or_incomplete_envelopes_are_not_recorded_as_success(self):
        mutations = [
            lambda b: b.update(model='other-model'),
            lambda b: b.update(created=True),
            lambda b: b['choices'][0].update(finish_reason='length'),
            lambda b: b['choices'][0]['message'].update(reasoning='private reasoning'),
            lambda b: b['choices'][0]['message'].update(tool_calls=[{}]),
            lambda b: b['usage'].update(total_tokens=1351),
            lambda b: b['usage'].update(prompt_tokens=9000),
            lambda b: b.update(system_fingerprint=123),
            lambda b: b.update(secret_echo=OTHER_SECRET),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                engine, opener = self.agent(opener=Opener(mutation=mutation), forbidden_secrets=(OTHER_SECRET,))
                with self.assertRaises(AgentError):
                    engine.rank(fixture_request())
                self.assertEqual(engine.calls, 1)
                self.assertEqual(len(opener.calls), 1)
                self.assertEqual(engine.observations, [])

    def test_frozen_contract_mutation_and_bad_request_rejected_before_transport(self):
        for damage in ('manifest', 'prompt', 'request', 'model', 'timeout', 'budget', 'counter'):
            with self.subTest(damage=damage):
                engine, opener = self.agent()
                request = fixture_request()
                if damage == 'manifest':
                    engine.manifest['options']['temperature'] = 0.5
                elif damage == 'prompt':
                    engine.system_prompt += 'changed'
                elif damage == 'request':
                    request['preferences']['favorite_entity_ids'] = []
                elif damage == 'model':
                    engine.model = 'other-model'
                elif damage == 'timeout':
                    engine.timeout = 300
                elif damage == 'budget':
                    engine.max_calls = 99
                else:
                    engine.calls = True
                with self.assertRaises(AgentError):
                    engine.rank(request)
                if damage != 'counter':
                    self.assertEqual(engine.calls, 0)
                self.assertEqual(opener.calls, [])

    def test_one_attempt_budget_and_429_no_retry(self):
        engine, opener = self.agent(max_calls=1)
        engine.rank(fixture_request())
        with self.assertRaises(AgentError):
            engine.rank(fixture_request())
        self.assertEqual(len(opener.calls), 1)
        failure = HTTPError(ENDPOINT, 429, 'synthetic quota test', {}, None)
        engine, opener = self.agent(max_calls=1, opener=Opener(failure=failure))
        with self.assertRaisesRegex(AgentError, 'HTTP429'):
            engine.rank(fixture_request())
        self.assertEqual(engine.calls, 1)
        self.assertEqual(engine.observations, [])
        with self.assertRaises(AgentError):
            engine.rank(fixture_request())
        self.assertEqual(len(opener.calls), 1)

    def test_manifest_has_separate_contract_and_no_immutable_weights_claim(self):
        value = model_manifest('test-double-only')
        self.assertEqual(value['response_contract'], 'groq-strict-discovery-rank-slots-v2-redacted-envelope')
        self.assertFalse(value['immutable_model_revision_attested'])
        self.assertIsNone(value['model_weights_sha256'])
        self.assertFalse(value['automatic_retry'])
        self.assertFalse(value['automatic_model_or_schema_fallback'])

    def test_pure_manifest_rejects_invalid_timeout_and_budget(self):
        for timeout in (True, 0, 121, float('nan'), '120'):
            with self.assertRaises(AgentError):
                model_manifest('test-double-only', timeout=timeout)
        for max_calls in (True, 0, 40, '2'):
            with self.assertRaises(AgentError):
                model_manifest('test-double-only', max_calls=max_calls)

    def test_repeated_completion_identity_consumes_attempt_without_second_success(self):
        opener = Opener(mutation=lambda body: body.update(id='synthetic-replayed-completion'))
        engine, opener = self.agent(max_calls=2, opener=opener)
        engine.rank(fixture_request())
        with self.assertRaisesRegex(AgentError, 'completion identity'):
            engine.rank(fixture_request(5))
        self.assertEqual(engine.calls, 2)
        self.assertEqual(len(opener.calls), 2)
        self.assertEqual(len(engine.observations), 1)
        self.assertEqual(engine.observations[0]['completion_id'], 'synthetic-replayed-completion')


if __name__ == '__main__':
    unittest.main()
