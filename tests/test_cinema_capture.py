"""Offline complete and interrupted cinema execution; no external or human proof."""
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
from affinityqa.cinema_capture import validate_request, prepare_plan, execute_capture
from affinityqa.cinema_preferences import CinemaMovieAgent
from affinityqa.cinema_verify import verify_cinema
from affinityqa.evidence import fingerprint
from affinityqa.errors import SchemaError
from affinityqa.groq_agent import MODEL
from affinityqa.individual_remote_verify import verify_individual_remote
from affinityqa.individual_verify import write_receipt
from affinityqa.qloo import Response, Settings
from test_groq_agent import OpenerFixture, UNIT_SECRET, UNIT_QLOO_SECRET
from test_individual_capture import fixture, TransportDouble


def request_fixture():
    value = fixture()
    ids = [r['entity_id'] for r in value['catalog']]
    value.update(schema_version=3, model={'provider': 'groq', 'name': MODEL},
        preferences={'A': {'schema_version': 1, 'favorite_entity_ids': [ids[10]], 'excluded_entity_ids': [ids[0]]},
                     'B': {'schema_version': 1, 'favorite_entity_ids': [], 'excluded_entity_ids': ids[15:]}})
    return value


class InterruptedOpener(OpenerFixture):
    def open(self, request, timeout):
        if len(self.calls) == 1:
            self.calls.append((request, json.loads(request.data), timeout))
            raise HTTPError(request.full_url, 429, 'Synthetic rate limit', {}, io.BytesIO(UNIT_SECRET.encode()))
        return super().open(request, timeout)


class HTTPFailureTransport(TransportDouble):
    def __init__(self, request, fail_at=1):
        super().__init__(request)
        self.fail_at = fail_at

    def send(self, path, params):
        response = super().send(path, params)
        return Response(429, {'error': 'Synthetic quota stop'}, {}) if len(self.calls) == self.fail_at else response


class CinemaCaptureTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT/'.test-runs'
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.output = self.parent/'cinema-capture'
        self.request = request_fixture()
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network denied in cinema capture fixture'))
            guard.start()
            self.addCleanup(guard.stop)

    def capture(self, opener=None, transport=None, pacing=None, clock=None):
        self.opener = opener or OpenerFixture()
        self.engine = CinemaMovieAgent(UNIT_SECRET, forbidden_secrets=(UNIT_QLOO_SECRET,), _test_opener=self.opener)
        self.transport = transport or TransportDouble(self.request)
        plan = prepare_plan(self.request, self.output, minimum_model_interval_seconds=pacing)
        with patch('affinityqa.cinema_capture.time.sleep'):
            self.report, self.run = execute_capture(self.request, self.output, plan['plan_sha256'],
                Settings(UNIT_QLOO_SECRET), UNIT_SECRET, minimum_model_interval_seconds=pacing,
                _test_adapters=(lambda: self.engine, lambda: self.transport), _test_pacing_clock=clock)
        return self.report

    def edit(self, name, action):
        path = self.run/name
        value = json.loads(path.read_text('utf-8'))
        action(value)
        path.write_text(json.dumps(value), 'utf-8')

    def reject(self):
        with self.assertRaises(SchemaError):
            verify_cinema(self.run)

    def rewrite_events(self, events):
        for i, event in enumerate(events, 1):
            event['sequence'] = i
        (self.run/'ledger.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events), 'utf-8')

    def events(self):
        return [json.loads(line) for line in (self.run/'ledger.jsonl').read_text('utf-8').splitlines()]

    def append_attempt_before_stop(self, previous_name, params, response):
        events = self.events()
        sequence = len(events)
        name = f'http-{sequence:04d}.json'
        sample = json.loads((self.run/previous_name).read_text('utf-8'))
        sample['request']['params'] = params
        sample.update(status=200, response=response, response_sha256=fingerprint(response))
        (self.run/name).write_text(json.dumps(sample), 'utf-8')
        events.insert(-1, {'sequence': sequence, 'timestamp_utc': events[-1]['timestamp_utc'], 'source': events[-1]['source'],
            'kind': 'tool_call', 'data': {'sample': name, **{k: v for k, v in sample.items() if k != 'response'}}})
        self.rewrite_events(events)
        self.edit('individual-report.json', lambda r: r.update(qloo_attempts=r['qloo_attempts'] + 1))

    def test_plan_is_pure_separate_version_and_bounded(self):
        plan = prepare_plan(self.request, self.output)
        self.assertEqual(plan['schema_version'], 4)
        self.assertEqual(plan['maximum_model_decisions'], 2)
        self.assertEqual(plan['maximum_qloo_requests'], 4)
        self.assertEqual(plan['faults'], [])
        self.assertEqual(plan['model_load_requests'], 0)
        self.assertEqual(list(self.parent.iterdir()), [])
        other = copy.deepcopy(self.request)
        other['preferences']['A']['favorite_entity_ids'] = []
        self.assertNotEqual(plan['plan_sha256'], prepare_plan(other, self.output)['plan_sha256'])

    def test_invalid_or_changed_plan_never_starts_factories_or_creates_output(self):
        def forbidden():
            self.fail('No factory may be started')
        with self.assertRaises(SchemaError):
            execute_capture(self.request, self.output, '0'*64, Settings(UNIT_QLOO_SECRET), UNIT_SECRET,
                _test_adapters=(forbidden, forbidden))
        invalid = copy.deepcopy(self.request)
        invalid['preferences']['A']['excluded_entity_ids'] = [r['entity_id'] for r in invalid['catalog'][:16]]
        with self.assertRaises(SchemaError):
            execute_capture(invalid, self.output, '0'*64, Settings(UNIT_QLOO_SECRET), UNIT_SECRET,
                _test_adapters=(forbidden, forbidden))
        self.assertFalse(self.output.exists())

    def test_closed_capture_request_rejects_hidden_labels_and_old_versions(self):
        for changed in ({**self.request, 'schema_version': 2}, {**self.request, 'ratings': [5]*20}):
            with self.assertRaises(SchemaError):
                validate_request(changed)

    def test_complete_proof_recomputes_raw_delivery_baseline_intent_and_cache(self):
        self.capture()
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()}
        receipt = verify_cinema(self.run)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_COMPLETE')
        self.assertEqual((receipt['verified_model_packets'], receipt['verified_provider_samples'], receipt['model_attempts']), (2, 4, 2))
        self.assertEqual(receipt['provenance'], 'SIMULATION_ONLY')
        self.assertEqual(receipt['preference_gate'], 'PASS')
        self.assertEqual(receipt['causal_gate'], 'NOT_EVALUATED')
        self.assertEqual(receipt['cultural_gate'], 'NOT_VALIDATED')
        self.assertFalse(receipt['external_service_attested'])
        for label in ('A', 'B'):
            result = receipt['cinema_results'][label]
            self.assertEqual(len(result['raw_ranking']), 20)
            self.assertEqual(len(result['delivered']), 5)
            self.assertFalse(set(result['delivered']) & set(result['preferences']['excluded_entity_ids']))
            self.assertNotEqual(result['raw_ranking_sha256'], result['delivery_sha256'])
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()})
        for path in self.run.iterdir():
            text = path.read_text('utf-8')
            self.assertNotIn(UNIT_SECRET, text)
            self.assertNotIn(UNIT_QLOO_SECRET, text)
        with self.assertRaises(SchemaError):
            verify_individual_remote(self.run)

    def test_qloo_failure_retains_all_requests_without_model_or_retry(self):
        self.capture(transport=TransportDouble(self.request, fail=True))
        receipt = verify_cinema(self.run)
        self.assertEqual((receipt['verification_status'], receipt['qloo_attempts'], receipt['model_attempts']), ('VERIFIED_PARTIAL', 1, 0))
        self.assertEqual(receipt['requested_profiles'], 2)
        self.assertEqual(receipt['successful_profiles'], 0)
        self.assertEqual(receipt['unattempted_profiles'], 2)

    def test_non200_is_terminal_at_each_qloo_boundary(self):
        for failed in range(1, 5):
            self.output = self.parent/('http-failure-' + str(failed))
            self.capture(transport=HTTPFailureTransport(self.request, fail_at=failed))
            receipt = verify_cinema(self.run)
            self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
            self.assertEqual(receipt['qloo_attempts'], failed)
            self.assertEqual(receipt['model_attempts'], 0)

    def test_forged_second_search_after_first_http429_is_rejected(self):
        self.capture(transport=HTTPFailureTransport(self.request))
        self.assertEqual(verify_cinema(self.run)['verification_status'], 'VERIFIED_PARTIAL')
        events = self.events()
        sample = json.loads((self.run/'http-0002.json').read_text('utf-8'))
        sample['request']['params'] = {'query': self.request['artists']['B'], 'take': 5}
        sample.update(status=200, response={'results': []}, response_sha256=fingerprint({'results': []}))
        (self.run/'http-0003.json').write_text(json.dumps(sample), 'utf-8')
        appended = {'sequence': 3, 'timestamp_utc': events[-1]['timestamp_utc'], 'source': events[-1]['source'],
            'kind': 'tool_call', 'data': {'sample': 'http-0003.json', **{k: v for k, v in sample.items() if k != 'response'}}}
        events.insert(-1, appended)
        self.rewrite_events(events)
        self.edit('individual-report.json', lambda r: r.update(qloo_attempts=2))
        self.reject()

    def test_forged_second_search_after_unresolvable_http200_is_rejected(self):
        class MissingArtist(TransportDouble):
            def send(transport, path, params):
                if path == '/search':
                    transport.calls.append((path, params))
                    return Response(200, {'results': []}, {})
                return super().send(path, params)
        self.capture(transport=MissingArtist(self.request))
        self.assertEqual(verify_cinema(self.run)['verification_status'], 'VERIFIED_PARTIAL')
        self.append_attempt_before_stop('http-0002.json', {'query': self.request['artists']['B'], 'take': 5}, {'results': []})
        self.reject()

    def test_forged_second_insight_after_invalid_first_context_is_rejected(self):
        self.capture(transport=TransportDouble(self.request, mismatch=True))
        self.assertEqual(verify_cinema(self.run)['verification_status'], 'VERIFIED_PARTIAL')
        previous = json.loads((self.run/'http-0004.json').read_text('utf-8'))
        profiles = json.loads((self.run/'individual-identities.json').read_text('utf-8'))
        params = {**previous['request']['params'], 'signal.interests.entities': profiles['B']['entity_id']}
        self.append_attempt_before_stop('http-0004.json', params, previous['response'])
        self.reject()

    def test_second_model_admission_after_missing_first_result_is_rejected(self):
        self.capture(opener=InterruptedOpener())
        (self.run/'cinema-result-A.json').unlink()
        self.edit('individual-report.json', lambda r: r.update(cinema_results={}, successful_profiles=0))
        self.reject()

    def test_second_model_after_incomplete_first_cache_boundary_is_rejected(self):
        self.capture(opener=InterruptedOpener())
        (self.run/'cinema-result-A.json').unlink()
        self.edit('individual-report.json', lambda r: r.update(cinema_results={}, successful_profiles=0))
        events = self.events()
        events = [e for e in events if not (e['kind'] == 'observed_cinema_boundary' and e['data']['cache_hit'] is True)]
        self.rewrite_events(events)
        self.reject()

    def test_second_slot_cannot_precede_first_cache_boundary_even_with_both_results(self):
        self.capture()
        events = self.events()
        boundary = next(e for e in events if e['kind'] == 'observed_cinema_boundary' and e['data']['call'] == 1 and e['data']['cache_hit'] is True)
        events.remove(boundary)
        position = next(i for i, e in enumerate(events) if e['kind'] == 'remote_model_attempt_admitted' and e['data']['slot'] == 2)
        events.insert(position + 1, boundary)
        timestamp = events[0]['timestamp_utc']
        for e in events:
            e['timestamp_utc'] = timestamp
        self.rewrite_events(events)
        self.reject()

    def test_legitimate_os_failure_after_first_cache_keeps_a_partial_prefix(self):
        from affinityqa.evidence import Ledger
        original = Ledger.write
        def fail_result(ledger, name, value):
            if name == 'cinema-result-A.json':
                raise OSError('Synthetic private recording failure')
            return original(ledger, name, value)
        with patch('affinityqa.cinema_capture.Ledger.write', fail_result):
            self.capture()
        receipt = verify_cinema(self.run)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual((receipt['model_attempts'], receipt['successful_profiles']), (1, 0))
        self.assertEqual(receipt['error_class'], 'OSError')

    def test_legitimate_os_failure_before_identity_file_keeps_two_searches(self):
        from affinityqa.evidence import Ledger
        original = Ledger.write
        def fail_identity(ledger, name, value):
            if name == 'individual-identities.json':
                raise OSError('Synthetic identity recording failure')
            return original(ledger, name, value)
        with patch('affinityqa.cinema_capture.Ledger.write', fail_identity):
            self.capture()
        receipt = verify_cinema(self.run)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual((receipt['qloo_attempts'], receipt['model_attempts']), (2, 0))

    def test_legitimate_os_failure_before_first_boundary_retains_raw_packet(self):
        from affinityqa.evidence import Ledger
        original = Ledger.record
        def fail_boundary(ledger, kind, value):
            if kind == 'observed_cinema_boundary':
                raise OSError('Synthetic boundary recording failure')
            return original(ledger, kind, value)
        with patch('affinityqa.cinema_capture.Ledger.record', fail_boundary):
            self.capture()
        receipt = verify_cinema(self.run)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual((receipt['verified_model_packets'], receipt['successful_profiles']), (1, 0))

    def test_second_rate_limit_preserves_first_output_and_failure_in_denominator(self):
        self.capture(opener=InterruptedOpener())
        receipt = verify_cinema(self.run)
        self.assertEqual((receipt['verification_status'], receipt['model_attempts'], receipt['verified_model_packets']), ('VERIFIED_PARTIAL', 2, 1))
        self.assertEqual(receipt['requested_profiles'], 2)
        self.assertEqual(receipt['successful_profiles'], 1)
        self.assertEqual(receipt['failed_model_attempts'], 1)
        self.assertEqual(receipt['preference_gate'], 'NOT_EVALUATED')
        self.assertEqual(len(self.opener.calls), 2)

    def test_first_truncated_response_never_fills_a_delivery(self):
        self.capture(opener=OpenerFixture(lambda b: b['choices'][0].update(finish_reason='length')))
        receipt = verify_cinema(self.run)
        self.assertEqual((receipt['model_attempts'], receipt['verified_model_packets'], receipt['successful_profiles']), (1, 0, 0))
        self.assertEqual(receipt['unattempted_profiles'], 1)

    def test_two_intent_observations_do_not_claim_causal_comparability(self):
        def change(body):
            body['system_fingerprint'] = 'unit-a' if len(self.opener.calls) == 1 else None
        self.capture(opener=OpenerFixture(change))
        receipt = verify_cinema(self.run)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_COMPLETE')
        self.assertEqual(receipt['causal_gate'], 'NOT_EVALUATED')

    def test_rehashed_delivery_cannot_hide_excluded_or_changed_raw_movie(self):
        self.capture()
        self.edit('cinema-result-A.json', lambda v: v['result'].update(delivered=v['uncached_boundary']['ranking'][:5],
            delivery_sha256=fingerprint(v['uncached_boundary']['ranking'][:5])))
        self.reject()

    def test_rehashed_packet_cannot_swap_preferences_or_the_effective_prompt(self):
        self.capture()
        self.edit('cinema-execution-001.json', lambda p: p['model_payload'].update(preferences_sha256='0'*64))
        self.reject()

    def test_invented_counters_gate_or_missing_cache_are_rejected(self):
        self.capture()
        path = self.run/'individual-report.json'
        original = path.read_bytes()
        for change in (lambda r: r.update(causal_gate='PASS'), lambda r: r.update(cultural_gate='PASS'),
                       lambda r: r.update(successful_profiles=True), lambda r: r.update(failed_model_attempts=1),
                       lambda r: r.update(unattempted_profiles=1), lambda r: r.update(model_attempts=3)):
            self.edit(path.name, change)
            self.reject()
            path.write_bytes(original)
        self.edit('cinema-result-A.json', lambda v: v['cached_boundary']['trace'].update(cache_hit=False))
        self.reject()

    def test_source_mutation_cannot_be_hidden_by_new_plan_and_report_hash(self):
        self.capture()
        plan = json.loads((self.run/'individual-plan.json').read_text())
        plan['source_sha256']['cinema_preferences.py'] = '0'*64
        plan['plan_sha256'] = fingerprint({k: v for k, v in plan.items() if k != 'plan_sha256'})
        (self.run/'individual-plan.json').write_text(json.dumps(plan), 'utf-8')
        self.edit('individual-report.json', lambda r: r.update(plan_sha256=plan['plan_sha256']))
        self.reject()

    def test_secret_inputs_rejected_before_any_record_or_send(self):
        for secret in (UNIT_SECRET, UNIT_QLOO_SECRET):
            request = copy.deepcopy(self.request)
            request['artists']['A'] = secret
            plan = prepare_plan(request, self.output)
            with self.assertRaises(SchemaError):
                execute_capture(request, self.output, plan['plan_sha256'], Settings(UNIT_QLOO_SECRET), UNIT_SECRET,
                    minimum_model_interval_seconds=0)
        self.assertFalse(self.output.exists())

    def test_receipt_is_exclusive_outside_capture_and_verifiable(self):
        self.capture()
        receipt = verify_cinema(self.run)
        destination = self.parent/'receipt.json'
        write_receipt(receipt, destination, self.run)
        self.assertEqual(json.loads(destination.read_text())['successful_profiles'], 2)
        with self.assertRaises(FileExistsError):
            write_receipt(receipt, destination, self.run)

    def test_pacing_uses_two_sealed_slots_and_honors_actual_wait(self):
        clock = [0.0]
        def now():
            return clock[0]
        def sleep(seconds):
            clock[0] += seconds
        self.capture(pacing=22, clock=(now, sleep))
        receipt = verify_cinema(self.run)
        self.assertEqual(receipt['admitted_model_slots'], 2)
        self.assertEqual(clock[0], 22.0)


if __name__ == '__main__':
    unittest.main()
