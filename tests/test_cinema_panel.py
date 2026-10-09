"""Cinema HTTP journeys: explicit plans, ownership, evidence and shared budgets."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from fastapi.testclient import TestClient
from affinityqa.cinema_preferences import CinemaMovieAgent
from affinityqa.public_demo import create_public_app
import test_public_case_api as fixture_module
from test_groq_agent import UNIT_SECRET,UNIT_QLOO_SECRET,OpenerFixture

PREFIX='/api/demo/cases'


class CinemaPanelTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_module.http_fixture()
        self.addCleanup(self.fixture.doCleanups)
        def engine():
            value=CinemaMovieAgent(UNIT_SECRET,forbidden_secrets=(UNIT_QLOO_SECRET,),_test_opener=OpenerFixture())
            self.fixture.engines.append(value)
            return value
        self.fixture.engine=engine
        self.service=self.fixture.service()
        self.client=TestClient(create_public_app(ROOT,origin=fixture_module.ORIGIN,case_manager=self.service),
                               base_url=fixture_module.ORIGIN,raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.csrf=self.client.post(PREFIX+'/session',json={},headers={'Origin':fixture_module.ORIGIN}).json()['csrf_token']
        catalog=self.fixture.request['catalog']
        self.preferences={label:{'schema_version':1,'favorite_entity_ids':[catalog[1]['entity_id']],
                                  'excluded_entity_ids':[catalog[0]['entity_id']]} for label in ('A','B')}
        self.guard=patch('affinityqa.cinema_capture.LiveTransport',side_effect=AssertionError('Real providers forbidden'))
        self.guard.start();self.addCleanup(self.guard.stop)

    def post(self,path,body):
        return self.client.post(PREFIX+path,json=body,headers={'Origin':fixture_module.ORIGIN,'X-AffinityQA-CSRF':self.csrf})

    def plan(self):
        response=self.post('/plans',{'artists':self.fixture.request['artists'],'preferences':self.preferences})
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def finish(self,job):
        response=self.post('/jobs/'+job['job_id']+'/execute',{'plan_sha256':job['plan_sha256']})
        self.assertEqual(response.status_code,202,response.text)
        self.service.manager.worker.join(timeout=15)
        self.assertFalse(self.service.manager.worker.is_alive())
        return self.client.get(PREFIX+'/jobs/'+job['job_id']).json()

    def test_preview_no_keys_new_hash_exact_preferences_and_declared_budget(self):
        first=self.plan()
        self.assertEqual((first['case_protocol'],first['maximum_model_decisions'],first['declared_faults']),('cinema-preferences-v1',2,0))
        self.assertEqual(first['preferences'],self.preferences)
        self.assertEqual((self.fixture.reads,len(self.fixture.engines)),([0,0],0))
        self.preferences['A']['favorite_entity_ids']=[]
        second=self.plan()
        self.assertNotEqual(first['plan_sha256'],second['plan_sha256'])
        self.assertEqual(self.post('/jobs/'+first['job_id']+'/execute',{'plan_sha256':second['plan_sha256']}).status_code,409)
        self.assertEqual(self.fixture.reads,[0,0])

    def test_complete_guarded_results_private_receipt_and_shared_admission(self):
        job=self.finish(self.plan())
        self.assertEqual(job['status'],'COMPLETE',job)
        result=job['result']
        self.assertEqual((job['saved_provider_samples'],job['saved_model_packets']),(4,2))
        self.assertEqual((result['preference_gate'],result['causal_gate'],result['cultural_gate']),('PASS','NOT_EVALUATED','NOT_VALIDATED'))
        for label,row in result['cinema_results'].items():
            self.assertEqual(len(row['raw_ranking']),20)
            self.assertEqual(len(row['delivered']),5)
            self.assertTrue(set(row['delivered']).isdisjoint(self.preferences[label]['excluded_entity_ids']))
            self.assertFalse(row['human_quality_validated'])
            self.assertIsNone(row['satisfaction_score'])
        receipt=self.client.get(PREFIX+'/jobs/'+job['job_id']+'/verification').json()
        text=json.dumps(receipt)
        for private in ('provider_envelope','provider_request_sha256','artifact_sha256',UNIT_SECRET,UNIT_QLOO_SECRET):
            self.assertNotIn(private,text)
        self.assertEqual(self.client.get(PREFIX+'/capabilities').json()['remaining_executions'],0)
        other_plan=self.plan()
        self.assertEqual(self.post('/jobs/'+other_plan['job_id']+'/execute',{'plan_sha256':other_plan['plan_sha256']}).status_code,429)

    def test_invalid_preferences_rejected_before_plan_storage_and_keys(self):
        ids=[row['entity_id'] for row in self.fixture.request['catalog']]
        invalid=[{'schema_version':True,'favorite_entity_ids':[],'excluded_entity_ids':[]},
                 {'schema_version':1,'favorite_entity_ids':[ids[0]],'excluded_entity_ids':[ids[0]]},
                 {'schema_version':1,'favorite_entity_ids':[],'excluded_entity_ids':ids[:16]},
                 {'schema_version':1,'favorite_entity_ids':[],'excluded_entity_ids':['not-a-catalog-id']},
                 {'schema_version':1,'favorite_entity_ids':[],'excluded_entity_ids':[],'ratings':[5]*20}]
        for value in invalid:
            with self.subTest(value=value):
                response=self.post('/plans',{'artists':self.fixture.request['artists'],'preferences':{**self.preferences,'A':value}})
                self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.fixture.reads,[0,0]);self.assertEqual(self.service.manager.jobs,{})
        self.assertFalse(self.service._mutations_blocked)

    def test_foreign_session_and_csrf_cannot_start_preference_case(self):
        job=self.plan()
        other=TestClient(self.client.app,base_url=fixture_module.ORIGIN)
        self.addCleanup(other.close)
        self.assertEqual(other.get(PREFIX+'/jobs/'+job['job_id']).status_code,404)
        denied=self.client.post(PREFIX+'/jobs/'+job['job_id']+'/execute',json={'plan_sha256':job['plan_sha256']},
                                headers={'Origin':fixture_module.ORIGIN,'X-AffinityQA-CSRF':'0'*64})
        self.assertEqual(denied.status_code,403);self.assertEqual(self.fixture.reads,[0,0])

    def test_post_verification_mutation_hides_results(self):
        job=self.finish(self.plan())
        directory=self.service.manager._capture_dir(job['job_id'])
        path=directory/'cinema-result-A.json'
        path.write_bytes(path.read_bytes()+b' ')
        view=self.client.get(PREFIX+'/jobs/'+job['job_id']).json()
        self.assertEqual(view['status'],'EVIDENCE_CHANGED');self.assertIsNone(view['result'])
