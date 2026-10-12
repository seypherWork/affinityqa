"""Versioned search projection, immutable raw rows and legacy compatibility."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.cinema_discovery_v3_capture import prepare_plan, search_identities, capture_confirmed
from affinityqa.cinema_discovery_v3_verify import verify_discovery_search, verify_confirmed_discoveries, _candidates
from affinityqa.search_music_candidates import music_candidates
from affinityqa.cinema_discovery_capture import prepare_plan as legacy_plan, search_identities as legacy_search
from affinityqa.cinema_discovery_file_verify import verify_discovery_search as legacy_verify
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent
from affinityqa.errors import SchemaError
from affinityqa.individual_verify import inventory
from affinityqa.identity_diagnostics import diagnose_identity_search
from affinityqa.evidence import fingerprint
from affinityqa.qloo import Settings
from test_cinema_identity_capture import identity_request, ID_A, ID_B
from test_discovery_capture import DiscoveryTransport
from test_discovery_agent import Opener, TEST_SECRET
from test_groq_agent import UNIT_QLOO_SECRET


def variant(body, path, params):
    if path == '/search':
        row = copy.deepcopy(body['results'][0])
        row.update(types=['urn:entity:person'], properties={})
        body['results'].append(row)


class DiscoveryV3SearchTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT/'.test-runs'; parent.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=parent); self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name)
        self.request = identity_request(); self.request['schema_version'] = 5
        self.opener = Opener()
        self.transport = DiscoveryTransport(self.request, mutation=variant)
        self.adapters = (lambda: DiscoveryMovieAgent(TEST_SECRET,
            forbidden_secrets=(UNIT_QLOO_SECRET,), _test_opener=self.opener), lambda: self.transport)
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network forbidden'))
            guard.start(); self.addCleanup(guard.stop)
        guard = patch('affinityqa.cinema_discovery_v3_capture.time.sleep')
        guard.start(); self.addCleanup(guard.stop)

    def search(self, mutation=variant):
        self.transport.mutation = mutation
        output = self.parent/'v3'
        plan = prepare_plan(self.request, output, minimum_model_interval_seconds=0.0)
        _, directory = search_identities(self.request, output, plan['plan_sha256'], Settings(UNIT_QLOO_SECRET),
            minimum_model_interval_seconds=0.0, _test_adapters=self.adapters)
        return directory, verify_discovery_search(directory)

    def test_nonmusical_UUID_variant_stops_legacy_but_v3_preserves_rows_and_awaits_choice(self):
        output = self.parent/'v2'
        plan = legacy_plan(self.request, output, minimum_model_interval_seconds=0.0)
        _, legacy = legacy_search(self.request, output, plan['plan_sha256'], Settings(UNIT_QLOO_SECRET),
            minimum_model_interval_seconds=0.0, _test_adapters=self.adapters)
        self.assertEqual(legacy_verify(legacy)['verification_status'], 'VERIFIED_PARTIAL')
        self.transport.calls.clear()
        directory, receipt = self.search()
        self.assertEqual(receipt['status'], 'AWAITING_IDENTITY_CONFIRMATION')
        self.assertEqual([len(receipt['identity_candidates'][k]) for k in ('A', 'B')], [1, 1])
        for filename in ('http-0002.json', 'http-0004.json'):
            rows = json.loads((directory/filename).read_text())['response']['results']
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['entity_id'], rows[1]['entity_id'])
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (2, 0))
        before = inventory(legacy)
        self.assertEqual(legacy_verify(legacy)['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual(inventory(legacy), before)

    def test_same_selectable_profile_collapses_without_rewriting_its_metadata(self):
        row = {'entity_id': ID_A, 'name': 'Music Example', 'types': ['urn:entity:artist']}
        second = {**copy.deepcopy(row), 'properties': {'synthetic_note': 'different provider detail'}}
        body = {'results': [row, second]}; before = copy.deepcopy(body)
        self.assertEqual(music_candidates(body), _candidates(body))
        self.assertEqual(len(music_candidates(body)), 1)
        self.assertEqual(body, before)

    def test_conflicting_musical_profiles_stop_without_retry_or_inference(self):
        def conflicting(body, path, params):
            if path == '/search':
                body['results'].append({**copy.deepcopy(body['results'][0]), 'name': 'Conflicting Artist'})
        _, receipt = self.search(conflicting)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (1, 0))
        self.assertEqual(receipt['error_class'], 'SchemaError')

    def test_invalid_nonmusical_rows_are_not_hidden_by_filtering(self):
        row = {'entity_id': ID_A, 'name': 'Music Example', 'types': ['urn:entity:artist']}
        for bad in ({**row, 'entity_id': 'not-a-uuid', 'types': ['urn:entity:person']},
                    {**row, 'types': ['urn:entity:person'], 'properties': []},
                    {**row, 'types': ['urn:entity:person'], 'query': {'affinity': 2}},
                    {**row, 'types': []}):
            with self.subTest(row=bad), self.assertRaises(SchemaError):
                music_candidates({'results': [row, bad]})
            with self.subTest(verifier=bad), self.assertRaises(SchemaError):
                _candidates({'results': [row, bad]})

    def test_raw_bound_applies_before_filtering_or_collapsing(self):
        row = {'entity_id': ID_A, 'name': 'Music Example', 'types': ['urn:entity:artist']}
        for parser in (music_candidates, _candidates):
            with self.assertRaises(SchemaError): parser({'results': [copy.deepcopy(row) for _ in range(6)]})

    def test_new_candidate_contract_cannot_be_changed_by_refingerprinting_plan(self):
        directory, _ = self.search()
        path = directory/'individual-plan.json'; value = json.loads(path.read_text())
        value['identity_candidate_contract'] = 'unreviewed-permissive-policy'
        value['plan_sha256'] = fingerprint({k:v for k,v in value.items() if k != 'plan_sha256'})
        path.write_text(json.dumps(value))
        with self.assertRaises(SchemaError): verify_discovery_search(directory)

    def test_diagnostic_selects_v3_source_bound_projection_without_changing_capture(self):
        directory, _ = self.search(); before = inventory(directory)
        result = diagnose_identity_search(directory)
        self.assertEqual(result['diagnosis'], 'SEARCH_COMPLETE')
        self.assertEqual([r['code'] for r in result['observations']], ['CANDIDATES_ACCEPTED']*2)
        self.assertEqual(inventory(directory), before)

    def test_complete_capture_still_requires_explicit_choices_and_exact_budgets(self):
        directory, receipt = self.search()
        with self.assertRaises(SchemaError):
            capture_confirmed(directory, {}, receipt, Settings(UNIT_QLOO_SECRET), TEST_SECRET,
                _test_adapters=self.adapters)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (2, 0))
        capture_confirmed(directory, {'A': ID_A, 'B': ID_B}, receipt, Settings(UNIT_QLOO_SECRET), TEST_SECRET,
            _test_adapters=self.adapters)
        result = verify_confirmed_discoveries(directory)
        self.assertEqual(result['verification_status'], 'VERIFIED_COMPLETE')
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (4, 2))
        self.assertEqual((result['cultural_gate'], result['release_gate']), ('NOT_VALIDATED', 'BLOCKED'))
        with self.assertRaises(SchemaError): legacy_verify(directory)

    def test_legacy_pending_case_keeps_original_capture_verifier_after_manager_restart(self):
        from test_discovery_jobs import DiscoveryJobTests
        fixture = DiscoveryJobTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        manager = fixture.manager()
        current_planner = manager._prepare_plan
        manager._prepare_plan = lambda request, output: legacy_plan(request, output, minimum_model_interval_seconds=0.0)
        job = fixture.plan(manager)
        manager._prepare_plan = current_planner
        manager.start(job['job_id'], job['plan_sha256']); manager.worker.join(15)
        self.assertEqual(manager.view(job['job_id'])['status'], 'AWAITING_IDENTITY_CONFIRMATION')
        manager.close()
        restored = fixture.manager(); saved = restored.view(job['job_id'])
        self.assertEqual(saved['case_protocol'], 'cinema-confirmed-discovery-v2')
        fixture.confirm(restored, saved); restored.worker.join(15)
        self.assertEqual(restored.view(job['job_id'])['status'], 'COMPLETE')
        self.assertEqual((len(fixture.transport.calls), len(fixture.opener.calls)), (4, 2))
