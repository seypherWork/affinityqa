"""Entirely synthetic discovery-contract fixtures, never real provider evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from affinityqa import cinema_discoveries as discovery
from affinityqa.causal_agent import context_from_sample as old_artist_context
from affinityqa.errors import SchemaError


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def synthetic_fixture(favorites=(4,), exclusions=(0,), *, reverse_catalog=False):
    catalog = [{'entity_id': str(UUID(int=i + 1)), 'name': 'Synthetic film ' + str(i),
                'release_year': 1990 + i} for i in range(20)]
    if reverse_catalog:
        catalog.reverse()
    profile = {'entity_id': str(UUID(int=100)), 'name': 'Synthetic music artist', 'type': 'urn:entity:artist'}
    ids = [r['entity_id'] for r in catalog]
    prefs = {'schema_version': 1, 'favorite_entity_ids': [ids[i] for i in favorites],
             'excluded_entity_ids': [ids[i] for i in exclusions]}
    expected = sorted(set(ids) - set(prefs['favorite_entity_ids']))
    params = {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': len(expected),
              'signal.interests.entities': ','.join(sorted([profile['entity_id'], *prefs['favorite_entity_ids']])),
              'filter.results.entities': ','.join(expected)}
    # Emulates a live-boundary record solely for testing pure validation.
    body = {'success': True, 'results': {'entities': [
        {'entity_id': r['entity_id'].upper(), 'name': r['name'], 'type': 'urn:entity',
         'subtype': 'urn:entity:movie', 'properties': {'release_year': r['release_year']},
         'query': {'affinity': 0.95 - i * 0.02}}
        for i, r in enumerate(catalog) if r['entity_id'] not in prefs['favorite_entity_ids']]}}
    sample = {'source': 'SYNTHETIC_TEST_DOUBLE_ONLY', 'request': {'method': 'GET',
              'host': 'https://hackathon.api.qloo.com', 'path': '/v2/insights', 'params': params},
              'status': 200, 'response': body, 'response_sha256': digest(body),
              'attempt': 1, 'live_network_request': True}
    return catalog, profile, prefs, sample


class DiscoveryContextTests(unittest.TestCase):
    def setUp(self):
        for name in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(name, side_effect=AssertionError('Network forbidden in synthetic test'))
            guard.start()
            self.addCleanup(guard.stop)

    def context(self, favorites=(4,), exclusions=(0,), reverse_catalog=False):
        values = synthetic_fixture(favorites, exclusions, reverse_catalog=reverse_catalog)
        catalog, profile, prefs, sample = values
        context = discovery.context_from_sample(profile, catalog, prefs, sample, digest(sample))
        return values, context

    def test_zero_one_five_favorites_exact_discovery_universes(self):
        for f, expected in (((), 20), ((4,), 19), ((1, 2, 3, 4, 5), 15)):
            with self.subTest(f=f):
                (catalog, profile, prefs, sample), context = self.context(f)
                ids = [r['entity_id'] for r in catalog]
                self.assertEqual(discovery.qloo_request(profile, catalog, prefs), sample['request'])
                self.assertEqual(context['schema_version'], 2)
                self.assertEqual(context['tool_name'], 'qloo-film-discovery-context-v1')
                self.assertEqual(len(context['ranked_entities']), expected)
                self.assertEqual(set(context['discovery_entity_ids']), set(ids) - set(prefs['favorite_entity_ids']))
                self.assertFalse(set(prefs['favorite_entity_ids']) & {r['entity_id'] for r in context['ranked_entities']})
                self.assertNotIn('excluded_entity_ids', context)
                self.assertNotIn('preferences_sha256', context)
                self.assertEqual(discovery.validate_context(context, catalog, prefs), context)

    def test_actual_mixed_signal_is_required_and_legacy_full20_is_unchanged(self):
        (catalog, profile, prefs, sample), _ = self.context()
        with self.assertRaises(SchemaError):
            old_artist_context(profile, catalog, sample, digest(sample))
        bad = copy.deepcopy(sample)
        bad['request']['params']['signal.interests.entities'] = profile['entity_id']
        with self.assertRaises(SchemaError):
            discovery.context_from_sample(profile, catalog, prefs, bad, digest(bad))

    def test_rejects_each_missing_extra_seed_duplicate_or_invalid_identity_row(self):
        (catalog, profile, prefs, sample), _ = self.context()
        rows = sample['response']['results']['entities']
        variants = []
        missing = copy.deepcopy(rows); missing.pop(); variants.append(missing)
        duplicate = copy.deepcopy(rows); duplicate[-1] = copy.deepcopy(duplicate[0]); variants.append(duplicate)
        for key, value in [('entity_id', str(UUID(int=300))), ('entity_id', prefs['favorite_entity_ids'][0]),
                           ('name', 'Wrong movie'), ('subtype', 'urn:entity:album'), ('entity_id', 'fixture:invalid')]:
            changed = copy.deepcopy(rows); changed[0][key] = value; variants.append(changed)
        for year in (1999, 1990.0, True, None):
            changed = copy.deepcopy(rows); changed[0]['properties']['release_year'] = year; variants.append(changed)
        for changed in variants:
            bad = copy.deepcopy(sample); bad['response']['results']['entities'] = changed
            bad['response_sha256'] = digest(bad['response'])
            with self.subTest(first=changed[0]), self.assertRaises(SchemaError):
                discovery.context_from_sample(profile, catalog, prefs, bad, digest(bad))

    def test_rejects_boolean_missing_nonfinite_out_of_range_affinities(self):
        (catalog, profile, prefs, sample), _ = self.context()
        for value in (None, True, -0.1, 1.1, '0.5', float('nan'), float('inf')):
            bad = copy.deepcopy(sample); bad['response']['results']['entities'][0]['query']['affinity'] = value
            if isinstance(value, float) and not (-1e10 < value < 1e10):
                bad['response_sha256'] = 'a' * 64
            else:
                bad['response_sha256'] = digest(bad['response'])
            with self.subTest(value=value), self.assertRaises(SchemaError):
                discovery.context_from_sample(profile, catalog, prefs, bad, 'b' * 64)

    def test_exact_http_boundary_and_response_hash_required(self):
        (catalog, profile, prefs, sample), _ = self.context()
        for key, value in [('status', 429), ('status', True), ('attempt', 2), ('attempt', True),
                           ('live_network_request', False), ('response_sha256', '0' * 64)]:
            bad = copy.deepcopy(sample); bad[key] = value
            with self.subTest(key=key), self.assertRaises(SchemaError):
                discovery.context_from_sample(profile, catalog, prefs, bad, digest(bad))
        for key, value in [('host', 'https://api.qloo.com'), ('method', 'POST'), ('path', '/search')]:
            bad = copy.deepcopy(sample); bad['request'][key] = value
            with self.subTest(key=key), self.assertRaises(SchemaError):
                discovery.context_from_sample(profile, catalog, prefs, bad, digest(bad))
        for params in ({'take': 20}, {'take': 19.0}, {'filter.exclude.entities': prefs['excluded_entity_ids'][0]}, {'bias.trends': 'on'}):
            bad = copy.deepcopy(sample); bad['request']['params'].update(params)
            with self.subTest(params=params), self.assertRaises(SchemaError):
                discovery.context_from_sample(profile, catalog, prefs, bad, digest(bad))
        with self.assertRaises(SchemaError):
            discovery.context_from_sample(profile, catalog, prefs, sample, 'not-a-hash')

    def test_closed_context_revalidates_positive_signal_and_canonical_hashes(self):
        (catalog, _, prefs, _), context = self.context()
        for field, value in [('schema_version', True), ('tool_name', 'qloo-movie-context-v1'),
                             ('signal_entity_ids', []), ('favorite_entity_ids', []),
                             ('profile_sha256', '0' * 64), ('signal_sha256', '0' * 64),
                             ('request_sha256', '0' * 64), ('catalog_sha256', '0' * 64),
                             ('discovery_sha256', '0' * 64)]:
            bad = copy.deepcopy(context); bad[field] = value
            bad['context_sha256'] = digest({k: v for k, v in bad.items() if k != 'context_sha256'})
            with self.subTest(field=field), self.assertRaises(SchemaError):
                discovery.validate_context(bad, catalog, prefs)
        bad = {**context, 'excluded_entity_ids': prefs['excluded_entity_ids']}
        with self.assertRaises(SchemaError):
            discovery.validate_context(bad, catalog, prefs)
        bad = copy.deepcopy(context); bad['ranked_entities'][0]['affinity'] = 0.123
        with self.assertRaises(SchemaError):
            discovery.validate_context(bad, catalog, prefs)

    def test_preference_validation_counts_favorites_as_nondeliverable(self):
        catalog, profile, prefs, _ = synthetic_fixture()
        ids = [r['entity_id'] for r in catalog]
        invalid = [None, {}, {**prefs, 'schema_version': True}, {**prefs, 'rating': 5},
                   {**prefs, 'favorite_entity_ids': ids[:6]}, {**prefs, 'favorite_entity_ids': [ids[4], ids[4]]},
                   {**prefs, 'favorite_entity_ids': [ids[0]]}, {**prefs, 'favorite_entity_ids': [str(UUID(int=300))]},
                   {**prefs, 'favorite_entity_ids': [ids[9].upper()]}, {**prefs, 'excluded_entity_ids': [True]},
                   {**prefs, 'excluded_entity_ids': ids[:4] + ids[5:16]}]
        # Last case leaves only four discoveries: legacy 20-minus-X counted five.
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(SchemaError):
                discovery.validate_preferences(value, catalog)
        bad_profile = {**profile, 'entity_id': ids[4]}
        with self.assertRaises(SchemaError):
            discovery.qloo_request(bad_profile, catalog, prefs)

    def test_request_payload_original_indices_known_inputs_and_no_seed_scores(self):
        (catalog, profile, prefs, _), context = self.context((2, 9, 14, 16, 18), (0,), reverse_catalog=True)
        request = discovery.make_request(catalog, profile, context, prefs, 'synthetic-request')
        self.assertEqual(request['schema_version'], 3)
        expected_indices = [i for i in range(20) if i not in (2, 9, 14, 16, 18)]
        self.assertEqual(request['discovery_catalog_indices'], expected_indices)
        schema = discovery.output_schema(request)
        ranks = schema['properties']['ordered_catalog_indices']
        self.assertEqual(len(ranks['required']), 15)
        self.assertTrue(all(field['enum'] == expected_indices for field in ranks['properties'].values()))
        payload = discovery.model_input(request, schema)
        self.assertEqual(len(payload['catalog']), 20)
        self.assertEqual(payload['profile'], profile)
        self.assertEqual(payload['discovery_catalog_indices'], expected_indices)
        self.assertEqual(len(payload['provider_movie_context']), 15)
        self.assertEqual({r['catalog_index'] for r in payload['known_favorite_movies']}, {2, 9, 14, 16, 18})
        self.assertTrue(all('affinity' not in r for r in payload['known_favorite_movies']))
        self.assertFalse(any(k in payload for k in ('ratings', 'ground_truth', 'expected_ranking')))
        payload['catalog'][0]['name'] = 'mutated copy'
        self.assertNotEqual(payload['catalog'][0]['name'], catalog[0]['name'])
        with self.assertRaises(SchemaError):
            discovery.model_input(request, {'type': 'object'})

    def test_request_rejects_context_from_different_positive_preferences_and_rehashed_tampering(self):
        (catalog, profile, prefs, _), context = self.context()
        changed = {**prefs, 'favorite_entity_ids': [catalog[5]['entity_id']]}
        with self.assertRaises(SchemaError):
            discovery.make_request(catalog, profile, context, changed, 'x')
        request = discovery.make_request(catalog, profile, context, prefs, 'x')
        for key, value in [('schema_version', True), ('top_k', True), ('task', 'different'),
                           ('protocol', 'cinema-preferences-v1'), ('signal_sha256', '0' * 64),
                           ('preferences_sha256', '0' * 64), ('intent_sha256', '0' * 64),
                           ('discovery_catalog_indices', list(range(20))), ('eligible_catalog_indices', [])]:
            bad = copy.deepcopy(request); bad[key] = value
            bad['request_id'] = digest({k: v for k, v in bad.items() if k != 'request_id'})
            with self.subTest(key=key), self.assertRaises(SchemaError):
                discovery.validate_request(bad)


if __name__ == '__main__':
    unittest.main()
