"""Owned wide-film HTTP journeys through the actual durable dispatcher, offline."""
import copy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from fastapi import FastAPI
from fastapi.testclient import TestClient
from affinityqa.wide_cinema_tokens import WideHarmonyTokenEstimator
from affinityqa.provider_scheduler import QuotaWindow
from affinityqa.repeatable_case_api import routes
from affinityqa.public_demo import create_public_app
from affinityqa.repeatable_cases import RepeatableCaseManager
from affinityqa.wide_cinema_agent import WideCinemaAgent
from test_wide_cinema_capture import WideTransport,WideOpener,request_fixture,UNIT_SECRET,QLOO_SECRET,SEED_ID,ARTIST_ID,FAVORITE_ID
import test_repeatable_cases as legacy

ORIGIN=legacy.ORIGIN;BASE='/api/demo/cases'


class WideRepeatableTests(unittest.TestCase):
    def setUp(self):
        self.f=legacy.RepeatableTests('test_same_session_three_complete_cases_no_lifetime_caps_and_owned_receipts')
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.transport=WideTransport();self.opener=WideOpener();self.scheduler=self.f.scheduler()
        self.estimator=WideHarmonyTokenEstimator(ROOT/'assets/tokenizers/o200k_base.tiktoken')
        self.manager=self.make_manager();self.client,self.headers=self.make_client(self.manager)
    def make_manager(self):
        service=RepeatableCaseManager(self.f.parent/'wide',self.f.request,origin=ORIGIN,minimum_model_interval_seconds=22,
            execution_enabled=True,settings_loader=lambda:__import__('affinityqa.qloo',fromlist=['Settings']).Settings(QLOO_SECRET),
            remote_key_loader=lambda:UNIT_SECRET,scheduler=self.scheduler,token_estimator=self.estimator,
            _test_adapters=(lambda:WideCinemaAgent(UNIT_SECRET,forbidden_secrets=(QLOO_SECRET,),_test_opener=self.opener,token_estimator=self.estimator),lambda:self.transport),
            _test_now=lambda:self.f.now,_test_autostart=False)
        self.addCleanup(service.close);return service
    def make_client(self,manager,token=None,*,public=False):
        if public:app=create_public_app(ROOT,origin=ORIGIN,case_manager=manager)
        else:
            app=FastAPI();app.include_router(routes(manager,origin=ORIGIN))
        client=TestClient(app,base_url=ORIGIN);self.addCleanup(client.close)
        if token:client.cookies.set('__Host-affinityqa-case',token,domain='judge.example',path='/')
        session=client.post(BASE+'/session',json={},headers={'origin':ORIGIN});self.assertEqual(session.status_code,200,session.text)
        return client,{'origin':ORIGIN,'x-affinityqa-csrf':session.json()['csrf_token']}
    def plan(self,mode='movie',favorite=False,**changes):
        body={k:v for k,v in request_fixture(mode,favorite,**changes).items() if k not in ('schema_version','model')}
        response=self.client.post(BASE+'/wide-cinema/plans',json=body,headers=self.headers);self.assertEqual(response.status_code,201,response.text)
        return response.json()
    def read(self,job):
        r=self.client.get(BASE+'/jobs/'+job['job_id']);self.assertEqual(r.status_code,200,r.text);return r.json()
    def search(self,job):
        r=self.client.post(BASE+'/jobs/'+job['job_id']+'/execute',json={'plan_sha256':job['plan_sha256']},headers=self.headers)
        self.assertEqual(r.status_code,202,r.text);self.assertTrue(self.manager.manager.run_once());view=self.read(job)
        self.assertEqual(view['status'],'AWAITING_IDENTITY_CONFIRMATION',view);return view
    def selection(self,pending):
        return {'plan_sha256':pending['plan_sha256'],'identity_receipt_sha256':pending['identity_receipt_sha256'],
            'selected_seed_entity_id':pending['seed_candidates'][0]['entity_id'],
            'selected_favorite_movie_entity_id':pending['favorite_movie_candidates'][0]['entity_id'] if pending['favorite_movie_candidates'] else None}
    def confirm(self,pending):
        r=self.client.post(BASE+'/jobs/'+pending['job_id']+'/confirm-wide',json=self.selection(pending),headers=self.headers)
        self.assertEqual(r.status_code,202,r.text);self.assertTrue(self.manager.manager.run_once());return self.read(pending)
    def finish(self,**kwargs):return self.confirm(self.search(self.plan(**kwargs)))
    def test_complete_owned_journey_100pool_download_and_restart_restore(self):
        final=self.finish(intent_text='Primero el humor que interprete el modelo, sin garantía de género.')
        self.assertEqual(final['status'],'COMPLETE',final);self.assertNotIn('artists',final)
        self.assertEqual(final['result']['wide_cinema_results']['candidate_count'],100)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,1))
        download=self.client.get(BASE+'/jobs/'+final['job_id']+'/verification');self.assertEqual(download.status_code,200)
        self.assertNotIn('provider_envelope',download.text);self.assertNotIn(QLOO_SECRET,download.text)
        before=download.json();token=self.client.cookies.get('__Host-affinityqa-case');self.manager.close()
        self.manager=self.make_manager();self.client,self.headers=self.make_client(self.manager,token)
        self.assertEqual(self.client.get(BASE+'/jobs/'+final['job_id']+'/verification').json(),before)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,1))
    def test_overlay_does_not_change_result_download_owner_or_saved_bytes(self):
        final=self.finish();job_id=final['job_id'];self.assertIsInstance(final['wide_cinema_display'],dict)
        self.assertNotIn('wide_cinema_display',final['result'])
        display=final['wide_cinema_display'];self.assertEqual(display['protocol_version'],'qloo-wide-cinema-discovery-v10')
        self.assertFalse(display['legacy_original_archived'])
        from affinityqa.wide_cinema_grounding import CURRENT_NOTICE
        from affinityqa.evidence import fingerprint
        self.assertEqual(display['notice'],CURRENT_NOTICE)
        self.assertEqual(display['binding_sha256'],fingerprint({k:v for k,v in display.items() if k!='binding_sha256'}))
        path=BASE+'/jobs/'+job_id+'/verification';original=self.client.get(path).content
        directory=Path(self.manager.manager._job(job_id)['directory'])
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}
        with patch('affinityqa.wide_cinema_grounding.display_for_receipt',side_effect=ValueError('Synthetic bad source')):
            self.assertIsNone(self.read(final)['wide_cinema_display'])
            self.assertEqual(self.client.get(path).content,original)
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()})
        stranger,_=self.make_client(self.manager);self.assertEqual(stranger.get(BASE+'/jobs/'+job_id).status_code,404)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,1))
    def test_music_optional_favorite_is_confirmed_and_excluded_from_selection(self):
        final=self.finish(mode='music',favorite=True);self.assertEqual(final['status'],'COMPLETE',final)
        result=final['result']['wide_cinema_results'];self.assertEqual(result['seed_identity']['entity_id'],ARTIST_ID)
        self.assertEqual(result['known_favorite_movie']['entity_id'],FAVORITE_ID);self.assertNotIn(FAVORITE_ID,result['delivered'])
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,1))
    def test_closed_body_and_owner_origin_csrf_and_foreign_selection(self):
        body={'mode':'movie','seed_query':'Synthetic seed 2000'}
        self.assertEqual(self.client.post(BASE+'/wide-cinema/plans',json={**body,'model':'other'},headers=self.headers).status_code,422)
        self.assertEqual(self.client.post(BASE+'/wide-cinema/plans',json=body).status_code,403)
        self.assertEqual(self.client.post(BASE+'/wide-cinema/plans',json={**body,'favorite_movie_query':'bad'},headers=self.headers).status_code,422)
        pending=self.search(self.plan());choice=self.selection(pending);choice['selected_seed_entity_id']=FAVORITE_ID
        self.assertEqual(self.client.post(BASE+'/jobs/'+pending['job_id']+'/confirm-wide',json=choice,headers=self.headers).status_code,409)
        other,_=self.make_client(self.manager);self.assertEqual(other.get(BASE+'/jobs/'+pending['job_id']).status_code,404)
        self.assertEqual(len(self.opener.calls),0)
    def test_history_is_dedicated_and_does_not_leak_into_old_surfaces(self):
        wide=self.plan();old=self.client.post(BASE+'/open-movies/plans',json={'movie_query':'Synthetic seed 2000'},headers=self.headers)
        self.assertEqual(old.status_code,201,old.text);old_id=old.json()['job_id']
        caps=self.client.get(BASE+'/capabilities').json();self.assertTrue(caps['wide_cinema_discovery_supported'])
        self.assertEqual([v['job_id'] for v in caps['wide_cinema_jobs']],[wide['job_id']])
        self.assertNotIn(wide['job_id'],[v['job_id'] for v in caps['jobs']+caps['open_movie_jobs']])
        history=self.client.get(BASE+'/wide-cinema/jobs').json();self.assertEqual([v['job_id'] for v in history['wide_cinema_jobs']],[wide['job_id']])
        self.assertIn('wide_cinema_jobs_truncated',history);self.assertIn('wide_cinema_next_cursor_job_id',history)
        self.assertEqual(self.client.get(BASE+'/jobs/'+old_id).json()['status'],'PLANNED')
    def test_public_boundary_allows_owned_history_by_path_and_keeps_query_rejection(self):
        self.client,self.headers=self.make_client(self.manager,public=True)
        with patch('affinityqa.repeatable_cases.HISTORY_PAGE_SIZE',3):
            created=[self.plan()['job_id'] for _ in range(4)]
            first=self.client.get(BASE+'/wide-cinema/jobs');self.assertEqual(first.status_code,200,first.text)
            page=first.json();self.assertEqual(len(page['wide_cinema_jobs']),3);self.assertTrue(page['wide_cinema_jobs_truncated'])
            cursor=page['wide_cinema_next_cursor_job_id'];path=BASE+'/wide-cinema/jobs/older-than/'+cursor
            second=self.client.get(path);self.assertEqual(second.status_code,200,second.text)
            older=second.json();self.assertEqual(len(older['wide_cinema_jobs']),1);self.assertFalse(older['wide_cinema_jobs_truncated'])
            self.assertEqual(set(created),{j['job_id'] for j in page['wide_cinema_jobs']+older['wide_cinema_jobs']})
            self.assertEqual(self.client.get(BASE+'/wide-cinema/jobs?cursor_job_id='+cursor).status_code,400)
            stranger,_=self.make_client(self.manager,public=True)
            self.assertEqual(stranger.get(path).status_code,404)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(0,0))
    def test_wide_view_reports_scheduler_zero_while_preserving_owner_interval22(self):
        job=self.plan();self.assertEqual(self.manager.manager.interval,22)
        self.assertEqual(job['minimum_model_interval_seconds'],0)
        saved=json.loads((self.manager.root/'jobs'/job['job_id']/'job-plan.json').read_bytes())['plan']['protocol_plan']
        self.assertEqual(saved['execution_pacing'],{'strategy':'shared-durable-provider-scheduler','minimum_interval_seconds':0})
    def test_unknown_model_send_is_terminal_never_retried(self):
        self.opener.failure=TimeoutError('synthetic read failure');pending=self.search(self.plan());final=self.confirm(pending)
        self.assertEqual(final['status'],'UNKNOWN',final);self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,1))
        self.assertFalse(self.manager.manager.run_once())
        self.assertEqual(self.client.post(BASE+'/jobs/'+final['job_id']+'/execute',json={'plan_sha256':final['plan_sha256']},headers=self.headers).status_code,409)
    def test_quota_wait_reconstructs_both_pages_without_second_qloo_send(self):
        self.scheduler.limits['groq']=(QuotaWindow('rpm',1,60),QuotaWindow('tpm',8000,60,'tokens'))
        first=self.finish();self.assertEqual(first['status'],'COMPLETE',first)
        pending=self.search(self.plan());waiting=self.confirm(pending);self.assertEqual(waiting['status'],'WAITING_PROVIDER_CAPACITY',waiting)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(6,1))
        self.f.now += timedelta(seconds=61);self.assertTrue(self.manager.manager.run_once());final=self.read(waiting)
        self.assertEqual(final['status'],'COMPLETE',final);self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(6,2))
    def test_confirmation_checkpoint_crash_restores_exact_explicit_selection(self):
        class Crash(BaseException):pass
        pending=self.search(self.plan());choice=self.selection(pending)
        with patch.object(self.manager.store,'transaction',side_effect=Crash),self.assertRaises(Crash):
            self.manager.manager.confirm_wide(pending['job_id'],choice['plan_sha256'],choice['identity_receipt_sha256'],choice['selected_seed_entity_id'])
        checkpoint=self.manager.root/'jobs'/pending['job_id']/'identity-confirmation.json';saved=checkpoint.read_bytes()
        token=self.client.cookies.get('__Host-affinityqa-case');self.manager.close();self.manager=self.make_manager();self.client,self.headers=self.make_client(self.manager,token)
        self.assertEqual(self.read(pending)['status'],'QUEUED');self.assertTrue(self.manager.manager.run_once())
        self.assertEqual(self.read(pending)['status'],'COMPLETE');self.assertEqual(checkpoint.read_bytes(),saved)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,1))


if __name__=='__main__':unittest.main()
