"""Denied-network full remote-protocol fixtures; no Groq or cultural proof."""
import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.agents import AgentError
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
from affinityqa.groq_agent import GroqToolContextMovieAgent, MODEL
from affinityqa.individual_remote_capture import prepare_plan, execute_capture, load_private_credential
from affinityqa.individual_remote_verify import verify_individual_remote, verify_manifest
from affinityqa.individual_verify import verify_individual, write_receipt
from affinityqa.qloo import Settings
from test_groq_agent import OpenerFixture, UNIT_SECRET, UNIT_QLOO_SECRET
from test_individual_capture import fixture, TransportDouble


def request_fixture():
    request = fixture()
    request.update(schema_version=2, model={'provider': 'groq', 'name': MODEL})
    return request


class InterruptedOpener(OpenerFixture):
    def open(self, request, timeout):
        if len(self.calls) == 8:
            self.calls.append((request, json.loads(request.data), timeout))
            raise HTTPError(request.full_url, 429, 'Synthetic rate limit', {}, io.BytesIO(UNIT_SECRET.encode()))
        return super().open(request, timeout)


class VariedBackendOpener(OpenerFixture):
    def __init__(self, *, absent=False, regression=False):
        super().__init__(self.vary)
        self.absent, self.regression = absent, regression

    def vary(self, body):
        body['system_fingerprint'] = None if self.absent and len(self.calls) == 2 else (
            'unit-deployment-a' if len(self.calls) % 2 else 'unit-deployment-b')
        if self.regression and len(self.calls) > 6:
            message = body['choices'][0]['message']
            indices = json.loads(message['content'])['ordered_catalog_indices']
            message['content'] = json.dumps({'ordered_catalog_indices': indices[1:]+indices[:1]})


