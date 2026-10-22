"""Raw provider titles stay source-bound; input queries keep their canonical contract."""
import copy
import hashlib
from pathlib import Path
import unittest
from uuid import UUID

import test_wide_cinema_capture as fixture
from affinityqa.errors import SchemaError
from affinityqa.wide_cinema_discovery import movie_identity,validate_request,MODEL
from affinityqa.wide_cinema_verify import _movie,verify_discoveries


class SourceTitleRegressionTests(unittest.TestCase):
    def movie(self,name):
        return {'entity_id':str(UUID(int=777)), 'name':name,'type':'urn:entity:movie','release_year':2000}

    def test_raw_provider_title_is_preserved_by_both_validators(self):
        for title in ['Synthetic  film','Synthetic\u00a0film','Synthetic \u2168','Cafe\u0301 film',' Synthetic film ']:
            with self.subTest(title=repr(title)):
                value=self.movie(title);before=copy.deepcopy(value)
                self.assertEqual(movie_identity(value),before)
                self.assertEqual(_movie(value),before)
                self.assertEqual(value,before)

    def test_raw_and_normalized_title_lengths_are_bounded(self):
        for title in [' '*301+'x','x'*301,'\ufb03'*101,('\ufb03'+' '*3)*51,' '*300,'\u00a0'*300]:
            with self.subTest(title_length=len(title)):
                for validator in (movie_identity,_movie):
                    with self.assertRaises(SchemaError):validator(self.movie(title))
        self.assertEqual(movie_identity(self.movie('x'*300))['name'],'x'*300)

    def test_title_controls_and_non_strings_are_rejected(self):
        for title in ['Synthetic\nfilm','Synthetic\u0000film','Synthetic\u202efilm','Synthetic\u200bfilm','Synthetic\u2028film','Synthetic\u2029film',None,True,123]:
            with self.subTest(title=repr(title)):
                for validator in (movie_identity,_movie):
                    with self.assertRaises(SchemaError):validator(self.movie(title))

    def test_identity_year_type_and_shape_are_not_relaxed(self):
        for changes in [{'entity_id':'not-a-uuid'},{'release_year':'2000'},{'release_year':True},{'release_year':2101},
                        {'type':'urn:entity:artist'},{'extra':'not-allowed'}]:
            with self.subTest(changes=changes):
                for validator in (movie_identity,_movie):
                    with self.assertRaises(SchemaError):validator({**self.movie('Synthetic  film'),**changes})

    def test_user_queries_still_normalize_separately(self):
        request={'schema_version':9,'mode':'movie','seed_query':'  Synthetic\u00a0 \u2168  ', 'model':dict(MODEL)}
        self.assertEqual(validate_request(request)['seed_query'],'Synthetic IX')

    def test_synthetic_pages_complete_with_exact_original_title_art_and_grounding(self):
        test=fixture.WideCaptureTests('test_movie100_actual_candidates_three_qloo_one_model');test.setUp()
        try:
            raw='Synthetic  \u2168 film 77'
            def mutate(body,page):
                if page==2:body['results']['entities'][26]['name']=raw
            def select(body):
                body['choices'][0]['message']['content']='{"ordered_catalog_indices":[{"catalog_index":76},{"catalog_index":0},{"catalog_index":1},{"catalog_index":2},{"catalog_index":3}]}'
            test.opener=fixture.WideOpener(mutation=select)
            report,receipt=test.finish(fixture.request_fixture('music',True),fixture.WideTransport(mutation=mutate))
            self.assertEqual((report['status'],receipt['verification_status']),('COMPLETE','VERIFIED_COMPLETE'))
            result=receipt['wide_cinema_results'];identity=str(UUID(int=77))
            self.assertEqual(result['delivered'][0],identity)
            movie=next(row for row in result['candidate_catalog'] if row['entity_id']==identity)
            self.assertEqual(movie['name'],raw)
            self.assertEqual(result['reasons'][0]['evidence']['title'],raw)
            self.assertEqual(len(result['presentation_assets']),100)
            self.assertEqual((len(test.transport.calls),len(test.opener.calls)),(4,1))
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in test.directory.iterdir() if p.is_file()}
            self.assertEqual(verify_discoveries(test.directory)['verification_status'],'VERIFIED_COMPLETE')
            self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in test.directory.iterdir() if p.is_file()})
        finally:test.doCleanups()


    def test_search_seed_and_favorite_keep_source_title_without_changing_ids(self):
        for mode,favorite in [('movie',False),('music',True)]:
            with self.subTest(mode=mode):
                test=fixture.WideCaptureTests('test_movie100_actual_candidates_three_qloo_one_model');test.setUp()
                try:
                    def mutate(body,params):
                        if params['types']=='urn:entity:movie':body['results'][0]['name']='Synthetic  \u2168 film'
                    report,receipt=test.finish(fixture.request_fixture(mode,favorite),fixture.WideTransport(search_mutation=mutate))
                    self.assertEqual((report['status'],receipt['verification_status']),('COMPLETE','VERIFIED_COMPLETE'))
                    identity=receipt['seed_identity'] if mode=='movie' else receipt['known_favorite_movie']
                    self.assertEqual(identity['name'],'Synthetic  \u2168 film')
                    self.assertEqual(identity['entity_id'],fixture.SEED_ID if mode=='movie' else fixture.FAVORITE_ID)
                finally:test.doCleanups()


if __name__=='__main__':unittest.main()
