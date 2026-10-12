"""Redacted offline diagnosis of original identity-search failures."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.errors import SchemaError
from affinityqa.identity_diagnostics import classify_candidates, diagnose_identity_search
from affinityqa.individual_verify import inventory
from affinityqa.qloo import Settings
from affinityqa.cinema_identity_capture import prepare_plan, search_identities
from test_cinema_identity_capture import identity_request, IdentityTransport
from test_groq_agent import UNIT_QLOO_SECRET
from test_discovery_capture import DiscoveryTransport


class IdentityDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT/'.test-runs'; parent.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temp.cleanup); self.parent = Path(temp.name)
        self.request = identity_request()
        for name in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(name, side_effect=AssertionError('Network forbidden'))
            guard.start(); self.addCleanup(guard.stop)

    def capture(self, mutation=None, fail_at=None):
        output = self.parent/'capture'
        plan = prepare_plan(self.request, output)
        transport = IdentityTransport(self.request, mutation=mutation, fail_at=fail_at)
        with patch('affinityqa.cinema_identity_capture.time.sleep'):
            _, directory = search_identities(self.request, output, plan['plan_sha256'], Settings(UNIT_QLOO_SECRET),
                _test_adapters=(lambda: self.fail('No model allowed'), lambda: transport))
        return directory

    def test_second_empty_response_diagnosed_without_query_identity_or_gate_changes(self):
        def empty(body, path, params):
            if params['query'] == self.request['artists']['B']: body['results'] = []
        directory = self.capture(mutation=empty); before = inventory(directory)
        report = diagnose_identity_search(directory)
        self.assertEqual(report['diagnosis'], 'RECORDED_RESPONSE_REJECTION_REPRODUCED')
        self.assertEqual([r['code'] for r in report['observations']], ['CANDIDATES_ACCEPTED', 'NO_VERIFIED_MUSIC_CANDIDATES'])
        self.assertEqual([r['candidate_event_committed'] for r in report['observations']], [True, False])
        self.assertEqual(report['original_gates']['release_gate'], 'BLOCKED')
        self.assertEqual(inventory(directory), before)
        text = json.dumps(report)
        for hidden in (UNIT_QLOO_SECRET, self.request['artists']['A'], self.request['artists']['B'], str(directory), 'bbbbbbbb-0000'):
            self.assertNotIn(hidden, text)

    def test_successful_search_remains_unapproved_and_never_selects_artist(self):
        report = diagnose_identity_search(self.capture())
        self.assertEqual(report['diagnosis'], 'SEARCH_COMPLETE')
        self.assertEqual(report['original_gates'], {'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED', 'preference_gate': 'NOT_EVALUATED'})
        self.assertEqual((report['new_provider_calls'], report['new_model_calls']), (0, 0))

    def test_transport_stop_has_no_fabricated_response_reason(self):
        report = diagnose_identity_search(self.capture(fail_at=2))
        self.assertEqual(report['observations'][1]['code'], 'TRANSPORT_FAILURE')
        self.assertIsNone(report['observations'][1]['returned_rows'])

    def test_discovery_v2_search_uses_its_own_full_source_bound_verifier(self):
        from affinityqa.cinema_discovery_capture import prepare_plan as prepare_discovery, search_identities as search_discovery
        request = copy.deepcopy(self.request); request['schema_version'] = 5
        output = self.parent/'discovery'
        plan = prepare_discovery(request, output, minimum_model_interval_seconds=0.0)
        def empty_second(body, path, params):
            if params['query'] == request['artists']['B']: body['results'] = []
        transport = DiscoveryTransport(request, mutation=empty_second)
        with patch('affinityqa.cinema_discovery_capture.time.sleep'):
            _, directory = search_discovery(request, output, plan['plan_sha256'], Settings(UNIT_QLOO_SECRET),
                minimum_model_interval_seconds=0.0,
                _test_adapters=(lambda: self.fail('No model allowed'), lambda: transport))
        report = diagnose_identity_search(directory)
        self.assertEqual(report['protocol'], 'cinema-confirmed-discovery-v2')
        self.assertEqual(report['observations'][1]['code'], 'NO_VERIFIED_MUSIC_CANDIDATES')
        self.assertEqual(report['verification_status'], 'VERIFIED_PARTIAL')

    def test_candidate_record_failure_is_not_mislabelled_as_response_schema_rejection(self):
        from affinityqa.evidence import Ledger
        original = Ledger.record
        def fail_second_candidate(ledger, kind, data):
            if kind == 'identity_candidates_recorded' and data['label'] == 'B':
                raise OSError('UNIT_PRIVATE_STORAGE_REASON')
            return original(ledger, kind, data)
        with patch('affinityqa.cinema_identity_capture.Ledger.record', fail_second_candidate):
            directory = self.capture()
        report = diagnose_identity_search(directory)
        self.assertEqual(report['diagnosis'], 'STOP_CAUSE_NOT_REPRODUCED')
        self.assertEqual([r['code'] for r in report['observations']], ['CANDIDATES_ACCEPTED'] * 2)
        self.assertFalse(report['observations'][1]['candidate_event_committed'])
        self.assertNotIn('UNIT_PRIVATE_STORAGE_REASON', json.dumps(report))

    def test_tampered_artifact_is_rejected_before_diagnosis(self):
        directory = self.capture()
        path = directory/'http-0002.json'; value = json.loads(path.read_text())
        value['response']['results'] = []; path.write_text(json.dumps(value))
        with self.assertRaises(SchemaError): diagnose_identity_search(directory)

    def test_candidate_codes_distinguish_bounds_duplicates_and_private_looking_names(self):
        row = {'entity_id': 'bbbbbbbb-0000-4000-8000-000000000001', 'name': 'PRIVATE_LOOKING_VALUE', 'types': ['urn:entity:artist']}
        for value, code in (
            ({'results': [row, copy.deepcopy(row)]}, 'DUPLICATE_ENTITY_IDS'),
            ({'results': [{**row, 'entity_id': 'SECRET_NOT_AN_ID'}]}, 'ENTITY_ID_NOT_UUID'),
            ({'results': [{**row, 'name': 'PRIVATE_LOOKING_VALUE\x00'}]}, 'CANDIDATE_NAME_CANONICALITY_REJECTED'),
            ({'results': [{**row, 'entity_id': f'bbbbbbbb-0000-4000-8000-{i:012d}'} for i in range(6)]}, 'SEARCH_RESULT_BOUND_EXCEEDED'),
        ):
            with self.subTest(code=code):
                result = classify_candidates(value)
                self.assertEqual(result['code'], code)
                self.assertNotIn('PRIVATE_LOOKING_VALUE', json.dumps(result))
                self.assertNotIn('SECRET_NOT_AN_ID', json.dumps(result))

    def test_unknown_schema_error_never_echoes_exception_text(self):
        with patch('affinityqa.identity_diagnostics.music_candidates', side_effect=SchemaError('UNIT_PRIVATE_SECRET')):
            result = classify_candidates({'results': []})
        self.assertEqual(result['code'], 'CANDIDATE_CONTRACT_REJECTED')
        self.assertNotIn('UNIT_PRIVATE_SECRET', json.dumps(result))

    def test_cli_rejection_is_redacted_instead_of_traceback_with_path(self):
        spec = importlib.util.spec_from_file_location('diagnose_search_cli', ROOT/'scripts/diagnose_identity_search.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        output = io.StringIO()
        with patch('sys.argv', ['diagnose', str(self.parent/'MISSING_PRIVATE_PATH')]), redirect_stdout(output):
            self.assertEqual(module.main(), 1)
        body = json.loads(output.getvalue())
        self.assertEqual(body['diagnosis'], 'EVIDENCE_REJECTED')
        self.assertNotIn('MISSING_PRIVATE_PATH', output.getvalue())
