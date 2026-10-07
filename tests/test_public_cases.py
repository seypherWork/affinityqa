"""Anonymous ownership and persistent budget contracts, with denied providers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
import tempfile
from threading import Event
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.errors import SchemaError
from affinityqa.groq_agent import GroqToolContextMovieAgent
from affinityqa.public_cases import PublicCaseManager,public_policy
from affinityqa.qloo import Settings
from test_groq_agent import OpenerFixture,UNIT_SECRET,UNIT_QLOO_SECRET
from test_individual_capture import TransportDouble
from test_individual_remote import request_fixture


class PublicCasesTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'.test-runs';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temp.cleanup)
        self.parent=Path(self.temp.name);self.request=request_fixture()
        self.reads=[0,0];self.engines=[];self.opener_factory=OpenerFixture
        self.now=datetime(2026,10,6,14,0,tzinfo=timezone.utc)
        for target in ('socket.socket','socket.create_connection','socket.getaddrinfo',
                       'affinityqa.individual_remote_capture.LiveTransport'):
            guard=patch(target,side_effect=AssertionError('Actual provider and DNS forbidden'))
            guard.start();self.addCleanup(guard.stop)

    def policy(self,**changes):
        values=dict(maximum_sessions=8,maximum_plans=10,maximum_executions=4,
                    plans_per_session=2,executions_per_session=1,session_hours=24)
        return public_policy(**{**values,**changes})

    def settings(self):self.reads[0]+=1;return Settings(UNIT_QLOO_SECRET)
    def key(self):self.reads[1]+=1;return UNIT_SECRET
    def engine(self):
        engine=GroqToolContextMovieAgent(UNIT_SECRET,forbidden_secrets=(UNIT_QLOO_SECRET,),_test_opener=self.opener_factory())
        self.engines.append(engine);return engine

    def service(self,root=None,policy=None,enabled=True,interval=0):
        service=PublicCaseManager(root or self.parent/'public',self.request,origin='https://judge.example',
            policy=policy or self.policy(),minimum_model_interval_seconds=interval,execution_enabled=enabled,
            settings_loader=self.settings,remote_key_loader=self.key,
            _test_adapters=(self.engine,lambda:TransportDouble(self.request)),_test_now=lambda:self.now)
        self.addCleanup(service.close);return service

    def visitor(self,service):
        token,info=service.session();service.authorize_mutation(token,info['csrf_token'])
        return token

    def finish(self,service,token,job):
        service.start(token,job['job_id'],job['plan_sha256'])
        service.manager.worker.join(timeout=15)
        self.assertFalse(service.manager.worker.is_alive())
        return service.view(token,job['job_id'])

    def test_policy_is_explicit_closed_and_bounded(self):
        for change in ({'maximum_sessions':True},{'maximum_sessions':10001},
                       {'maximum_plans':0},{'maximum_executions':11},
                       {'executions_per_session':3},{'session_hours':169}):
            with self.subTest(change=change),self.assertRaises(SchemaError):self.policy(**change)
        policy=self.policy();policy['provider_quota_or_cost_reserved']=True
        with self.assertRaises(SchemaError):self.service(policy=policy)
        self.assertFalse((self.parent/'public').exists())

    def test_preview_and_visitor_isolation_read_no_keys_and_persist_no_tokens(self):
        service=self.service(enabled=False);a=self.visitor(service);b=self.visitor(service)
        job=service.prepare(a,self.request['artists'])
        self.assertEqual(service.capabilities(b)['jobs'],[])
        for action in (lambda:service.view(b,job['job_id']),
                       lambda:service.start(b,job['job_id'],job['plan_sha256']),
                       lambda:service.verification(b,job['job_id'])):
            with self.assertRaises(FileNotFoundError):action()
        self.assertEqual(self.reads,[0,0]);self.assertEqual(self.engines,[])
        serialized=''.join(path.read_text(encoding='utf-8') for path in service.root.rglob('*.json'))
        for token in (a,b):self.assertNotIn(token,serialized)
        self.assertNotIn(service.session(a)[1]['csrf_token'],serialized)

    def test_mutation_token_is_session_specific_and_not_sufficient_for_other_case(self):
        service=self.service();a,first=service.session();b,second=service.session()
        self.assertNotEqual(first['csrf_token'],second['csrf_token'])
        for token,csrf in ((a,None),(a,'ñ'),(a,second['csrf_token']),('x'*43,first['csrf_token'])):
            with self.assertRaises((SchemaError,FileNotFoundError)):service.authorize_mutation(token,csrf)
        self.assertEqual(self.reads,[0,0])

    def test_complete_case_retains_full_protocol_and_filters_private_receipt(self):
        service=self.service();token=self.visitor(service)
        job=self.finish(service,token,service.prepare(token,self.request['artists']))
        self.assertEqual((job['status'],job['saved_model_packets']),('COMPLETE',39))
        self.assertEqual(job['result']['provenance'],'SIMULATION_ONLY')
        self.assertEqual(len(job['result']['frames']),3)
        public=service.verification(token,job['job_id']);text=json.dumps(public)
        for forbidden in (UNIT_SECRET,UNIT_QLOO_SECRET,str(self.parent),'artifact_sha256','source_sha256','provider_envelope'):
            self.assertNotIn(forbidden,text)
        self.assertEqual(public['result']['cultural_gate'],'NOT_VALIDATED')
        self.assertEqual(self.reads,[1,1])

    def test_failed_capture_consumes_budget_and_preserves_verified_partial(self):
        self.opener_factory=lambda:OpenerFixture(failure=HTTPError('https://unit.invalid',429,'unit failure',{},None))
        service=self.service();token=self.visitor(service)
        job=self.finish(service,token,service.prepare(token,self.request['artists']))
        self.assertEqual(job['status'],'PARTIAL')
        self.assertEqual(job['result']['verified_model_packets'],0)
        self.assertEqual(service.capabilities(token)['remaining_executions'],0)
        self.assertEqual(self.engines[0].calls,1)

    def test_new_sessions_cannot_multiply_shared_global_budget(self):
        service=self.service(policy=self.policy(maximum_executions=1));a=self.visitor(service)
        self.finish(service,a,service.prepare(a,self.request['artists']))
        b=self.visitor(service);job=service.prepare(b,self.request['artists'])
        with self.assertRaises(SchemaError):service.start(b,job['job_id'],job['plan_sha256'])
        self.assertEqual(service.capabilities(b)['remaining_executions'],0)
        self.assertEqual((self.reads,len(self.engines)),([1,1],1))

    def test_per_session_plans_and_executions_have_separate_bounds(self):
        service=self.service();token=self.visitor(service)
        self.finish(service,token,service.prepare(token,self.request['artists']))
        another=service.prepare(token,self.request['artists'])
        with self.assertRaises(SchemaError):service.start(token,another['job_id'],another['plan_sha256'])
        with self.assertRaises(SchemaError):service.prepare(token,self.request['artists'])
        self.assertEqual(self.reads,[1,1])

    def test_restart_keeps_ownership_receipt_and_consumed_admission(self):
        service=self.service(policy=self.policy(maximum_executions=1));token=self.visitor(service)
        job=self.finish(service,token,service.prepare(token,self.request['artists']))
        service.close();restored=self.service(root=service.root,policy=self.policy(maximum_executions=1))
        self.assertEqual(restored.view(token,job['job_id'])['status'],'COMPLETE')
        self.assertEqual(restored.capabilities(token)['remaining_executions'],0)
        self.assertEqual(self.reads,[1,1])

    def test_server_restart_abandons_reserved_capture_without_refund_or_resume(self):
        service=self.service(policy=self.policy(maximum_executions=1));token=self.visitor(service)
        job=service.prepare(token,self.request['artists'])
        service.manager._event(job['job_id'],'STARTED')
        service.close();restored=self.service(root=service.root,policy=self.policy(maximum_executions=1))
        self.assertEqual(restored.view(token,job['job_id'])['status'],'ABANDONED')
        self.assertEqual(restored.capabilities(token)['remaining_executions'],0)
        self.assertEqual(self.reads,[0,0]);self.assertEqual(self.engines,[])

    def test_worker_launch_failure_is_reserved_and_cannot_retry(self):
        service=self.service();token=self.visitor(service);job=service.prepare(token,self.request['artists'])
        with patch('affinityqa.individual_jobs.Thread.start',side_effect=RuntimeError('unit launch failure')):
            with self.assertRaises(RuntimeError):service.start(token,job['job_id'],job['plan_sha256'])
        self.assertEqual(service.view(token,job['job_id'])['status'],'FAILED')
        self.assertEqual(service.capabilities(token)['remaining_executions'],0)
        self.assertEqual(self.engines,[])

    def test_failed_admission_flush_blocks_following_capture_before_dispatch(self):
        service=self.service(policy=self.policy(maximum_executions=1))
        a=self.visitor(service);b=self.visitor(service)
        first=service.prepare(a,self.request['artists']);second=service.prepare(b,self.request['artists'])
        with patch('affinityqa.individual_jobs.os.fsync',side_effect=OSError('unit admission flush failure')):
            with self.assertRaises(OSError):service.start(a,first['job_id'],first['plan_sha256'])
        self.assertEqual(self.engines,[])
        with self.assertRaisesRegex(SchemaError,'blocked'):service.start(b,second['job_id'],second['plan_sha256'])
        self.assertEqual(self.reads,[1,1]);self.assertEqual(self.engines,[])

    def test_last_global_admission_is_atomic_under_competing_visitors(self):
        gate=Event()
        class GatedOpener(OpenerFixture):
            def open(self,request,timeout):
                if not self.calls and not gate.wait(5):raise AssertionError('Fixture gate timeout')
                return super().open(request,timeout)
        self.opener_factory=GatedOpener
        service=self.service(policy=self.policy(maximum_executions=1));tokens=[self.visitor(service) for _ in range(2)]
        jobs=[service.prepare(token,self.request['artists']) for token in tokens]
        def start(index):
            try:service.start(tokens[index],jobs[index]['job_id'],jobs[index]['plan_sha256']);return True
            except SchemaError:return False
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:accepted=list(pool.map(start,(0,1)))
            self.assertEqual(sum(accepted),1)
            self.assertEqual(sum(job['sequence']>0 for job in service.manager.jobs.values()),1)
        finally:gate.set()
        service.manager.worker.join(timeout=15)
        self.assertFalse(service.manager.worker.is_alive());self.assertEqual(self.reads,[1,1])

    def test_changed_policy_or_active_second_instance_cannot_reset_budget(self):
        service=self.service();path=service.root/'public-policy.json';before=path.read_bytes()
        with self.assertRaises((SchemaError,OSError)):self.service(root=service.root)
        service.close()
        with self.assertRaises(SchemaError):self.service(root=service.root,policy=self.policy(maximum_executions=5))
        self.assertEqual(path.read_bytes(),before);self.assertEqual(self.reads,[0,0])

    def test_expired_session_is_rejected_without_automatic_replacement(self):
        service=self.service();token=self.visitor(service);count=len(service.session_keys)
        self.now+=timedelta(hours=25)
        with self.assertRaises(FileNotFoundError):service.session(token)
        self.assertEqual(len(service.session_keys),count)

    def test_session_capacity_and_missing_cadence_stop_before_provider_access(self):
        service=self.service(policy=self.policy(maximum_sessions=1));self.visitor(service)
        with self.assertRaises(SchemaError):service.session()
        with self.assertRaises(SchemaError):self.service(root=self.parent/'unconfigured',interval=None)
        self.assertFalse((self.parent/'unconfigured').exists());self.assertEqual(self.reads,[0,0])

    def test_failed_session_flush_blocks_same_process_mutations_and_keeps_reads(self):
        service=self.service(policy=self.policy(maximum_sessions=2));token=self.visitor(service)
        job=service.prepare(token,self.request['artists'])
        with patch('affinityqa.individual_jobs.os.fsync',side_effect=OSError('unit session flush failure')):
            with self.assertRaises(OSError):service.session()
        self.assertEqual(len(list(service.sessions.iterdir())),2)
        with self.assertRaisesRegex(SchemaError,'blocked'):service.session()
        with self.assertRaisesRegex(SchemaError,'blocked'):service.prepare(token,self.request['artists'])
        with self.assertRaisesRegex(SchemaError,'blocked'):service.start(token,job['job_id'],job['plan_sha256'])
        self.assertEqual(service.view(token,job['job_id'])['status'],'PLANNED')
        self.assertTrue(service.capabilities(token)['admissions_blocked'])
        self.assertFalse(service.capabilities(token)['execution_enabled'])
        self.assertEqual(self.reads,[0,0]);self.assertEqual(self.engines,[])

    def test_changed_ownership_and_orphaned_plans_fail_closed(self):
        service=self.service();a=self.visitor(service);b=self.visitor(service)
        job=service.prepare(a,self.request['artists']);path=service.owners/(job['job_id']+'.json')
        before=path.read_bytes();owner=json.loads(before);owner['session_sha256']=next(key for key in service.session_keys if key!=service.job_owners[job['job_id']])
        path.write_text(json.dumps(owner),encoding='utf-8')
        with self.assertRaises(SchemaError):service.capabilities(a)
        with self.assertRaises(FileNotFoundError):service.view(b,job['job_id'])
        path.write_bytes(before)
        with patch('affinityqa.public_cases.write',side_effect=OSError('unit ownership commit failure')):
            with self.assertRaises(OSError):service.prepare(a,self.request['artists'])
        self.assertEqual(len(service.manager.jobs),2);self.assertEqual(self.reads,[0,0])
        with self.assertRaisesRegex(SchemaError,'blocked'):service.prepare(a,self.request['artists'])
        with self.assertRaisesRegex(SchemaError,'blocked'):service.start(a,job['job_id'],job['plan_sha256'])
        self.assertEqual(len(service.manager.jobs),2);self.assertEqual(self.reads,[0,0])
        service.close()
        with self.assertRaises(SchemaError):self.service(root=service.root)

    def test_mutating_manager_budget_is_rejected_before_credentials(self):
        service=self.service();token=self.visitor(service);job=service.prepare(token,self.request['artists'])
        service.manager.maximum_executions=100
        with self.assertRaises(SchemaError):service.start(token,job['job_id'],job['plan_sha256'])
        self.assertEqual(self.reads,[0,0])

    def test_invalid_inputs_and_wrong_plan_hash_do_not_disable_other_admissions(self):
        service=self.service();token=self.visitor(service)
        with self.assertRaises(SchemaError):service.prepare(token,{'A':'  invalid','B':'Artist B'})
        job=service.prepare(token,self.request['artists'])
        with self.assertRaises(SchemaError):service.start(token,job['job_id'],'0'*64)
        self.assertFalse(service.capabilities(token)['admissions_blocked'])
        self.assertEqual(service.prepare(token,self.request['artists'])['status'],'PLANNED')
        self.assertEqual(self.reads,[0,0])

    def test_retyped_policy_file_is_rejected_even_when_python_values_compare_equal(self):
        service=self.service();token=self.visitor(service)
        path=service.root/'public-policy.json';policy=json.loads(path.read_text())
        policy['schema_version']=True
        self.assertEqual(policy,service.binding)
        path.write_text(json.dumps(policy),encoding='utf-8')
        with self.assertRaises(SchemaError):service.capabilities(token)
        self.assertEqual(self.reads,[0,0])
