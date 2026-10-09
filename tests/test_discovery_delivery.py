"""Synthetic rankings; guard success is not a claim about subjective quality."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from affinityqa import cinema_discoveries as discovery
from affinityqa.agents import AgentError
from affinityqa.errors import SchemaError
from test_discovery_context import synthetic_fixture, digest
from test_discovery_agent import rank_slots


class DiscoveryDeliveryTests(unittest.TestCase):
    def fixture(self, favorites=(4,), exclusions=(0,)):
        catalog, profile, prefs, sample = synthetic_fixture(favorites, exclusions)
        context = discovery.context_from_sample(profile, catalog, prefs, sample, digest(sample))
        request = discovery.make_request(catalog, profile, context, prefs, 'synthetic')
        return catalog, profile, prefs, context, request

    def test_model_output_requires_complete_nonseed_original_index_permutation(self):
        for favorites in ((), (4,), (1, 2, 3, 4, 5)):
            catalog, _, _, _, request = self.fixture(favorites)
            indices = [i for i in range(20) if i not in favorites]
            ranking = discovery.validate_model_output(request, {'ordered_catalog_indices': rank_slots(reversed(indices))})
            self.assertEqual(ranking, [catalog[i]['entity_id'] for i in reversed(indices)])
            response = {'schema_version': 1, 'request_id': request['request_id'], 'ranked_entity_ids': ranking}
            self.assertEqual(discovery.validate_response(request, response), ranking)
        _, _, _, _, request = self.fixture()
        indices = [i for i in range(20) if i != 4]
        invalid = [indices[:-1], indices + [4], [indices[0]] * 19,
                   [True, *indices[1:]], [0.0, *indices[1:]], [-1, *indices[1:]],
                   [20, *indices[1:]], [str(i) for i in indices]]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(AgentError):
                discovery.validate_model_output(request, {'ordered_catalog_indices': rank_slots(values)})
        with self.assertRaises(AgentError):
            discovery.validate_model_output(request, {'ordered_catalog_indices': rank_slots(indices), 'reasoning': 'unapproved'})

    def test_common_response_envelope_is_closed_and_checks_full_discovery_set(self):
        catalog, _, prefs, _, request = self.fixture()
        ids = [row['entity_id'] for row in catalog if row['entity_id'] not in prefs['favorite_entity_ids']]
        valid = {'schema_version': 1, 'request_id': request['request_id'], 'ranked_entity_ids': ids}
        bad_values = [{**valid, 'schema_version': True}, {**valid, 'request_id': '0' * 64},
                      {**valid, 'reasoning': 'unapproved'}, {**valid, 'ranked_entity_ids': ids[:5]},
                      {**valid, 'ranked_entity_ids': ids + prefs['favorite_entity_ids']},
                      {**valid, 'ranked_entity_ids': [ids[0]] * 19}]
        for value in bad_values:
            with self.subTest(value=value), self.assertRaises(AgentError):
                discovery.validate_response(request, value)

    def test_stable_guard_excludes_X_never_overlays_F_and_preserves_raw(self):
        catalog, _, prefs, context, _ = self.fixture((4,), (0, 1, 3))
        ids = [r['entity_id'] for r in catalog]
        raw = [v for v in ids if v != ids[4]]
        before = copy.deepcopy(raw)
        output = discovery.deliver(raw, catalog, prefs)
        self.assertEqual(raw, before)
        self.assertEqual(output['raw_ranked_entity_ids'], raw)
        self.assertEqual(output['delivered_entity_ids'], [ids[i] for i in (2, 5, 6, 7, 8)])
        self.assertFalse(set(output['delivered_entity_ids']) & set(prefs['favorite_entity_ids'] + prefs['excluded_entity_ids']))
        self.assertEqual(output['raw_output_sha256'], digest(raw))
        self.assertEqual(output['delivered_output_sha256'], digest(output['delivered_entity_ids']))
        self.assertEqual(output['eligible_movies'], 16)
        self.assertIsNone(output['satisfaction_score'])
        baseline = discovery.baseline(context, catalog, prefs)
        self.assertEqual(baseline['qloo_raw_ranked_entity_ids'], raw)
        self.assertEqual(baseline['delivery']['delivered_entity_ids'], output['delivered_entity_ids'])

    def test_exactly_five_eligible_and_missing_raw_rejected_without_fill(self):
        catalog, _, prefs, _, _ = self.fixture((15, 16, 17, 18, 19), tuple(range(10)))
        ids = [r['entity_id'] for r in catalog]
        raw = ids[:15]
        self.assertEqual(discovery.deliver(raw, catalog, prefs)['delivered_entity_ids'], ids[10:15])
        for invalid in (raw[:-1], raw + [ids[15]], [raw[0]] * 15, list(range(15))):
            with self.assertRaises(SchemaError):
                discovery.deliver(invalid, catalog, prefs)

    def test_F_changes_tool_cache_X_only_changes_full_intent_model_and_delivery(self):
        catalog, profile, prefs, context, request = self.fixture()
        key = discovery.qloo_cache_key(profile, catalog, prefs)
        changed_x = {**prefs, 'excluded_entity_ids': [catalog[1]['entity_id']]}
        x_request = discovery.make_request(catalog, profile, context, changed_x, 'different-nonce')
        self.assertEqual(key, discovery.qloo_cache_key(profile, catalog, changed_x))
        self.assertEqual(request['signal_sha256'], x_request['signal_sha256'])
        self.assertNotEqual(request['preferences_sha256'], x_request['preferences_sha256'])
        self.assertNotEqual(request['intent_sha256'], x_request['intent_sha256'])
        self.assertNotEqual(discovery.cache_key(request, {'model': 'synthetic'}),
                            discovery.cache_key(x_request, {'model': 'synthetic'}))
        raw = [r['entity_id'] for r in catalog if r['entity_id'] not in prefs['favorite_entity_ids']]
        self.assertNotEqual(discovery.deliver(raw, catalog, prefs)['delivery_intent_sha256'],
                            discovery.deliver(raw, catalog, changed_x)['delivery_intent_sha256'])
        changed_f = {**prefs, 'favorite_entity_ids': [catalog[5]['entity_id']]}
        self.assertNotEqual(key, discovery.qloo_cache_key(profile, catalog, changed_f))
        self.assertNotEqual(discovery.signal_hash(profile, prefs, catalog), discovery.signal_hash(profile, changed_f, catalog))
        _, _, _, _, f_request = self.fixture((5,))
        self.assertNotEqual(discovery.cache_key(request, {'model': 'synthetic'}), discovery.cache_key(f_request, {'model': 'synthetic'}))

    def test_nonce_and_set_order_do_not_create_semantically_different_cache_keys(self):
        catalog, profile, prefs, context, request = self.fixture((3, 4), (0, 1))
        reordered = {**prefs, 'favorite_entity_ids': list(reversed(prefs['favorite_entity_ids'])),
                     'excluded_entity_ids': list(reversed(prefs['excluded_entity_ids']))}
        second = discovery.make_request(catalog, profile, context, reordered, 'nonce2')
        self.assertNotEqual(request['request_id'], second['request_id'])
        self.assertEqual(request['intent_sha256'], second['intent_sha256'])
        self.assertEqual(discovery.cache_key(request, {}), discovery.cache_key(second, {}))
        self.assertNotEqual(discovery.cache_key(request, {'model': 'one'}), discovery.cache_key(request, {'model': 'two'}))
        broken_context = copy.deepcopy(context); broken_context['ranked_entities'].reverse()
        broken_context['context_sha256'] = digest({k: v for k, v in broken_context.items() if k != 'context_sha256'})
        changed_request = discovery.make_request(catalog, profile, broken_context, prefs, 'nonce3')
        self.assertNotEqual(discovery.cache_key(request, {}), discovery.cache_key(changed_request, {}))


if __name__ == '__main__':
    unittest.main()
