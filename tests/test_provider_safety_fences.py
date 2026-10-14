"""A disproved token bound stops future sends across instances and restarts."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.evidence import fingerprint
from affinityqa.provider_scheduler import ProviderScheduler, QuotaWindow, ProviderAdmissionPaused
from affinityqa.provider_runtime import ProviderRuntime, PinnedHarmonyTokenEstimator
from affinityqa.groq_agent import GroqToolContextMovieAgent
import test_causal_agent as causal_fixtures
from test_groq_agent import OpenerFixture, ResponseFixture, UNIT_SECRET
from affinityqa.qloo import QlooClient, Response
from affinityqa.evidence import Ledger
from affinityqa.provider_scheduler import ProviderRecordedFailure, ProviderUncertain
import test_provider_runtime as runtime_fixtures


class ProviderSafetyFenceTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT.parent/'test-private-scratch'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'scheduler.sqlite3'
        self.now = 100000
        self.limits = {'groq': (QuotaWindow('tokens', 8000, 60, 'tokens'),
            QuotaWindow('input', 7000, 60, 'input_tokens'), QuotaWindow('output', 4096, 60, 'output_tokens')),
            'qloo': (QuotaWindow('rpm', 10, 60),)}
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('No real network in safety fixture'))
            guard.start(); self.addCleanup(guard.stop)

    def scheduler(self): return ProviderScheduler(self.path, limits=self.limits, clock=lambda:self.now)

    def identity(self, number, provider='groq'):
        return {'owner_id':'unit-owner','job_id':'job-'+str(number),'stage':'capture',
                'provider':provider,'request_sha256':fingerprint(number)}

    def test_observed_input_overage_is_charged_and_fences_new_reserved_sends_after_restart(self):
        scheduler = self.scheduler()
        first = scheduler.reserve(**self.identity(1), tokens=2000, input_tokens=1000, output_tokens=1000)
        reserved = scheduler.reserve(**self.identity(2), tokens=2000, input_tokens=1000, output_tokens=1000)
        scheduler.mark_sent(first['id'])
        result = scheduler.finish(first['id'], result={'accepted':True}, status=200,
            tokens=2500, input_tokens=2200, output_tokens=300)
        self.assertTrue(result['reservation_exceeded'])
        row = scheduler.lookup(**self.identity(1))
        self.assertEqual(row['state'], 'ACCEPTED')
        self.assertEqual(row['input_tokens'], 2200)
        self.assertEqual(row['output_tokens'], 1000)
        self.assertEqual(row['tokens'], 3200)
        self.now += 86401
        restored = self.scheduler()
        self.assertEqual(restored.paused_providers(), scheduler.paused_providers())
        with self.assertRaises(ProviderAdmissionPaused): restored.reserve(**self.identity(3), tokens=100)
        with self.assertRaises(ProviderAdmissionPaused): restored.mark_sent(reserved['id'])
        # A different provider is independent; this internal check makes no HTTP call.
        qloo = restored.reserve(**self.identity(4, 'qloo'))
        self.assertEqual(qloo['state'], 'RESERVED')

    def test_output_overage_alone_is_also_durable(self):
        scheduler = self.scheduler()
        op = scheduler.reserve(**self.identity(1), tokens=1500, input_tokens=1000, output_tokens=500)
        scheduler.mark_sent(op['id'])
        scheduler.finish(op['id'], status=200, result={'accepted':True},
            tokens=1400, input_tokens=700, output_tokens=700)
        self.assertIn('groq', self.scheduler().paused_providers())

    def test_runtime_keeps_accepted_observation_but_never_sends_next_job_after_disproved_estimate(self):
        fixture = causal_fixtures.CausalAgentTests(); fixture.setUp()
        def overage(body):body['usage'].update(prompt_tokens=7900, completion_tokens=300, total_tokens=8200)
        opener = OpenerFixture(mutation=overage)
        estimator = PinnedHarmonyTokenEstimator(ROOT/'assets/tokenizers/o200k_base.tiktoken')
        scheduler = self.scheduler()
        first = ProviderRuntime(scheduler, 'first', 'owner', token_estimator=estimator)
        agent = GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener)
        with first.activate(), self.assertRaises(ProviderAdmissionPaused):agent.rank(fixture.requests[0])
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(len(first.receipts), 1)
        self.assertTrue(first.receipts[0]['current_network_request'])
        self.now += 86401
        with ProviderRuntime(self.scheduler(), 'second', 'owner', token_estimator=estimator).activate(), self.assertRaises(ProviderAdmissionPaused):
            GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener).rank(fixture.requests[0])
        self.assertEqual(len(opener.calls), 1)

    def test_qloo_error_body_is_omitted_from_every_private_ledger_and_operation(self):
        marker = 'arbitrary-provider-debug-context-must-not-be-stored'
        class DebugTool(runtime_fixtures.Tool):
            def send(self, path, params):
                self.calls.append((path, params))
                return Response(401, {'provider_debug_context': marker}, {}, 1.0)
        root = Path(self.temp.name)
        tool = DebugTool()
        client = QlooClient(tool, Ledger(root/'captures', 'test-double-only', (UNIT_SECRET,)))
        runtime = ProviderRuntime(self.scheduler(), 'error-case', 'owner')
        with runtime.activate(), self.assertRaises(ProviderRecordedFailure):
            client.get('/search', {'query': 'Artist'})
        self.assertEqual(len(tool.calls), 1)
        for path in root.rglob('*'):
            if path.is_file():self.assertNotIn(marker.encode(), path.read_bytes())

    def test_timeout_reading_body_after_http200_is_unknown_and_cannot_be_resent(self):
        class TimedOutBody(ResponseFixture):
            def read(self, *args):raise TimeoutError(UNIT_SECRET)
        class ReadTimeoutOpener(OpenerFixture):
            def open(self, request, timeout):
                super().open(request, timeout)
                return TimedOutBody(b'', status=200)
        fixture = causal_fixtures.CausalAgentTests(); fixture.setUp()
        opener = ReadTimeoutOpener()
        scheduler = self.scheduler()
        runtime = ProviderRuntime(scheduler, 'read-timeout', 'owner')
        with runtime.activate(), self.assertRaises(ProviderUncertain):
            GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener).rank(fixture.requests[0])
        stats = scheduler.job_stats('read-timeout')['groq']
        self.assertEqual(stats['unknown_attempts'], 1)
        self.assertEqual(runtime.receipts[0]['operation_mode'], 'unknown')
        with ProviderRuntime(self.scheduler(), 'read-timeout', 'owner').activate(), self.assertRaises(ProviderUncertain):
            GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener).rank(fixture.requests[0])
        self.assertEqual(len(opener.calls), 1)

    def test_invalid_qloo_http200_envelope_omits_arbitrary_body_before_persistence(self):
        from affinityqa.errors import SchemaError
        marker = 'invalid-success-provider-debug-body-must-not-be-stored'
        class InvalidSuccessTool(runtime_fixtures.Tool):
            def send(self, path, params):
                self.calls.append((path, params))
                return Response(200, {'debug_error': marker}, {}, 1.0)
        root = Path(self.temp.name)
        tool = InvalidSuccessTool()
        client = QlooClient(tool, Ledger(root/'captures', 'test-double-only', (UNIT_SECRET,)))
        runtime = ProviderRuntime(self.scheduler(), 'invalid-response', 'owner')
        with runtime.activate(), self.assertRaises(SchemaError):client.get('/search', {'query': 'Artist'})
        for path in root.rglob('*'):
            if path.is_file():self.assertNotIn(marker.encode(), path.read_bytes())
        self.assertEqual(len(tool.calls), 1)

    def test_rejected_model_envelope_still_charges_reported_output_and_pauses_admissions(self):
        from affinityqa.agents import AgentError
        fixture = causal_fixtures.CausalAgentTests(); fixture.setUp()
        def over_output(body):body['usage'].update(prompt_tokens=1000, completion_tokens=1300, total_tokens=2300)
        opener = OpenerFixture(mutation=over_output)
        scheduler = self.scheduler()
        runtime = ProviderRuntime(scheduler, 'over-output', 'owner')
        with runtime.activate(), self.assertRaises(AgentError):
            GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener).rank(fixture.requests[0])
        self.assertEqual(len(opener.calls), 1)
        self.assertIn('groq', self.scheduler().paused_providers())


if __name__ == '__main__': unittest.main()
