"""Safe provider failure categories, with denied-network synthetic responses."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent
from test_discovery_agent import Opener, TEST_SECRET, fixture_request


class DiscoveryDiagnosticTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Real network denied'))
            guard.start(); self.addCleanup(guard.stop)

    def test_HTTP_failure_class_distinguishes_quota_credentials_request_and_service(self):
        for code, expected in ((429, 'DiscoveryRateLimitError'), (401, 'DiscoveryCredentialsError'),
                               (403, 'DiscoveryCredentialsError'), (400, 'DiscoveryRequestRejectedError'),
                               (422, 'DiscoveryRequestRejectedError'), (503, 'DiscoveryServiceError')):
            with self.subTest(code=code):
                opener = Opener(failure=HTTPError('https://example.invalid/'+TEST_SECRET, code, TEST_SECRET, {}, None))
                engine = DiscoveryMovieAgent(TEST_SECRET, _test_opener=opener)
                with self.assertRaises(Exception) as caught: engine.rank(fixture_request())
                self.assertEqual(type(caught.exception).__name__, expected)
                self.assertIn('HTTP'+str(code), str(caught.exception))
                self.assertNotIn(TEST_SECRET, str(caught.exception))
                self.assertEqual((engine.calls, len(opener.calls), len(engine.observations)), (1, 1, 0))

    def test_network_failure_is_distinct_and_does_not_echo_private_error_text(self):
        opener = Opener(failure=URLError(TEST_SECRET))
        engine = DiscoveryMovieAgent(TEST_SECRET, _test_opener=opener)
        with self.assertRaises(Exception) as caught: engine.rank(fixture_request())
        self.assertEqual(type(caught.exception).__name__, 'DiscoveryNetworkError')
        self.assertNotIn(TEST_SECRET, str(caught.exception))
        self.assertEqual((engine.calls, len(opener.calls), len(engine.observations)), (1, 1, 0))

    def test_HTTP200_invalid_model_contract_is_not_misreported_as_rate_limit(self):
        opener = Opener(mutation=lambda body: body.update(object='invalid.object'))
        engine = DiscoveryMovieAgent(TEST_SECRET, _test_opener=opener)
        with self.assertRaises(Exception) as caught: engine.rank(fixture_request())
        self.assertEqual(type(caught.exception).__name__, 'AgentError')
        self.assertEqual((engine.calls, len(opener.calls), len(engine.observations)), (1, 1, 0))


if __name__ == '__main__': unittest.main()
