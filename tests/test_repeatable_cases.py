"""Repeatable access: real protocol runners behind strictly offline providers."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.evidence import fingerprint
from affinityqa.errors import SchemaError
from affinityqa.groq_agent import GroqToolContextMovieAgent
from affinityqa.cinema_preferences import CinemaMovieAgent
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent
from affinityqa.public_cases import PublicCaseManager, public_policy
from affinityqa.repeatable_cases import RepeatableCaseManager, JUDGING_END
from affinityqa.provider_scheduler import ProviderScheduler, QuotaWindow
from affinityqa.qloo import Settings
from affinityqa.qloo_cache import PrivateQlooCache
from test_individual_jobs import TransportDouble
from test_individual_remote_jobs import request_fixture
from test_groq_agent import OpenerFixture, UNIT_SECRET, UNIT_QLOO_SECRET
from test_cinema_capture import request_fixture as cinema_request
from test_cinema_identity_capture import identity_request, IdentityTransport, ID_A, ID_B
from test_discovery_capture import DiscoveryTransport
from test_discovery_agent import Opener as DiscoveryOpener, TEST_SECRET

ORIGIN='https://judge.example'


class RepeatableTests(unittest.TestCase):
    def setUp(self):
        parent=Path(os.environ.get('AFFINITYQA_TEST_STORAGE_ROOT',str(ROOT.parent/'test-private-scratch')))
        parent.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.temp.cleanup)
        self.parent=Path(self.temp.name);self.now=datetime(2026,10,14,20,tzinfo=timezone.utc)
        self.request=request_fixture();self.opener=OpenerFixture();self.transport=TransportDouble(self.request)
        self.engines=[];self.reads=[0,0]
        for target in ('socket.create_connection','socket.getaddrinfo'):
            guard=patch(target,side_effect=AssertionError('Real provider access forbidden'))
            guard.start();self.addCleanup(guard.stop)
        guard=patch('time.sleep');guard.start();self.addCleanup(guard.stop)

    def settings(self):self.reads[0]+=1;return Settings(UNIT_QLOO_SECRET)
    def key(self):self.reads[1]+=1;return TEST_SECRET if self.request['schema_version']==5 else UNIT_SECRET

    def engine(self):
        cls=DiscoveryMovieAgent if self.request['schema_version']==5 else CinemaMovieAgent if self.request['schema_version'] in (3,4) else GroqToolContextMovieAgent
        value=cls(self.key(),forbidden_secrets=(UNIT_QLOO_SECRET,),_test_opener=self.opener)
        self.engines.append(value);return value

    def scheduler(self,qloo_requests=1000,groq_requests=1000):
        scheduler=ProviderScheduler(self.parent/'provider.sqlite3',clock=lambda:self.now.timestamp(),limits={
            'qloo':(QuotaWindow('rpm',qloo_requests,60),),
            'groq':(QuotaWindow('rpm',groq_requests,60),QuotaWindow('tokens',1000000,60,'tokens'))})
        return scheduler

    def manager(self,*,root=None,scheduler=None,legacy_root=None):
        template=copy.deepcopy(self.request);template.pop('preferences',None);template['schema_version']=2
        manager=RepeatableCaseManager(root or self.parent/'repeatable',template,origin=ORIGIN,
            minimum_model_interval_seconds=0.0,execution_enabled=True,settings_loader=self.settings,
            remote_key_loader=self.key,legacy_root=legacy_root,scheduler=scheduler,
            _test_adapters=(self.engine,lambda:self.transport),_test_now=lambda:self.now,_test_autostart=False)
        self.addCleanup(manager.close);return manager

    def prepare(self,manager,token):
        return manager.prepare(token,self.request['artists'],self.request.get('preferences'),
            confirm_identities=self.request['schema_version'] in (4,5),discover_new_movies=self.request['schema_version']==5)

    def finish(self,manager,token,job):
        manager.start(token,job['job_id'],job['plan_sha256']);manager.manager.run_once()
        pending=manager.view(token,job['job_id'])
        if pending['status']=='AWAITING_IDENTITY_CONFIRMATION':
            manager.confirm_identities(token,job['job_id'],job['plan_sha256'],pending['identity_receipt_sha256'],{'A':ID_A,'B':ID_B})
            manager.manager.run_once()
        return manager.view(token,job['job_id'])

    def test_same_session_three_complete_cases_no_lifetime_caps_and_owned_receipts(self):
        manager=self.manager(scheduler=self.scheduler());token,info=manager.session();results=[]
        for _ in range(3):
            job=self.finish(manager,token,self.prepare(manager,token));results.append(job)
            self.assertEqual(job['status'],'COMPLETE',job)
            self.assertEqual(job['saved_model_packets'],39)
            self.assertEqual(job['result']['cultural_gate'],'NOT_VALIDATED')
            self.assertEqual(manager.verification(token,job['job_id'])['result']['verified_model_packets'],39)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(12,117))
        cap=manager.capabilities(token)
        self.assertIsNone(cap['remaining_plans']);self.assertIsNone(cap['remaining_executions'])
        self.assertEqual(info['expires_utc'],JUDGING_END);self.assertEqual(len(cap['jobs']),3)
        stranger,_=manager.session()
        with self.assertRaises(FileNotFoundError):manager.view(stranger,results[0]['job_id'])
        manager.close();restored=self.manager(root=manager.root,scheduler=manager.manager.scheduler)
        self.assertEqual(restored.session(token)[0],token)
        for job in results:self.assertEqual(restored.view(token,job['job_id'])['status'],'COMPLETE')
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(12,117))

    def test_supported_request_modes_keep_protocol_and_attempt_bounds(self):
        for version in (3,4,5):
            with self.subTest(version=version):
                self.request=cinema_request() if version==3 else identity_request();self.request['schema_version']=version
                self.transport=DiscoveryTransport(self.request) if version==5 else TransportDouble(self.request) if version==3 else IdentityTransport(self.request)
                self.opener=DiscoveryOpener() if version==5 else OpenerFixture()
                manager=self.manager(root=self.parent/f'mode-{version}',scheduler=self.scheduler())
                token,_=manager.session();job=self.finish(manager,token,self.prepare(manager,token))
                self.assertEqual(job['status'],'COMPLETE',job)
                self.assertEqual(job['maximum_model_decisions'],2)
                self.assertEqual(job['saved_model_packets'],2)
                self.assertEqual(job['result']['verified_provider_samples'],4)
                self.assertIn('cinema_results',job['result']);self.assertEqual(job['result']['cultural_gate'],'NOT_VALIDATED')
                manager.close()

    def test_restart_before_any_dispatch_retains_fifo_and_both_owners(self):
        scheduler=self.scheduler();manager=self.manager(scheduler=scheduler)
        tokens=[manager.session()[0] for _ in range(2)]
        jobs=[self.prepare(manager,token) for token in tokens]
        for token,job in zip(tokens,jobs):manager.start(token,job['job_id'],job['plan_sha256'])
        self.assertEqual([manager.view(t,j['job_id'])['queue_position'] for t,j in zip(tokens,jobs)],[1,2])
        self.assertEqual(len(self.transport.calls),0)
        manager.close();restored=self.manager(root=manager.root,scheduler=scheduler)
        restored.manager.run_once();self.assertEqual(restored.view(tokens[0],jobs[0]['job_id'])['status'],'COMPLETE')
        self.assertEqual(restored.view(tokens[1],jobs[1]['job_id'])['status'],'QUEUED')
        restored.manager.run_once();self.assertEqual(restored.view(tokens[1],jobs[1]['job_id'])['status'],'COMPLETE')
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(8,78))

    def test_quota_pause_before_second_profile_survives_restart_without_resending_accepted(self):
        self.request=identity_request();self.request['schema_version']=5
        self.transport=DiscoveryTransport(self.request);self.opener=DiscoveryOpener()
        scheduler=self.scheduler(groq_requests=1);manager=self.manager(scheduler=scheduler);token,_=manager.session()
        job=self.prepare(manager,token);manager.start(token,job['job_id'],job['plan_sha256']);manager.manager.run_once()
        pending=manager.view(token,job['job_id']);self.assertEqual(pending['status'],'AWAITING_IDENTITY_CONFIRMATION',pending)
        manager.confirm_identities(token,job['job_id'],job['plan_sha256'],pending['identity_receipt_sha256'],{'A':ID_A,'B':ID_B})
        manager.manager.run_once();waiting=manager.view(token,job['job_id'])
        self.assertEqual(waiting['status'],'WAITING_PROVIDER_CAPACITY',waiting)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,1))
        self.assertEqual(set(waiting['provider_stats']),{'qloo','groq'})
        self.assertEqual(waiting['provider_stats']['qloo']['http_attempts'],4)
        self.assertEqual(waiting['provider_stats']['groq']['http_attempts'],1)
        self.assertEqual(waiting['provider_stats']['groq']['unknown_attempts'],0)
        attempts=manager.root/'jobs'/job['job_id']/'attempts'
        preserved={str(p.relative_to(attempts)):hashlib.sha256(p.read_bytes()).hexdigest() for p in attempts.rglob('*') if p.is_file()}
        manager.close();self.now+=timedelta(seconds=61)
        restored=self.manager(root=manager.root,scheduler=scheduler);restored.manager.run_once()
        final=restored.view(token,job['job_id']);self.assertEqual(final['status'],'COMPLETE',final)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,2))
        for name,digest in preserved.items():self.assertEqual(hashlib.sha256((attempts/name).read_bytes()).hexdigest(),digest)
        self.assertGreater(final['provider_stats']['groq']['reconstructed_steps'],0)

    def test_unknown_after_send_is_retained_and_never_blindly_replayed(self):
        class TimeoutOpener(OpenerFixture):
            def open(self,request,timeout):
                self.calls.append((request,json.loads(request.data),timeout));raise TimeoutError('synthetic')
        self.opener=TimeoutOpener();scheduler=self.scheduler();manager=self.manager(scheduler=scheduler);token,_=manager.session()
        job=self.finish(manager,token,self.prepare(manager,token))
        self.assertEqual(job['status'],'UNKNOWN',job)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,1))
        manager.close();restored=self.manager(root=manager.root,scheduler=scheduler)
        self.assertEqual(restored.view(token,job['job_id'])['status'],'UNKNOWN')
        self.assertFalse(restored.manager.run_once());restored.view(token,job['job_id'])
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,1))
        next_plan=self.prepare(restored,token);self.assertEqual(next_plan['status'],'PLANNED')

    def test_private_qloo_cache_preserves_exact_scope_and_fresh_models(self):
        manager=self.manager(scheduler=self.scheduler())
        manager.manager.qloo_cache=PrivateQlooCache(self.parent/'private-cache')
        token,_=manager.session()
        first=self.finish(manager,token,self.prepare(manager,token))
        second=self.finish(manager,token,self.prepare(manager,token))
        self.assertEqual((first['status'],second['status']),('COMPLETE','COMPLETE'))
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,78))
        self.assertEqual(second['provider_stats']['qloo']['cache_hits'],4)
        self.assertEqual(second['provider_stats']['qloo']['http_attempts'],0)
        self.assertEqual(second['provider_stats']['groq']['http_attempts'],39)
        changed={'A':self.request['artists']['A'],'B':'New musical identity'}
        self.transport.request={**self.request,'artists':changed}
        job=manager.prepare(token,changed);third=self.finish(manager,token,job)
        self.assertEqual(third['status'],'COMPLETE',third)
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(8,117))

    def test_discovery_search_variants_survive_private_cache_and_repeat_with_fresh_models(self):
        from test_discovery_v3_search import variant
        self.request=identity_request();self.request['schema_version']=5
        self.transport=DiscoveryTransport(self.request,mutation=variant);self.opener=DiscoveryOpener()
        manager=self.manager(scheduler=self.scheduler())
        manager.manager.qloo_cache=PrivateQlooCache(self.parent/'variant-cache')
        token,_=manager.session();results=[]
        for _ in range(2):
            job=self.finish(manager,token,self.prepare(manager,token));results.append(job)
            self.assertEqual(job['status'],'COMPLETE',job)
            private=manager.manager.receipt(job['job_id'])
            directory=Path(manager.manager._job(job['job_id'])['directory'])
            # Duplicate raw UUID variants stay in evidence; only the explicit
            # selectable musical-profile contract collapses eligible choices.
            for sample in sorted(directory.glob('http-000[24].json')):
                rows=json.loads(sample.read_text())['response']['results']
                self.assertEqual(len(rows),2)
                self.assertEqual(rows[0]['entity_id'],rows[1]['entity_id'])
            self.assertEqual(private['verification_status'],'VERIFIED_COMPLETE')
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,4))
        self.assertEqual(results[1]['provider_stats']['qloo']['http_attempts'],0)
        self.assertEqual(results[1]['provider_stats']['qloo']['cache_hits'],4)
        self.assertEqual(results[1]['provider_stats']['groq']['http_attempts'],2)
        self.assertEqual(manager.verification(token,results[0]['job_id'])['result']['verification_status'],'VERIFIED_COMPLETE')

    def test_source_change_after_admission_blocks_restart_before_keys_or_send(self):
        manager=self.manager(scheduler=self.scheduler());token,_=manager.session()
        job=self.prepare(manager,token);manager.start(token,job['job_id'],job['plan_sha256']);manager.close()
        from affinityqa.repeatable_jobs import helper_bindings
        altered={**helper_bindings(),'provider_runtime.py':'0'*64}
        with patch('affinityqa.repeatable_jobs.helper_bindings',return_value=altered):
            restored=self.manager(root=manager.root,scheduler=manager.manager.scheduler)
            restored.manager.run_once();result=restored.view(token,job['job_id'])
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(self.reads,[0,0])
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(0,0))

    def test_sent_qloo_429_retains_partial_receipt_and_does_not_retry(self):
        from affinityqa.qloo import Response
        class RateTransport(TransportDouble):
            def send(self,path,params):
                result=super().send(path,params)
                return Response(429,{'error':'synthetic quota stop'},{}) if len(self.calls)==2 else result
        self.transport=RateTransport(self.request)
        manager=self.manager(scheduler=self.scheduler());token,_=manager.session()
        final=self.finish(manager,token,self.prepare(manager,token))
        self.assertEqual(final['status'],'PARTIAL',final)
        self.assertEqual(final['provider_stats']['qloo']['http_attempts'],2)
        self.assertEqual(manager.verification(token,final['job_id'])['result']['verification_status'],'VERIFIED_PARTIAL')
        self.assertFalse(manager.manager.run_once())
        with self.assertRaises(SchemaError):manager.start(token,final['job_id'],final['plan_sha256'])
        self.assertEqual(len(self.transport.calls),2)

    def test_provenance_sidecar_tampering_hides_verified_result(self):
        manager=self.manager(scheduler=self.scheduler());token,_=manager.session()
        final=self.finish(manager,token,self.prepare(manager,token))
        self.assertEqual(final['status'],'COMPLETE')
        private=manager.manager.receipt(final['job_id'])
        provenance=private['repeatable_contract']['provider_provenance']
        self.assertTrue(provenance['artifact_sha256'])
        relative=next(iter(provenance['artifact_sha256']))
        path=manager.root/'jobs'/final['job_id']/relative
        with path.open('ab') as handle:handle.write(b' ')
        self.assertEqual(manager.view(token,final['job_id'])['status'],'EVIDENCE_CHANGED')
        with self.assertRaises(SchemaError):manager.verification(token,final['job_id'])

    def test_partial_identity_evidence_remains_readable_without_confirming_or_resending(self):
        from affinityqa.qloo import Response
        for version in (4,5):
            with self.subTest(version=version):
                self.request=identity_request();self.request['schema_version']=version
                base=DiscoveryTransport if version==5 else IdentityTransport
                class IncompleteSearch(base):
                    def send(self,path,params):
                        result=super().send(path,params)
                        return Response(200,{'results':[]},{}) if len(self.calls)==2 else result
                self.transport=IncompleteSearch(self.request)
                self.opener=DiscoveryOpener() if version==5 else OpenerFixture()
                scheduler=self.scheduler();manager=self.manager(root=self.parent/f'partial-{version}',scheduler=scheduler)
                token,_=manager.session();planned=self.prepare(manager,token)
                manager.start(token,planned['job_id'],planned['plan_sha256']);manager.manager.run_once()
                final=manager.view(token,planned['job_id'])
                self.assertEqual(final['status'],'PARTIAL',final)
                self.assertEqual(final['error_class'],'SchemaError')
                verification=manager.verification(token,final['job_id'])
                self.assertEqual(verification['result']['verification_status'],'VERIFIED_PARTIAL')
                self.assertEqual(verification['result']['error_class'],'SchemaError')
                self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(2,0))
                with self.assertRaises(SchemaError):
                    manager.confirm_identities(token,final['job_id'],final['plan_sha256'],'0'*64,{'A':ID_A,'B':ID_B})
                with self.assertRaises(SchemaError):manager.start(token,final['job_id'],final['plan_sha256'])
                self.assertFalse(manager.manager.run_once())
                job_root=manager.root/'jobs'/final['job_id']
                preserved={str(p.relative_to(job_root)):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in job_root.rglob('*') if p.is_file()}
                manager.close();restored=self.manager(root=manager.root,scheduler=scheduler)
                self.assertEqual(restored.view(token,final['job_id'])['status'],'PARTIAL')
                self.assertEqual(restored.verification(token,final['job_id']),verification)
                self.assertFalse(restored.manager.run_once())
                for name,digest in preserved.items():self.assertEqual(hashlib.sha256((job_root/name).read_bytes()).hexdigest(),digest)
                self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(2,0))
                receipt=next(job_root.glob('attempts/attempt-*/identity-verification.json'))
                with receipt.open('ab') as handle:handle.write(b' ')
                self.assertEqual(restored.view(token,final['job_id'])['status'],'EVIDENCE_CHANGED')
                with self.assertRaises((SchemaError,OSError)):restored.verification(token,final['job_id'])
                restored.close()

    def test_saved_explicit_confirmation_recovers_before_next_dispatch(self):
        self.request=identity_request();self.request['schema_version']=5
        self.transport=DiscoveryTransport(self.request);self.opener=DiscoveryOpener()
        manager=self.manager(scheduler=self.scheduler());token,_=manager.session()
        planned=self.prepare(manager,token);manager.start(token,planned['job_id'],planned['plan_sha256']);manager.manager.run_once()
        pending=manager.view(token,planned['job_id'])
        self.assertEqual(pending['status'],'AWAITING_IDENTITY_CONFIRMATION')
        receipt=manager.manager.identity_receipt(planned['job_id'])
        from affinityqa.cinema_identity_verify import selection_profiles
        from affinityqa.individual_jobs import write
        selected={'A':ID_A,'B':ID_B}
        choice={'schema_version':1,'identity_receipt_sha256':pending['identity_receipt_sha256'],
                'identity_receipt':receipt,'selected_entity_ids':selected,'chosen_identities':selection_profiles(receipt,selected)}
        # Inject the exact checkpoint between durable explicit choice and queue
        # commit; it is generated test evidence, never an inferred user choice.
        write(manager.root/'jobs'/planned['job_id']/'identity-confirmation.json',choice)
        manager.close();restored=self.manager(root=manager.root,scheduler=manager.manager.scheduler)
        self.assertEqual(restored.view(token,planned['job_id'])['status'],'QUEUED')
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(2,0))
        restored.manager.run_once();self.assertEqual(restored.view(token,planned['job_id'])['status'],'COMPLETE')
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,2))

    def test_storage_failure_halts_all_queued_work_and_stays_blocked_after_restart(self):
        manager=self.manager(scheduler=self.scheduler());token,_=manager.session()
        jobs=[self.prepare(manager,token) for _ in range(2)]
        for job in jobs:manager.start(token,job['job_id'],job['plan_sha256'])
        with patch('affinityqa.repeatable_jobs.execute_stage',side_effect=OSError('synthetic storage failure')):
            self.assertTrue(manager.manager.run_once())
        health=manager.health();self.assertTrue(health['admissions_blocked']);self.assertFalse(health['execution_enabled'])
        self.assertEqual(manager.view(token,jobs[0]['job_id'])['status'],'FAILED')
        self.assertEqual(manager.view(token,jobs[1]['job_id'])['status'],'QUEUED')
        self.assertFalse(manager.manager.run_once())
        with patch.object(manager.manager.condition,'wait',side_effect=AssertionError('Blocked worker must exit, not poll')):
            manager.manager._loop()
        manager.session(token);self.assertEqual(len(manager.capabilities(token)['jobs']),2)
        with self.assertRaises(SchemaError):self.prepare(manager,token)
        with self.assertRaises(SchemaError):manager.session()
        manager.close();restored=self.manager(root=manager.root,scheduler=manager.manager.scheduler)
        self.assertTrue(restored.health()['admissions_blocked']);self.assertFalse(restored.manager.run_once())
        self.assertEqual(restored.view(token,jobs[1]['job_id'])['status'],'QUEUED')
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(0,0))

    def test_prepare_storage_failure_blocks_worker_as_well_as_public_admissions(self):
        manager=self.manager(scheduler=self.scheduler());token,_=manager.session()
        queued=self.prepare(manager,token);manager.start(token,queued['job_id'],queued['plan_sha256'])
        with patch('affinityqa.repeatable_jobs.write',side_effect=OSError('synthetic plan storage failure')):
            with self.assertRaises(OSError):self.prepare(manager,token)
        self.assertTrue(manager.health()['admissions_blocked'])
        self.assertFalse(manager.manager.run_once())
        self.assertEqual(manager.view(token,queued['job_id'])['status'],'QUEUED')
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(0,0))

    def test_legacy_swallowed_local_io_failure_blocks_before_partial_verification(self):
        from affinityqa.evidence import Ledger
        original=Ledger.write
        def fail_context(ledger,name,value):
            if name=='individual-tool-inputs.json':raise PermissionError('synthetic context file failure')
            return original(ledger,name,value)
        manager=self.manager(scheduler=self.scheduler());token,_=manager.session()
        jobs=[self.prepare(manager,token) for _ in range(2)]
        for job in jobs:manager.start(token,job['job_id'],job['plan_sha256'])
        with patch.object(Ledger,'write',new=fail_context):manager.manager.run_once()
        self.assertTrue(manager.health()['admissions_blocked'])
        self.assertEqual(manager.view(token,jobs[0]['job_id'])['status'],'FAILED')
        self.assertEqual(manager.view(token,jobs[1]['job_id'])['status'],'QUEUED')
        self.assertFalse(manager.manager.run_once())
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,0))

    def test_provider_accounting_fence_retains_queue_and_read_access(self):
        scheduler=self.scheduler();manager=self.manager(scheduler=scheduler);token,_=manager.session()
        job=self.prepare(manager,token);manager.start(token,job['job_id'],job['plan_sha256'])
        with patch.object(scheduler,'paused_providers',return_value=['groq'],create=True):
            self.assertTrue(manager.health()['admissions_blocked'])
            self.assertFalse(manager.health()['execution_enabled'])
            self.assertFalse(manager.manager.run_once())
            self.assertEqual(manager.view(token,job['job_id'])['status'],'QUEUED')
            manager.session(token)
            with self.assertRaises(SchemaError):self.prepare(manager,token)
            with self.assertRaises(SchemaError):manager.session()
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(0,0))

    def test_expired_legacy_owner_renews_new_access_without_touching_old_records(self):
        template=copy.deepcopy(self.request)
        old=PublicCaseManager(self.parent/'legacy',template,origin=ORIGIN,
            policy=public_policy(maximum_sessions=3,maximum_plans=3,maximum_executions=1,plans_per_session=3,executions_per_session=1,session_hours=1),
            minimum_model_interval_seconds=0.0,execution_enabled=True,settings_loader=self.settings,remote_key_loader=self.key,
            _test_adapters=(self.engine,lambda:self.transport),_test_now=lambda:self.now)
        token,_=old.session();planned=old.prepare(token,self.request['artists']);done=old.prepare(token,self.request['artists'])
        old.start(token,done['job_id'],done['plan_sha256']);old.manager.worker.join(15)
        self.assertEqual(old.view(token,done['job_id'])['status'],'COMPLETE');old.close()
        before={str(p.relative_to(old.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in old.root.rglob('*') if p.is_file()}
        self.now+=timedelta(hours=2)
        manager=self.manager(legacy_root=old.root,scheduler=self.scheduler());manager.session(token)
        self.assertTrue(manager.view(token,planned['job_id'])['read_only'])
        self.assertEqual(manager.view(token,done['job_id'])['status'],'COMPLETE')
        self.assertEqual(manager.verification(token,done['job_id'])['result']['verified_model_packets'],39)
        with self.assertRaises(SchemaError):manager.start(token,planned['job_id'],planned['plan_sha256'])
        self.assertEqual(before,{str(p.relative_to(old.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in old.root.rglob('*') if p.is_file()})
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(4,39))


if __name__=='__main__':unittest.main()


