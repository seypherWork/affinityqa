"""Synthetic remote job/API lifecycle; no provider or GPU requests."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.api import create_app
from affinityqa.errors import SchemaError
from affinityqa.groq_agent import GroqToolContextMovieAgent
from affinityqa.individual_jobs import IndividualJobManager
from affinityqa.qloo import Settings
from test_groq_agent import OpenerFixture, UNIT_SECRET, UNIT_QLOO_SECRET
from test_individual_capture import TransportDouble
from test_individual_jobs import asgi
from test_individual_remote import request_fixture, InterruptedOpener, VariedBackendOpener


class RemoteJobTests(unittest.TestCase):
    def setUp(self):
        temporary = ROOT/'.test-runs'
        temporary.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.request = request_fixture()
        self.reads = [0,0]
        self.engines = []
        self.opener_factory = OpenerFixture
        self.transport_fail = False
        for target in ('socket.create_connection', 'socket.getaddrinfo',
                       'affinityqa.individual_remote_capture.LiveTransport'):
            guard = patch(target, side_effect=AssertionError('Provider/DNS denied in remote job fixture'))
            guard.start()
            self.addCleanup(guard.stop)
        guard = patch('affinityqa.individual_remote_capture.time.sleep')
        guard.start()
        self.addCleanup(guard.stop)

    def settings(self):
        self.reads[0] += 1
        return Settings(UNIT_QLOO_SECRET)

    def key(self):
        self.reads[1] += 1
        return UNIT_SECRET

    def engine(self):
        value = GroqToolContextMovieAgent(UNIT_SECRET, forbidden_secrets=(UNIT_QLOO_SECRET,), _test_opener=self.opener_factory())
        self.engines.append(value)
        return value

    def manager(self, enabled=True, root=None, adapters=True):
        manager = IndividualJobManager(root or self.parent/'jobs', self.request,
            execution_enabled=enabled, settings_loader=self.settings, remote_key_loader=self.key,
            operator='groq', _test_adapters=(self.engine,lambda:TransportDouble(self.request,fail=self.transport_fail)) if adapters else None)
        self.addCleanup(manager.close)
        return manager

    def finish(self, manager, job):
        manager.start(job['job_id'], job['plan_sha256'])
        manager.worker.join(timeout=15)
        self.assertFalse(manager.worker.is_alive())
        return manager.view(job['job_id'])

    def call(self, manager):
        app = create_app(ROOT, store_root=self.parent/'backend', individual_manager=manager)
        return lambda method,path,**kw:asyncio.run(asgi(app,method,path,**kw))

    def test_preview_exposes_remote_mode_but_no_keys_or_factory_calls(self):
        manager = self.manager()
        job = manager.prepare(self.request['artists'])
        self.assertEqual(self.reads,[0,0])
        self.assertEqual(self.engines,[])
        self.assertEqual(job['operator_mode'],'groq')
        self.assertEqual((job['model_load_requests'],job['model_metadata_requests']),(0,0))
        self.assertFalse((manager.root/job['job_id']/'capture').exists())
        self.assertEqual(manager.capabilities()['provider'],'groq')

    def test_complete_frames_have_verified_receipt_and_simulation_provenance(self):
        manager = self.manager()
        job = self.finish(manager,manager.prepare(self.request['artists']))
        self.assertEqual(job['status'],'COMPLETE')
        self.assertEqual((job['saved_provider_samples'],job['saved_model_packets']),(4,39))
        self.assertEqual(job['result']['behavioral_gate'],'OBSERVED_RECOVERY')
        self.assertEqual(job['result']['provenance'],'SIMULATION_ONLY')
        self.assertEqual(len(job['result']['frames']),3)
        self.assertEqual(self.reads,[1,1])
        self.assertNotIn(UNIT_SECRET,json.dumps(manager.receipt(job['job_id'])))
        self.assertNotIn(UNIT_QLOO_SECRET,json.dumps(job))

    def test_varied_backend_is_visible_as_complete_inconclusive_result(self):
        self.opener_factory = VariedBackendOpener
        manager = self.manager()
        job = self.finish(manager,manager.prepare(self.request['artists']))
        self.assertEqual((job['status'],job['saved_model_packets']),('COMPLETE',39))
        self.assertEqual(job['result']['integration_gate'],'PASS')
        self.assertEqual(job['result']['causal_gate'],'INCONCLUSIVE')
        self.assertEqual(job['result']['backend_comparability']['status'],'VARIED')
        self.assertEqual(len(job['result']['frames']),3)

    def test_remote_partial_is_reviewable_and_cannot_execute_again(self):
        self.opener_factory = InterruptedOpener
        manager = self.manager()
        job = self.finish(manager,manager.prepare(self.request['artists']))
        self.assertEqual(job['status'],'PARTIAL')
        self.assertEqual((job['result']['model_attempts'],job['result']['verified_model_packets']),(9,8))
        self.assertEqual(job['result']['causal_gate'],'NOT_EVALUATED')
        with self.assertRaises(SchemaError):
            manager.start(job['job_id'],job['plan_sha256'])
        self.assertEqual(self.reads,[1,1])

    def test_invalid_key_does_not_consume_job_execution_admission(self):
        manager = self.manager()
        manager.remote_key_loader = lambda:'invalid'
        job = manager.prepare(self.request['artists'])
        with self.assertRaises(SchemaError):
            manager.start(job['job_id'],job['plan_sha256'])
        self.assertEqual(manager.view(job['job_id'])['status'],'PLANNED')
        self.assertEqual(manager.capabilities()['remaining_executions'],3)
        self.assertEqual(self.engines,[])

    def test_disabled_wrong_hash_and_changed_file_reject_before_credential_reads(self):
        manager = self.manager(enabled=False)
        job = manager.prepare(self.request['artists'])
        with self.assertRaises(SchemaError):manager.start(job['job_id'],job['plan_sha256'])
        manager.enabled = True
        with self.assertRaises(SchemaError):manager.start(job['job_id'],'0'*64)
        path = manager.root/job['job_id']/'job-plan.json'
        value = json.loads(path.read_text())
        value['plan']['remote_operator']['options']['seed'] = 8
        path.write_text(json.dumps(value))
        with self.assertRaises(SchemaError):manager.start(job['job_id'],job['plan_sha256'])
        self.assertEqual(self.reads,[0,0])

    def test_restart_preserves_verified_simulation_without_test_adapters(self):
        manager = self.manager()
        job = self.finish(manager,manager.prepare(self.request['artists']))
        manager.close()
        restored = self.manager(enabled=False,root=manager.root,adapters=False)
        self.assertTrue(restored.view(job['job_id'])['simulation_only'])
        self.assertEqual(restored.view(job['job_id'])['result']['provenance'],'SIMULATION_ONLY')
        self.assertEqual(self.reads,[1,1])

    def test_lifetime_budget_survives_restart_and_no_silent_resume(self):
        self.transport_fail = True
        manager = self.manager()
        for _ in range(3):
            self.finish(manager,manager.prepare(self.request['artists']))
        manager.close()
        restored = self.manager(root=manager.root)
        job = restored.prepare(self.request['artists'])
        with self.assertRaises(SchemaError):restored.start(job['job_id'],job['plan_sha256'])
        self.assertEqual(self.reads,[3,3])

    def test_cloud_operator_requires_own_template_and_excludes_ollama_configuration(self):
        from test_individual_capture import fixture
        for template,url in ((fixture(),None),(self.request,'http://127.0.0.1:11434')):
            with self.assertRaises(SchemaError):
                IndividualJobManager(self.parent/'invalid',template,url,operator='groq')
        self.assertFalse((self.parent/'invalid').exists())

    def test_same_origin_http_plan_execute_status_and_receipt(self):
        manager = self.manager()
        call = self.call(manager)
        code,cap,_ = call('GET','/api/individual/capabilities')
        self.assertEqual((code,cap['provider']),(200,'groq'))
        for origin in (None,'null','https://foreign.invalid'):
            self.assertEqual(call('POST','/api/individual/plans',body={'artists':self.request['artists']},origin=origin)[0],403)
        for extra in ('model','provider','api_key','endpoint'):
            code,body,_ = call('POST','/api/individual/plans',body={'artists':self.request['artists'],extra:UNIT_SECRET})
            self.assertEqual(code,422)
            self.assertNotIn(UNIT_SECRET,json.dumps(body))
        code,job,headers = call('POST','/api/individual/plans',body={'artists':self.request['artists']})
        self.assertEqual(code,201)
        self.assertEqual(headers[b'cache-control'],b'no-store')
        base = '/api/individual/jobs/'+job['job_id']
        self.assertEqual(call('POST',base+'/execute',body={'plan_sha256':job['plan_sha256']})[0],202)
        manager.worker.join(timeout=15)
        self.assertFalse(manager.worker.is_alive())
        code,job,_ = call('GET',base)
        self.assertEqual((code,job['status']),(200,'COMPLETE'))
        code,receipt,headers = call('GET',base+'/verification')
        self.assertEqual((code,receipt['verified_model_packets']),(200,39))
        self.assertEqual(headers[b'cache-control'],b'no-store')
        self.assertIn(b'attachment',headers[b'content-disposition'])
        self.assertEqual(self.reads,[1,1])

    def test_status_metadata_declares_remote_and_synthetic_mode_without_execution(self):
        manager = self.manager()
        code,value,_ = self.call(manager)('GET','/api/status')
        self.assertEqual(code,200)
        self.assertEqual(value['http_agent_execution'],'explicit-individual-remote')
        self.assertTrue(value['individual_simulation_only'])
        self.assertEqual(self.reads,[0,0])
        self.assertEqual(self.engines,[])

    def test_tampered_envelope_hides_previously_verified_result(self):
        manager = self.manager()
        job = self.finish(manager,manager.prepare(self.request['artists']))
        packet = manager._capture_dir(job['job_id'])/'causal-execution-007.json'
        packet.write_bytes(packet.read_bytes()+b' ')
        self.assertEqual(manager.view(job['job_id'])['status'],'EVIDENCE_CHANGED')
        with self.assertRaises(SchemaError):manager.receipt(job['job_id'])

    def test_cli_remote_preview_and_enable_flag_do_not_read_keys_at_startup(self):
        from affinityqa.cli import main
        template = self.parent/'template.json'
        template.write_text(json.dumps(self.request))
        for enabled in (False,True):
            seen = []
            def serve(app,**kwargs):
                self.assertEqual(kwargs['host'],'127.0.0.1')
                seen.append(asyncio.run(asgi(app,'GET','/api/individual/capabilities'))[1])
            args = ['serve','--individual-provider','groq','--individual-template',str(template),
                '--individual-output',str(self.parent/('enabled' if enabled else 'preview')),
                '--store',str(self.parent/('backend-enabled' if enabled else 'backend-preview'))]
            if enabled:
                args += ['--individual-remote-enabled','--env-file',str(self.parent/'absent-qloo.env'),
                         '--groq-env-file',str(self.parent/'absent-groq.env'), '--remote-model-minimum-interval','0']
            with patch('uvicorn.run',side_effect=serve), \
                 patch('affinityqa.qloo.Settings.from_environment',side_effect=AssertionError('No credential loading')), \
                 patch('affinityqa.individual_remote_capture.load_private_credential',side_effect=AssertionError('No remote credential loading')):
                self.assertEqual(main(args),0)
            self.assertEqual((seen[0]['provider'],seen[0]['execution_enabled'],seen[0]['jobs']),('groq',enabled,[]))

    def test_cli_wrong_provider_or_mixed_local_configuration_cannot_start_server(self):
        from contextlib import redirect_stdout
        import io
        from affinityqa.cli import main
        variants = [['serve','--individual-remote-enabled'],
            ['serve','--individual-provider','groq','--individual-local-enabled'],
            ['serve','--individual-provider','groq','--ollama-url','http://127.0.0.1:11434']]
        for args in variants:
            with self.subTest(args=args), patch('uvicorn.run',side_effect=AssertionError('Server must not start')), redirect_stdout(io.StringIO()):
                self.assertEqual(main(args),2)

    def test_real_manager_requires_explicit_cadence_before_any_private_loader(self):
        with self.assertRaisesRegex(SchemaError,'reviewed model interval'):
            IndividualJobManager(self.parent/'not-created',self.request,operator='groq',execution_enabled=True,
                settings_loader=self.settings,remote_key_loader=self.key)
        self.assertEqual(self.reads,[0,0])
        self.assertFalse((self.parent/'not-created').exists())

    def test_owner_cadence_change_invalidates_job_before_private_loader(self):
        manager=self.manager()
        job=manager.prepare(self.request['artists'])
        manager.remote_minimum_interval_seconds=2.0
        with self.assertRaises(SchemaError):manager.start(job['job_id'],job['plan_sha256'])
        self.assertEqual(self.reads,[0,0])
        self.assertIsNone(manager.worker)

    def test_cli_missing_or_invalid_cadence_never_starts_server_or_reads_private_file(self):
        from affinityqa.cli import main
        from contextlib import redirect_stdout
        import io
        template=self.parent/'pacing-template.json'
        template.write_text(json.dumps(self.request),encoding='utf-8')
        base=['serve','--individual-provider','groq','--individual-template',str(template),
              '--individual-remote-enabled','--env-file',str(self.parent/'absent-qloo.env'),
              '--groq-env-file',str(self.parent/'absent-groq.env'),
              '--individual-output',str(self.parent/'not-created')]
        for extra in ([],['--remote-model-minimum-interval','nan'],['--remote-model-minimum-interval','66']):
            with self.subTest(extra=extra),redirect_stdout(io.StringIO()), \
                 patch('uvicorn.run',side_effect=AssertionError('Server must not start')), \
                 patch('affinityqa.qloo.Settings.from_environment',side_effect=AssertionError('No private reads')):
                self.assertEqual(main(base+extra),2)
        self.assertFalse((self.parent/'not-created').exists())


if __name__=='__main__':
    unittest.main()
