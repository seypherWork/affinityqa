"""Prepared-request and HTTP failure evidence; synthetic, all network denied."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent
from affinityqa.evidence import fingerprint
from test_discovery_agent import Opener, TEST_SECRET, fixture_request
import test_discovery_session as session_fixture


class MemoryLedger:
    run_id = 'synthetic-dispatch-proof'

    def __init__(self, fail=False):
        self.events, self.fail = [], fail

    def record(self, kind, data):
        if self.fail:
            raise OSError('Synthetic evidence disk unavailable')
        self.events.append({'kind':kind, 'data':data})


class FailureEvidenceTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Real network denied'))
            guard.start(); self.addCleanup(guard.stop)

    def engine(self, *, body=None, code=400, ledger=None):
        error = None if body is None else HTTPError('https://example.invalid/'+TEST_SECRET,
            code, TEST_SECRET, {}, io.BytesIO(body))
        opener = Opener(failure=error)
        engine = DiscoveryMovieAgent(TEST_SECRET, _test_opener=opener)
        ledger = MemoryLedger() if ledger is None else ledger
        # On the old implementation this test reaches the real missing evidence.
        if hasattr(engine, 'bind_dispatch_ledger'):
            engine.bind_dispatch_ledger(ledger)
        return engine, opener, ledger

    def test_exact_HTTP_and_allowlisted_reason_survive_without_private_text(self):
        raw = json.dumps({'error':{'type':'invalid_request_error','code':'json_validate_failed',
            'message':TEST_SECRET,'failed_generation':TEST_SECRET,'reasoning':TEST_SECRET}}).encode()
        engine, opener, ledger = self.engine(body=raw)
        with self.assertRaises(Exception) as caught:
            engine.rank(fixture_request())
        diagnostic = getattr(caught.exception,'http_diagnostic',None)
        self.assertEqual(diagnostic, {'schema_version':1,'http_status':400,
            'provider_error_type':'invalid_request_error','provider_error_code':'json_validate_failed'})
        self.assertNotIn(TEST_SECRET, json.dumps(diagnostic))
        self.assertNotIn(TEST_SECRET, str(caught.exception))
        self.assertEqual((engine.calls,len(opener.calls),len(engine.observations)),(1,1,0))
        self.assertEqual(len(ledger.events),1)

    def test_prepared_receipt_binds_exact_wire_without_headers_or_content(self):
        engine, opener, ledger = self.engine()
        request = fixture_request()
        engine.rank(request)
        self.assertEqual(len(ledger.events),1)
        receipt = ledger.events[0]
        self.assertEqual(receipt['kind'],'discovery_request_prepared')
        data = receipt['data']
        self.assertEqual(data['wire_sha256'],hashlib.sha256(opener.calls[0][0].data).hexdigest())
        self.assertEqual(data['provider_request_sha256'],fingerprint(opener.calls[0][1]))
        self.assertEqual(data['request_bytes'],len(opener.calls[0][0].data))
        self.assertEqual((data['run_id'],data['slot'],data['request_id']),
                         (ledger.run_id,1,request['request_id']))
        self.assertIs(data['external_dispatch_attested'],False)
        self.assertNotIn(TEST_SECRET,json.dumps(data))
        self.assertNotIn('messages',data)

    def test_evidence_writer_failure_prevents_HTTP_and_attempt_increment(self):
        engine, opener, ledger = self.engine(ledger=MemoryLedger(fail=True))
        with self.assertRaises(OSError):
            engine.rank(fixture_request())
        self.assertEqual((engine.calls,len(opener.calls),len(engine.observations)),(0,0,0))

    def test_malformed_unknown_and_oversized_bodies_keep_only_exact_HTTP(self):
        cases = [b'not-json', b'{"error":{"type":"invalid_request_error","type":"server_error"}}',
                 json.dumps({'error':{'type':TEST_SECRET,'code':TEST_SECRET}}).encode(),
                 b'{"error":{"code":"json_validate_failed"},"pad":"'+b'x'*9000+b'"}']
        for raw in cases:
            with self.subTest(length=len(raw)):
                engine, _, _ = self.engine(body=raw,code=422)
                with self.assertRaises(Exception) as caught:
                    engine.rank(fixture_request())
                self.assertEqual(getattr(caught.exception,'http_diagnostic',None),
                    {'schema_version':1,'http_status':422,'provider_error_type':None,'provider_error_code':None})

    def test_failed_second_admission_cannot_reuse_the_first_request_receipt(self):
        first, second = fixture_request(1), fixture_request(5)
        opener = Opener()
        session, engine, ledger = session_fixture.DiscoverySessionTests().session([first, second], opener=opener, paced=True)
        session.rank(first)
        record = ledger.record

        def failing_admission(kind, data):
            if kind == 'remote_model_attempt_admitted':
                raise OSError('Synthetic second admission write failure')
            return record(kind, data)

        ledger.record = failing_admission
        with self.assertRaises(OSError):
            session.rank(second)
        self.assertEqual((engine.calls, len(opener.calls)), (1, 1))
        self.assertIsNone(session.last_failure['prepared_receipt_sha256'])
        self.assertIsNone(session.last_failure['http_failure'])


if __name__ == '__main__': unittest.main()
