"""Public boundary and deployment selection: offline, no credentials or provider calls."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from fastapi.testclient import TestClient
from affinityqa.provider_scheduler import GROQ_FREE_CONSERVATIVE
from affinityqa.public_demo import create_public_app
from affinityqa.repeatable_case_config import configure_repeatable_cases
from affinityqa.repeatable_cases import repeatable_policy
from test_individual_remote import request_fixture


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class RepeatablePublicIntegrationTests(unittest.TestCase):
    def setUp(self):
        parent = Path(os.environ.get('AFFINITYQA_TEST_STORAGE_ROOT', str(ROOT.parent/'test-private-scratch')))
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='rpt-http-', dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root/'owner-repeatable.json'
        self.value = {'schema_version': 2, 'admission_mode': 'repeatable-v1',
            'request': request_fixture(), 'policy': repeatable_policy(),
            'minimum_model_interval_seconds': 22,
            'http_limits': {'case_session_limit': 12, 'case_write_limit': 30, 'case_read_limit': 240},
            'provider_limits': {'groq': [vars(x) for x in GROQ_FREE_CONSERVATIVE],
                'qloo': [{'name': 'rpm', 'capacity': 10, 'seconds': 60, 'metric': 'requests', 'basis': 'conservative'}]}}
        self.config.write_text(json.dumps(self.value), encoding='utf8')
        (self.root/'web/out').mkdir(parents=True)
        (self.root/'web/out/demo.html').write_text('<html/>', encoding='utf8')
        self.render = module('repeatable_render_fixture', ROOT/'deployment/start_render.py')
        self.serve = module('repeatable_serve_fixture', ROOT/'scripts/serve_public_demo.py')
        for target in ('socket.getaddrinfo', 'socket.create_connection'):
            guard = patch(target, side_effect=AssertionError('External network forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def env(self):
        return {'RENDER_EXTERNAL_URL': 'https://judge.example',
            'AFFINITYQA_REPEATABLE_CASE_CONFIG': str(self.config),
            'AFFINITYQA_REPEATABLE_CASE_STORAGE': str(self.root/'repeatable')}

    def test_actual_server_uses_repeatable_router_and_retains_http_security(self):
        with patch('affinityqa.repeatable_case_config.Settings.from_environment', side_effect=AssertionError('No key read')):
            manager, limits = configure_repeatable_cases(self.config, self.root/'repeatable', origin='https://judge.example')
        self.addCleanup(manager.close)
        app = create_public_app(ROOT, origin='https://judge.example', case_manager=manager, **limits)
        with TestClient(app, base_url='https://judge.example', raise_server_exceptions=False) as client:
            self.assertEqual(client.post('/api/demo/cases/session', json={}).status_code, 403)
            response = client.post('/api/demo/cases/session', json={}, headers={'Origin': 'https://judge.example'})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['admission_mode'], 'repeatable-v1')
            self.assertIn('HttpOnly', response.headers['set-cookie'])
            self.assertIn('Secure', response.headers['set-cookie'])
            self.assertIn('SameSite=strict', response.headers['set-cookie'])
            self.assertEqual(client.get('/api/demo/cases/capabilities').json()['remaining_executions'], None)
            header = {'Origin': 'https://judge.example', 'X-AffinityQA-CSRF': response.json()['csrf_token']}
            body = {'artists': self.value['request']['artists']}
            self.assertEqual(client.post('/api/demo/cases/plans', json=body, headers={'Origin': 'https://judge.example'}).status_code, 403)
            jobs = [client.post('/api/demo/cases/plans', json=body, headers=header) for _ in range(3)]
            self.assertTrue(all(x.status_code == 201 for x in jobs), [x.text for x in jobs])
            job = jobs[0].json()
            self.assertEqual(client.get('/api/demo/cases/jobs/'+job['job_id']).status_code, 200)
            self.assertEqual(client.get('/api/demo/cases/jobs/'+job['job_id']+'?owner=other').status_code, 400)
            started = client.post('/api/demo/cases/jobs/'+job['job_id']+'/execute',
                json={'plan_sha256': job['plan_sha256']}, headers=header)
            self.assertEqual(started.status_code, 503)
            health = client.get('/healthz').json()
            self.assertEqual(health['admission_mode'], 'repeatable-v1')
            self.assertEqual(health['queued'], 0)
            self.assertFalse(health['capture_active'])
            self.assertEqual(health['provider_readiness'], 'NOT_CHECKED_BY_LIVENESS')

    def test_render_routes_historical_store_only_to_read_only_reader(self):
        env = self.env()
        env.update(AFFINITYQA_PUBLIC_CASE_CONFIG=str(self.root/'legacy-owner.json'),
            AFFINITYQA_PUBLIC_CASE_STORAGE=str(self.root/'legacy'))
        command = self.render.command(env, self.root)
        self.assertIn('--repeatable-config', command)
        self.assertIn('--repeatable-storage', command)
        self.assertIn('--legacy-cases-storage', command)
        self.assertNotIn('--cases-config', command)
        self.assertNotIn('--cases-storage', command)
        self.assertNotIn('--cases-execute', command)

    def test_render_rejects_half_configured_relative_or_nested_repeatable_store(self):
        for update in ({'AFFINITYQA_REPEATABLE_CASE_CONFIG': ''},
            {'AFFINITYQA_REPEATABLE_CASE_STORAGE': ''},
            {'AFFINITYQA_REPEATABLE_CASE_STORAGE': 'relative'},
            {'AFFINITYQA_REPEATABLE_CASE_CONFIG': 'relative'}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.render.command({**self.env(), **update}, self.root)
        old = self.root/'sealed'
        for new in (old, old/'nested', self.root):
            env = {**self.env(), 'AFFINITYQA_PUBLIC_CASE_CONFIG': str(self.root/'legacy.json'),
                'AFFINITYQA_PUBLIC_CASE_STORAGE': str(old), 'AFFINITYQA_REPEATABLE_CASE_STORAGE': str(new)}
            with self.subTest(path=new), self.assertRaises(ValueError): self.render.command(env, self.root)

    def test_render_keeps_private_keys_explicit_without_printing_values(self):
        env = {**self.env(), 'AFFINITYQA_ENABLE_NEW_CASES': '1'}
        with self.assertRaises(ValueError): self.render.command(env, self.root)
        env.update(AFFINITYQA_QLOO_ENV_FILE=str(self.root/'private-qloo.env'),
            AFFINITYQA_MODEL_ENV_FILE=str(self.root/'private-groq.env'))
        command = self.render.command(env, self.root)
        self.assertIn('--cases-execute', command)
        self.assertEqual(command[command.index('--case-model-env')+1], str(self.root/'private-groq.env'))
        self.assertNotIn('--cases-config', command)

    def test_cli_refuses_ambiguous_managers_or_implicit_history(self):
        base = ['serve_public_demo.py', '--origin', 'https://judge.example']
        variants = [base+['--legacy-cases-storage', str(self.root/'legacy')],
            base+['--repeatable-config', str(self.config)],
            base+['--repeatable-config', str(self.config), '--repeatable-storage', str(self.root/'new'),
                '--cases-config', str(self.config), '--cases-storage', str(self.root/'old')]]
        for argv in variants:
            with self.subTest(argv=argv), patch.object(sys, 'argv', argv), patch('uvicorn.run') as run, self.assertRaises(SystemExit):
                self.serve.main()
            run.assert_not_called()

    def test_cli_preview_closes_repeatable_manager_and_retains_bound_origin(self):
        argv = ['serve_public_demo.py', '--origin', 'https://judge.example',
            '--repeatable-config', str(self.config), '--repeatable-storage', str(self.root/'repeatable')]
        with patch.object(sys, 'argv', argv), patch('uvicorn.run') as run:
            self.assertEqual(self.serve.main(), 0)
        app = run.call_args.args[0]
        self.assertEqual(app.state.case_manager.origin, 'https://judge.example')
        self.assertTrue(app.state.case_manager.manager.closed)
        self.assertEqual(run.call_args.kwargs['host'], '127.0.0.1')


if __name__ == '__main__': unittest.main()
