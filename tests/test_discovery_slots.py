"""Required rank slots preserve complete raw permutations, not partial fills."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.agents import AgentError
from affinityqa.cinema_discoveries import output_schema, validate_model_output, model_input, make_request, qloo_cache_key
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent
from affinityqa.cinema_discovery_session import DiscoverySession
from affinityqa.cinema_discovery_verify import verify_packet
from affinityqa.evidence import fingerprint
from affinityqa.errors import SchemaError
from affinityqa.groq_agent import MODEL, MAX_REQUEST_BYTES
from test_causal_agent import FakeLedger
from test_discovery_agent import fixture_request, Response, Opener, TEST_SECRET
from test_discovery_session import sample_for


def slots(values):
    return {f'rank_{position:02d}': value for position, value in enumerate(values, 1)}


class SlotsOpener:
    def __init__(self, mutate=None):
        self.calls = []
        self.mutate = mutate

    def open(self, request, timeout):
        payload = json.loads(request.data)
        self.calls.append(payload)
        data = json.loads(payload['messages'][1]['content'])
        indices = [row['catalog_index'] for row in data['provider_movie_context']]
        output = {'ordered_catalog_indices': dict(reversed(list(slots(indices).items())))}
        if self.mutate:
            self.mutate(output)
        body = {'id': 'synthetic-slot-' + str(len(self.calls)), 'object': 'chat.completion',
            'created': 1791569900, 'model': MODEL, 'system_fingerprint': 'synthetic-provider-only',
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {
                'role': 'assistant', 'content': json.dumps(output)}}],
            'usage': {'prompt_tokens': 1600, 'completion_tokens': 220, 'total_tokens': 1820,
                'completion_tokens_details': {'reasoning_tokens': 20}}}
        return Response(json.dumps(body).encode())


class DiscoverySlotContractTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('No network or DNS in slot contract tests'))
            guard.start()
            self.addCleanup(guard.stop)

    def test_explicit_v2_schema_requires_every_slot_for_zero_one_five_favorites(self):
        for favorite_count in (0, 1, 5):
            request = fixture_request(favorite_count)
            self.assertEqual(request['protocol'], 'cinema-confirmed-discovery-v2')
            schema = output_schema(request)
            inner = schema['properties']['ordered_catalog_indices']
            names = [f'rank_{i:02d}' for i in range(1, 21-favorite_count)]
            self.assertEqual(inner['type'], 'object')
            self.assertEqual(set(inner['properties']), set(names))
            self.assertEqual(inner['required'], names)
            self.assertFalse(inner['additionalProperties'])
            self.assertNotIn('minItems', json.dumps(schema))
            self.assertNotIn('maxItems', json.dumps(schema))
            for field in inner['properties'].values():
                self.assertEqual(field, {'type': 'integer', 'enum': list(range(favorite_count, 20))})
            self.assertEqual(model_input(request)['output_schema'], schema)

    def test_object_order_is_not_rank_order_and_raw_keeps_excluded_candidate(self):
        for favorite_count in (0, 1, 5):
            request = fixture_request(favorite_count)
            indices = list(range(19, favorite_count-1, -1))
            output = {'ordered_catalog_indices': dict(reversed(list(slots(indices).items())))}
            expected = [request['catalog'][i]['entity_id'] for i in indices]
            self.assertEqual(validate_model_output(request, output), expected)
            self.assertIn(request['preferences']['excluded_entity_ids'][0], expected)

    def test_missing_extra_bool_duplicate_seed_unknown_and_legacy_array_rejected(self):
        request = fixture_request(1)
        valid = slots(list(range(1, 20)))
        bad = []
        for mutate in (
            lambda value: value.pop('rank_19'),
            lambda value: value.update(rank_20=19),
            lambda value: value.update(rank_01=True),
            lambda value: value.update(rank_01=2),
            lambda value: value.update(rank_01=0),
            lambda value: value.update(rank_01=20),
            lambda value: value.update(rank_01='1'),
            lambda value: value.update(rank_1=value.pop('rank_01')),
        ):
            value = copy.deepcopy(valid)
            mutate(value)
            bad.append(value)
        bad.extend((list(range(1, 20)), None))
        for value in bad:
            with self.subTest(value=value), self.assertRaises(AgentError):
                validate_model_output(request, {'ordered_catalog_indices': value})
        with self.assertRaises(AgentError):
            validate_model_output(request, {'ordered_catalog_indices': valid, 'reasoning': 'must not pass'})

    def test_transport_records_actual_slots_and_independent_auditor_normalizes_them(self):
        request = fixture_request()
        opener, ledger = SlotsOpener(), FakeLedger()
        engine = DiscoveryMovieAgent(TEST_SECRET, max_calls=1, _test_opener=opener)
        digest = request['tool_context']['sample_sha256']
        session = DiscoverySession(request['catalog'], engine, ledger,
            {qloo_cache_key(request['profile'], request['catalog'], request['preferences']): request['tool_context']},
            {digest: sample_for(request)})
        first = session.rank(request)
        packet = ledger.files['discovery-execution-001.json']
        envelope = packet['observation']['provider_envelope']
        self.assertEqual(envelope['schema_version'], 3)
        raw = envelope['choice']['ordered_catalog_indices']
        self.assertIsInstance(raw, dict)
        self.assertEqual(list(raw), list(reversed([f'rank_{i:02d}' for i in range(1, 20)])))
        checked = verify_packet(packet, engine.manifest, engine.source, sample_for(request), digest)
        self.assertEqual(first['ranking'], checked['raw_ranking'])
        self.assertEqual(len(first['ranking']), 19)
        self.assertEqual(len(first['delivery']['delivered_entity_ids']), 5)
        reused = make_request(request['catalog'], request['profile'], request['tool_context'], request['preferences'], 'new-nonce')
        self.assertTrue(session.rank(reused)['trace']['cache_hit'])
        self.assertEqual(len(opener.calls), 1)
        self.assertFalse(checked['quality_validated'])
        # Reseal a fabricated partial envelope: the independent permutation check
        # must still reject it, even if a caller updates its self hash.
        damaged = copy.deepcopy(packet)
        damaged['observation']['provider_envelope']['choice']['ordered_catalog_indices'].pop('rank_19')
        damaged['observation']['provider_envelope_sha256'] = fingerprint(damaged['observation']['provider_envelope'])
        with self.assertRaises(SchemaError):
            verify_packet(damaged, engine.manifest, engine.source, sample_for(request), digest)

    def test_invalid_provider_slot_output_consumes_one_attempt_without_fallback(self):
        for mutate in (lambda output: output['ordered_catalog_indices'].pop('rank_19'),
                       lambda output: output.update(ordered_catalog_indices=list(range(1, 20)))):
            opener = SlotsOpener(mutate)
            engine = DiscoveryMovieAgent(TEST_SECRET, max_calls=1, _test_opener=opener)
            with self.assertRaises(AgentError):
                engine.rank(fixture_request())
            self.assertEqual(engine.calls, 1)
            self.assertEqual(len(opener.calls), 1)
            self.assertEqual(engine.observations, [])

    def test_v1_tag_cannot_be_reinterpreted_under_v2(self):
        request = fixture_request()
        damaged = copy.deepcopy(request)
        damaged['protocol'] = 'cinema-confirmed-discovery-v1'
        damaged['request_id'] = fingerprint({k:v for k,v in damaged.items() if k!='request_id'})
        engine = DiscoveryMovieAgent(TEST_SECRET, max_calls=1, _test_opener=SlotsOpener())
        with self.assertRaises(AgentError):
            engine.rank(damaged)
        self.assertEqual(engine.calls, 0)

    def test_repeated_raw_json_slot_key_is_rejected_after_one_attempt(self):
        def damage(body):
            message = body['choices'][0]['message']
            self.assertIn('"rank_01": 19', message['content'])
            message['content'] = message['content'].replace('"rank_01": 19', '"rank_01": 19, "rank_01": 19')
        opener = Opener(mutation=damage)
        engine = DiscoveryMovieAgent(TEST_SECRET, max_calls=1, _test_opener=opener)
        with self.assertRaises(AgentError):
            engine.rank(fixture_request())
        self.assertEqual(engine.calls, 1)
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(engine.observations, [])

    def test_maximum_slot_payload_keeps_existing_transport_and_token_caps(self):
        opener = SlotsOpener()
        engine = DiscoveryMovieAgent(TEST_SECRET, max_calls=1, _test_opener=opener)
        engine.rank(fixture_request(0))
        payload = opener.calls[0]
        self.assertLessEqual(len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')), MAX_REQUEST_BYTES)
        self.assertEqual(payload['max_completion_tokens'], 1024)
        self.assertEqual(engine.manifest['max_inference_calls'], 1)
        self.assertFalse(engine.manifest['automatic_retry'])
        self.assertFalse(engine.manifest['automatic_model_or_schema_fallback'])


if __name__ == '__main__':
    unittest.main()
