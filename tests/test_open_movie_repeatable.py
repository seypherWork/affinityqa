"""Owned open-film HTTP, durable quota reconstruction and historical preservation.

All providers are synthetic; these are engineering checks, not a taste study.
"""
import copy
from datetime import timedelta
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from fastapi import FastAPI
from fastapi.testclient import TestClient
from affinityqa.errors import SchemaError
from affinityqa.open_movie_discovery_agent import OpenMovieAgent
from affinityqa.provider_scheduler import ProviderScheduler, QuotaWindow
from affinityqa.repeatable_case_api import routes
from affinityqa.repeatable_cases import RepeatableCaseManager
from test_groq_agent import UNIT_SECRET, UNIT_QLOO_SECRET
from test_open_movie_discovery_capture import MovieTransport, ModelOpener, request_fixture
import test_repeatable_cases as legacy

ORIGIN=legacy.ORIGIN
BASE='/api/demo/cases'


class OpenMovieRepeatableTests(unittest.TestCase):
    def setUp(self):
        self.f=legacy.RepeatableTests('test_same_session_three_complete_cases_no_lifetime_caps_and_owned_receipts')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.transport=MovieTransport();self.opener=ModelOpener();self.request=request_fixture()
        self.scheduler=self.f.scheduler()
        self.manager=self.make_manager()
        self.client,self.headers=self.make_client(self.manager)

    def make_manager(self):
        manager=RepeatableCaseManager(self.f.parent/'open-service',self.f.request,origin=ORIGIN,
            minimum_model_interval_seconds=0.0,execution_enabled=True,settings_loader=self.f.settings,
            remote_key_loader=lambda:UNIT_SECRET,scheduler=self.scheduler,
            _test_adapters=(lambda:OpenMovieAgent(UNIT_SECRET,forbidden_secrets=(UNIT_QLOO_SECRET,),_test_opener=self.opener),
                            lambda:self.transport),_test_now=lambda:self.f.now,_test_autostart=False)
        self.addCleanup(manager.close);return manager

    def make_client(self,manager,token=None):
        app=FastAPI();app.include_router(routes(manager,origin=ORIGIN))
        client=TestClient(app,base_url=ORIGIN);self.addCleanup(client.close)
        if token:client.cookies.set('__Host-affinityqa-case',token,domain='judge.example',path='/')
        session=client.post(BASE+'/session',json={},headers={'origin':ORIGIN})
        self.assertEqual(session.status_code,200,session.text)
        return client,{'origin':ORIGIN,'x-affinityqa-csrf':session.json()['csrf_token']}

    def plan(self,**changes):
        body={k:copy.deepcopy(self.request[k]) for k in ('movie_query','intent_text','excluded_entity_ids')}
        body.update(changes)
        response=self.client.post(BASE+'/open-movies/plans',json=body,headers=self.headers)
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def read(self,job):
        response=self.client.get(BASE+'/jobs/'+job['job_id'])
        self.assertEqual(response.status_code,200,response.text);return response.json()

    def search(self,job):
        response=self.client.post(BASE+'/jobs/'+job['job_id']+'/execute',
            json={'plan_sha256':job['plan_sha256']},headers=self.headers)
        self.assertEqual(response.status_code,202,response.text)
        self.assertTrue(self.manager.manager.run_once())
        pending=self.read(job);self.assertEqual(pending['status'],'AWAITING_IDENTITY_CONFIRMATION',pending)
        self.assertEqual(len(self.opener.calls),0)
        return pending

    def selection(self,pending):
        return {'plan_sha256':pending['plan_sha256'],'identity_receipt_sha256':pending['identity_receipt_sha256'],
                'selected_movie_entity_id':pending['movie_candidates'][0]['entity_id']}

    def confirm(self,pending):
        response=self.client.post(BASE+'/jobs/'+pending['job_id']+'/confirm-movie',
            json=self.selection(pending),headers=self.headers)
        self.assertEqual(response.status_code,202,response.text)
        self.assertTrue(self.manager.manager.run_once())
        return self.read(pending)

    def retained_files(self,job_id):
        root=self.manager.root/'jobs'/job_id
        return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob('*') if p.is_file()}

    def test_full_owned_journey_and_legacy_plan_preserved(self):
        token=self.client.cookies.get('__Host-affinityqa-case')
        old=self.manager.prepare(token,self.f.request['artists'])
        original=self.retained_files(old['job_id'])
        plan=self.plan();self.assertNotIn('artists',plan)
        self.assertEqual((plan['maximum_qloo_requests'],plan['maximum_model_decisions']),(2,1))
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(0,0))
        pending=self.search(plan);done=self.confirm(pending)
        self.assertEqual(done['status'],'COMPLETE',done)
        result=done['result']['open_movie_results']
        self.assertEqual(len(result['delivered']),5)
        self.assertNotIn(result['seed_movie']['entity_id'],result['delivered'])
        self.assertEqual(len(result['reasons']),5)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(2,1))
        self.assertEqual(done['saved_model_packets'],1)
        self.assertEqual(done['result']['cultural_gate'],'NOT_VALIDATED')
        receipt=self.client.get(BASE+'/jobs/'+done['job_id']+'/verification')
        self.assertEqual(receipt.status_code,200,receipt.text)
        self.assertIn('attachment;',receipt.headers['content-disposition'])
        self.assertEqual(receipt.json()['result']['open_movie_results'],result)
        for private in ('artifact_sha256','provider_envelope','source_sha256','owner_sha256',str(self.manager.root)):
            self.assertNotIn(private,receipt.text)
        cap=self.client.get(BASE+'/capabilities').json()
        self.assertTrue(cap['open_movie_discovery_supported'])
        self.assertEqual([row['job_id'] for row in cap['jobs']],[old['job_id']])
        self.assertEqual([row['job_id'] for row in cap['open_movie_jobs']],[done['job_id']])
        self.assertEqual(self.retained_files(old['job_id']),original)
        self.assertEqual(self.manager.view(token,old['job_id'])['status'],'PLANNED')
        self.assertEqual(self.client.post(BASE+'/jobs/'+done['job_id']+'/confirm-movie',
            json=self.selection(pending),headers=self.headers).status_code,409)

    def test_wrong_choice_or_receipt_never_starts_discovery(self):
        pending=self.search(self.plan());url=BASE+'/jobs/'+pending['job_id']+'/confirm-movie'
        for change in ({'selected_movie_entity_id':'00000000-0000-4000-8000-000000000000'},
                       {'identity_receipt_sha256':'0'*64},{'plan_sha256':'0'*64}):
            response=self.client.post(url,json={**self.selection(pending),**change},headers=self.headers)
            self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.read(pending)['status'],'AWAITING_IDENTITY_CONFIRMATION')
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(1,0))

    def test_incompatible_retained_plans_are_read_only_without_rewriting_evidence(self):
        planned=self.plan();pending=self.search(self.plan())
        token=self.client.cookies.get('__Host-affinityqa-case')
        old=self.manager.prepare(token,self.f.request['artists'])
        before={job['job_id']:self.retained_files(job['job_id']) for job in (planned,pending,old)}
        with patch('affinityqa.repeatable_jobs.helper_bindings',return_value={'changed-source.py':'0'*64}):
            for job in (planned,pending,old):
                view=self.read(job);self.assertTrue(view['read_only'])
                self.assertEqual(view['continuity_reason'],'EXECUTION_SOURCE_CHANGED')
                self.assertEqual(view['status'],job['status'])
            cap=self.client.get(BASE+'/capabilities').json()
            self.assertTrue(all(row['read_only'] for row in cap['jobs']+cap['open_movie_jobs']))
            self.assertEqual(self.client.post(BASE+'/jobs/'+planned['job_id']+'/execute',
                json={'plan_sha256':planned['plan_sha256']},headers=self.headers).status_code,409)
            self.assertEqual(self.client.post(BASE+'/jobs/'+pending['job_id']+'/confirm-movie',
                json=self.selection(pending),headers=self.headers).status_code,409)
        for job in (planned,pending,old):self.assertEqual(self.retained_files(job['job_id']),before[job['job_id']])
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(1,0))

    def test_closed_http_origin_csrf_ownership_and_retained_receipts(self):
        body={'movie_query':self.request['movie_query']}
        self.assertEqual(self.client.post(BASE+'/open-movies/plans',json=body,headers={'origin':ORIGIN}).status_code,403)
        self.assertEqual(self.client.post(BASE+'/open-movies/plans',json=body,
            headers={**self.headers,'origin':'https://other.invalid'}).status_code,403)
        for extra in ({'model':self.request['model']},{'intent_text':'x'*601},{'excluded_entity_ids':['invalid']}):
            self.assertEqual(self.client.post(BASE+'/open-movies/plans',json={**body,**extra},headers=self.headers).status_code,422)
        pending=self.search(self.plan());url=BASE+'/jobs/'+pending['job_id']
        self.assertEqual(self.client.post(url+'/confirm-movie',json={**self.selection(pending),'chosen_movie_input':{}},headers=self.headers).status_code,422)
        other,headers=self.make_client(self.manager)
        self.assertEqual(other.get(url).status_code,404)
        self.assertEqual(other.get(url+'/verification').status_code,404)
        self.assertEqual(other.post(url+'/confirm-movie',json=self.selection(pending),headers=headers).status_code,404)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(1,0))

    def test_restart_restores_pending_choice_and_completed_receipt_without_dispatch(self):
        pending=self.search(self.plan());token=self.client.cookies.get('__Host-affinityqa-case')
        before=self.retained_files(pending['job_id']);self.manager.close()
        self.manager=self.make_manager();self.client,self.headers=self.make_client(self.manager,token)
        restored=self.read(pending)
        self.assertEqual(restored,pending)
        self.assertEqual(self.retained_files(pending['job_id']),before)
        done=self.confirm(restored);self.assertEqual(done['status'],'COMPLETE',done)
        receipt=self.client.get(BASE+'/jobs/'+done['job_id']+'/verification').json()
        before=self.retained_files(done['job_id']);self.manager.close()
        self.manager=self.make_manager();self.client,self.headers=self.make_client(self.manager,token)
        self.assertEqual(self.client.get(BASE+'/jobs/'+done['job_id']+'/verification').json(),receipt)
        self.assertEqual(self.retained_files(done['job_id']),before)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(2,1))

    def test_quota_wait_reconstructs_accepted_work_and_keeps_first_case(self):
        # A single free-provider slot forces the next model decision to wait.
        self.manager.close()
        self.scheduler=ProviderScheduler(self.f.parent/'one-slot-provider.sqlite3',clock=lambda:self.f.now.timestamp(),limits={
            'qloo':(QuotaWindow('rpm',1000,60),),
            'groq':(QuotaWindow('rpm',1,60),QuotaWindow('tokens',1000000,60,'tokens'))})
        self.manager=self.make_manager();self.client,self.headers=self.make_client(self.manager)
        first=self.confirm(self.search(self.plan()))
        self.assertEqual(first['status'],'COMPLETE',first)
        original=self.retained_files(first['job_id'])
        plan=self.plan();self.client.post(BASE+'/jobs/'+plan['job_id']+'/execute',
            json={'plan_sha256':plan['plan_sha256']},headers=self.headers)
        self.manager.manager.run_once();pending=self.read(plan)
        waiting=self.confirm(pending)
        self.assertEqual(waiting['status'],'WAITING_PROVIDER_CAPACITY',waiting)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,1))
        token=self.client.cookies.get('__Host-affinityqa-case');self.manager.close();self.f.now+=timedelta(seconds=61)
        self.manager=self.make_manager();self.client,self.headers=self.make_client(self.manager,token)
        self.assertTrue(self.manager.manager.run_once());done=self.read(plan)
        self.assertEqual(done['status'],'COMPLETE',done)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,2))
        self.assertGreater(done['provider_stats']['qloo']['reconstructed_steps'],0)
        self.assertEqual(self.retained_files(first['job_id']),original)

    def test_unknown_model_send_survives_restart_and_never_retries(self):
        def timeout(request,timeout):
            self.opener.calls.append(request);raise TimeoutError('synthetic uncertain send')
        with patch.object(self.opener,'open',side_effect=timeout):
            done=self.confirm(self.search(self.plan()))
        self.assertEqual(done['status'],'UNKNOWN',done)
        token=self.client.cookies.get('__Host-affinityqa-case');self.manager.close()
        self.manager=self.make_manager();self.client,self.headers=self.make_client(self.manager,token)
        self.assertEqual(self.read(done)['status'],'UNKNOWN')
        self.assertFalse(self.manager.manager.run_once())
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(2,1))

    def test_uncommitted_selection_checkpoint_is_recovered_once(self):
        pending=self.search(self.plan());selected=self.selection(pending)
        # Simulate process exit between immutable selection write and DB commit.
        class ProcessExit(BaseException):pass
        with patch.object(self.manager.store,'transaction',side_effect=ProcessExit):
            with self.assertRaises(ProcessExit):
                self.manager.manager.confirm_movie(pending['job_id'],selected['plan_sha256'],
                    selected['identity_receipt_sha256'],selected['selected_movie_entity_id'])
        token=self.client.cookies.get('__Host-affinityqa-case');self.manager.close()
        self.manager=self.make_manager();self.client,self.headers=self.make_client(self.manager,token)
        self.assertEqual(self.read(pending)['status'],'QUEUED')
        self.assertTrue(self.manager.manager.run_once())
        self.assertEqual(self.read(pending)['status'],'COMPLETE')
        self.assertFalse(self.manager.manager.run_once())
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(2,1))


if __name__=='__main__':unittest.main()
