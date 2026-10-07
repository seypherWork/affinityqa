"""Public HTTP ownership and admission journeys with denied real providers."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from fastapi.testclient import TestClient
from affinityqa import public_demo as public
from affinityqa.public_case_api import cookie_name
import test_public_cases as case_fixtures
from test_groq_agent import OpenerFixture,UNIT_SECRET,UNIT_QLOO_SECRET
from test_public_demo import SyntheticCapture

ORIGIN='https://judge.example'
PREFIX='/api/demo/cases'


def http_fixture():
    fixture=case_fixtures.PublicCasesTests()
    base=ROOT/'.test-runs';base.mkdir(exist_ok=True)
    fixture.temp=tempfile.TemporaryDirectory(dir=base)
    fixture.addCleanup(fixture.temp.cleanup)
    fixture.parent=Path(fixture.temp.name)
    fixture.request=case_fixtures.request_fixture()
    fixture.reads=[0,0];fixture.engines=[];fixture.opener_factory=OpenerFixture
    fixture.now=datetime(2026,10,6,14,0,tzinfo=timezone.utc)
    # Windows' proactor checks isinstance(conn, socket.socket). Replacing that
    # class breaks its local self-pipe. Keep it intact; forbid provider/DNS
    # dispatch and use only in-process ASGI plus the explicit fake adapter.
    for target in ('socket.create_connection','socket.getaddrinfo',
                   'affinityqa.individual_remote_capture.LiveTransport'):
        guard=patch(target,side_effect=AssertionError('Actual provider and DNS forbidden'))
        guard.start();fixture.addCleanup(guard.stop)
    return fixture


class PublicCaseHTTPTests(unittest.TestCase):
    def setUp(self):
        # Reuse provider-denied fixture setup; do not inherit and rerun its tests.
        self.fixture=http_fixture()
        self.addCleanup(self.fixture.doCleanups)
        self.manager=self.fixture.service()
        self.app=public.create_public_app(ROOT,origin=ORIGIN,case_manager=self.manager)

    def client(self,app=None,base=ORIGIN):
        client=TestClient(app or self.app,base_url=base,raise_server_exceptions=False,follow_redirects=False)
        self.addCleanup(client.close)
        return client

    def session(self,client):
        response=client.post(PREFIX+'/session',json={},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['csrf_token']

    def post(self,client,path,csrf,body):
        return client.post(PREFIX+path,json=body,headers={'Origin':ORIGIN,'X-AffinityQA-CSRF':csrf})

    def plan(self,client,csrf):
        response=self.post(client,'/plans',csrf,{'artists':self.fixture.request['artists']})
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def finish(self,client,csrf,job):
        response=self.post(client,'/jobs/'+job['job_id']+'/execute',csrf,{'plan_sha256':job['plan_sha256']})
        self.assertEqual(response.status_code,202,response.text)
        self.manager.manager.worker.join(timeout=15)
        self.assertFalse(self.manager.manager.worker.is_alive())
        return client.get(PREFIX+'/jobs/'+job['job_id'])

    def test_cookie_is_secure_private_and_session_does_not_renew_or_return_bearer(self):
        client=self.client()
        csrf=self.session(client)
        token=client.cookies.get(cookie_name(ORIGIN))
        self.assertIsNotNone(token)
        answer=client.post(PREFIX+'/session',json={},headers={'Origin':ORIGIN})
        self.assertNotIn('set-cookie',answer.headers)
        self.assertEqual(answer.json()['csrf_token'],csrf)
        self.assertNotIn(token,answer.text)
        self.assertEqual(len(self.manager.session_keys),1)
        other=self.client()
        response=other.post(PREFIX+'/session',json={},headers={'Origin':ORIGIN})
        header=response.headers['set-cookie']
        for attribute in ('__Host-affinityqa-case=', 'HttpOnly', 'Secure', 'SameSite=strict', 'Path=/'):
            self.assertIn(attribute,header)
        self.assertNotIn('Domain=',header)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(self.fixture.reads,[0,0])

    def test_two_visitors_cannot_list_read_execute_or_export_each_others_case(self):
        a,b=self.client(),self.client()
        csrf_a,csrf_b=self.session(a),self.session(b)
        job=self.plan(a,csrf_a)
        self.assertEqual(b.get(PREFIX+'/capabilities').json()['jobs'],[])
        for path in ('/jobs/'+job['job_id'], '/jobs/'+job['job_id']+'/verification'):
            self.assertEqual(b.get(PREFIX+path).status_code,404)
        response=self.post(b,'/jobs/'+job['job_id']+'/execute',csrf_b,{'plan_sha256':job['plan_sha256']})
        self.assertEqual(response.status_code,404)
        unknown=b.get(PREFIX+'/jobs/20261006T000000Z-00000000')
        self.assertEqual(unknown.json(),response.json())
        self.assertEqual(self.fixture.reads,[0,0])

    def test_csrf_origin_and_cookie_are_required_before_plan_or_start(self):
        a,b=self.client(),self.client()
        ca,cb=self.session(a),self.session(b)
        job=self.plan(a,ca)
        for csrf in ('', 'ñ', cb):
            # Non-ASCII token is delivered as latin-1 in the raw header fixture below.
            if csrf=='ñ':continue
            self.assertEqual(self.post(a,'/plans',csrf,{'artists':self.fixture.request['artists']}).status_code,403)
            self.assertEqual(self.post(a,'/jobs/'+job['job_id']+'/execute',csrf,{'plan_sha256':job['plan_sha256']}).status_code,403)
        for origin in (None,'https://attacker.example','null','http://judge.example'):
            headers={'X-AffinityQA-CSRF':ca}
            if origin is not None:headers['Origin']=origin
            self.assertEqual(a.post(PREFIX+'/plans',json={'artists':self.fixture.request['artists']},headers=headers).status_code,403)
        outsider=self.client()
        self.assertEqual(self.post(outsider,'/plans',ca,{'artists':self.fixture.request['artists']}).status_code,404)
        self.assertEqual(self.fixture.reads,[0,0])

    def test_full_http_journey_preserves_three_faults_and_filtered_verification(self):
        client=self.client();csrf=self.session(client);job=self.plan(client,csrf)
        result=self.finish(client,csrf,job)
        self.assertEqual(result.status_code,200)
        value=result.json()
        self.assertEqual((value['status'],value['saved_model_packets']),('COMPLETE',39))
        self.assertEqual(value['result']['provenance'],'SIMULATION_ONLY')
        self.assertEqual(len(value['result']['frames']),3)
        self.assertEqual(value['result']['cultural_gate'],'NOT_VALIDATED')
        self.assertEqual(value['result']['release_gate'],'BLOCKED')
        receipt=client.get(PREFIX+'/jobs/'+job['job_id']+'/verification')
        self.assertEqual(receipt.status_code,200)
        self.assertIn('attachment;',receipt.headers['content-disposition'])
        for hidden in (UNIT_SECRET,UNIT_QLOO_SECRET,str(self.fixture.parent),
                       'artifact_sha256','source_sha256','provider_envelope'):
            self.assertNotIn(hidden,receipt.text)
        self.assertEqual(self.fixture.reads,[1,1])

    def test_response_loss_does_not_make_a_second_post_admission_safe(self):
        client=self.client();csrf=self.session(client);job=self.plan(client,csrf)
        self.finish(client,csrf,job)  # Treat the accepted response as lost by the browser.
        response=self.post(client,'/jobs/'+job['job_id']+'/execute',csrf,{'plan_sha256':job['plan_sha256']})
        self.assertEqual(response.status_code,409)
        self.assertEqual(client.get(PREFIX+'/capabilities').json()['remaining_executions'],0)
        self.assertEqual(self.fixture.reads,[1,1])
        self.assertEqual(self.fixture.engines[0].calls,39)

    def test_provider_failure_is_partial_consumed_and_never_exposed_as_success(self):
        self.fixture.opener_factory=lambda:OpenerFixture(failure=HTTPError('https://unit.invalid',429,'UNIT_PRIVATE_ERROR',{},None))
        client=self.client();csrf=self.session(client);job=self.plan(client,csrf)
        result=self.finish(client,csrf,job).json()
        self.assertEqual(result['status'],'PARTIAL')
        self.assertEqual(result['result']['verified_model_packets'],0)
        receipt=client.get(PREFIX+'/jobs/'+job['job_id']+'/verification')
        self.assertEqual(receipt.status_code,200)
        self.assertNotIn('UNIT_PRIVATE_ERROR',receipt.text)
        self.assertEqual(client.get(PREFIX+'/capabilities').json()['remaining_executions'],0)

    def test_disabled_or_absent_service_never_reads_keys_or_creates_a_session(self):
        no_service=public.create_public_app(ROOT,origin=ORIGIN)
        client=self.client(no_service)
        response=client.post(PREFIX+'/session',json={},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,503)
        self.assertNotIn('set-cookie',response.headers)
        disabled=self.fixture.service(root=self.fixture.parent/'disabled',enabled=False)
        other=self.client(public.create_public_app(ROOT,origin=ORIGIN,case_manager=disabled))
        csrf=self.session(other);job=self.plan(other,csrf)
        response=self.post(other,'/jobs/'+job['job_id']+'/execute',csrf,{'plan_sha256':job['plan_sha256']})
        self.assertEqual(response.status_code,503)
        self.assertEqual(self.fixture.reads,[0,0]);self.assertEqual(self.fixture.engines,[])

    def test_expired_or_unknown_cookie_is_not_replaced_automatically(self):
        client=self.client();self.session(client)
        self.fixture.now+=timedelta(hours=24)
        response=client.post(PREFIX+'/session',json={},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,404)
        self.assertNotIn('set-cookie',response.headers)
        self.assertEqual(len(self.manager.session_keys),1)
        other=self.client();other.cookies.set(cookie_name(ORIGIN),'x'*43)
        response=other.post(PREFIX+'/session',json={},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,404)
        self.assertNotIn('set-cookie',response.headers)
        self.assertEqual(len(self.manager.session_keys),1)

    def test_cookie_ambiguity_and_critical_header_duplicates_are_rejected(self):
        client=self.client();csrf=self.session(client)
        token=client.cookies.get(cookie_name(ORIGIN));name=cookie_name(ORIGIN)
        for raw in (f'{name}={token}; {name}={token}',f'{name}={token}; broken',
                    f'other=a; other=b; {name}={token}'):
            response=client.get(PREFIX+'/capabilities',headers={'Cookie':raw})
            self.assertEqual(response.status_code,400)
            self.assertNotIn(token,response.text)
        for name,value in (('Host','judge.example'),('Origin',ORIGIN),('Cookie',f'{cookie_name(ORIGIN)}={token}'),
                           ('Content-Type','application/json'),('Content-Length','2'),('X-AffinityQA-CSRF',csrf)):
            headers=[('Origin',ORIGIN),('Content-Type','application/json')]
            headers=[item for item in headers if item[0].lower()!=name.lower()]+[(name,value),(name,value)]
            response=client.post(PREFIX+'/session',content=b'{}',headers=headers)
            self.assertEqual(response.status_code,400,name)
        self.assertEqual(len(self.manager.session_keys),1)

    def test_strict_bodies_reject_provider_urls_duplicate_json_and_unknown_fields(self):
        client=self.client();csrf=self.session(client)
        for body in ({'token':'DO_NOT_DISCLOSE'},{'origin':ORIGIN}):
            self.assertEqual(client.post(PREFIX+'/session',json=body,headers={'Origin':ORIGIN}).status_code,422)
        for body in ({'artists':{**self.fixture.request['artists'],'model_url':'https://unit.invalid'}},
                     {'artists':self.fixture.request['artists'],'policy':{}},
                     {'artists':{'A':True,'B':'Artist B'}}):
            self.assertEqual(self.post(client,'/plans',csrf,body).status_code,422)
        raw=b'{"artists":{"A":"Artist A","A":"Artist B","B":"Artist C"}}'
        self.assertEqual(client.post(PREFIX+'/plans',content=raw,headers={
            'Origin':ORIGIN,'Content-Type':'application/json','X-AffinityQA-CSRF':csrf}).status_code,422)
        self.assertEqual(self.manager.manager.jobs,{})

    def test_separate_global_http_quotas_leave_replay_and_liveness_available(self):
        app=public.create_public_app(ROOT,origin=ORIGIN,case_manager=self.manager,
                                     case_session_limit=1,case_write_limit=1,case_read_limit=1)
        client=self.client(app);csrf=self.session(client)
        self.assertEqual(client.post(PREFIX+'/session',json={},headers={'Origin':ORIGIN}).status_code,429)
        job=self.plan(client,csrf)
        self.assertEqual(self.post(client,'/plans',csrf,{'artists':self.fixture.request['artists']}).status_code,429)
        self.assertEqual(client.get(PREFIX+'/jobs/'+job['job_id']).status_code,200)
        self.assertEqual(client.get(PREFIX+'/capabilities').status_code,429)
        self.assertEqual(client.get('/healthz').status_code,200)
        self.assertEqual(client.get('/api/demo/summary').status_code,200)
        self.assertEqual(self.fixture.reads,[0,0])

    def test_shared_execution_budget_cannot_be_reset_by_new_browser(self):
        self.manager.close()
        manager=self.fixture.service(root=self.fixture.parent/'shared',policy=self.fixture.policy(maximum_executions=1))
        self.manager=manager
        self.app=public.create_public_app(ROOT,origin=ORIGIN,case_manager=manager)
        a=self.client();ca=self.session(a);first=self.plan(a,ca);self.finish(a,ca,first)
        b=self.client();cb=self.session(b);second=self.plan(b,cb)
        self.assertEqual(self.post(b,'/jobs/'+second['job_id']+'/execute',cb,{'plan_sha256':second['plan_sha256']}).status_code,429)
        self.assertEqual(self.fixture.reads,[1,1])

    def test_read_only_storage_failure_and_wrong_plan_do_not_expose_private_errors(self):
        client=self.client();csrf=self.session(client);job=self.plan(client,csrf)
        response=self.post(client,'/jobs/'+job['job_id']+'/execute',csrf,{'plan_sha256':'0'*64})
        self.assertEqual(response.status_code,409)
        self.manager._mutations_blocked=True
        response=self.post(client,'/jobs/'+job['job_id']+'/execute',csrf,{'plan_sha256':job['plan_sha256']})
        self.assertEqual(response.status_code,503)
        self.assertEqual(client.get(PREFIX+'/jobs/'+job['job_id']).status_code,200)
        self.assertEqual(self.fixture.reads,[0,0])
        self.assertNotIn(str(self.fixture.parent),response.text)

    def test_health_is_cheap_and_does_not_attest_provider_or_cultural_readiness(self):
        with patch.object(self.manager,'capabilities',side_effect=AssertionError('Liveness must not verify records')):
            health=self.client().get('/healthz').json()
        self.assertTrue(health['new_cases_configured'])
        self.assertEqual(health['provider_readiness'],'NOT_CHECKED_BY_LIVENESS')
        self.assertFalse(health['capture_active'])
        self.assertTrue(health['remote_execution_configured'])
        self.assertFalse(health['admissions_blocked'])
        self.manager._mutations_blocked=True
        blocked=self.client().get('/healthz').json()
        self.assertTrue(blocked['remote_execution_configured'])
        self.assertTrue(blocked['admissions_blocked'])
        self.assertNotIn('live_inference',health)
        self.assertEqual(self.fixture.reads,[0,0])

    def test_private_routes_slash_redirects_and_url_token_transfer_are_unavailable(self):
        client=self.client();csrf=self.session(client)
        for uri in ('/api/individual/capabilities','/api/individual/plans','/.env','/docs',
                    '/api/demo/cases/session/','/api/demo/cases/jobs'):
            response=client.get(uri)
            self.assertIn(response.status_code,(404,405));self.assertNotIn('location',response.headers)
        response=client.get(PREFIX+'/capabilities?token=DO_NOT_DISCLOSE')
        self.assertEqual(response.status_code,400);self.assertNotIn('DO_NOT_DISCLOSE',response.text)
        response=client.post(PREFIX+'/session/',json={},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,404);self.assertNotIn('location',response.headers)

    def test_public_replay_does_not_require_session_csrf_or_cloud_keys(self):
        with patch.object(public,'_Capture',SyntheticCapture):
            app=public.create_public_app(ROOT,origin=ORIGIN,case_manager=self.manager,
                run_id='20261004T000000Z-00000000',receipt_sha256='c'*64)
        response=self.client(app).post('/api/demo/replay',json={
            'pair_id':'causal-validation-01','fault':'stale-profile','repeat':1},headers={'Origin':ORIGIN})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.fixture.reads,[0,0]);self.assertEqual(self.manager.session_keys,set())

    def test_lifespan_closes_shared_manager_and_http_loopback_cookie_has_separate_name(self):
        with TestClient(self.app,base_url=ORIGIN) as client:
            self.assertEqual(client.get('/healthz').status_code,200)
        self.assertTrue(self.manager.manager.closed)
        loop_origin='http://127.0.0.1:8798'
        from affinityqa.public_cases import PublicCaseManager
        service=PublicCaseManager(self.fixture.parent/'loopback',self.fixture.request,origin=loop_origin,
            policy=self.fixture.policy(),minimum_model_interval_seconds=0,execution_enabled=False)
        self.addCleanup(service.close)
        app=public.create_public_app(ROOT,origin=loop_origin,case_manager=service)
        client=self.client(app,base=loop_origin)
        response=client.post(PREFIX+'/session',json={},headers={'Origin':loop_origin})
        self.assertEqual(response.status_code,200,response.text)
        cookie=response.headers['set-cookie']
        self.assertIn('affinityqa-loopback-case=',cookie)
        self.assertNotIn('__Host-',cookie);self.assertNotIn('Secure',cookie)

    def test_manager_origin_and_request_budget_must_be_explicitly_consistent(self):
        with self.assertRaises(ValueError):public.create_public_app(ROOT,origin='https://other.example',case_manager=self.manager)
        for value in (True,0,601):
            with self.assertRaises(ValueError):public.create_public_app(ROOT,origin=ORIGIN,case_read_limit=value)
        self.assertEqual(self.fixture.reads,[0,0])


class PublicCaseBodyBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def scope(self,path=PREFIX+'/session'):
        return {'type':'http','method':'POST','path':path,'query_string':b'',
            'headers':[(b'host',b'judge.example'),(b'origin',ORIGIN.encode()),(b'content-type',b'application/json')]}

    async def dispatch(self,boundary,scope,receive):
        messages=[]
        async def send(message):messages.append(message)
        await boundary(scope,receive,send)
        return messages

    async def test_case_session_body_timeout_reserves_its_own_request_slot(self):
        async def app(scope,receive,send):self.fail('Unfinished body reached router.')
        boundary=public._Boundary(app,origin=ORIGIN,case_session_limit=1,read_timeout=.02)
        async def stalled():await asyncio.Future()
        first=await self.dispatch(boundary,self.scope(),stalled)
        self.assertEqual(first[0]['status'],408)
        async def forbidden():self.fail('Exhausted slot read another body.')
        second=await self.dispatch(boundary,self.scope(),forbidden)
        self.assertEqual(second[0]['status'],429)
        self.assertTrue(boundary.readers.acquire(blocking=False));boundary.readers.release()
        self.assertEqual(len(boundary.replay_times),0)

    async def test_streamed_case_body_size_framing_and_header_bounds_precede_router(self):
        async def app(scope,receive,send):self.fail('Invalid request reached router.')
        boundary=public._Boundary(app,origin=ORIGIN)
        async def large():return {'type':'http.request','body':b'x'*4097,'more_body':False}
        self.assertEqual((await self.dispatch(boundary,self.scope(PREFIX+'/plans'),large))[0]['status'],413)
        for extra in ([(b'content-length',b'3')],[(b'content-length',b'2'),(b'transfer-encoding',b'chunked')],
                      [(b'x-affinityqa-csrf',b'a'*64),(b'x-affinityqa-csrf',b'a'*64)],
                      [(b'excessive',b'x'*8192)]):
            scope=self.scope();scope['headers']+=extra
            async def body():return {'type':'http.request','body':b'{}','more_body':False}
            messages=await self.dispatch(boundary,scope,body)
            self.assertIn(messages[0]['status'],(400,431))

    async def test_non_ascii_csrf_is_denied_without_comparison_error(self):
        fixture=http_fixture()
        try:
            manager=fixture.service();token,_=manager.session()
            app=public.create_public_app(ROOT,origin=ORIGIN,case_manager=manager)
            scope=self.scope(PREFIX+'/plans')
            scope.update(http_version='1.1',scheme='https',server=('judge.example',443),
                         client=('127.0.0.1',1),root_path='')
            scope['headers'] += [(b'cookie',f'{cookie_name(ORIGIN)}={token}'.encode()),(b'x-affinityqa-csrf',b'\xf1')]
            async def body():return {'type':'http.request','body':json.dumps({'artists':fixture.request['artists']}).encode(),'more_body':False}
            messages=await self.dispatch(app,scope,body)
            self.assertEqual(messages[0]['status'],403)
            self.assertEqual(fixture.reads,[0,0])
        finally:fixture.doCleanups()


if __name__=='__main__':unittest.main()
