"""Pure-contract tests using clearly synthetic candidate metadata and affinities."""
import copy
import json
from pathlib import Path
import sys
import unittest
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
from affinityqa.open_movie_discovery import (MODEL, SOURCE, PROMPT, validate_request, movie_identity,
    movie_candidates, select_movie, qloo_request, context_from_sample, validate_context, make_decision,
    validate_decision, output_schema, model_input, validate_output, result_for, cache_key)
from affinityqa.open_movie_discovery_agent import model_manifest, OpenMovieAgent
from test_open_movie_discovery_capture import (request_fixture, movie_row, MovieTransport, ModelOpener,
    TokenEstimator, UNIT_SECRET, QLOO_SECRET, SEED_ID)


SEED = {'entity_id': SEED_ID, 'name': 'Synthetic seed', 'release_year': 2000, 'type': 'urn:entity:movie'}


def sample_fixture(count=20):
    body = MovieTransport(count=count).send('/v2/insights', {}) .body
    return {'source': 'test-double-only', 'request': qloo_request(SEED), 'status': 200, 'response': body,
            'response_sha256': fingerprint(body), 'response_headers': {}, 'elapsed_ms': 1.25, 'attempt': 1,
            'live_network_request': False}


def context_fixture(count=20):return context_from_sample(SEED, sample_fixture(count), 'a'*64)


def output_fixture(decision):
    indices = list(reversed(range(len(decision['context']['candidate_catalog']))))
    eligible = [i for i in indices if i in decision['eligible_catalog_indices']][:5]
    return {'ordered_catalog_indices': {'ranking': indices, 'reasons': [
        {'catalog_index': i, 'text': f'La película sintética {i} podría encajar como interpretación personal de la semilla, sin garantía.'}
        for i in eligible]}}


