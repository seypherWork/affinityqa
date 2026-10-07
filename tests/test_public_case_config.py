"""Explicit server startup and lazy private credentials; no real providers."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.errors import AffinityQAError
from affinityqa.public_case_config import configure_cases, read_configuration
from affinityqa.public_cases import public_policy
from test_individual_remote import request_fixture


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


class PublicCaseConfigurationTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'.test-runs';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'owner.json'
        self.value={'schema_version':1,'request':request_fixture(),
            'policy':public_policy(maximum_sessions=5,maximum_plans=5,maximum_executions=1,
                                   plans_per_session=2,executions_per_session=1,session_hours=24),
            'minimum_model_interval_seconds':0,
            'http_limits':{'case_session_limit':12,'case_write_limit':30,'case_read_limit':240}}
        self.save(self.value)
        self.render=module('private_render_command_fixture',ROOT/'deployment/start_render.py')
        self.serve=module('private_serve_command_fixture',ROOT/'scripts/serve_public_demo.py')
        for target in ('socket.create_connection','socket.getaddrinfo','affinityqa.individual_remote_capture.LiveTransport'):
            guard=patch(target,side_effect=AssertionError('Provider/DNS forbidden'));guard.start();self.addCleanup(guard.stop)

    def save(self,value):self.path.write_text(json.dumps(value),encoding='utf-8')

    def test_documented_closed_policy_is_accepted_by_actual_reader(self):
        text=(ROOT/'docs/PUBLIC-NEW-CASES.md').read_text(encoding='utf-8')
        example=text.split('```json\n',1)[1].split('\n```',1)[0]
        self.value['policy']=json.loads(example)
        self.save(self.value)
        self.assertEqual(read_configuration(self.path)['policy'],self.value['policy'])

    def manager(self,**kwargs):
        current,limits=configure_cases(self.path,self.root/'store',origin='https://judge.example',**kwargs)
        self.addCleanup(current.close);return current,limits

    def test_explicit_preview_does_not_read_private_credentials(self):
        with (patch('affinityqa.public_case_config.Settings.from_environment',side_effect=AssertionError('Read key in preview')),
              patch('affinityqa.public_case_config.load_private_credential',side_effect=AssertionError('Read key in preview'))):
            current,limits=self.manager(qloo_env=self.root/'nonexistent.env',model_env=self.root/'nonexistent-model.env')
            token,_=current.session();job=current.prepare(token,self.value['request']['artists'])
            self.assertEqual(job['status'],'PLANNED')
            self.assertFalse(current.capabilities(token)['execution_enabled'])
            self.assertEqual(limits,self.value['http_limits'])

    def test_enabled_startup_only_inspects_explicit_private_file_metadata(self):
        qloo,model=self.root/'qloo.env',self.root/'model.env'
        qloo.write_text('UNIT_FILE_NOT_A_REAL_KEY',encoding='utf-8');model.write_text('UNIT_FILE_NOT_A_REAL_KEY',encoding='utf-8')
        with (patch('affinityqa.public_case_config.Settings.from_environment',side_effect=AssertionError('Startup key read')),
              patch('affinityqa.public_case_config.load_private_credential',side_effect=AssertionError('Startup key read'))):
            current,_=self.manager(execution_enabled=True,qloo_env=qloo,model_env=model)
            token,_=current.session();current.prepare(token,self.value['request']['artists'])
            self.assertTrue(current.capabilities(token)['execution_enabled'])

    def test_invalid_configuration_is_rejected_before_storage_creation(self):
        for mutate in (lambda v:v.update(schema_version=True),lambda v:v.update(provider_url='https://unit.invalid'),
                       lambda v:v['policy'].update(maximum_executions=True),lambda v:v['http_limits'].update(case_read_limit=601),
                       lambda v:v['http_limits'].update(case_read_limit=True),lambda v:v.update(minimum_model_interval_seconds=None)):
            value=copy.deepcopy(self.value);mutate(value);self.save(value)
            with self.assertRaises(AffinityQAError):self.manager()
            self.assertFalse((self.root/'store').exists())

    def test_missing_or_relative_credentials_and_storage_fail_before_lease(self):
        for values in ({'execution_enabled':True},{'execution_enabled':True,'qloo_env':Path('relative.env'),'model_env':self.root/'missing.env'}):
            with self.assertRaises(AffinityQAError):self.manager(**values)
            self.assertFalse((self.root/'store').exists())
        with self.assertRaises(AffinityQAError):configure_cases(self.path,Path('relative-storage'),origin='https://judge.example')

    def test_duplicate_owner_json_and_changed_persisted_policy_are_rejected(self):
        self.path.write_text('{"schema_version":1,"schema_version":1}',encoding='utf-8')
        with self.assertRaises(AffinityQAError):read_configuration(self.path)
        self.save(self.value);current,_=self.manager();current.close()
        changed=copy.deepcopy(self.value);changed['http_limits']['case_read_limit']=200;self.save(changed)
        restored,_=self.manager();restored.close()  # Request queues are not retained execution budgets.
        changed['policy']['maximum_sessions']=6;self.save(changed)
        with self.assertRaises(AffinityQAError):self.manager()

    def test_render_can_start_cases_without_a_private_replay_bundle(self):
        (self.root/'web/out').mkdir(parents=True);(self.root/'web/out/demo.html').write_text('<html/>',encoding='utf-8')
        env={'RENDER_EXTERNAL_URL':'https://judge.example','AFFINITYQA_PUBLIC_CASE_CONFIG':str(self.path),
             'AFFINITYQA_PUBLIC_CASE_STORAGE':str(self.root/'store')}
        command=self.render.command(env,self.root)
        self.assertIn('--cases-config',command);self.assertIn('--cases-storage',command)
        self.assertNotIn('--cases-execute',command);self.assertNotIn('--run-id',command)
        self.assertNotIn('--evidence-root',command)

    def test_render_enable_requires_private_paths_and_keeps_owner_origin(self):
        (self.root/'web/out').mkdir(parents=True);(self.root/'web/out/demo.html').write_text('<html/>',encoding='utf-8')
        env={'RENDER_EXTERNAL_URL':'https://judge.example','AFFINITYQA_PUBLIC_CASE_CONFIG':str(self.path),
             'AFFINITYQA_PUBLIC_CASE_STORAGE':str(self.root/'store'),'AFFINITYQA_ENABLE_NEW_CASES':'1'}
        with self.assertRaises(ValueError):self.render.command(env,self.root)
        env.update(AFFINITYQA_QLOO_ENV_FILE=str(self.root/'qloo.env'),AFFINITYQA_MODEL_ENV_FILE=str(self.root/'model.env'))
        command=self.render.command(env,self.root)
        self.assertIn('--cases-execute',command)
        self.assertEqual(command[command.index('--origin')+1],'https://judge.example')
        for bad in ('true','yes','2'):
            with self.assertRaises(ValueError):self.render.command({**env,'AFFINITYQA_ENABLE_NEW_CASES':bad},self.root)

    def test_render_rejects_implicit_or_half_configured_surface(self):
        (self.root/'web/out').mkdir(parents=True);(self.root/'web/out/demo.html').write_text('<html/>',encoding='utf-8')
        for extra in ({},{'AFFINITYQA_ENABLE_NEW_CASES':'1'},
                      {'AFFINITYQA_PUBLIC_CASE_CONFIG':str(self.path)},
                      {'AFFINITYQA_RUN_ID':'20261006T000000Z-00000000'}):
            with self.assertRaises(ValueError):self.render.command({'RENDER_EXTERNAL_URL':'https://judge.example',**extra},self.root)

    def test_cli_default_starts_no_case_manager_and_uses_loopback(self):
        with (patch.object(sys,'argv',['serve_public_demo.py','--origin','http://127.0.0.1:8798']),
              patch('uvicorn.run') as run):
            self.assertEqual(self.serve.main(),0)
            self.assertIsNone(run.call_args.args[0].state.case_manager)
            self.assertEqual(run.call_args.kwargs['host'],'127.0.0.1')
            self.assertFalse(run.call_args.kwargs['access_log'])

    def test_cli_preview_closes_manager_without_model_or_qloo_reads(self):
        argv=['serve_public_demo.py','--origin','https://judge.example','--cases-config',str(self.path),'--cases-storage',str(self.root/'store')]
        with patch.object(sys,'argv',argv),patch('uvicorn.run') as run:
            self.assertEqual(self.serve.main(),0)
        self.assertTrue(run.call_args.args[0].state.case_manager.manager.closed)

    def test_cli_case_flags_require_config_and_failed_app_binding_releases_lease(self):
        with (patch.object(sys,'argv',['serve_public_demo.py','--origin','https://judge.example','--cases-execute']),
              patch('uvicorn.run') as run,self.assertRaises(SystemExit)):self.serve.main()
        run.assert_not_called()
        argv=['serve_public_demo.py','--origin','https://judge.example','--cases-config',str(self.path),
              '--cases-storage',str(self.root/'store'),'--run-id','bad','--receipt-sha256','bad']
        with patch.object(sys,'argv',argv),patch('uvicorn.run') as run,self.assertRaises(ValueError):self.serve.main()
        run.assert_not_called()
        restored,_=self.manager();restored.close()


if __name__=='__main__':unittest.main()
