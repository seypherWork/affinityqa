"""Staged external-film capture with fake providers, no network or real people."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.cinema_discovery_v4_capture import prepare_plan,search_identities,capture_confirmed
from affinityqa.cinema_discovery_v4_verify import verify_discovery_search,verify_confirmed_discoveries,selection_movies
from affinityqa.cinema_discovery_v4_agent import DiscoveryMovieAgent
from affinityqa.cinema_discovery_v3_verify import verify_discovery_search as legacy_verify
from affinityqa.errors import SchemaError,TransportError
from affinityqa.evidence import fingerprint
from affinityqa.individual_verify import inventory
from affinityqa.qloo import Response,Settings
from test_cinema_identity_capture import identity_request,ID_A,ID_B
from test_discovery_capture import DiscoveryTransport
from test_discovery_agent import Opener,TEST_SECRET
from test_groq_agent import UNIT_QLOO_SECRET
from test_movie_inputs import EXT,raw

class MovieTransport(DiscoveryTransport):
    def __init__(self,request,*,movie_rows=None,**kwargs):
        super().__init__(request,**kwargs);self.movie_rows=movie_rows or [raw()]
    def send(self,path,params):
        if path=='/search' and params['types']=='urn:entity:movie':
            self.calls.append((path,copy.deepcopy(params)))
            if len(self.calls)==self.fail_at:raise TransportError('Synthetic movie transport stop')
            if len(self.calls)==self.http_at:return Response(429,{'error':'Synthetic quota stop'},{})
            return Response(200,{'results':copy.deepcopy(self.movie_rows)},{})
        return super().send(path,params)

class DiscoveryV4Tests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'.test-runs';parent.mkdir(exist_ok=True);tmp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(tmp.cleanup);self.parent=Path(tmp.name)
        self.request=identity_request();self.request.update(schema_version=6,movie_queries={'A':['Synthetic external'],'B':[]})
        self.opener=Opener();self.transport=MovieTransport(self.request)
        self.adapters=(lambda:DiscoveryMovieAgent(TEST_SECRET,forbidden_secrets=(UNIT_QLOO_SECRET,),_test_opener=self.opener),lambda:self.transport)
        for target in ('socket.socket','socket.create_connection','socket.getaddrinfo'):
            guard=patch(target,side_effect=AssertionError('Network forbidden in v4 tests'));guard.start();self.addCleanup(guard.stop)
        guard=patch('affinityqa.cinema_discovery_v4_capture.time.sleep');guard.start();self.addCleanup(guard.stop)
    def search(self):
        output=self.parent/'capture';plan=prepare_plan(self.request,output,minimum_model_interval_seconds=0.0)
        report,directory=search_identities(self.request,output,plan['plan_sha256'],Settings(UNIT_QLOO_SECRET),minimum_model_interval_seconds=0.0,_test_adapters=self.adapters)
        self.directory=directory;self.receipt=verify_discovery_search(directory);return report,self.receipt
    def confirm(self,selected=None):
        selected=selected or {'A':[EXT['entity_id']],'B':[]}
        return capture_confirmed(self.directory,{'A':ID_A,'B':ID_B},self.receipt,Settings(UNIT_QLOO_SECRET),TEST_SECRET,selected_movie_entity_ids=selected,_test_adapters=self.adapters)
    def test_complete_external_case_records_real_shaped_inputs_without_seed_output(self):
        _,receipt=self.search();self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,0))
        self.assertEqual(selection_movies(receipt,{'A':[EXT['entity_id']],'B':[]}),{'A':[EXT],'B':[]})
        report,_=self.confirm();self.assertEqual(report['status'],'COMPLETE');before=inventory(self.directory)
        result=verify_confirmed_discoveries(self.directory);self.assertEqual(result['verification_status'],'VERIFIED_COMPLETE');self.assertEqual(inventory(self.directory),before)
        self.assertEqual(result['chosen_movie_inputs'],{'A':[EXT],'B':[]});self.assertEqual(result['movie_queries'],self.request['movie_queries'])
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(5,2));self.assertEqual((result['cultural_gate'],result['release_gate']),('NOT_VALIDATED','BLOCKED'))
        payload=json.loads(self.opener.calls[0][1]['messages'][1]['content']);self.assertEqual(payload['external_favorite_movies'],[EXT]);self.assertNotIn(EXT['entity_id'],report['cinema_results']['A']['delivered'])
        insight=[params for path,params in self.transport.calls if path=='/v2/insights'][0];self.assertIn(EXT['entity_id'],insight['signal.interests.entities'].split(','))
        with self.assertRaises(SchemaError):legacy_verify(self.directory)
    def test_two_queries_shared_movie_across_profiles_exact_six_two_budget(self):
        self.request['movie_queries']['B']=['Same real-shaped synthetic movie'];self.search();self.confirm({'A':[EXT['entity_id']],'B':[EXT['entity_id']]})
        self.assertEqual(verify_confirmed_discoveries(self.directory)['verification_status'],'VERIFIED_COMPLETE');self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(6,2))
    def test_in_catalog_selection_is_a_seed_not_a_discovery(self):
        movie={**self.request['catalog'][3],'type':'urn:entity:movie'};self.transport.movie_rows=[raw(movie)];self.search();report,_=self.confirm({'A':[movie['entity_id']],'B':[]})
        self.assertEqual(report['status'],'COMPLETE');self.assertEqual(verify_confirmed_discoveries(self.directory)['verification_status'],'VERIFIED_COMPLETE')
        self.assertNotIn(movie['entity_id'],report['cinema_results']['A']['raw_ranking']);self.assertEqual(report['cinema_results']['A']['discovery_count'],20-len(self.request['preferences']['A']['favorite_entity_ids'])-1)
    def test_movie_http_or_missing_year_stops_without_model_or_retry(self):
        for mode in ('http','no_year','empty'):
            with self.subTest(mode=mode):
                self.transport.calls.clear();self.transport.http_at=3 if mode=='http' else None;self.transport.movie_rows=[raw()|{'properties':{}}] if mode=='no_year' else [raw()]
                self.transport.movie_rows=[] if mode=='empty' else self.transport.movie_rows
                self.parent=self.parent/mode;self.parent.mkdir();report,receipt=self.search();self.assertEqual(receipt['verification_status'],'VERIFIED_PARTIAL');self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,0));self.assertEqual(report['status'],'INCOMPLETE')
    def test_invalid_movie_choice_rejected_before_confirmation_or_model(self):
        self.search();before=inventory(self.directory)
        with self.assertRaises(SchemaError):self.confirm({'A':[ID_A],'B':[]})
        self.assertEqual(inventory(self.directory),before);self.assertEqual(len(self.opener.calls),0)
    def test_self_rehashed_plan_cannot_change_search_budget(self):
        self.search();path=self.directory/'individual-plan.json';plan=json.loads(path.read_text());plan['maximum_qloo_requests']=99;plan['plan_sha256']=fingerprint({k:v for k,v in plan.items() if k!='plan_sha256'});path.write_text(json.dumps(plan))
        with self.assertRaises(SchemaError):verify_discovery_search(self.directory)
    def test_model_failure_preserves_prepared_request_consumed_slot_and_partial(self):
        self.search();from urllib.error import HTTPError
        self.opener.failure=HTTPError('https://synthetic.invalid',429,'Synthetic rate limit',{},None)
        report,_=self.confirm();self.assertEqual(report['status'],'INCOMPLETE');self.assertEqual(report['model_attempts'],1)
        self.assertEqual(verify_confirmed_discoveries(self.directory)['verification_status'],'VERIFIED_PARTIAL');self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(5,1))

    def test_false_producer_projection_is_rejected_by_independent_rows(self):
        with patch('affinityqa.cinema_discovery_v4_capture.movie_candidates',return_value=[EXT|{'release_year':1980}]):
            with self.assertRaises(SchemaError):self.search()
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,0))
    def test_confirmation_metadata_tampering_cannot_be_self_attested(self):
        self.search();self.confirm();path=self.directory/'confirmation.json';value=json.loads(path.read_text());value['selected_movies']['A'][0]['release_year']=1980;path.write_text(json.dumps(value))
        with self.assertRaises(SchemaError):verify_confirmed_discoveries(self.directory)
    def test_duplicate_with_existing_favorite_is_rejected_before_model(self):
        favorite_id=self.request['preferences']['A']['favorite_entity_ids'][0];movie={**next(v for v in self.request['catalog'] if v['entity_id']==favorite_id),'type':'urn:entity:movie'};self.transport.movie_rows=[raw(movie)];self.search();before=inventory(self.directory)
        with self.assertRaises(SchemaError):self.confirm({'A':[movie['entity_id']],'B':[]})
        self.assertEqual(inventory(self.directory),before);self.assertEqual(len(self.opener.calls),0)
    def test_movie_slot_order_is_binding(self):
        other=EXT|{'entity_id':'eeeeeeee-0000-4000-8000-000000000002','name':'Different synthetic movie'}
        self.request['movie_queries']={'A':['First','Second'],'B':[]}
        original=self.transport.send
        def send(path,params):
            if path=='/search' and params['types']=='urn:entity:movie':self.transport.movie_rows=[raw(EXT if params['query']=='First' else other)]
            return original(path,params)
        self.transport.send=send;self.search();before=inventory(self.directory)
        with self.assertRaises(SchemaError):self.confirm({'A':[other['entity_id'],EXT['entity_id']],'B':[]})
        self.assertEqual(inventory(self.directory),before);self.assertEqual(len(self.opener.calls),0)