class RemoteIndividualTests(unittest.TestCase):
    def setUp(self):
        temporary = ROOT/'.test-runs'
        temporary.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.output = self.parent/'remote-capture'
        self.request = request_fixture()
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network/DNS denied in remote fixture'))
            guard.start()
            self.addCleanup(guard.stop)

    def capture(self, opener=None, transport=None):
        self.opener = opener or OpenerFixture()
        self.engine = GroqToolContextMovieAgent(UNIT_SECRET, forbidden_secrets=(UNIT_QLOO_SECRET,), _test_opener=self.opener)
        self.transport = transport or TransportDouble(self.request)
        plan = prepare_plan(self.request, self.output)
        with patch('affinityqa.individual_remote_capture.time.sleep'):
            self.report, self.run = execute_capture(self.request, self.output, plan['plan_sha256'],
                Settings(UNIT_QLOO_SECRET), UNIT_SECRET,
                _test_adapters=(lambda: self.engine, lambda: self.transport))
        return self.report

    def edit(self, name, action):
        path = self.run/name
        value = json.loads(path.read_text('utf-8'))
        action(value)
        path.write_text(json.dumps(value), 'utf-8')

    def packet(self, action, number=7, rehash=True):
        def mutate(packet):
            action(packet)
            if rehash:
                packet['observation']['provider_envelope_sha256'] = fingerprint(packet['observation']['provider_envelope'])
        self.edit(f'causal-execution-{number:03d}.json', mutate)

    def rejected(self):
        with self.assertRaises(SchemaError):
            verify_individual_remote(self.run)

    def test_plan_is_pure_and_closes_provider_contract(self):
        plan = prepare_plan(self.request, self.output)
        self.assertEqual(list(self.parent.iterdir()), [])
        self.assertEqual(plan['schema_version'], 3)
        self.assertNotIn('ollama_url', plan)
        self.assertNotIn('model_digest', json.dumps(plan))
        self.assertEqual(plan['model_load_requests'], 0)
        self.assertEqual(plan['new_model_metadata_requests'], 0)
        self.assertEqual(plan['remote_operator']['model'], MODEL)

    def test_old_version_digest_endpoint_or_model_cannot_enter_remote_plan(self):
        mutations = [lambda r:r.update(schema_version=1),
            lambda r:r['model'].update(digest='d'*64),
            lambda r:r['model'].update(name='other-model'),
            lambda r:r['model'].update(endpoint='https://other.invalid')]
        for change in mutations:
            request = copy.deepcopy(self.request)
            change(request)
            with self.subTest(request=request), self.assertRaises(SchemaError):
                prepare_plan(request, self.output)
        self.assertFalse(self.output.exists())

    def test_changed_hash_rejected_before_factories_or_output(self):
        with self.assertRaises(SchemaError):
            execute_capture(self.request, self.output, '0'*64, Settings(UNIT_QLOO_SECRET), UNIT_SECRET,
                _test_adapters=(lambda:self.fail('factory started'), lambda:self.fail('transport started')))
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_both_private_credentials_rejected_before_any_record_or_send(self):
        for secret in (UNIT_SECRET, UNIT_QLOO_SECRET):
            request = copy.deepcopy(self.request)
            request['artists']['A'] = secret
            plan = prepare_plan(request, self.output)
            with self.assertRaises(SchemaError):
                execute_capture(request, self.output, plan['plan_sha256'], Settings(UNIT_QLOO_SECRET), UNIT_SECRET)
        self.assertFalse(self.output.exists())

    def test_complete_remote_protocol_simulation_is_independently_recomputed(self):
        self.capture()
        before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()}
        receipt = verify_individual_remote(self.run)
        self.assertEqual((receipt['verification_status'], receipt['verified_model_packets'], receipt['verified_provider_samples']),
                         ('VERIFIED_COMPLETE',39,4))
        self.assertEqual(receipt['causal_gate'], 'PASS')
        self.assertEqual(receipt['integration_gate'], 'PASS')
        self.assertEqual(receipt['backend_comparability']['status'], 'STABLE_KNOWN')
        self.assertEqual(receipt['backend_comparability']['observed_decisions'], 39)
        self.assertEqual(receipt['behavioral_gate'], 'OBSERVED_RECOVERY')
        self.assertEqual(receipt['independent_score_reports'], 3)
        self.assertEqual(receipt['provenance'], 'SIMULATION_ONLY')
        self.assertFalse(receipt['external_service_attested'])
        self.assertEqual(receipt['cultural_gate'], 'NOT_VALIDATED')
        self.assertEqual(receipt['release_gate'], 'BLOCKED')
        self.assertEqual(receipt['model_load_attempts'], 0)
        self.assertEqual(len(self.opener.calls), 39)
        events = [json.loads(r) for r in (self.run/'ledger.jsonl').read_text().splitlines()]
        self.assertEqual(sum(r['kind']=='observed_session_boundary' for r in events), 54)
        self.assertFalse((self.run/'model-readiness.json').exists())
        self.assertEqual(before, {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()})
        for path in self.run.iterdir():
            text = path.read_text('utf-8')
            self.assertNotIn(UNIT_SECRET, text)
            self.assertNotIn(UNIT_QLOO_SECRET, text)

    def test_partial_qloo_failure_has_no_remote_requests(self):
        self.capture(transport=TransportDouble(self.request, fail=True))
        receipt = verify_individual_remote(self.run)
        self.assertEqual((receipt['verification_status'], receipt['qloo_attempts'], receipt['verified_provider_samples'],
                          receipt['model_attempts'], len(self.opener.calls)), ('VERIFIED_PARTIAL',1,0,0,0))

    def test_partial_qloo_failure_cannot_claim_a_model_attempt_before_preflight(self):
        self.capture(transport=TransportDouble(self.request, fail=True))
        self.edit('individual-report.json',lambda r:r.update(model_attempts=1))
        self.rejected()

    def test_partial_remote_rate_limit_after_policy_retains_first_failed_attempt(self):
        self.capture(opener=InterruptedOpener())
        receipt = verify_individual_remote(self.run)
        self.assertEqual((receipt['verification_status'], receipt['model_attempts'], receipt['verified_model_packets']),
                         ('VERIFIED_PARTIAL',9,8))
        self.assertEqual(receipt['error_class'], 'AgentError')
        self.assertEqual(receipt['causal_gate'], 'NOT_EVALUATED')
        self.assertTrue((self.run/'frozen-causal-policy.json').exists())
        self.assertEqual(len(self.opener.calls), 9)

    def test_partial_truncated_decision_is_never_filled_or_approved(self):
        self.capture(opener=OpenerFixture(lambda b:b['choices'][0].update(finish_reason='length')))
        receipt = verify_individual_remote(self.run)
        self.assertEqual((receipt['model_attempts'], receipt['verified_model_packets']), (1,0))
        self.assertEqual(receipt['behavioral_gate'], 'NOT_EVALUATED')

    def test_complete_insensitive_behavior_remains_inconclusive(self):
        def insensitive(body):
            body['choices'][0]['message']['content'] = json.dumps({'ordered_catalog_indices': list(range(20))})
        self.capture(opener=OpenerFixture(insensitive))
        receipt = verify_individual_remote(self.run)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_COMPLETE')
        self.assertEqual(receipt['behavioral_gate'], 'INCONCLUSIVE')

    def test_varied_backend_completes_39_decisions_but_causal_attribution_is_inconclusive(self):
        self.capture(opener=VariedBackendOpener())
        self.assertEqual((self.report['status'], self.report['model_attempts']), ('COMPLETE', 39))
        receipt = verify_individual_remote(self.run)
        self.assertEqual(receipt['verified_model_packets'], 39)
        self.assertEqual(receipt['integration_gate'], 'PASS')
        self.assertEqual(receipt['causal_gate'], 'INCONCLUSIVE')
        self.assertEqual(receipt['backend_comparability']['status'], 'VARIED')
        self.assertEqual(receipt['backend_comparability']['system_fingerprints'],
                         ['unit-deployment-a', 'unit-deployment-b'])
        self.assertEqual(receipt['behavioral_gate'], 'OBSERVED_RECOVERY')
        self.assertEqual(set(receipt['observed_recoveries_by_fault'].values()), {3})
        self.assertTrue(all(len(case['checks']) == 9 and all(case['checks'].values())
                            for case in receipt['summary']['cases']))

    def test_backend_variance_does_not_hide_failed_integration_checks(self):
        self.capture(opener=VariedBackendOpener(regression=True))
        receipt = verify_individual_remote(self.run)
        self.assertEqual(receipt['verified_model_packets'], 39)
        self.assertEqual(receipt['integration_gate'], 'FAIL')
        self.assertEqual(receipt['causal_gate'], 'FAIL')

    def test_mixed_absent_and_varied_backend_is_inconclusive(self):
        self.capture(opener=VariedBackendOpener(absent=True))
        receipt = verify_individual_remote(self.run)
        self.assertEqual(receipt['integration_gate'], 'PASS')
        self.assertEqual(receipt['causal_gate'], 'INCONCLUSIVE')
        self.assertEqual(receipt['backend_comparability']['status'], 'VARIED_AND_ABSENT')
        self.assertEqual(receipt['backend_comparability']['missing_fingerprint_decisions'], 1)

    def test_rehashed_report_cannot_promote_backend_variance_to_causal_pass(self):
        self.capture(opener=VariedBackendOpener())
        self.edit('individual-report.json', lambda r:r.update(causal_gate='PASS'))
        self.rejected()

    def test_provider_manifest_wrong_weights_digest_or_options_rejected(self):
        self.capture()
        for change in (lambda m:m.update(model_digest='d'*64), lambda m:m['options'].update(seed=8),
                       lambda m:m.update(immutable_model_revision_attested=True)):
            original = (self.run/'model-manifest.json').read_bytes()
            self.edit('model-manifest.json', change)
            self.rejected()
            (self.run/'model-manifest.json').write_bytes(original)

    def test_envelope_hash_cannot_hide_answer_model_usage_or_private_field_change(self):
        self.capture()
        mutations = [lambda p:p['observation']['provider_envelope'].update(model='other-model'),
            lambda p:p['observation']['provider_envelope']['choice'].update(ordered_catalog_indices=list(reversed(range(20)))),
            lambda p:p['observation']['provider_envelope']['usage'].update(prompt_tokens=1001),
            lambda p:p['observation']['provider_envelope']['choice'].update(reasoning='private text'),
            lambda p:p['observation']['provider_envelope']['usage'].update(total_tokens=True)]
        path = self.run/'causal-execution-007.json'
        original = path.read_bytes()
        for change in mutations:
            self.packet(change)
            self.rejected()
            path.write_bytes(original)

    def test_effective_http_body_hash_is_checked_beyond_decision_input(self):
        self.capture()
        self.packet(lambda p:p['observation'].update(provider_request_sha256='0'*64))
        self.rejected()

    def test_missing_envelope_or_mixed_provenance_is_rejected(self):
        self.capture()
        path = self.run/'causal-execution-007.json'
        original = path.read_bytes()
        self.packet(lambda p:p['observation'].pop('provider_envelope'), rehash=False)
        self.rejected()
        path.write_bytes(original)
        self.packet(lambda p:p['observation']['provider_envelope'].update(execution_source='remote-llm'))
        self.rejected()

    def test_rehashed_packet_cannot_keep_false_stable_backend_pass(self):
        self.capture()
        def change(packet):
            packet['observation']['system_fingerprint'] = None
            packet['observation']['provider_envelope']['system_fingerprint'] = None
        self.packet(change)
        self.rejected()

    def test_all_null_fingerprints_are_explicitly_unattested(self):
        self.capture(opener=OpenerFixture(lambda b:b.pop('system_fingerprint')))
        receipt = verify_individual_remote(self.run)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_COMPLETE')
        self.assertEqual(receipt['integration_gate'], 'PASS')
        self.assertEqual(receipt['causal_gate'], 'INCONCLUSIVE')
        self.assertEqual(receipt['backend_comparability']['status'], 'ABSENT')
        self.assertEqual(receipt['backend_comparability']['missing_fingerprint_decisions'], 39)
        self.assertFalse(receipt['external_service_attested'])

    def test_rehashed_first_fingerprint_cannot_keep_false_absent_backend_report(self):
        self.capture(opener=OpenerFixture(lambda b:b.pop('system_fingerprint')))
        def change(packet):
            packet['observation']['system_fingerprint'] = 'appeared'
            packet['observation']['provider_envelope']['system_fingerprint'] = 'appeared'
        self.packet(change)
        self.rejected()

    def test_partial_cannot_invent_many_unrecorded_attempts(self):
        self.capture(opener=InterruptedOpener())
        self.edit('individual-report.json', lambda r:r.update(model_attempts=10))
        self.rejected()

    def test_local_loader_or_readiness_record_is_never_admitted(self):
        self.capture()
        self.edit('individual-report.json', lambda r:r.update(model_load_attempts=1))
        self.rejected()
        self.edit('individual-report.json', lambda r:r.update(model_load_attempts=0))
        (self.run/'model-readiness.json').write_text('{}')
        self.rejected()

    def test_local_v1_verifier_does_not_silently_admit_remote_v3(self):
        self.capture()
        with self.assertRaises(SchemaError):
            verify_individual(self.run)

    def test_remote_source_change_cannot_be_hidden_by_new_plan_hash(self):
        self.capture()
        plan = json.loads((self.run/'individual-plan.json').read_text())
        plan['source_sha256']['groq_agent.py'] = '0'*64
        plan['plan_sha256'] = fingerprint({k:v for k,v in plan.items() if k!='plan_sha256'})
        (self.run/'individual-plan.json').write_text(json.dumps(plan))
        self.edit('individual-report.json', lambda r:r.update(plan_sha256=plan['plan_sha256']))
        self.rejected()

    def test_receipt_is_exclusive_and_outside_evidence(self):
        self.capture()
        receipt = verify_individual_remote(self.run)
        destination = self.parent/'receipt.json'
        write_receipt(receipt, destination, self.run)
        self.assertEqual(json.loads(destination.read_text())['verified_model_packets'],39)
        with self.assertRaises(FileExistsError):
            write_receipt(receipt, destination, self.run)

    def test_production_manifest_has_separate_remote_identity_without_attestation(self):
        from affinityqa.groq_agent import model_manifest
        verify_manifest(model_manifest('remote-llm'), 'qloo-tool+groq-remote-llm')
        with self.assertRaises(SchemaError):
            verify_manifest(model_manifest('remote-llm'), 'test-double-only')

    def test_private_loader_never_discovers_or_overrides_from_process_environment(self):
        path = self.parent/'private.env'
        path.write_text('GROQ_API_KEY = '+UNIT_SECRET+'\n', 'utf-8')
        with patch.dict('os.environ', {'GROQ_API_KEY': 'unrelated'}):
            self.assertEqual(load_private_credential(path), UNIT_SECRET)
        path.write_text('GROQ_API_KEY='+UNIT_SECRET+'\nGROQ_API_KEY='+UNIT_SECRET)
        with self.assertRaises(SchemaError):
            load_private_credential(path)

    def test_cli_plan_ignores_absent_credentials_and_never_creates_output(self):
        path = self.parent/'request.json'
        path.write_text(json.dumps(self.request))
        stdout = io.StringIO()
        with patch.object(sys, 'argv', [str(ROOT/'scripts/capture_individual_remote.py'), '--request', str(path),
                '--output', str(self.output), '--env-file', str(self.parent/'absent.env')]), redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(ROOT/'scripts/capture_individual_remote.py'), run_name='__main__')
        self.assertEqual(stopped.exception.code, 0)
        self.assertEqual(json.loads(stdout.getvalue())['mode'], 'individual-remote-capture')
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
