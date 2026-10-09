"""Private/public discovery journeys with explicitly synthetic, denied-network providers."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from fastapi import FastAPI
from fastapi.testclient import TestClient
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent
from affinityqa.errors import SchemaError
from affinityqa.individual_api import routes
from affinityqa.individual_jobs import IndividualJobManager
from affinityqa.public_cases import PublicCaseManager, public_policy
from affinityqa.public_demo import create_public_app
from affinityqa.qloo import Settings
from test_cinema_identity_capture import identity_request, ID_A, ID_B
from test_discovery_capture import DiscoveryTransport, InterruptedDiscoveryOpener
from test_discovery_agent import Opener, TEST_SECRET
from test_groq_agent import UNIT_QLOO_SECRET

ORIGIN = 'https://judge.example'
PREFIX = '/api/demo/cases'


class DiscoveryJobTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT/'.test-runs'; parent.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=parent); self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name)
        self.request = identity_request()
        self.request['schema_version'] = 5
        for label, count in (('A', 1), ('B', 5)):
            self.request['preferences'][label] = {'schema_version': 1,
                'favorite_entity_ids': [r['entity_id'] for r in self.request['catalog'][:count]],
                'excluded_entity_ids': [self.request['catalog'][19]['entity_id']]}
        self.template = copy.deepcopy(self.request)
        self.template.pop('preferences'); self.template['schema_version'] = 2
        self.transport = DiscoveryTransport(self.request)
        self.opener = Opener(); self.reads = [0, 0]; self.engines = []
        for target in ('socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Real providers denied'))
            guard.start(); self.addCleanup(guard.stop)
        guard = patch('affinityqa.cinema_discovery_capture.time.sleep')
        guard.start(); self.addCleanup(guard.stop)

    def settings(self):
        self.reads[0] += 1
        return Settings(UNIT_QLOO_SECRET)

    def key(self):
        self.reads[1] += 1
        return TEST_SECRET

    def engine(self):
        value = DiscoveryMovieAgent(TEST_SECRET, forbidden_secrets=(UNIT_QLOO_SECRET,), _test_opener=self.opener)
        self.engines.append(value)
        return value

    def manager(self):
        value = IndividualJobManager(self.parent/'local', self.template, operator='groq', execution_enabled=True,
            settings_loader=self.settings, remote_key_loader=self.key, remote_minimum_interval_seconds=0.0,
            _test_adapters=(self.engine, lambda: self.transport), maximum_executions=1)
        self.addCleanup(value.close)
        return value

    def service(self):
        value = PublicCaseManager(self.parent/'public', self.template, origin=ORIGIN,
            policy=public_policy(maximum_sessions=4, maximum_plans=4, maximum_executions=1,
                plans_per_session=2, executions_per_session=1, session_hours=24),
            minimum_model_interval_seconds=0.0, execution_enabled=True,
            settings_loader=self.settings, remote_key_loader=self.key,
            _test_adapters=(self.engine, lambda: self.transport))
        self.addCleanup(value.close)
        return value

    def plan(self, manager):
        return manager.prepare(self.request['artists'], self.request['preferences'],
                               confirm_identities=True, discover_new_movies=True)

    def pending(self, manager):
        job = self.plan(manager)
        self.assertEqual(self.reads, [0, 0]); self.assertEqual(len(self.transport.calls), 0)
        manager.start(job['job_id'], job['plan_sha256']); manager.worker.join(15)
        self.assertFalse(manager.worker.is_alive())
        job = manager.view(job['job_id'])
        self.assertEqual(job['status'], 'AWAITING_IDENTITY_CONFIRMATION', job)
        self.assertEqual((self.reads, len(self.opener.calls), len(self.transport.calls)), ([1, 0], 0, 2))
        return job

    def confirm(self, manager, job, **changes):
        values = {'plan_hash': job['plan_sha256'], 'identity_receipt_hash': job['identity_receipt_sha256'],
                  'selected_entity_ids': {'A': ID_A, 'B': ID_B}}
        values.update(changes)
        return manager.confirm_identities(job['job_id'], **values)

    def test_pure_plan_new_capability_and_strict_explicit_contract(self):
        manager = self.manager()
        self.assertTrue(manager.capabilities()['cinema_discoveries_supported'])
        job = self.plan(manager)
        self.assertEqual((job['case_protocol'], job['maximum_model_decisions']), ('cinema-confirmed-discovery-v2', 2))
        self.assertEqual(manager.jobs[job['job_id']]['plan']['schema_version'], 6)
        for kwargs in ({'discover_new_movies': True}, {'discover_new_movies': 1, 'confirm_identities': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SchemaError):
                manager.request_for(self.request['artists'], self.request['preferences'], **kwargs)
        with self.assertRaises(SchemaError):
            manager.request_for(self.request['artists'], confirm_identities=True, discover_new_movies=True)
        self.assertEqual(self.reads, [0, 0]); self.assertFalse(self.opener.calls)

    def test_old_requests_keep_their_protocols(self):
        manager = self.manager()
        for confirmation, expected in ((False, 'cinema-preferences-v1'), (True, 'cinema-confirmed-identity-v1')):
            job = manager.prepare(self.request['artists'], self.request['preferences'], confirm_identities=confirmation)
            self.assertEqual(job['case_protocol'], expected)

    def test_private_complete_five_new_movies_and_one_consumed_admission(self):
        manager = self.manager(); job = self.pending(manager)
        self.assertEqual(manager.capabilities()['remaining_executions'], 0)
        self.confirm(manager, job); manager.worker.join(15)
        final = manager.view(job['job_id'])
        self.assertEqual(final['status'], 'COMPLETE', final)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (4, 2))
        self.assertEqual(final['saved_model_packets'], 2)
        for label, count in (('A', 19), ('B', 15)):
            row = final['result']['cinema_results'][label]
            self.assertEqual(len(row['raw_ranking']), count)
            self.assertEqual(len(row['delivered']), 5)
            forbidden = set(self.request['preferences'][label]['favorite_entity_ids'] + self.request['preferences'][label]['excluded_entity_ids'])
            self.assertTrue(set(row['delivered']).isdisjoint(forbidden))
        self.assertEqual(final['result']['causal_gate'], 'NOT_EVALUATED')
        self.assertEqual(final['result']['cultural_gate'], 'NOT_VALIDATED')
        with self.assertRaises(SchemaError): self.confirm(manager, job)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (4, 2))

    def test_pending_restart_retains_selection_without_new_calls(self):
        manager = self.manager(); job = self.pending(manager); manager.close()
        restored = self.manager()
        saved = restored.view(job['job_id'])
        self.assertEqual(saved['status'], 'AWAITING_IDENTITY_CONFIRMATION')
        self.assertEqual(saved['identity_candidates'], job['identity_candidates'])
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (2, 0))
        self.confirm(restored, saved); restored.worker.join(15)
        self.assertEqual(restored.view(job['job_id'])['status'], 'COMPLETE')

    def test_invalid_selection_hash_or_changed_artifacts_blocks_before_keys(self):
        manager = self.manager(); job = self.pending(manager)
        for kwargs in ({'plan_hash': '0'*64}, {'identity_receipt_hash': '0'*64},
                       {'selected_entity_ids': {'A': ID_A, 'B': ID_A}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SchemaError): self.confirm(manager, job, **kwargs)
        sample = next(manager._capture_dir(job['job_id']).glob('http-*.json'))
        sample.write_bytes(sample.read_bytes() + b' ')
        with self.assertRaises(SchemaError): self.confirm(manager, job)
        self.assertEqual((self.reads, len(self.opener.calls), len(self.transport.calls)), ([1, 0], 0, 2))

    def test_second_model_429_is_partial_and_cannot_execute_again(self):
        self.opener = InterruptedDiscoveryOpener(2)
        manager = self.manager(); job = self.pending(manager)
        self.confirm(manager, job); manager.worker.join(15)
        final = manager.view(job['job_id'])
        self.assertEqual(final['status'], 'PARTIAL', final)
        self.assertEqual(final['error_class'], 'DiscoveryRateLimitError')
        self.assertEqual((final['result']['model_attempts'], len(self.opener.calls)), (2, 2))
        self.assertEqual(set(final['result']['cinema_results']), {'A'})
        with self.assertRaises(SchemaError): manager.start(job['job_id'], job['plan_sha256'])
        self.assertEqual(len(self.opener.calls), 2)

    def test_public_HTTP_owned_confirmation_complete_and_redacted_receipt(self):
        service = self.service()
        client = TestClient(create_public_app(ROOT, origin=ORIGIN, case_manager=service), base_url=ORIGIN, raise_server_exceptions=False)
        self.addCleanup(client.close)
        csrf = client.post(PREFIX+'/session', json={}, headers={'Origin': ORIGIN}).json()['csrf_token']
        headers = {'Origin': ORIGIN, 'X-AffinityQA-CSRF': csrf}
        cap = client.get(PREFIX+'/capabilities').json()
        self.assertTrue(cap['cinema_discoveries_supported'])
        body = {'artists': self.request['artists'], 'preferences': self.request['preferences'],
                'confirm_identities': True, 'discover_new_movies': True}
        answer = client.post(PREFIX+'/plans', json=body, headers=headers)
        self.assertEqual(answer.status_code, 201, answer.text); job = answer.json()
        client.post(PREFIX+'/jobs/'+job['job_id']+'/execute', json={'plan_sha256': job['plan_sha256']}, headers=headers)
        service.manager.worker.join(15)
        job = client.get(PREFIX+'/jobs/'+job['job_id']).json()
        self.assertEqual(job['status'], 'AWAITING_IDENTITY_CONFIRMATION', job)
        path = PREFIX+'/jobs/'+job['job_id']+'/confirm-identities'
        confirm = {'plan_sha256': job['plan_sha256'], 'identity_receipt_sha256': job['identity_receipt_sha256'],
                   'selected_entity_ids': {'A': ID_A, 'B': ID_B}}
        self.assertEqual(client.post(path, json=confirm, headers={'Origin': ORIGIN}).status_code, 403)
        outsider = TestClient(client.app, base_url=ORIGIN, raise_server_exceptions=False); self.addCleanup(outsider.close)
        self.assertEqual(outsider.get(PREFIX+'/jobs/'+job['job_id']).status_code, 404)
        response = client.post(path, json=confirm, headers=headers)
        self.assertEqual(response.status_code, 202, response.text); service.manager.worker.join(15)
        final = client.get(PREFIX+'/jobs/'+job['job_id']).json()
        self.assertEqual(final['status'], 'COMPLETE', final)
        self.assertEqual(client.post(path, json=confirm, headers=headers).status_code, 409)
        text = client.get(PREFIX+'/jobs/'+job['job_id']+'/verification').text
        for value in (TEST_SECRET, UNIT_QLOO_SECRET, str(self.parent), 'artifact_sha256', 'provider_envelope'):
            self.assertNotIn(value, text)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (4, 2))

    def test_private_HTTP_versioned_preview(self):
        manager = self.manager(); app = FastAPI(); app.include_router(routes(manager))
        client = TestClient(app, base_url='http://localhost'); self.addCleanup(client.close)
        body = {'artists': self.request['artists'], 'preferences': self.request['preferences'],
                'confirm_identities': True, 'discover_new_movies': True}
        response = client.post('/api/individual/plans', json=body, headers={'Origin': 'http://localhost'})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()['case_protocol'], 'cinema-confirmed-discovery-v2')
        self.assertEqual(self.reads, [0, 0]); self.assertFalse(self.transport.calls)


if __name__ == '__main__': unittest.main()
