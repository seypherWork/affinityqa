"""Synthetic movie identity/conditioning tests; network forbidden."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.cinema_movie_inputs import validate_movie_queries,movie_candidates,compile_preferences,selection_movies
from affinityqa.cinema_discovery_v4_verify import _movie_candidates,selection_movies as independent_selection
from affinityqa.cinema_discoveries_v4 import qloo_request,context_from_sample,make_request,model_input,deliver,cache_key,qloo_cache_key
from affinityqa.cinema_discovery_v4_boundary_verify import expected_input,verify_context
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
from test_discovery_agent import fixture_request
EXT={'entity_id':'eeeeeeee-0000-4000-8000-000000000001','name':'Synthetic external movie','release_year':1997,'type':'urn:entity:movie'}

def raw(movie=EXT):
    return {'entity_id':movie['entity_id'],'name':movie['name'],'types':['urn:entity:movie'],'properties':{'release_year':movie['release_year']}}

class MovieInputsTests(unittest.TestCase):
    def setUp(self):
        for name in ('socket.socket','socket.create_connection','socket.getaddrinfo'):
            guard=patch(name,side_effect=AssertionError('Network forbidden'));guard.start();self.addCleanup(guard.stop)
        self.old=fixture_request(0);self.catalog=self.old['catalog'];self.prefs=self.old['preferences']
    def test_query_normalization_and_total_bound(self):
        self.assertEqual(validate_movie_queries({'A':['  Movie   title  '],'B':[]}),{'A':['Movie title'],'B':[]})
        for queries in ({'A':[],'B':[]},{'A':['a','b'],'B':['c']},{'A':['x'*201],'B':[]},{'A':['a\nb'],'B':[]}):
            with self.subTest(queries=queries),self.assertRaises(SchemaError):validate_movie_queries(queries)
    def test_provider_year_required_and_duplicate_policy(self):
        body={'results':[raw(),raw()]};before=copy.deepcopy(body)
        self.assertEqual(movie_candidates(body),[EXT]);self.assertEqual(_movie_candidates(body),[EXT]);self.assertEqual(body,before)
        for row in (raw()|{'properties':{}},raw()|{'properties':{'release_year':True}},raw()|{'types':['urn:entity:book']}):
            for parser in (movie_candidates,_movie_candidates):
                with self.assertRaises(SchemaError):parser({'results':[row]})
        for parser in (movie_candidates,_movie_candidates):
            with self.assertRaises(SchemaError):parser({'results':[raw(),raw(EXT|{'release_year':1998})]})
            with self.assertRaises(SchemaError):parser({'results':[raw()]*6})
            with self.assertRaises(SchemaError):parser({'results':[raw(),{'entity_id':'bad'}]})
    def test_external_positive_signal_exact_payload_and_independent_input(self):
        prefs=compile_preferences(self.catalog,self.prefs,[EXT]);profile=self.old['profile']
        query=qloo_request(profile,self.catalog,prefs)
        self.assertIn(EXT['entity_id'],query['params']['signal.interests.entities'].split(','))
        self.assertNotIn(EXT['entity_id'],query['params']['filter.results.entities'].split(','))
        rows=[raw({'entity_id':v['entity_id'],'name':v['name'],'release_year':v['release_year']})|{'query':{'affinity':1-i/20}} for i,v in enumerate(self.catalog)]
        sample={'request':query,'status':200,'attempt':1,'live_network_request':True,'response':{'success':True,'results':{'entities':rows}}};sample['response_sha256']=fingerprint(sample['response'])
        context=context_from_sample(profile,self.catalog,prefs,sample,fingerprint(sample))
        self.assertEqual(verify_context(context,self.catalog,profile,prefs,sample,fingerprint(sample)),context)
        request=make_request(self.catalog,profile,context,prefs,'synthetic')
        payload=model_input(request);self.assertEqual(payload,expected_input(request));self.assertEqual(payload['external_favorite_movies'],[EXT])
        self.assertEqual(len(payload['discovery_catalog_indices']),20)
        ranked=[v['entity_id'] for v in self.catalog];out=deliver(ranked,self.catalog,prefs)
        self.assertNotIn(EXT['entity_id'],out['delivered_entity_ids']);self.assertEqual(out['known_favorite_count'],1)
        changed=copy.deepcopy(request);changed['preferences']['external_favorite_movies'][0]['name']='Changed'
        with self.assertRaises(SchemaError):cache_key(changed,{})
    def test_catalog_selection_becomes_known_favorite(self):
        row=self.catalog[3];movie={**row,'type':'urn:entity:movie'}
        prefs=compile_preferences(self.catalog,self.prefs,[movie]);self.assertIn(row['entity_id'],prefs['favorite_entity_ids']);self.assertEqual(prefs['external_favorite_movies'],[])
        query=qloo_request(self.old['profile'],self.catalog,prefs);self.assertNotIn(row['entity_id'],query['params']['filter.results.entities']);self.assertEqual(query['params']['take'],19)
    def test_conflicts_and_combined_five_bound(self):
        row=self.catalog[2];movie={**row,'type':'urn:entity:movie'}
        for prefs,movies in ((self.prefs,[EXT,EXT]),(self.prefs|{'favorite_entity_ids':[row['entity_id']]},[movie]),(self.prefs|{'excluded_entity_ids':[row['entity_id']]},[movie]),(self.prefs|{'favorite_entity_ids':[v['entity_id'] for v in self.catalog[:5]]},[EXT]),(self.prefs,[movie|{'release_year':1980}]),(self.prefs,[EXT|{'name':row['name'],'release_year':row['release_year']}])):
            with self.subTest(movies=movies),self.assertRaises(SchemaError):compile_preferences(self.catalog,prefs,movies)
    def test_slot_membership_and_shared_cross_profile_selection(self):
        receipt={'verification_status':'VERIFIED_IDENTITY_SEARCH','status':'AWAITING_IDENTITY_CONFIRMATION','movie_candidates':{'A':[[EXT]],'B':[[EXT]]}}
        selected={'A':[EXT['entity_id']],'B':[EXT['entity_id']]}
        self.assertEqual(selection_movies(receipt,selected),independent_selection(receipt,selected))
        for parser in (selection_movies,independent_selection):
            with self.assertRaises(SchemaError):parser(receipt,{'A':[],'B':[EXT['entity_id']]})
            with self.assertRaises(SchemaError):parser(receipt,{'A':['aaaaaaaa-0000-4000-8000-000000000099'],'B':[EXT['entity_id']]})

    def test_seed_metadata_participates_in_query_cache_identity(self):
        profile=self.old['profile'];one=compile_preferences(self.catalog,self.prefs,[EXT]);two=compile_preferences(self.catalog,self.prefs,[EXT|{'name':'Different confirmed title'}])
        self.assertEqual(qloo_request(profile,self.catalog,one),qloo_request(profile,self.catalog,two))
        self.assertNotEqual(qloo_cache_key(profile,self.catalog,one),qloo_cache_key(profile,self.catalog,two))
