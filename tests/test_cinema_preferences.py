"""Synthetic contract checks; excluded IDs are decidable, subjective liking is not."""
import copy
from itertools import combinations
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.causal_agent import profile_hash
from affinityqa.cinema_preferences import (CinemaMovieAgent, CinemaSession, make_request, validate_preferences,
    deliver, baseline, cache_key, CINEMA_PROMPT)
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
import test_causal_agent as causal_fixtures
from test_groq_agent import OpenerFixture, UNIT_SECRET


class CinemaPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.fixture = causal_fixtures.CausalAgentTests()
        self.fixture.setUp()
        self.catalog = self.fixture.catalog
        self.ids = [r['entity_id'] for r in self.catalog]
        self.profile = self.fixture.profiles[0]
        self.context = self.fixture.contexts[profile_hash(self.profile)]
        self.preferences = {'schema_version': 1, 'favorite_entity_ids': [self.ids[10]], 'excluded_entity_ids': [self.ids[0]]}
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network denied in cinema fixture'))
            guard.start()
            self.addCleanup(guard.stop)

    def request(self, preferences=None, nonce='cinema-test'):
        return make_request(self.catalog, self.profile, self.context, preferences or self.preferences, nonce)

    def test_preferences_are_closed_typed_canonical_unique_and_coherent(self):
        invalid = [None, {}, {**self.preferences, 'rating': 5}, {**self.preferences, 'schema_version': True},
            {**self.preferences, 'favorite_entity_ids': self.ids[:6]},
            {**self.preferences, 'excluded_entity_ids': self.ids[:16]},
            {**self.preferences, 'excluded_entity_ids': [self.ids[0], self.ids[0]]},
            {**self.preferences, 'favorite_entity_ids': [self.ids[0]]},
            {**self.preferences, 'excluded_entity_ids': [self.ids[0].upper()]},
            {**self.preferences, 'excluded_entity_ids': ['ffffffff-ffff-4fff-8fff-ffffffffffff']},
            {**self.preferences, 'excluded_entity_ids': [True]}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SchemaError):
                validate_preferences(value, self.catalog)

    def test_set_order_is_canonical_and_changes_bind_request_and_cache(self):
        a = {'schema_version': 1, 'favorite_entity_ids': [self.ids[12], self.ids[10]], 'excluded_entity_ids': self.ids[1:3]}
        b = {'schema_version': 1, 'favorite_entity_ids': list(reversed(a['favorite_entity_ids'])),
             'excluded_entity_ids': list(reversed(a['excluded_entity_ids']))}
        self.assertEqual(self.request(a), self.request(b))
        c = copy.deepcopy(a)
        c['favorite_entity_ids'] = [self.ids[15]]
        self.assertNotEqual(self.request(a)['intent_sha256'], self.request(c)['intent_sha256'])
        self.assertNotEqual(cache_key(self.request(a), {}), cache_key(self.request(c), {}))

    def test_raw_order_is_preserved_and_exclusions_enforced_for_many_sets(self):
        raw = list(self.ids)
        checked = 0
        for count in range(6):
            for indices in combinations(range(8), count):
                prefs = {'schema_version': 1, 'favorite_entity_ids': [], 'excluded_entity_ids': [self.ids[i] for i in indices]}
                delivered = deliver(raw, self.catalog, prefs)
                self.assertEqual(delivered['raw_ranked_entity_ids'], raw)
                self.assertEqual(raw, self.ids)
                self.assertEqual(len(delivered['delivered_entity_ids']), 5)
                self.assertFalse(set(delivered['delivered_entity_ids']) & set(prefs['excluded_entity_ids']))
                self.assertIsNone(delivered['satisfaction_score'])
                checked += 1
        self.assertEqual(checked, 219)

    def test_five_eligible_boundary_delivers_exact_five_without_synthetic_fill(self):
        prefs = {'schema_version': 1, 'favorite_entity_ids': [], 'excluded_entity_ids': self.ids[:15]}
        output = deliver(self.ids, self.catalog, prefs)
        self.assertEqual(output['delivered_entity_ids'], self.ids[15:])
        self.assertTrue(output['selection_changed'])
        for raw in (self.ids[:5], [self.ids[0]]*20, list(range(20))):
            with self.assertRaises(SchemaError):
                deliver(raw, self.catalog, prefs)

    def test_actual_input_contains_preferences_and_distinct_prompt_without_labels(self):
        opener = OpenerFixture()
        engine = CinemaMovieAgent(UNIT_SECRET, _test_opener=opener)
        request = self.request()
        response = engine.rank(request)
        http_payload = opener.calls[0][1]
        data = json.loads(http_payload['messages'][1]['content'])
        self.assertEqual(http_payload['messages'][0]['content'], CINEMA_PROMPT)
        self.assertEqual(data['cinema_preferences']['favorite_catalog_indices'], [10])
        self.assertEqual(data['cinema_preferences']['excluded_catalog_indices'], [0])
        self.assertEqual(data['preferences_sha256'], request['preferences_sha256'])
        self.assertEqual(data['intent_sha256'], request['intent_sha256'])
        self.assertEqual(engine.observations[0]['output_sha256'], fingerprint(response['ranked_entity_ids']))
        self.assertEqual(engine.manifest['max_inference_calls'], 2)
        self.assertFalse(any(key in data for key in ('ratings', 'ground_truth', 'expected_ranking')))

    def test_same_artist_new_favorite_is_a_cache_miss_then_exact_intent_hits(self):
        engine = CinemaMovieAgent(UNIT_SECRET, _test_opener=OpenerFixture())
        session = CinemaSession(engine, causal_fixtures.FakeLedger(), self.fixture.contexts)
        first = session.rank(self.request())
        changed = {**self.preferences, 'favorite_entity_ids': [self.ids[11]]}
        second = session.rank(self.request(changed))
        repeat = session.rank(self.request(changed, 'new-nonce-same-intent'))
        self.assertEqual(engine.calls, 2)
        self.assertFalse(first['trace']['cache_hit'])
        self.assertFalse(second['trace']['cache_hit'])
        self.assertTrue(repeat['trace']['cache_hit'])
        self.assertNotEqual(first['trace']['cache_key_sha256'], second['trace']['cache_key_sha256'])
        self.assertEqual(second['trace']['requested_preferences_sha256'], repeat['trace']['transmitted_preferences_sha256'])
        self.assertEqual(first['trace']['tool_profile_sha256'], second['trace']['tool_profile_sha256'])
        self.assertNotEqual(first['trace']['requested_intent_sha256'], second['trace']['requested_intent_sha256'])

    def test_baseline_uses_same_favorites_and_exclusions_without_changing_qloo(self):
        before = copy.deepcopy(self.context)
        output = baseline(self.context, self.catalog, self.preferences)
        self.assertEqual(output['qloo_raw_ranked_entity_ids'], self.ids)
        self.assertEqual(output['delivery']['delivered_entity_ids'], [self.ids[10], *self.ids[1:5]])
        self.assertEqual(self.context, before)


if __name__ == '__main__':
    unittest.main()
