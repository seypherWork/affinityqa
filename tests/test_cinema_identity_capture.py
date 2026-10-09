"""Offline staged identity fixtures: explicit selection is never simulated as real consent."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.cinema_identity_capture import validate_request, prepare_plan, search_identities, selection_profiles, capture_confirmed
from affinityqa.cinema_identity_verify import verify_identity_search, verify_confirmed_cinema
from affinityqa.cinema_preferences import CinemaMovieAgent
from affinityqa.errors import SchemaError, TransportError
from affinityqa.evidence import fingerprint
from affinityqa.individual_verify import write_receipt
from affinityqa.qloo import Response, Settings
from test_cinema_capture import request_fixture
from test_groq_agent import OpenerFixture, UNIT_SECRET, UNIT_QLOO_SECRET


ID_A = 'bbbbbbbb-0000-4000-8000-000000000000'
ID_B = 'bbbbbbbb-0000-4000-8000-000000000001'
ID_ALT = 'bbbbbbbb-0000-4000-8000-000000000002'


def identity_request():
    request = request_fixture()
    request.update(schema_version=4, artists={'A': 'Florence & the Machine', 'B': 'The xx'})
    return request


class IdentityTransport:
    def __init__(self, request, *, ambiguous=False, mutation=None, fail_at=None, http_at=None):
        self.request, self.ambiguous, self.mutation = request, ambiguous, mutation
        self.fail_at, self.http_at = fail_at, http_at
        self.calls = []

    def send(self, path, params):
        self.calls.append((path, copy.deepcopy(params)))
        if len(self.calls) == self.fail_at:
            raise TransportError('Synthetic transport stop')
        if len(self.calls) == self.http_at:
            return Response(429, {'error': 'Synthetic quota stop'}, {})
        if path == '/search':
            self_query = params['query']
            if self_query == self.request['artists']['A']:
                rows = [{'entity_id': ID_A, 'name': 'Florence + The Machine', 'types': ['urn:entity:artist']}]
                if self.ambiguous:
                    rows.append({'entity_id': ID_ALT, 'name': 'Florence and the Machine Tribute', 'types': ['urn:entity:artist']})
            else:
                rows = [{'entity_id': ID_B, 'name': 'The xx', 'types': ['urn:entity:artist']}]
            body = {'results': rows}
        elif path == '/v2/insights':
            rows = [{'entity_id': row['entity_id'], 'name': row['name'], 'types': ['urn:entity:movie'],
                'properties': {'release_year': row['release_year']}, 'query': {'affinity': 1-i/20}}
                for i, row in enumerate(self.request['catalog'])]
            if params['signal.interests.entities'] == ID_B:
                rows.reverse()
            body = {'success': True, 'results': {'entities': rows}}
        else:
            raise AssertionError('Unexpected provider path')
        if self.mutation:
            self.mutation(body, path, params)
        return Response(200, body, {})


class InterruptedOpener(OpenerFixture):
    def open(self, request, timeout):
        if len(self.calls) == 1:
            self.calls.append((request, json.loads(request.data), timeout))
            raise HTTPError(request.full_url, 429, 'Synthetic rate limit', {}, io.BytesIO(b'offline'))
        return super().open(request, timeout)


class ConfirmedIdentityTests(unittest.TestCase):
    def setUp(self):
        temp_parent = ROOT/'.test-runs'
        temp_parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_parent)
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.output = self.parent/'capture'
        self.request = identity_request()
        self.engine_calls = 0
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network denied in confirmed identity fixture'))
            guard.start()
            self.addCleanup(guard.stop)

    def no_engine(self):
        self.fail('Search must not initialize a model or require a Groq key')

    def search(self, transport=None):
        self.transport = transport or IdentityTransport(self.request)
        self.plan = prepare_plan(self.request, self.output)
        with patch('affinityqa.cinema_identity_capture.time.sleep'):
            self.report, self.run = search_identities(self.request, self.output, self.plan['plan_sha256'], Settings(UNIT_QLOO_SECRET),
                _test_adapters=(self.no_engine, lambda: self.transport))
        self.receipt = verify_identity_search(self.run)
        return self.receipt

    def confirm(self, selected=None, receipt=None, opener=None):
        self.opener = opener or OpenerFixture()
        def make_engine():
            self.engine_calls += 1
            self.engine = CinemaMovieAgent(UNIT_SECRET, forbidden_secrets=(UNIT_QLOO_SECRET,), _test_opener=self.opener)
            return self.engine
        with patch('affinityqa.cinema_identity_capture.time.sleep'):
            self.final, directory = capture_confirmed(self.run, selected or {'A': ID_A, 'B': ID_B}, receipt or self.receipt,
                Settings(UNIT_QLOO_SECRET), UNIT_SECRET, _test_adapters=(make_engine, lambda: self.transport))
        self.assertEqual(directory, self.run)
        return verify_confirmed_cinema(self.run)

    def edit(self, name, action):
        path = self.run/name
        value = json.loads(path.read_text('utf-8'))
        action(value)
        path.write_text(json.dumps(value), 'utf-8')

    def reject_final(self):
        with self.assertRaises(SchemaError):
            verify_confirmed_cinema(self.run)

    def test_plan_is_pure_separate_and_has_explicit_confirmation_budget(self):
        plan = prepare_plan(self.request, self.output)
        self.assertEqual((plan['schema_version'], plan['maximum_qloo_requests'], plan['maximum_model_decisions']), (5, 4, 2))
        self.assertTrue(plan['explicit_identity_confirmation_required'])
        self.assertEqual(list(self.parent.iterdir()), [])
        self.assertEqual(plan['new_model_metadata_requests'], 0)

    def test_alias_queries_keep_provider_names_and_zero_model_calls_until_choice(self):
        receipt = self.search()
        self.assertEqual(receipt['verification_status'], 'VERIFIED_IDENTITY_SEARCH')
        self.assertEqual(receipt['status'], 'AWAITING_IDENTITY_CONFIRMATION')
        self.assertEqual(receipt['identity_queries']['A'], 'Florence & the Machine')
        self.assertEqual(receipt['identity_candidates']['A'][0]['name'], 'Florence + The Machine')
        self.assertEqual((receipt['qloo_attempts'], receipt['model_attempts']), (2, 0))
        self.assertFalse((self.run/'model-manifest.json').exists())
        self.assertFalse((self.run/'individual-report.json').exists())
        self.assertEqual(len(self.transport.calls), 2)
        self.assertTrue(all(params['types'] == 'urn:entity:artist,urn:entity:person' for _, params in self.transport.calls))
        self.assertEqual(verify_confirmed_cinema(self.run)['verification_status'], 'VERIFIED_IDENTITY_SEARCH')

    def test_full_confirmation_preserves_search_prefix_and_cumulative_four_two(self):
        self.search()
        frozen = (self.run/'identity-ledger.jsonl').read_bytes()
        initial = {name: digest for name, digest in self.receipt['artifact_sha256'].items() if name != 'ledger.jsonl'}
        receipt = self.confirm()
        self.assertEqual(receipt['verification_status'], 'VERIFIED_COMPLETE')
        self.assertEqual((receipt['qloo_attempts'], receipt['model_attempts'], self.engine_calls), (4, 2, 1))
        self.assertEqual((receipt['verified_provider_samples'], receipt['verified_model_packets']), (4, 2))
        self.assertEqual(receipt['chosen_identities']['A']['name'], 'Florence + The Machine')
        self.assertTrue((self.run/'ledger.jsonl').read_bytes().startswith(frozen))
        self.assertEqual(frozen, (self.run/'identity-ledger.jsonl').read_bytes())
        self.assertEqual(initial, {name: hashlib.sha256((self.run/name).read_bytes()).hexdigest() for name in initial})
        self.assertEqual([path for path, _ in self.transport.calls], ['/search', '/search', '/v2/insights', '/v2/insights'])
        self.assertEqual(receipt['preference_gate'], 'PASS')
        self.assertEqual(receipt['causal_gate'], 'NOT_EVALUATED')
        self.assertEqual(receipt['cultural_gate'], 'NOT_VALIDATED')
        self.assertFalse(receipt['external_service_attested'])
        for label in ('A', 'B'):
            result = receipt['cinema_results'][label]
            self.assertEqual(len(result['delivered']), 5)
            self.assertFalse(set(result['delivered']) & set(result['preferences']['excluded_entity_ids']))
        data = json.loads(self.opener.calls[0][1]['messages'][1]['content'])
        self.assertEqual(data['profile']['name'], 'Florence + The Machine')

    def test_ambiguity_requires_exact_explicit_candidate_selection_without_default(self):
        receipt = self.search(IdentityTransport(self.request, ambiguous=True))
        self.assertEqual(len(receipt['identity_candidates']['A']), 2)
        for selected in (None, {}, {'A': ID_A}, {'A': True, 'B': ID_B}, {'A': 'ffffffff-ffff-4fff-8fff-ffffffffffff', 'B': ID_B}):
            with self.assertRaises(SchemaError):
                selection_profiles(receipt, selected)
        final = self.confirm({'A': ID_ALT, 'B': ID_B})
        self.assertEqual(final['chosen_identities']['A']['entity_id'], ID_ALT)
        self.assertEqual(final['chosen_identities']['A']['name'], 'Florence and the Machine Tribute')

    def test_wrong_or_noncanonical_choice_rejected_before_factories_and_evidence(self):
        self.search()
        for selected in ({'A': ID_B, 'B': ID_B}, {'A': ID_A.upper(), 'B': ID_B}, {'A': ID_A, 'B': ID_ALT}):
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()}
            with self.assertRaises(SchemaError):
                self.confirm(selected)
            self.assertEqual(self.engine_calls, 0)
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()})

    def test_same_candidate_for_both_profiles_is_never_admitted(self):
        def same(body, path, params):
            if path == '/search':
                body['results'] = [{'entity_id': ID_A, 'name': 'Florence + The Machine', 'types': ['urn:entity:artist']}]
        self.search(IdentityTransport(self.request, mutation=same))
        with self.assertRaises(SchemaError):
            self.confirm({'A': ID_A, 'B': ID_A})
        self.assertEqual(self.engine_calls, 0)

    def test_only_musical_people_are_offered_not_albums_or_unverified_persons(self):
        def people(body, path, params):
            if path == '/search' and params['query'] == self.request['artists']['A']:
                body['results'] = [{'entity_id': ID_A, 'name': 'Florence Welch', 'types': ['urn:entity:person'], 'properties': {'occupation': 'singer-songwriter'}},
                    {'entity_id': ID_ALT, 'name': 'Album', 'types': ['urn:entity:album']},
                    {'entity_id': 'bbbbbbbb-0000-4000-8000-000000000003', 'name': 'Unknown person', 'types': ['urn:entity:person']}]
        receipt = self.search(IdentityTransport(self.request, mutation=people))
        self.assertEqual(receipt['identity_candidates']['A'], [{'entity_id': ID_A, 'name': 'Florence Welch', 'type': 'urn:entity:person'}])

    def test_musical_external_service_can_verify_person_without_occupation(self):
        def people(body, path, params):
            if path == '/search' and params['query'] == self.request['artists']['A']:
                body['results'][0].update(name='Florence Welch', types=['urn:entity:person'], properties={'external': {'spotify': {'id': 'fixture-person-id'}}})
        receipt = self.search(IdentityTransport(self.request, mutation=people))
        self.assertEqual(receipt['identity_candidates']['A'][0]['type'], 'urn:entity:person')

    def test_album_empty_duplicate_malformed_or_oversized_first_search_stop_immediately(self):
        mutations = [lambda b: b.update(results=[]),
            lambda b: b['results'][0].update(types=['urn:entity:album']),
            lambda b: b['results'].append(copy.deepcopy(b['results'][0])),
            lambda b: b['results'][0].update(entity_id='bad-id'),
            lambda b: b['results'][0].update(name='Bad\x00name'),
            lambda b: b.update(results=[{'entity_id': f'bbbbbbbb-0000-4000-8000-{i:012d}', 'name': str(i), 'types': ['urn:entity:artist']} for i in range(6)])]
        for i, mutation in enumerate(mutations):
            self.output = self.parent/('invalid-' + str(i))
            def alter(body, path, params):
                if path == '/search':
                    mutation(body)
            receipt = self.search(IdentityTransport(self.request, mutation=alter))
            self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
            self.assertEqual((receipt['qloo_attempts'], receipt['model_attempts']), (1, 0))
            self.assertEqual(len(self.transport.calls), 1)
            with self.assertRaises(SchemaError):
                selection_profiles(receipt, {'A': ID_A, 'B': ID_B})

    def test_search_transport_and_http_failures_keep_first_failure_and_all_counters(self):
        for i, kwargs in enumerate(({'fail_at': 1}, {'http_at': 1}, {'fail_at': 2}, {'http_at': 2})):
            self.output = self.parent/('failure-' + str(i))
            receipt = self.search(IdentityTransport(self.request, **kwargs))
            self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
            self.assertEqual(receipt['qloo_attempts'], next(iter(kwargs.values())))
            self.assertEqual(receipt['model_attempts'], 0)

    def test_cross_bound_or_changed_search_receipt_cannot_continue(self):
        self.search()
        original_run, original_receipt, original_transport = self.run, self.receipt, self.transport
        self.output = self.parent/'other-capture'
        other = self.search()
        self.run, self.receipt, self.transport = original_run, original_receipt, original_transport
        with self.assertRaises(SchemaError):
            self.confirm(receipt=other)
        forged = copy.deepcopy(original_receipt)
        forged['identity_candidates']['A'][0]['name'] = 'Invented name'
        with self.assertRaises(SchemaError):
            self.confirm(receipt=forged)
        self.assertEqual(self.engine_calls, 0)

    def test_invalid_receipt_timestamp_rejected_before_confirmation_or_network(self):
        self.search()
        forged = copy.deepcopy(self.receipt)
        forged['verified_utc'] = 'not-a-time'
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()}
        with self.assertRaises(SchemaError):
            self.confirm(receipt=forged)
        self.assertEqual(self.engine_calls, 0)
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()})

    def test_changed_source_or_initial_snapshot_is_rejected_before_model(self):
        self.search()
        self.edit('individual-plan.json', lambda p: p['source_sha256'].update(cinema_identity_capture='0'*64))
        with self.assertRaises(SchemaError):
            self.confirm()
        self.assertEqual(self.engine_calls, 0)

    def test_confirmed_insight_failures_preserve_cumulative_search_budget(self):
        for i, kwargs in enumerate(({'fail_at': 3}, {'http_at': 3}, {'fail_at': 4}, {'http_at': 4})):
            self.output = self.parent/('confirmed-stop-' + str(i))
            self.search(IdentityTransport(self.request, **kwargs))
            receipt = self.confirm()
            self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
            self.assertEqual(receipt['qloo_attempts'], next(iter(kwargs.values())))
            self.assertEqual(receipt['model_attempts'], 0)
            self.assertEqual(receipt['status'], 'INCOMPLETE')

    def test_second_model_failure_preserves_first_delivery_and_single_admission(self):
        self.search()
        receipt = self.confirm(opener=InterruptedOpener())
        self.assertEqual((receipt['verification_status'], receipt['qloo_attempts'], receipt['model_attempts']), ('VERIFIED_PARTIAL', 4, 2))
        self.assertEqual((receipt['successful_profiles'], receipt['failed_model_attempts']), (1, 1))
        with self.assertRaises(SchemaError):
            self.confirm()
        self.assertEqual(self.engine_calls, 1)

    def test_os_failure_recording_search_candidate_is_preserved_without_advancement(self):
        from affinityqa.evidence import Ledger
        original = Ledger.record
        def fail_candidates(ledger, kind, data):
            if kind == 'identity_candidates_recorded':
                raise OSError('Synthetic candidate observation failure')
            return original(ledger, kind, data)
        with patch('affinityqa.cinema_identity_capture.Ledger.record', fail_candidates):
            receipt = self.search()
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual(receipt['qloo_attempts'], 1)
        self.assertEqual(receipt['identity_candidates'], {})

    def test_os_failure_before_second_model_keeps_a_confirmed_partial_prefix(self):
        from affinityqa.evidence import Ledger
        original = Ledger.write
        def fail_result(ledger, name, data):
            if name == 'cinema-result-A.json':
                raise OSError('Synthetic result observation failure')
            return original(ledger, name, data)
        self.search()
        with patch('affinityqa.cinema_identity_capture.Ledger.write', fail_result):
            receipt = self.confirm()
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual((receipt['qloo_attempts'], receipt['model_attempts'], receipt['successful_profiles']), (4, 1, 0))
        self.assertEqual(receipt['error_class'], 'OSError')

    def test_interrupt_during_inference_preserves_failed_attempt_without_resume(self):
        class Interrupted(OpenerFixture):
            def open(opener, request, timeout):
                opener.calls.append((request, json.loads(request.data), timeout))
                raise KeyboardInterrupt()
        self.search()
        with self.assertRaises(KeyboardInterrupt):
            self.confirm(opener=Interrupted())
        receipt = verify_confirmed_cinema(self.run)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual((receipt['qloo_attempts'], receipt['model_attempts'], receipt['verified_model_packets']), (4, 1, 0))
        self.assertEqual(receipt['error_class'], 'KeyboardInterrupt')

    def test_forged_model_admission_before_explicit_confirmation_is_rejected(self):
        self.search()
        events = [json.loads(line) for line in (self.run/'ledger.jsonl').read_text().splitlines()]
        events.append({'sequence': len(events)+1, 'timestamp_utc': events[-1]['timestamp_utc'], 'source': 'test-double-only',
            'kind': 'remote_model_attempt_admitted', 'data': {}})
        raw = ''.join(json.dumps(e) + '\n' for e in events)
        (self.run/'ledger.jsonl').write_text(raw, 'utf-8')
        (self.run/'identity-ledger.jsonl').write_text(raw, 'utf-8')
        with self.assertRaises(SchemaError):
            verify_identity_search(self.run)

    def test_forged_candidate_event_cannot_advance_empty_http200_identity_search(self):
        def empty(body, path, params):
            if path == '/search':
                body['results'] = []
        self.search(IdentityTransport(self.request, mutation=empty))
        events = [json.loads(line) for line in (self.run/'identity-ledger.jsonl').read_text().splitlines()]
        events.pop()  # Replace the real stop with a forged advancement.
        name = 'http-0002.json'
        events.append({'sequence': 3, 'timestamp_utc': events[-1]['timestamp_utc'], 'source': 'test-double-only',
            'kind': 'identity_candidates_recorded', 'data': {'label': 'A', 'query': self.request['artists']['A'],
                'sample_sha256': hashlib.sha256((self.run/name).read_bytes()).hexdigest(), 'candidates_sha256': fingerprint([])}})
        sample = json.loads((self.run/name).read_text())
        sample['request']['params']['query'] = self.request['artists']['B']
        body = {'results': [{'entity_id': ID_B, 'name': 'The xx', 'types': ['urn:entity:artist']}]}
        sample.update(response=body, response_sha256=fingerprint(body))
        (self.run/'http-0004.json').write_text(json.dumps(sample), 'utf-8')
        events.append({'sequence': 4, 'timestamp_utc': events[-1]['timestamp_utc'], 'source': 'test-double-only',
            'kind': 'tool_call', 'data': {'sample': 'http-0004.json', **{k: v for k, v in sample.items() if k != 'response'}}})
        events.append({'sequence': 5, 'timestamp_utc': events[-1]['timestamp_utc'], 'source': 'test-double-only',
            'kind': 'stopped_without_retry', 'data': {'error_class': 'OSError'}})
        raw = ''.join(json.dumps(e) + '\n' for e in events)
        (self.run/'ledger.jsonl').write_text(raw, 'utf-8')
        (self.run/'identity-ledger.jsonl').write_text(raw, 'utf-8')
        self.edit('identity-report.json', lambda r: r.update(qloo_attempts=2, error_class='OSError'))
        with self.assertRaises(SchemaError):
            verify_identity_search(self.run)

    def test_forged_second_insight_after_invalid_first_selected_context_is_rejected(self):
        def invalid(body, path, params):
            if path == '/v2/insights' and params['signal.interests.entities'] == ID_A:
                body['results']['entities'][0]['name'] = 'Wrong canonical movie'
        self.search(IdentityTransport(self.request, mutation=invalid))
        receipt = self.confirm()
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual(receipt['qloo_attempts'], 3)
        raw_prefix = (self.run/'identity-ledger.jsonl').read_bytes()
        events = [json.loads(line) for line in (self.run/'ledger.jsonl').read_text().splitlines()]
        sample = json.loads((self.run/'http-0008.json').read_text())
        sample['request']['params']['signal.interests.entities'] = ID_B
        (self.run/'http-0009.json').write_text(json.dumps(sample), 'utf-8')
        events.insert(-1, {'sequence': 9, 'timestamp_utc': events[-1]['timestamp_utc'], 'source': 'test-double-only',
            'kind': 'tool_call', 'data': {'sample': 'http-0009.json', **{k: v for k, v in sample.items() if k != 'response'}}})
        suffix = events[6:]
        for i, event in enumerate(suffix, 7):
            event['sequence'] = i
        with (self.run/'ledger.jsonl').open('wb') as out:
            out.write(raw_prefix)
            out.write(''.join(json.dumps(e) + '\n' for e in suffix).encode())
        self.edit('individual-report.json', lambda r: r.update(qloo_attempts=4))
        self.reject_final()

    def test_confirmation_receipt_and_selected_identity_cannot_be_rehashed_into_other_choice(self):
        self.search()
        self.confirm()
        self.edit('confirmation.json', lambda c: c['selected_profiles']['A'].update(name='Invented'))
        self.reject_final()

    def test_initial_ledger_snapshot_must_equal_final_ledger_prefix(self):
        self.search()
        self.confirm()
        events = [json.loads(line) for line in (self.run/'ledger.jsonl').read_text().splitlines()]
        events[1]['data']['request']['params']['query'] = 'Swapped query'
        (self.run/'ledger.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events), 'utf-8')
        self.reject_final()

    def test_phase_two_never_accepts_untyped_search_or_missing_first_result_before_b(self):
        self.search()
        self.confirm(opener=InterruptedOpener())
        (self.run/'cinema-result-A.json').unlink()
        self.edit('individual-report.json', lambda r: r.update(cinema_results={}, successful_profiles=0))
        self.reject_final()

    def test_identity_receipt_can_be_saved_exclusively_outside_capture(self):
        receipt = self.search()
        path = self.parent/'identity-verification.json'
        write_receipt(receipt, path, self.run)
        self.assertEqual(json.loads(path.read_text())['verification_status'], 'VERIFIED_IDENTITY_SEARCH')

    def test_no_private_keys_are_in_artifacts_and_private_input_stops_before_search(self):
        self.search()
        self.confirm()
        for path in self.run.iterdir():
            self.assertNotIn(UNIT_SECRET, path.read_text('utf-8'))
            self.assertNotIn(UNIT_QLOO_SECRET, path.read_text('utf-8'))
        request = identity_request()
        request['artists']['A'] = UNIT_QLOO_SECRET
        output = self.parent/'secret-input'
        plan = prepare_plan(request, output)
        with self.assertRaises(SchemaError):
            search_identities(request, output, plan['plan_sha256'], Settings(UNIT_QLOO_SECRET), _test_adapters=(self.no_engine, lambda: self.fail('no transport')))
        self.assertFalse(output.exists())

    def test_previous_versions_hidden_labels_and_changed_plan_never_create_output(self):
        for invalid in ({**self.request, 'schema_version': 3}, {**self.request, 'ratings': [5]*20}):
            with self.assertRaises(SchemaError):
                validate_request(invalid)
        with self.assertRaises(SchemaError):
            search_identities(self.request, self.output, '0'*64, Settings(UNIT_QLOO_SECRET), _test_adapters=(self.no_engine, lambda: self.fail('no transport')))
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