class OpenMovieContractTests(unittest.TestCase):
    def decision(self, count=20, **kwargs):return make_decision(request_fixture(**kwargs), context_fixture(count), 'synthetic-case')

    def test_request_normalizes_optional_fields_and_fixes_owner_model(self):
        self.assertEqual(validate_request({'schema_version': 8, 'movie_query': '  Film   2000 ', 'model': MODEL}), request_fixture(movie_query='Film 2000'))
        request = request_fixture(excluded_entity_ids=[str(UUID(int=2)), str(UUID(int=1))])
        self.assertEqual(validate_request(request)['excluded_entity_ids'], sorted(request['excluded_entity_ids']))

    def test_request_rejects_unknown_fields_boolean_schema_and_other_model(self):
        for change in ({'schema_version': True}, {'artists': {'A': 'bad'}}, {'model': {'provider': 'other', 'name': 'paid'}}, {'catalog': []}):
            with self.subTest(change=change), self.assertRaises(SchemaError):validate_request(request_fixture(**change))

    def test_request_bounds_no_silent_truncation(self):
        for change in ({'movie_query': ''}, {'movie_query': 'x'*201}, {'intent_text': 'x'*601}, {'intent_text': '\n'},
                {'excluded_entity_ids': ['invalid']}, {'excluded_entity_ids': [str(UUID(int=1))]*2},
                {'excluded_entity_ids': [str(UUID(int=i)) for i in range(16)]}):
            with self.subTest(change=change), self.assertRaises(SchemaError):validate_request(request_fixture(**change))

    def test_identity_never_guesses_missing_or_malformed_year_or_category(self):
        for change in ({'release_year': None}, {'release_year': 2000.0}, {'release_year': True},
                {'release_year': 1800}, {'name': ''}, {'type': 'urn:entity:album'}, {'entity_id': 'madeup'}):
            with self.subTest(change=change), self.assertRaises(SchemaError):movie_identity({**SEED, **change})

    def test_search_retains_ambiguity_as_explicit_choices_not_auto_resolution(self):
        other = movie_row(10001, seed=True); other['entity_id'] = str(UUID(int=10001)); other['properties']['release_year'] = 2001
        choices = movie_candidates({'results': [movie_row(0, seed=True), other]})
        self.assertEqual(len(choices), 2)
        receipt = {'verification_status': 'VERIFIED_IDENTITY_SEARCH', 'status': 'AWAITING_IDENTITY_CONFIRMATION', 'movie_candidates': choices}
        self.assertEqual(select_movie(receipt, other['entity_id'])['release_year'], 2001)
        with self.assertRaises(SchemaError):select_movie(receipt, None)

    def test_context_accepts_only_actual_bounded5to20_and_preserves_provider_order(self):
        for n in (5, 7, 20):
            with self.subTest(n=n):
                value = context_fixture(n); self.assertEqual(len(value['candidate_catalog']), n)
                self.assertEqual(value['raw_provider_ranking'], [str(UUID(int=i)) for i in range(1, n+1)])
                self.assertNotIn(SEED_ID, value['raw_provider_ranking'])
        for n in (0, 4, 21):
            with self.subTest(n=n), self.assertRaises(SchemaError):context_fixture(n)

    def test_query_is_open_seed_only_never_old_catalog_or_optional_intent(self):
        query = qloo_request(SEED)
        self.assertEqual(query['params'], {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': 20,
            'signal.interests.entities': SEED_ID, 'filter.exclude.entities': SEED_ID})
        sample = sample_fixture(); sample['request']['params']['filter.results.entities'] = str(UUID(int=1))
        with self.assertRaises(SchemaError):context_from_sample(SEED, sample, 'a'*64)

    def test_invalid_affinities_types_years_ids_and_duplicate_aliases_rejected(self):
        mutations = [lambda r:r['query'].update(affinity=float('nan')), lambda r:r['query'].update(affinity=True),
            lambda r:r['query'].update(affinity=1.1), lambda r:r.update(types=['urn:entity:artist']),
            lambda r:r['properties'].update(release_year=None), lambda r:r.update(entity_id='fabricated'),
            lambda r:r.update(entity_id=SEED_ID), lambda r:r.update(name='Synthetic seed', properties={'release_year': 2000})]
        for mutation in mutations:
            sample = sample_fixture(); mutation(sample['response']['results']['entities'][0])
            if all(not (isinstance(v,float) and v!=v) for v in sample['response']['results']['entities'][0]['query'].values()):sample['response_sha256'] = fingerprint(sample['response'])
            with self.subTest(mutation=mutation), self.assertRaises(SchemaError):context_from_sample(SEED, sample, 'a'*64)
        sample = sample_fixture(); sample['response']['results']['entities'][1] = copy.deepcopy(sample['response']['results']['entities'][0])
        sample['response_sha256'] = fingerprint(sample['response'])
        with self.assertRaises(SchemaError):context_from_sample(SEED, sample, 'a'*64)

    def test_context_hash_request_source_and_permutation_are_bound(self):
        changes = [('context_sha256', '0'*64), ('catalog_sha256', '0'*64), ('seed_sha256', '0'*64),
                   ('request_sha256', '0'*64), ('source', 'unrecorded'), ('raw_provider_ranking', [str(UUID(int=1))]*20)]
        for name, value in changes:
            context = context_fixture(); context[name] = value
            with self.subTest(name=name), self.assertRaises(SchemaError):validate_context(context)

    def test_complete_permutation_uses_original_zero_based_indices_and_hard_exclusions(self):
        excluded = [str(UUID(int=i)) for i in (20, 19, 18)]
        decision = self.decision(excluded_entity_ids=excluded); output = output_fixture(decision)
        checked = validate_output(decision, output); result = result_for(decision, output)
        self.assertEqual(len(checked['ranking']), 20)
        self.assertEqual(result['delivered'], [str(UUID(int=i)) for i in (17, 16, 15, 14, 13)])
        self.assertEqual(result['baseline_delivered'], [str(UUID(int=i)) for i in (1, 2, 3, 4, 5)])
        self.assertEqual([r['catalog_index'] for r in result['reasons']], [16,15,14,13,12])
        self.assertTrue(all(r['kind'] == 'MODEL_INTERPRETATION' and r['verification'] == 'NOT_FACT_CHECKED' for r in result['reasons']))

    def test_missing_duplicate_boolean_and_invented_model_positions_rejected(self):
        for order in (list(range(19)), [0]*20, list(range(19))+[True], list(range(19))+[20], list(range(19))+['19']):
            decision = self.decision(); output = output_fixture(decision); output['ordered_catalog_indices']['ranking'] = order
            with self.subTest(order=order), self.assertRaises(SchemaError):validate_output(decision, output)

    def test_free_reasons_are_bounded_canonical_and_exact_delivered_references(self):
        for mutation in (lambda b:b['reasons'][0].update(text='too short'), lambda b:b['reasons'][0].update(text='x'*241),
                lambda b:b['reasons'][0].update(text='x'*45+'\n'), lambda b:b['reasons'][0].update(catalog_index=0),
                lambda b:b['reasons'][0].update(catalog_index=True), lambda b:b['reasons'][0].update(percent=100)):
            decision = self.decision(); output = output_fixture(decision); mutation(output['ordered_catalog_indices'])
            with self.subTest(mutation=mutation), self.assertRaises(SchemaError):validate_output(decision, output)

    def test_decision_intent_key_changes_do_not_claim_qloo_saw_text(self):
        context = context_fixture(); manifest = model_manifest('test-double-only')
        original = make_decision(request_fixture(), context, 'one')
        other_nonce = make_decision(request_fixture(), context, 'two')
        text = make_decision(request_fixture(intent_text='Humor absurdo y terror como sugerencia.'), context, 'one')
        excluded = make_decision(request_fixture(excluded_entity_ids=[str(UUID(int=20))]), context, 'one')
        self.assertEqual(cache_key(original, manifest), cache_key(other_nonce, manifest))
        self.assertNotEqual(original['request_id'], other_nonce['request_id'])
        self.assertEqual(original['provider_intent_sha256'], text['provider_intent_sha256'])
        self.assertNotEqual(cache_key(original, manifest), cache_key(text, manifest))
        self.assertNotEqual(cache_key(original, manifest), cache_key(excluded, manifest))
        self.assertFalse(result_for(text, output_fixture(text))['information_policy']['same_explicit_information'])
        self.assertFalse(result_for(original, output_fixture(original))['information_policy']['same_total_information_attested'])

    def test_model_payload_discloses_knowledge_and_has_only_actual_original_indices(self):
        decision = self.decision(count=7); data = model_input(decision)
        self.assertEqual([r['index'] for r in data['catalog']], list(range(7)))
        self.assertIn('NOT_FACT_CHECKED', data['reason_notice']); self.assertIn('cinematic knowledge', PROMPT)
        schema = output_schema(decision)['properties']['ordered_catalog_indices']['properties']
        self.assertEqual(schema['ranking']['minItems'], 7)
        self.assertEqual(schema['reasons']['items']['properties']['text'], {'type':'string','minLength':40,'maxLength':240})

    def test_mutated_decision_rejected_before_provider(self):
        decision = self.decision(); decision['eligible_catalog_indices'] = []
        opener = ModelOpener(); engine = OpenMovieAgent(UNIT_SECRET, _test_opener=opener, token_estimator=TokenEstimator())
        with self.assertRaises(SchemaError):engine.rank(decision)
        self.assertEqual((engine.calls, opener.calls), (0, []))

    def test_private_credentials_in_optional_text_rejected_before_send(self):
        opener = ModelOpener(); engine = OpenMovieAgent(UNIT_SECRET, _test_opener=opener, forbidden_secrets=(QLOO_SECRET,), token_estimator=TokenEstimator())
        with self.assertRaises(Exception):engine.rank(self.decision(intent_text='No enviar '+QLOO_SECRET))
        self.assertEqual((engine.calls, opener.calls), (0, []))

    def test_too_large_token_reservation_stops_before_send(self):
        class LargeEstimator:
            def estimate(self, encoded):return {'tokens': 8001, 'input_tokens': 6977, 'output_tokens':1024}
        opener = ModelOpener(); engine = OpenMovieAgent(UNIT_SECRET, _test_opener=opener, token_estimator=LargeEstimator())
        with self.assertRaises(Exception):engine.rank(self.decision())
        self.assertEqual((engine.calls, opener.calls), (0, []))


if __name__ == '__main__':unittest.main()
