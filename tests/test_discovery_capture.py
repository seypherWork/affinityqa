"""Staged discovery integration with synthetic transport; all network denied."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.cinema_discovery_capture import prepare_plan, search_identities, capture_confirmed
from affinityqa.cinema_discovery_file_verify import verify_discovery_search, verify_confirmed_discoveries
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent
from affinityqa.cinema_identity_verify import verify_confirmed_cinema
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
from affinityqa.qloo import Settings, Response
from test_cinema_identity_capture import identity_request, IdentityTransport, ID_A, ID_B
from test_discovery_agent import Opener, TEST_SECRET
from test_groq_agent import UNIT_QLOO_SECRET


class DiscoveryTransport(IdentityTransport):
    def send(self, path, params):
        response = super().send(path, params)
        if path == '/v2/insights' and response.status == 200:
            allowed = set(params['filter.results.entities'].split(','))
            rows = [r for r in response.body['results']['entities'] if r['entity_id'] in allowed]
            if ID_B in params['signal.interests.entities'].split(','):
                rows.reverse()
            response.body['results']['entities'] = rows
        return response


class InterruptedDiscoveryOpener(Opener):
    def __init__(self, at):
        super().__init__()
        self.at = at

    def open(self, request, timeout):
        if len(self.calls) + 1 == self.at:
            self.failure = HTTPError(request.full_url, 429, 'synthetic private-looking failure text', {}, None)
        return super().open(request, timeout)


class DiscoveryCaptureTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT/'.test-runs'
        parent.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name)
        self.output = self.parent/'capture'
        self.request = identity_request()
        self.request['schema_version'] = 5
        self.request['preferences']['A']['favorite_entity_ids'] = [self.request['catalog'][0]['entity_id']]
        self.request['preferences']['B']['favorite_entity_ids'] = [r['entity_id'] for r in self.request['catalog'][:5]]
        for label in ('A', 'B'):
            self.request['preferences'][label]['excluded_entity_ids'] = [self.request['catalog'][19]['entity_id']]
        self.engine_calls = 0
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network denied in staged discovery integration'))
            guard.start()
            self.addCleanup(guard.stop)

    def search(self, transport=None):
        self.transport = transport or DiscoveryTransport(self.request)
        self.plan = prepare_plan(self.request, self.output, minimum_model_interval_seconds=0.0)
        with patch('affinityqa.cinema_discovery_capture.time.sleep'):
            self.initial, self.run = search_identities(self.request, self.output, self.plan['plan_sha256'],
                Settings(UNIT_QLOO_SECRET), minimum_model_interval_seconds=0.0,
                _test_adapters=(lambda: self.fail('No model during search'), lambda: self.transport))
        self.receipt = verify_discovery_search(self.run)
        return self.receipt

    def confirm(self, *, selected=None, receipt=None, opener=None):
        self.opener = opener or Opener()
        def factory():
            self.engine_calls += 1
            self.engine = DiscoveryMovieAgent(TEST_SECRET, forbidden_secrets=(UNIT_QLOO_SECRET,), _test_opener=self.opener)
            return self.engine
        with patch('affinityqa.cinema_discovery_capture.time.sleep'):
            self.final, directory = capture_confirmed(self.run, selected or {'A': ID_A, 'B': ID_B}, receipt or self.receipt,
                Settings(UNIT_QLOO_SECRET), TEST_SECRET, _test_adapters=(factory, lambda: self.transport))
        self.assertEqual(directory, self.run)
        return verify_confirmed_discoveries(self.run)

    def edit(self, name, action):
        path = self.run/name
        value = json.loads(path.read_text(encoding='utf-8'))
        action(value)
        path.write_text(json.dumps(value), encoding='utf-8')

    def test_failed_second_profile_records_only_its_HTTP_and_prepared_receipt(self):
        import io
        self.search()
        class SecondFailure(Opener):
            def open(self, request, timeout):
                if len(self.calls) == 1:
                    raw = json.dumps({'error':{'type':'invalid_request_error',
                        'code':'json_validate_failed','message':TEST_SECRET}}).encode()
                    self.failure = HTTPError(request.full_url,400,TEST_SECRET,{},io.BytesIO(raw))
                return super().open(request,timeout)
        verified = self.confirm(opener=SecondFailure())
        self.assertEqual(verified['verification_status'],'VERIFIED_PARTIAL')
        failure = self.final['terminal_failure']
        self.assertEqual(failure.get('http_failure'),{'schema_version':1,'http_status':400,
            'provider_error_type':'invalid_request_error','provider_error_code':'json_validate_failed'})
        rows = [json.loads(line) for line in (self.run/'ledger.jsonl').read_bytes().splitlines()]
        prepared = [row['data'] for row in rows if row['kind']=='discovery_request_prepared']
        self.assertEqual(len(prepared),2)
        self.assertEqual(failure['prepared_receipt_sha256'],fingerprint(prepared[1]))
        self.assertNotEqual(failure['prepared_receipt_sha256'],fingerprint(prepared[0]))
        self.assertEqual((self.final['model_attempts'],self.final['successful_profiles']), (2,1))

    def test_tampered_wire_receipt_rejected_and_cache_adds_no_receipt(self):
        self.search(); self.confirm()
        path = self.run/'ledger.jsonl'
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        prepared = [row for row in rows if row['kind']=='discovery_request_prepared']
        self.assertEqual(len(prepared),2)
        prepared[0]['data']['wire_sha256']='f'*64
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
        with self.assertRaises(SchemaError): verify_confirmed_discoveries(self.run)

    def test_HTTP_failure_cannot_claim_zero_consumed_model_attempts(self):
        self.search()
        error = HTTPError('https://example.invalid', 400, 'synthetic rejection', {}, None)
        self.confirm(opener=Opener(failure=error))
        self.edit('individual-report.json', lambda report: report.update(
            model_attempts=0, failed_model_attempts=0, unattempted_profiles=2,
            terminal_failure={**report['terminal_failure'], 'model_attempts': 0}))
        path = self.run/'ledger.jsonl'
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        for row in rows:
            if row['kind'] == 'discovery_session_stopped':
                row['data']['model_attempts'] = 0
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding='utf8')
        with self.assertRaises(SchemaError): verify_confirmed_discoveries(self.run)

    def test_pure_plan_is_versioned_and_rejects_fewer_than_five_unknown_eligible(self):
        plan = prepare_plan(self.request, self.output)
        self.assertEqual((plan['request']['schema_version'], plan['schema_version']), (5, 6))
        self.assertEqual((plan['maximum_qloo_requests'], plan['maximum_model_decisions']), (4, 2))
        self.assertEqual(plan['protocol_version'], 'cinema-confirmed-discovery-v2')
        self.assertEqual(list(self.parent.iterdir()), [])
        damaged = copy.deepcopy(self.request)
        damaged['preferences']['B']['excluded_entity_ids'] = [r['entity_id'] for r in damaged['catalog'][5:]]
        with self.assertRaises(SchemaError):
            prepare_plan(damaged, self.output)

    def test_search_preserves_provider_alias_and_requires_explicit_membership(self):
        receipt = self.search(DiscoveryTransport(self.request, ambiguous=True))
        self.assertEqual(receipt['status'], 'AWAITING_IDENTITY_CONFIRMATION')
        self.assertEqual(receipt['identity_candidates']['A'][0]['name'], 'Florence + The Machine')
        self.assertEqual((receipt['qloo_attempts'], receipt['model_attempts'], self.engine_calls), (2, 0, 0))
        self.assertFalse((self.run/'model-manifest.json').exists())
        with self.assertRaises(SchemaError):
            self.confirm(selected={'A': self.request['catalog'][0]['entity_id'], 'B': ID_B})
        self.assertEqual(len(self.transport.calls), 2)
        self.assertEqual(self.engine_calls, 0)

    def test_complete_capture_binds_mixed_signals_nonseed_packets_and_nonce_cache(self):
        self.search()
        initial = {n: hashlib.sha256((self.run/n).read_bytes()).hexdigest()
                   for n in self.receipt['artifact_sha256'] if n != 'ledger.jsonl'}
        receipt = self.confirm()
        self.assertEqual(receipt['verification_status'], 'VERIFIED_COMPLETE')
        self.assertEqual((receipt['qloo_attempts'], receipt['model_attempts'], receipt['admitted_model_slots']), (4, 2, 2))
        self.assertEqual((receipt['verified_provider_samples'], receipt['verified_model_packets']), (4, 2))
        self.assertEqual(initial, {n: hashlib.sha256((self.run/n).read_bytes()).hexdigest() for n in initial})
        for label, count, profile_id in (('A', 19, ID_A), ('B', 15, ID_B)):
            result = receipt['cinema_results'][label]
            self.assertEqual(len(result['raw_ranking']), count)
            self.assertEqual(len(result['delivered']), 5)
            forbidden = set(result['preferences']['favorite_entity_ids'] + result['preferences']['excluded_entity_ids'])
            self.assertFalse(set(result['delivered']) & forbidden)
            file = json.loads((self.run/f'cinema-result-{label}.json').read_text(encoding='utf-8'))
            self.assertTrue(file['cached_boundary']['trace']['cache_hit'])
            self.assertNotEqual(file['cached_boundary']['trace']['requested_request_sha256'],
                                file['cached_boundary']['trace']['execution_request_sha256'])
            self.assertEqual(file['uncached_boundary']['ranking'], file['cached_boundary']['ranking'])
            params = self.transport.calls[2 if label == 'A' else 3][1]
            self.assertEqual(set(params['signal.interests.entities'].split(',')),
                             {profile_id, *result['preferences']['favorite_entity_ids']})
            self.assertFalse(set(params['filter.results.entities'].split(',')) & set(result['preferences']['favorite_entity_ids']))
        self.assertEqual(receipt['causal_gate'], 'NOT_EVALUATED')
        self.assertEqual(receipt['cultural_gate'], 'NOT_VALIDATED')
        self.assertEqual(receipt['release_gate'], 'BLOCKED')
        self.assertFalse(receipt['external_service_attested'])
        with self.assertRaises(SchemaError):
            verify_confirmed_cinema(self.run)

    def test_complete_or_interrupted_capture_cannot_retry_confirmation(self):
        for failure_at in (None, 1):
            with self.subTest(failure_at=failure_at):
                self.output = self.parent/f'capture-{failure_at}'
                self.search()
                self.confirm(opener=InterruptedDiscoveryOpener(failure_at) if failure_at else Opener())
                calls = len(self.transport.calls), len(self.opener.calls)
                factories = self.engine_calls
                with self.assertRaises(SchemaError):
                    self.confirm()
                self.assertEqual(len(self.transport.calls), calls[0])
                self.assertEqual(self.engine_calls, factories)

    def test_429_preserves_consumed_attempt_and_partial_denominator(self):
        for failure_at in (1, 2):
            with self.subTest(failure_at=failure_at):
                self.output = self.parent/f'quota-{failure_at}'
                self.search()
                receipt = self.confirm(opener=InterruptedDiscoveryOpener(failure_at))
                self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
                self.assertEqual(receipt['model_attempts'], failure_at)
                self.assertEqual(receipt['admitted_model_slots'], failure_at)
                self.assertEqual(receipt['successful_profiles'], failure_at-1)
                self.assertEqual(receipt['failed_model_attempts'], 1)
                self.assertEqual(receipt['unattempted_profiles'], 2-failure_at)
                self.assertEqual(receipt['terminal_failure']['terminal_recording_state'], 'RECORDED')
                self.assertNotIn('private-looking', json.dumps(receipt))

    def test_tool_429_stops_before_model_and_remains_partial(self):
        self.search(DiscoveryTransport(self.request, http_at=4))
        receipt = self.confirm()
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual((receipt['qloo_attempts'], receipt['model_attempts']), (4, 0))
        self.assertEqual(self.opener.calls, [])
        self.assertFalse((self.run/'individual-tool-inputs.json').exists())

    def test_changed_receipt_and_plan_are_rejected_before_new_provider_calls(self):
        self.search()
        wrong = copy.deepcopy(self.receipt)
        wrong['qloo_attempts'] = 1
        with self.assertRaises(SchemaError):
            self.confirm(receipt=wrong)
        self.assertEqual(len(self.transport.calls), 2)
        self.assertEqual(self.engine_calls, 0)
        self.edit('individual-plan.json', lambda p: p.update(maximum_model_decisions=3))
        with self.assertRaises(SchemaError):
            self.confirm()
        self.assertEqual(len(self.transport.calls), 2)

    def test_file_audit_rejects_modified_context_packet_delivery_or_quality_claim(self):
        changes = [
            ('individual-tool-inputs.json', lambda p: next(iter(p.values())).update(signal_sha256='0'*64)),
            ('discovery-execution-001.json', lambda p: p['model_payload'].update(signal_sha256='0'*64)),
            ('cinema-result-A.json', lambda p: p['result']['delivered'].__setitem__(0, self.request['catalog'][0]['entity_id'])),
            ('individual-report.json', lambda p: p.update(cultural_gate='PASS')),
            ('individual-report.json', lambda p: p.update(model_attempts=True)),
            ('individual-report.json', lambda p: p.update(human_participants=12)),
        ]
        for i, (name, change) in enumerate(changes):
            with self.subTest(name=name):
                self.output = self.parent/f'mutated-{i}'
                self.search()
                self.confirm()
                self.edit(name, change)
                with self.assertRaises(SchemaError):
                    verify_confirmed_discoveries(self.run)

    def test_extra_file_is_rejected(self):
        self.search()
        self.confirm()
        extra = self.run/'unexpected.json'
        extra.write_text('{}', encoding='utf-8')
        with self.assertRaises(SchemaError):
            verify_confirmed_discoveries(self.run)

    def test_same_response_with_changed_sample_bytes_cannot_reuse_context_hash(self):
        self.search()
        self.confirm()
        context = next(iter(json.loads((self.run/'individual-tool-inputs.json').read_text(encoding='utf-8')).values()))
        sample = next(p for p in self.run.glob('http-*.json')
                      if hashlib.sha256(p.read_bytes()).hexdigest() == context['sample_sha256'])
        original = sample.read_bytes()
        sample.write_bytes(original + b'\n')
        self.assertEqual(json.loads(original), json.loads(sample.read_bytes()))
        with self.assertRaises(SchemaError):
            verify_confirmed_discoveries(self.run)

    def test_partial_second_tool_failure_cannot_follow_an_invalid_first_sample(self):
        for i, damage in enumerate(('missing', 'album', 'year', 'affinity')):
            with self.subTest(damage=damage):
                self.output = self.parent/f'prior-invalid-{i}'
                self.search(DiscoveryTransport(self.request, http_at=4))
                self.assertEqual(self.confirm()['verification_status'], 'VERIFIED_PARTIAL')
                ledger = self.run/'ledger.jsonl'
                events = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
                event = next(e for e in events if e['kind'] == 'tool_call' and e['data']['request']['path'] == '/v2/insights')
                path = self.run/event['data']['sample']
                sample = json.loads(path.read_text(encoding='utf-8'))
                rows = sample['response']['results']['entities']
                if damage == 'missing':
                    rows.pop()
                elif damage == 'album':
                    rows[0]['types'] = ['urn:entity:album']
                elif damage == 'year':
                    rows[0]['properties']['release_year'] = 1900
                else:
                    rows[0]['query']['affinity'] = 1.1
                sample['response_sha256'] = fingerprint(sample['response'])
                event['data']['response_sha256'] = sample['response_sha256']
                path.write_text(json.dumps(sample), encoding='utf-8')
                ledger.write_text(''.join(json.dumps(e) + '\n' for e in events), encoding='utf-8')
                with self.assertRaises(SchemaError):
                    verify_confirmed_discoveries(self.run)


if __name__ == '__main__':
    unittest.main()
