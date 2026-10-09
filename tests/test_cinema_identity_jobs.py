"""Owned two-phase admissions, denied providers and persistent identity choices."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from fastapi.testclient import TestClient
from affinityqa.cinema_preferences import CinemaMovieAgent
from affinityqa.errors import SchemaError
from affinityqa.individual_jobs import write
from affinityqa.public_cases import PublicCaseManager, public_policy
from affinityqa.public_demo import create_public_app
from affinityqa.qloo import Response, Settings
from test_cinema_capture import request_fixture
from test_groq_agent import OpenerFixture, UNIT_SECRET, UNIT_QLOO_SECRET
from test_individual_capture import TransportDouble

ORIGIN = 'https://judge.example'
PREFIX = '/api/demo/cases'


class ChoiceTransport(TransportDouble):
    def send(self, path, params):
        response = super().send(path, params)
        if path == '/search':
            # Deliberately different canonical name and a non-first selection.
            suffix = 2 if params['query'] == self.request['artists']['A'] else 3
            response.body['results'].append({'entity_id': f'bbbbbbbb-0000-4000-8000-{suffix:012d}',
                'name': 'Confirmed + canonical ' + str(suffix), 'types': ['urn:entity:artist']})
        return response


class CinemaIdentityJobTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT/'.test-runs'; parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent); self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.request = request_fixture()
        self.template = copy.deepcopy(self.request)
        self.template.pop('preferences'); self.template['schema_version'] = 2
        self.reads = [0, 0]; self.engine_count = 0
        self.transport = ChoiceTransport(self.request)
        self.opener = OpenerFixture()
        self.policy = public_policy(maximum_sessions=4, maximum_plans=4, maximum_executions=1,
            plans_per_session=2, executions_per_session=1, session_hours=24)
        for name in ('socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(name, side_effect=AssertionError('Actual provider denied'))
            guard.start(); self.addCleanup(guard.stop)

    def settings(self):
        self.reads[0] += 1
        return Settings(UNIT_QLOO_SECRET)

    def key(self):
        self.reads[1] += 1
        return UNIT_SECRET

    def engine(self):
        self.engine_count += 1
        return CinemaMovieAgent(UNIT_SECRET, forbidden_secrets=(UNIT_QLOO_SECRET,), _test_opener=self.opener)

    def service(self):
        value = PublicCaseManager(self.parent/'public', self.template, origin=ORIGIN,
            policy=self.policy, minimum_model_interval_seconds=0, execution_enabled=True,
            settings_loader=self.settings, remote_key_loader=self.key,
            _test_adapters=(self.engine, lambda: self.transport))
        self.addCleanup(value.close)
        return value

    def plan(self, service, token):
        return service.prepare(token, self.request['artists'], self.request['preferences'], confirm_identities=True)

    def pending(self, service, token):
        job = self.plan(service, token)
        self.assertEqual(self.reads, [0, 0])
        service.start(token, job['job_id'], job['plan_sha256'])
        service.manager.worker.join(15)
        self.assertFalse(service.manager.worker.is_alive())
        job = service.view(token, job['job_id'])
        self.assertEqual(job['status'], 'AWAITING_IDENTITY_CONFIRMATION', job)
        self.assertEqual((self.reads, self.engine_count, len(self.transport.calls)), ([1, 0], 0, 2))
        self.assertEqual(service.capabilities(token)['remaining_executions'], 0)
        return job

    def selection(self, job):
        return {k: job['identity_candidates'][k][-1]['entity_id'] for k in ('A', 'B')}

    def confirm(self, service, token, job, **changes):
        values = {'plan_hash': job['plan_sha256'], 'identity_receipt_hash': job['identity_receipt_sha256'],
                  'selected_entity_ids': self.selection(job)}
        values.update(changes)
        return service.confirm_identities(token, job['job_id'], **values)

    def test_capability_and_plan_are_pure_and_versioned(self):
        service = self.service(); token, _ = service.session()
        self.assertTrue(service.capabilities(token)['cinema_identity_confirmation_supported'])
        job = self.plan(service, token)
        self.assertEqual(job['case_protocol'], 'cinema-confirmed-identity-v1')
        self.assertEqual((job['maximum_qloo_requests'], job['maximum_model_decisions']), (4, 2))
        self.assertEqual(self.reads, [0, 0]); self.assertEqual(self.transport.calls, [])

    def test_same_admission_completes_manual_nonfirst_choices_at_zero_remaining(self):
        service = self.service(); token, _ = service.session(); job = self.pending(service, token)
        self.confirm(service, token, job)
        service.manager.worker.join(15)
        final = service.view(token, job['job_id'])
        self.assertEqual(final['status'], 'COMPLETE', final)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (4, 2))
        self.assertEqual(final['result']['qloo_attempts'], 4)
        self.assertEqual(final['result']['model_attempts'], 2)
        self.assertEqual(final['result']['preference_gate'], 'PASS')
        self.assertEqual(final['chosen_identities']['A']['entity_id'], self.selection(job)['A'])
        self.assertEqual(final['result']['cultural_gate'], 'NOT_VALIDATED')
        self.assertEqual(final['result']['causal_gate'], 'NOT_EVALUATED')
        service.verification(token, job['job_id'])
        with self.assertRaises(SchemaError): self.confirm(service, token, job)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (4, 2))

    def test_invalid_selection_hashes_or_cross_owner_read_no_remote_key(self):
        service = self.service(); token, _ = service.session(); other, _ = service.session()
        job = self.pending(service, token)
        for change in ({'plan_hash': '0'*64}, {'identity_receipt_hash': '0'*64},
                       {'selected_entity_ids': {'A': 'ffffffff-0000-4000-8000-000000000000', 'B': self.selection(job)['B']}},
                       {'selected_entity_ids': {'A': self.selection(job)['A'], 'B': self.selection(job)['A']}},
                       {'selected_entity_ids': {**self.selection(job), 'name': 'Injected'}}):
            with self.subTest(change=change), self.assertRaises(SchemaError): self.confirm(service, token, job, **change)
        with self.assertRaises(FileNotFoundError): self.confirm(service, other, job)
        self.assertEqual((self.reads, self.engine_count, len(self.transport.calls)), ([1, 0], 0, 2))

    def test_pending_restart_restores_choices_without_calls(self):
        service = self.service(); token, _ = service.session(); job = self.pending(service, token)
        service.close(); restored = self.service()
        saved = restored.view(token, job['job_id'])
        self.assertEqual(saved['identity_candidates'], job['identity_candidates'])
        self.assertEqual(saved['status'], 'AWAITING_IDENTITY_CONFIRMATION')
        self.assertEqual((self.reads, self.engine_count, len(self.transport.calls)), ([1, 0], 0, 2))
        self.confirm(restored, token, saved); restored.manager.worker.join(15)
        self.assertEqual(restored.view(token, job['job_id'])['status'], 'COMPLETE')

    def test_uncommitted_confirmation_restart_is_abandoned_without_calls(self):
        service = self.service(); token, _ = service.session(); job = self.pending(service, token)
        write(service.manager.root/job['job_id']/'identity-confirmation.json', {'incomplete': True})
        service.close(); restored = self.service()
        self.assertEqual(restored.view(token, job['job_id'])['status'], 'ABANDONED')
        self.assertEqual((self.reads, len(self.transport.calls)), ([1, 0], 2))
        with self.assertRaises(SchemaError): self.confirm(restored, token, job)

    def test_changed_saved_search_blocks_before_keys(self):
        service = self.service(); token, _ = service.session(); job = self.pending(service, token)
        directory = service.manager._capture_dir(job['job_id'])
        target = next(directory.glob('http-*.json'))
        target.write_bytes(target.read_bytes() + b' ')
        with self.assertRaises(SchemaError): self.confirm(service, token, job)
        self.assertEqual(self.reads, [1, 0]); self.assertEqual(len(self.transport.calls), 2)

    def test_http_closed_confirmation_requires_owner_origin_csrf_and_pending_hash(self):
        service = self.service()
        app = create_public_app(ROOT, origin=ORIGIN, case_manager=service)
        client = TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)
        self.addCleanup(client.close)
        csrf = client.post(PREFIX+'/session', json={}, headers={'Origin': ORIGIN}).json()['csrf_token']
        headers = {'Origin': ORIGIN, 'X-AffinityQA-CSRF': csrf}
        answer = client.post(PREFIX+'/plans', json={'artists': self.request['artists'],
            'preferences': self.request['preferences'], 'confirm_identities': True}, headers=headers)
        self.assertEqual(answer.status_code, 201, answer.text); job = answer.json()
        client.post(PREFIX+'/jobs/'+job['job_id']+'/execute', json={'plan_sha256': job['plan_sha256']}, headers=headers)
        service.manager.worker.join(15)
        job = client.get(PREFIX+'/jobs/'+job['job_id']).json()
        self.assertEqual(job['status'], 'AWAITING_IDENTITY_CONFIRMATION', job)
        body = {'plan_sha256': job['plan_sha256'], 'identity_receipt_sha256': job['identity_receipt_sha256'],
                'selected_entity_ids': self.selection(job)}
        path = PREFIX+'/jobs/'+job['job_id']+'/confirm-identities'
        for altered in ({}, {'Origin': 'https://evil.example', 'X-AffinityQA-CSRF': csrf}):
            self.assertEqual(client.post(path, json=body, headers=altered).status_code, 403)
        self.assertEqual(client.post(path, json={**body, 'name': 'Forged'}, headers=headers).status_code, 422)
        self.assertEqual(client.post(path, json={**body, 'identity_receipt_sha256': '0'*64}, headers=headers).status_code, 409)
        self.assertEqual(self.reads, [1, 0])
        response = client.post(path, json=body, headers=headers)
        self.assertEqual(response.status_code, 202, response.text)
        service.manager.worker.join(15)
        self.assertEqual(client.get(PREFIX+'/jobs/'+job['job_id']).json()['status'], 'COMPLETE')
        self.assertEqual(client.post(path, json=body, headers=headers).status_code, 409)
        text = client.get(PREFIX+'/jobs/'+job['job_id']+'/verification').text
        for value in (UNIT_SECRET, UNIT_QLOO_SECRET, str(self.parent), 'artifact_sha256'):
            self.assertNotIn(value, text)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (4, 2))


if __name__ == '__main__': unittest.main()
