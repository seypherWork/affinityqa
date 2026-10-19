"""Actual local code over fabricated artifacts; no empirical provider proof."""
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'src')]

from fastapi.testclient import TestClient
from affinityqa import causal_review, public_demo
from affinityqa.evidence import fingerprint
from affinityqa.errors import SchemaError
import causal_evidence_fixture as fixture_module

SOURCE = Path(causal_review.__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'synthetic_public_replay_verifier', SOURCE / 'scripts/verify_public_demo.py')
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class CausalEvidenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='aq-causal-synthetic-')
        self.addCleanup(self.temporary.cleanup)
        self.fixture = fixture_module.build_synthetic_capture(
            Path(self.temporary.name) / 'capture', source_root=SOURCE)

    def replay(self, fault='stale-profile', repeat=1):
        return causal_review.replay_causal(
            self.fixture.root, fixture_module.PAIR_ID, fault, repeat)

    def assert_rehashed_semantics_rejected_before_patch(self):
        self.fixture.reseal_for_negative_test()
        # Byte integrity/report replay remains valid: exercise the NEW guard.
        causal_review._verified(self.fixture.root, self.fixture.receipt_path)
        with patch.object(causal_review.CausalMovieSession, 'apply',
                          side_effect=AssertionError('Patch must not run')) as applied:
            with self.assertRaises(SchemaError):
                self.replay()
            applied.assert_not_called()

    def app(self):
        return public_demo.create_public_app(
            self.fixture.root, origin='https://review.example',
            run_id=fixture_module.RUN_ID,
            receipt_sha256=self.fixture.receipt_sha256,
            case_manager=None,
        )

    def test_complete_fixture_has_real_byte_hashes_sources_and_39_fake_packets(self):
        run, report, receipt = causal_review._verified(
            self.fixture.root, self.fixture.receipt_path)
        self.assertEqual(run, self.fixture.run)
        self.assertEqual(len(self.fixture.packet_paths), 39)
        self.assertEqual(set(receipt['source_sha256']), set(fixture_module.SOURCES))
        for name, digest in receipt['source_sha256'].items():
            self.assertEqual(fixture_module.sha(SOURCE / 'src/affinityqa' / name), digest)
        bundle = json.loads((run / 'causal-tool-inputs.json').read_bytes())[fixture_module.PAIR_ID]
        raw = causal_review._recorded_tool_samples(run, receipt, bundle['contexts'])
        self.assertEqual(len(raw), 2)
        for name in ('http-0001.json', 'http-0002.json'):
            self.assertIn(fixture_module.sha(run / name), raw)
        self.assertEqual(report['fixture_provenance'], fixture_module.SYNTHETIC)
        self.assertEqual(report['actual_external_model_calls'], 0)
        self.assertEqual(report['actual_external_Qloo_calls'], 0)
        self.assertEqual(fixture_module.sha(self.fixture.root / 'scripts/run_causal_repair.py'),
                         fixture_module.sha(SOURCE / 'scripts/run_causal_repair.py'))

    def test_three_faults_times_three_repeats_execute_and_preserve_artifacts(self):
        before = self.fixture.inventory()
        receipt_before = self.fixture.receipt_sha256
        for fault, dispatches in (('cache-omits-profile', 3), ('stale-profile', 4),
                                  ('wrong-tool-profile', 4)):
            for repeat in (1, 2, 3):
                with self.subTest(fault=fault, repeat=repeat):
                    result = self.replay(fault, repeat)
                    self.assertEqual(result['status'], 'PASS')
                    self.assertEqual(result['recorded_decision_dispatches'], dispatches)
                    self.assertEqual(result['new_model_calls'], 0)
                    self.assertEqual(result['new_qloo_calls'], 0)
                    self.assertEqual(len(result['checks']), 6)
                    self.assertTrue(all(value is True for value in result['checks'].values()))
                    proof = result['diagnostic_evidence']
                    self.assertEqual(proof['status'], 'VERIFIED')
                    self.assertEqual(len(proof['checks']), 8)
                    self.assertTrue(all(value is True for value in proof['checks'].values()))
        self.assertEqual(self.fixture.inventory(), before)
        self.assertEqual(self.fixture.receipt_sha256, receipt_before)

    def test_actual_public_api_projects_v2_and_passes_independent_verifier(self):
        before = self.fixture.inventory()
        with patch('socket.create_connection', side_effect=AssertionError('No network')):
            with TestClient(self.app(), base_url='https://review.example',
                            raise_server_exceptions=False) as client:
                summary = client.get('/api/demo/summary')
                self.assertEqual(summary.status_code, 200)
                self.assertEqual(summary.json()['replay_schema_version'], 2)
                for fault in VERIFIER.OPERATIONS:
                    for repeat in (1, 2, 3):
                        with self.subTest(fault=fault, repeat=repeat):
                            response = client.post('/api/demo/replay',
                                headers={'Origin': 'https://review.example'},
                                json={'pair_id': fixture_module.PAIR_ID,
                                      'fault': fault, 'repeat': repeat})
                            self.assertEqual(response.status_code, 200, response.text)
                            value = response.json()
                            self.assertEqual(value['schema_version'], 2)
                            VERIFIER.validate_replay(value,
                                run_id=fixture_module.RUN_ID, pair_id=fixture_module.PAIR_ID,
                                fault=fault, repeat=repeat, artists=self.fixture.artists)
                self.assertEqual(client.get('/healthz').json()['live_inference'], False)
                self.assertEqual(client.get('/api/causal-repair/export').status_code, 404)
        self.assertEqual(self.fixture.inventory(), before)

    def test_packet_payload_rehash_does_not_bypass_semantic_gate(self):
        relative = self.fixture.packet_paths[-1].relative_to(self.fixture.run).as_posix()
        def corrupt(packet):
            packet['model_payload']['provider_movie_context'][0]['affinity'] = .123
            packet['observation']['input_sha256'] = fingerprint(packet['model_payload'])
        self.fixture.rewrite_run_json(relative, corrupt)
        self.assert_rehashed_semantics_rejected_before_patch()

    def test_context_rehash_does_not_bypass_independent_raw_reconstruction(self):
        def corrupt(bundle):
            context = next(iter(bundle[fixture_module.PAIR_ID]['contexts'].values()))
            context['ranked_entities'][0]['affinity'] = .123
            context['context_sha256'] = fingerprint({
                key: value for key, value in context.items() if key != 'context_sha256'})
        self.fixture.rewrite_run_json('causal-tool-inputs.json', corrupt)
        self.assert_rehashed_semantics_rejected_before_patch()

    def test_duplicate_captured_execution_is_rejected_before_patch(self):
        packet = self.fixture.packet_paths[-1]
        relative = packet.relative_to(self.fixture.run).as_posix()
        first = json.loads(self.fixture.packet_paths[0].read_bytes())
        self.fixture.rewrite_run_json(relative, lambda value:
            value.update(execution_id=first['execution_id']))
        self.assert_rehashed_semantics_rejected_before_patch()

    def test_ambiguous_raw_sample_hash_is_rejected_before_patch(self):
        duplicate = self.fixture.run / 'http-0003.json'
        with duplicate.open('xb') as output:
            output.write((self.fixture.run / 'http-0001.json').read_bytes())
        self.assert_rehashed_semantics_rejected_before_patch()

    def test_unsealed_packet_change_fails_original_byte_integrity(self):
        relative = self.fixture.packet_paths[0].relative_to(self.fixture.run).as_posix()
        self.fixture.rewrite_run_json(relative, lambda packet:
            packet['observation'].update(input_sha256='0' * 64))
        with self.assertRaises(SchemaError):
            causal_review._verified(self.fixture.root, self.fixture.receipt_path)

    def test_api_semantic_failure_is_generic_without_private_packet_leak(self):
        relative = self.fixture.packet_paths[-1].relative_to(self.fixture.run).as_posix()
        def corrupt(packet):
            packet['model_payload']['catalog'][0]['name'] = 'PRIVATE_PACKET_CANARY'
            packet['observation']['input_sha256'] = fingerprint(packet['model_payload'])
        self.fixture.rewrite_run_json(relative, corrupt)
        self.fixture.reseal_for_negative_test()
        with TestClient(self.app(), base_url='https://review.example',
                        raise_server_exceptions=False) as client:
            response = client.post('/api/demo/replay',
                headers={'Origin': 'https://review.example'},
                json={'pair_id': fixture_module.PAIR_ID, 'fault': 'stale-profile', 'repeat': 1})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('PRIVATE_PACKET_CANARY', response.text)
            self.assertNotIn(str(self.fixture.root), response.text)
            self.assertNotIn('diagnostic_evidence', response.json())

    def test_v2_projection_and_verifier_reject_extra_or_truthy_proof_fields(self):
        base = self.replay()
        for mode in ('extra', 'missing', 'truthy', 'false', 'wrong-operation'):
            with self.subTest(mode=mode):
                result = copy.deepcopy(base)
                proof = result['diagnostic_evidence']
                if mode == 'extra': proof['private_packet'] = 'PRIVATE_PROOF_CANARY'
                elif mode == 'missing': proof['checks'].pop('model_payload_bound')
                elif mode == 'truthy': proof['checks']['model_payload_bound'] = 1
                elif mode == 'false': proof['checks']['model_payload_bound'] = False
                else: proof['operation'] = 'none'
                with self.assertRaises(SchemaError):
                    public_demo.replay_dto(result, profile_names=self.fixture.profile_names)
        dto = public_demo.replay_dto(base, profile_names=self.fixture.profile_names)
        dto['diagnostic_evidence']['checks']['raw_qloo_request_bound'] = 1
        with self.assertRaises(RuntimeError):
            VERIFIER.validate_replay(dto, run_id=fixture_module.RUN_ID,
                pair_id=fixture_module.PAIR_ID, fault='stale-profile', repeat=1,
                artists=self.fixture.artists)

    def test_public_projection_removes_unrelated_private_fields(self):
        result = self.replay()
        result['private_packet'] = 'PRIVATE_ROOT_CANARY'
        result['trace']['private_path'] = 'PRIVATE_TRACE_CANARY'
        result['before'][0]['raw_provider'] = 'PRIVATE_FILM_CANARY'
        dto = public_demo.replay_dto(result, profile_names=self.fixture.profile_names)
        rendered = json.dumps(dto)
        for canary in ('PRIVATE_ROOT_CANARY', 'PRIVATE_TRACE_CANARY', 'PRIVATE_FILM_CANARY'):
            self.assertNotIn(canary, rendered)
        VERIFIER.validate_replay(dto, run_id=fixture_module.RUN_ID,
            pair_id=fixture_module.PAIR_ID, fault='stale-profile', repeat=1,
            artists=self.fixture.artists)

    def test_legacy_v1_projection_remains_verifiable_without_new_proof_claim(self):
        result = self.replay()
        del result['diagnostic_evidence']
        dto = public_demo.replay_dto(result, profile_names=self.fixture.profile_names)
        self.assertEqual(dto['schema_version'], 1)
        self.assertNotIn('diagnostic_evidence', dto)
        VERIFIER.validate_replay(dto, run_id=fixture_module.RUN_ID,
            pair_id=fixture_module.PAIR_ID, fault='stale-profile', repeat=1,
            artists=self.fixture.artists)

    def test_fixture_creation_refuses_existing_root_without_overwrite(self):
        before = self.fixture.inventory()
        with self.assertRaises(FileExistsError):
            fixture_module.build_synthetic_capture(self.fixture.root, source_root=SOURCE)
        self.assertEqual(self.fixture.inventory(), before)


    def test_verifier_enforces_advertised_version_without_breaking_legacy(self):
        result = self.replay()
        dto = public_demo.replay_dto(result, profile_names=self.fixture.profile_names)
        expected = dict(run_id=fixture_module.RUN_ID, pair_id=fixture_module.PAIR_ID,
                        fault='stale-profile', repeat=1, artists=self.fixture.artists)
        VERIFIER.validate_replay(dto, required_version=2, **expected)
        legacy = copy.deepcopy(dto)
        legacy['schema_version'] = 1
        del legacy['diagnostic_evidence']
        VERIFIER.validate_replay(legacy, **expected)
        VERIFIER.validate_replay(legacy, required_version=1, **expected)
        for value, advertised in ((legacy, 2), (dto, 1), (dto, True), (dto, 3)):
            with self.subTest(advertised=advertised), self.assertRaises(RuntimeError):
                VERIFIER.validate_replay(value, required_version=advertised, **expected)


if __name__ == '__main__':
    unittest.main()
