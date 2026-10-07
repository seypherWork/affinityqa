"""Adversarial local-panel tests. Every provider/model adapter is synthetic."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from affinityqa.api import create_app
from affinityqa.errors import SchemaError
from affinityqa.individual_jobs import IndividualJobManager
from affinityqa.qloo import Settings
from test_individual_capture import fixture, TransportDouble
from test_individual_verify import AuditEngine, RegressiveAuditEngine, InterruptedAuditEngine

async def asgi(app,method,path,body=None,origin='http://127.0.0.1:8794'):
    headers=[(b'host',b'127.0.0.1:8794'),(b'content-type',b'application/json')]
    if origin is not None:headers.append((b'origin',origin.encode()))
    scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':path,
        'raw_path':path.encode(),'query_string':b'','root_path':'','headers':headers,'client':('127.0.0.1',1),'server':('127.0.0.1',8794)}
    messages=[]
    async def receive():return {'type':'http.request','body':json.dumps(body).encode() if body is not None else b'','more_body':False}
    async def send(value):messages.append(value)
    await app(scope,receive,send)
    start=next(v for v in messages if v['type']=='http.response.start')
    return start['status'],json.loads(b''.join(v.get('body',b'') for v in messages if v['type']=='http.response.body')),dict(start['headers'])

class IndividualJobTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'.test-runs';parent.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.temp.cleanup)
        self.parent=Path(self.temp.name);self.request=fixture();self.reads=0;self.engines=[]
        self.transport_fail=False;self.engine_type=AuditEngine
        self.addCleanup(patch.stopall)
        patch('affinityqa.individual_capture.time.sleep').start()
        # Windows asyncio opens its own loopback pipe; block provider factories/DNS,
        # while every admitted capture receives explicitly labelled synthetic adapters.
        for target in ('socket.create_connection','socket.getaddrinfo',
                       'affinityqa.individual_capture.ToolContextMovieAgent',
                       'affinityqa.individual_capture.LiveTransport'):
            patch(target,side_effect=AssertionError('No provider network or DNS')).start()
    def loader(self):self.reads+=1;return Settings('unit-key-only')
    def engine(self):
        value=self.engine_type();self.engines.append(value);return value
    def manager(self,enabled=True,root=None,adapters=True):
        value=IndividualJobManager(root or self.parent/'jobs',self.request,'http://127.0.0.1:11434',
            execution_enabled=enabled,settings_loader=self.loader,
            _test_adapters=(self.engine,lambda:TransportDouble(self.request,fail=self.transport_fail)) if adapters else None)
        self.addCleanup(value.close);return value
    def plan(self,m):return m.prepare(self.request['artists'])
    def finish(self,m,j):
        m.start(j['job_id'],j['plan_sha256']);m.worker.join(timeout=15)
        self.assertFalse(m.worker.is_alive());return m.view(j['job_id'])
    def test_preview_has_no_credentials_adapters_or_capture(self):
        m=self.manager();j=self.plan(m)
        self.assertEqual((j['status'],self.reads,len(self.engines)),('PLANNED',0,0))
        self.assertFalse((m.root/j['job_id']/'capture').exists())
    def test_complete_verified_frames_receipt_and_simulation_label(self):
        m=self.manager();j=self.finish(m,self.plan(m));r=j['result']
        self.assertEqual(j['status'],'COMPLETE')
        self.assertEqual((j['saved_provider_samples'],j['saved_model_packets']),(4,39))
        self.assertEqual((r['provenance'],r['causal_gate'],r['behavioral_gate']),('SIMULATION_ONLY','PASS','OBSERVED_RECOVERY'))
        self.assertEqual((r['cultural_gate'],r['release_gate']),('NOT_VALIDATED','BLOCKED'))
        self.assertEqual((len(r['frames']),len(r['frames'][0]['repeats'])),(3,3))
        self.assertFalse(m.receipt(j['job_id'])['external_service_attested'])
        self.assertNotIn('unit-key-only',json.dumps(j))
    def test_complete_causal_failure_is_displayed(self):
        self.engine_type=RegressiveAuditEngine;m=self.manager();j=self.finish(m,self.plan(m))
        self.assertEqual(j['status'],'COMPLETE');self.assertEqual(j['result']['causal_gate'],'FAIL')
        self.assertEqual(j['result']['behavioral_gate'],'INCONCLUSIVE')
    def test_provider_and_model_interruption_preserve_partials(self):
        for kind in ('provider','model'):
            with self.subTest(kind=kind):
                self.transport_fail=kind=='provider';self.engine_type=InterruptedAuditEngine if kind=='model' else AuditEngine
                m=self.manager(root=self.parent/kind);j=self.finish(m,self.plan(m))
                self.assertEqual(j['status'],'PARTIAL');self.assertEqual(j['result']['causal_gate'],'NOT_EVALUATED')
                self.assertEqual(j['error_class'],'TransportError')
                with self.assertRaises(SchemaError):m.start(j['job_id'],j['plan_sha256'])
    def test_disabled_wrong_hash_and_repeated_execution_rejected(self):
        m=self.manager(enabled=False);j=self.plan(m)
        with self.assertRaises(SchemaError):m.start(j['job_id'],j['plan_sha256'])
        m.enabled=True
        with self.assertRaises(SchemaError):m.start(j['job_id'],'a'*64)
        self.assertEqual(self.reads,0);self.finish(m,j)
        with self.assertRaises(SchemaError):m.start(j['job_id'],j['plan_sha256'])
        self.assertEqual(self.reads,1)
    def test_concurrent_work_rejected_before_second_credential_read(self):
        gate,entered=Event(),Event();base=self.engine
        def held():entered.set();gate.wait(timeout=10);return base()
        m=self.manager();m.adapters=(held,lambda:TransportDouble(self.request));a,b=self.plan(m),self.plan(m)
        m.start(a['job_id'],a['plan_sha256']);self.assertTrue(entered.wait(timeout=5))
        try:
            with self.assertRaises(SchemaError):m.start(b['job_id'],b['plan_sha256'])
            self.assertEqual(self.reads,1)
        finally:gate.set();m.worker.join(timeout=15)
    def test_second_manager_cannot_share_active_storage(self):
        m=self.manager()
        with self.assertRaises(SchemaError):self.manager(root=m.root)
    def test_saved_plan_and_capture_tampering_not_admitted(self):
        m=self.manager();j=self.plan(m);p=m.root/j['job_id']/'job-plan.json';old=p.read_bytes()
        value=json.loads(old);value['plan']['request']['artists']['A']='Changed';p.write_text(json.dumps(value),'utf-8')
        with self.assertRaises(SchemaError):m.start(j['job_id'],j['plan_sha256'])
        self.assertEqual(self.reads,0);p.write_bytes(old);self.finish(m,j)
        p=m._capture_dir(j['job_id'])/'individual-report.json';p.write_bytes(p.read_bytes()+b' ')
        view=m.view(j['job_id']);self.assertEqual(view['status'],'EVIDENCE_CHANGED');self.assertIsNone(view['result'])
        with self.assertRaises(SchemaError):m.receipt(j['job_id'])
    def test_changed_receipt_hides_result(self):
        m=self.manager();j=self.finish(m,self.plan(m));p=m.root/j['job_id']/'verification.json'
        p.write_bytes(p.read_bytes()+b' ');self.assertEqual(m.view(j['job_id'])['status'],'EVIDENCE_CHANGED')
    def test_restart_abandons_unfinished_and_never_resumes(self):
        m=self.manager();j=self.plan(m);m._event(j['job_id'],'STARTED');m.close();r=self.manager(root=m.root)
        self.assertEqual(r.view(j['job_id'])['status'],'ABANDONED');self.assertEqual(r.capabilities()['remaining_executions'],2)
        with self.assertRaises(SchemaError):r.start(j['job_id'],j['plan_sha256'])
        self.assertEqual(self.reads,0);self.assertTrue((m.root/j['job_id']/'event-0001.json').is_file())
    def test_restart_retains_simulation_even_without_test_adapters(self):
        m=self.manager();j=self.finish(m,self.plan(m));m.close();r=self.manager(enabled=False,root=m.root,adapters=False)
        self.assertTrue(r.view(j['job_id'])['simulation_only']);self.assertEqual(self.reads,1)
    def test_three_execution_limit_survives_restart(self):
        self.transport_fail=True;m=self.manager()
        for _ in range(3):self.finish(m,self.plan(m))
        j=self.plan(m)
        with self.assertRaises(SchemaError):m.start(j['job_id'],j['plan_sha256'])
        m.close();r=self.manager(root=m.root);self.assertEqual(r.capabilities()['remaining_executions'],0)
        with self.assertRaises(SchemaError):r.start(j['job_id'],j['plan_sha256'])
    def test_invalid_interests_make_no_plan(self):
        m=self.manager()
        for artists in ({'A':'Same','B':'same'},{'A':' extra ','B':'Unit pop'},{'A':'\n','B':'Unit pop'},{'A':'Unit jazz','B':'Unit pop','key':'secret'}):
            with self.subTest(artists=artists),self.assertRaises(SchemaError):m.prepare(artists)
        self.assertEqual(m.capabilities()['remaining_plans'],20)
    def call(self,m):
        app=create_app(ROOT,store_root=self.parent/'backend',individual_manager=m)
        return lambda method,path,**kw:asyncio.run(asgi(app,method,path,**kw))
    def test_api_origin_schema_disabled_execution_and_route_visibility(self):
        m=self.manager(enabled=False);call=self.call(m)
        self.assertEqual(call('GET','/api/individual/capabilities')[0],200)
        for origin in (None,'http://evil.invalid','null'):
            self.assertEqual(call('POST','/api/individual/plans',body={'artists':self.request['artists']},origin=origin)[0],403)
        status,body,_=call('POST','/api/individual/plans',body={'artists':self.request['artists'],'QLOO_API_KEY':'DO_NOT_ECHO'})
        self.assertEqual(status,422);self.assertNotIn('DO_NOT_ECHO',json.dumps(body))
        status,j,headers=call('POST','/api/individual/plans',body={'artists':self.request['artists']})
        self.assertEqual(status,201);self.assertEqual(headers[b'cache-control'],b'no-store')
        self.assertEqual(call('POST',f"/api/individual/jobs/{j['job_id']}/execute",body={'plan_sha256':j['plan_sha256']})[0],422)
        self.assertEqual(self.reads,0)
    def test_api_complete_and_fixed_verification_download(self):
        m=self.manager();call=self.call(m);_,j,_=call('POST','/api/individual/plans',body={'artists':self.request['artists']})
        self.assertEqual(call('POST',f"/api/individual/jobs/{j['job_id']}/execute",body={'plan_sha256':j['plan_sha256']})[0],202)
        m.worker.join(timeout=15);status,v,_=call('GET',f"/api/individual/jobs/{j['job_id']}")
        self.assertEqual((status,v['status']),(200,'COMPLETE'))
        status,r,headers=call('GET',f"/api/individual/jobs/{j['job_id']}/verification")
        self.assertEqual((status,r['provenance']),(200,'SIMULATION_ONLY'));self.assertIn(b'attachment',headers[b'content-disposition'])
        self.assertEqual(call('GET','/api/individual/jobs/not-a-job')[0],422)
    def test_unconfigured_api_cannot_prepare_or_execute(self):
        call=self.call(None)
        status,cap,_=call('GET','/api/individual/capabilities')
        self.assertEqual(status,200);self.assertFalse(cap['configured'])
        self.assertEqual(call('POST','/api/individual/plans',body={'artists':self.request['artists']})[0],503)
        self.assertEqual(self.reads,0)
    def test_twenty_plan_limit(self):
        m=self.manager()
        for _ in range(20):self.plan(m)
        with self.assertRaises(SchemaError):self.plan(m)
        self.assertEqual(self.reads,0);self.assertEqual(m.capabilities()['remaining_plans'],0)
    def test_thread_launch_failure_retained_without_execution(self):
        m=self.manager();j=self.plan(m)
        with patch('affinityqa.individual_jobs.Thread.start',side_effect=RuntimeError('Synthetic launch failure')):
            with self.assertRaises(RuntimeError):m.start(j['job_id'],j['plan_sha256'])
        self.assertEqual(m.view(j['job_id'])['status'],'FAILED');self.assertEqual(len(self.engines),0)
    def test_integrity_race_after_receipt_hides_all_results(self):
        m=self.manager();j=self.finish(m,self.plan(m))
        from affinityqa.individual_jobs import inventory
        good=inventory(m._capture_dir(j['job_id']))
        with patch('affinityqa.individual_jobs.inventory',side_effect=[good,{}]):
            view=m.view(j['job_id'])
        self.assertEqual(view['status'],'EVIDENCE_CHANGED');self.assertIsNone(view['result'])
        self.assertNotIn('receipt_sha256',view)
    def test_close_captures_concurrently_admitted_worker_before_releasing_lease(self):
        m=self.manager();j=self.plan(m)
        class Worker:
            joined=False
            def start(self):pass
            def join(self):self.joined=True
            def is_alive(self):return not self.joined
        worker=Worker();real=m.lock
        class LockHook:
            called=False
            def __enter__(inner):
                real.__enter__()
                if not inner.called:
                    inner.called=True
                    m.start(j['job_id'],j['plan_sha256'])
            def __exit__(inner,*args):return real.__exit__(*args)
        m.lock=LockHook()
        with patch('affinityqa.individual_jobs.Thread',return_value=worker):m.close()
        self.assertTrue(worker.joined)
    def test_cli_preview_configuration_never_reads_credentials(self):
        from affinityqa.cli import main
        template=self.parent/'template.json';template.write_text(json.dumps(self.request),'utf-8')
        seen=[]
        def serve(app,**kwargs):
            seen.append(asyncio.run(asgi(app,'GET','/api/individual/capabilities'))[1])
        with patch('uvicorn.run',side_effect=serve),patch('affinityqa.qloo.Settings.from_environment',side_effect=AssertionError('No credential loading')):
            result=main(['serve','--port','8794','--store',str(self.parent/'backend'),
                '--individual-template',str(template),'--individual-output',str(self.parent/'cli-jobs'),
                '--ollama-url','http://127.0.0.1:11434'])
        self.assertEqual(result,0);self.assertTrue(seen[0]['configured']);self.assertFalse(seen[0]['execution_enabled'])
    def test_cli_enabled_configuration_requires_explicit_plan_not_startup_execution(self):
        from affinityqa.cli import main
        template=self.parent/'template.json';template.write_text(json.dumps(self.request),'utf-8')
        seen=[]
        def serve(app,**kwargs):seen.append(asyncio.run(asgi(app,'GET','/api/individual/capabilities'))[1])
        with patch('uvicorn.run',side_effect=serve),patch('affinityqa.qloo.Settings.from_environment',side_effect=AssertionError('No credential loading')):
            result=main(['serve','--port','8794','--store',str(self.parent/'backend'),
                '--individual-template',str(template),'--individual-output',str(self.parent/'cli-jobs'),
                '--ollama-url','http://127.0.0.1:11434','--individual-local-enabled','--env-file',str(self.parent/'.env-not-present')])
        self.assertEqual(result,0);self.assertTrue(seen[0]['execution_enabled']);self.assertEqual(seen[0]['jobs'],[])
    def test_restored_partial_displays_receipt_error_even_if_old_journal_omitted_it(self):
        self.transport_fail=True;m=self.manager();j=self.finish(m,self.plan(m));m.close()
        p=m.root/j['job_id']/'event-0003.json';v=json.loads(p.read_bytes());v['error_class']=None
        p.write_text(json.dumps(v),'utf-8')
        r=self.manager(enabled=False,root=m.root,adapters=False)
        self.assertEqual(r.view(j['job_id'])['error_class'],'TransportError')

if __name__=='__main__':unittest.main()
