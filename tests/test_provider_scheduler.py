"""Behavioral quota/crash fixtures; no claim of real account capacity."""
import concurrent.futures
from email.utils import formatdate
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from affinityqa.evidence import fingerprint
from affinityqa.provider_scheduler import (ProviderScheduler, QuotaWindow, ProviderDeferred,
    ProviderRequestTooLarge, ProviderUncertain, ProviderRecordedFailure, safe_quota_metadata)


class Clock:
    def __init__(self, now=100000): self.now = now
    def __call__(self): return self.now


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / 'test-private-scratch'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'quota.sqlite3'
        self.clock = Clock()

    def scheduler(self, windows=None):
        return ProviderScheduler(self.path, limits={'groq': windows or (
            QuotaWindow('rpm', 2, 60), QuotaWindow('rpd', 3, 86400),
            QuotaWindow('tpm', 100, 60, 'tokens'), QuotaWindow('tpd', 150, 86400, 'tokens'))}, clock=self.clock)

    def identity(self, n):
        return dict(owner_id='owner', job_id='job' + str(n), stage='stage', provider='groq', request_sha256=fingerprint(n))

    def send(self, scheduler, n, tokens=40):
        op = scheduler.reserve(**self.identity(n), tokens=tokens)
        scheduler.mark_sent(op['id'])
        scheduler.finish(op['id'], result={'accepted': n}, status=200, tokens=tokens)
        return op

    def test_minute_then_daily_token_waits_survive_new_instance_without_midnight(self):
        scheduler = self.scheduler()
        self.send(scheduler, 1)
        self.send(scheduler, 2)
        with self.assertRaises(ProviderDeferred) as caught:
            scheduler.reserve(**self.identity(3), tokens=40)
        self.assertEqual(caught.exception.next_eligible_at, self.clock() + 60)
        self.clock.now += 60
        fresh = self.scheduler()
        self.send(fresh, 3)
        self.clock.now += 60
        with self.assertRaises(ProviderDeferred) as caught:
            fresh.reserve(**self.identity(4), tokens=40)
        self.assertEqual(caught.exception.next_eligible_at, 100000 + 86400)
        self.assertIn('tpd', caught.exception.reason)
        self.clock.now = caught.exception.next_eligible_at
        self.send(self.scheduler(), 4)

    def test_monthly_window_is_explicit_rolling_window(self):
        windows = (QuotaWindow('month', 1, 31*86400),)
        scheduler = self.scheduler(windows)
        self.send(scheduler, 1, 0)
        with self.assertRaises(ProviderDeferred) as caught:
            scheduler.reserve(**self.identity(2))
        self.assertEqual(caught.exception.next_eligible_at, 100000 + 31*86400)
        self.clock.now = caught.exception.next_eligible_at
        self.send(self.scheduler(windows), 2, 0)

    def test_two_independent_instances_cannot_multiply_quota(self):
        windows = (QuotaWindow('rpm', 1, 60),)
        first, second = self.scheduler(windows), self.scheduler(windows)
        def reserve(pair):
            scheduler, n = pair
            try:
                return scheduler.reserve(**self.identity(n))['state']
            except ProviderDeferred:
                return 'WAIT'
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(reserve, ((first, 1), (second, 2))))
        self.assertCountEqual(outcomes, ['RESERVED', 'WAIT'])

    def test_pre_send_restart_reuses_reservation_once_and_post_send_never_replays(self):
        scheduler = self.scheduler()
        operation = scheduler.reserve(**self.identity(1), tokens=40)
        restarted = self.scheduler()
        same = restarted.reserve(**self.identity(1), tokens=40)
        self.assertEqual(operation['id'], same['id'])
        restarted.mark_sent(same['id'])
        with self.assertRaises(RuntimeError):
            scheduler.mark_sent(operation['id'])
        self.assertEqual(restarted.recover_sent(job_id='job1', owner_id='owner'), 1)
        with self.assertRaises(ProviderUncertain):
            self.scheduler().reserve(**self.identity(1), tokens=40)
        stats = restarted.job_stats('job1')
        self.assertEqual((stats['groq']['http_attempts'], stats['groq']['unknown_attempts']), (1, 1))

    def test_stale_before_send_reservation_rechecks_capacity(self):
        scheduler = self.scheduler((QuotaWindow('rpm', 1, 60),))
        stale = scheduler.reserve(**self.identity(1))
        self.clock.now += 61
        other = scheduler.reserve(**self.identity(2))
        scheduler.mark_sent(other['id'])
        with self.assertRaises(ProviderDeferred):
            scheduler.mark_sent(stale['id'])
        self.assertEqual(scheduler.lookup(**self.identity(1))['state'], 'PENDING')

    def test_oversized_request_diagnosed_and_does_not_block_eligible_job(self):
        scheduler = self.scheduler()
        with self.assertRaises(ProviderRequestTooLarge) as caught:
            scheduler.reserve(**self.identity(1), tokens=101)
        self.assertEqual((caught.exception.window, caught.exception.required, caught.exception.capacity), ('tpm', 101, 100))
        self.send(scheduler, 2)
        self.assertIsNone(scheduler.lookup(**self.identity(1))['sent'])
        with self.assertRaises(ProviderRequestTooLarge):
            self.scheduler().reserve(**self.identity(1), tokens=101)

    def test_long_token_wait_does_not_block_small_eligible_request(self):
        scheduler = self.scheduler()
        self.send(scheduler, 1, 80)
        with self.assertRaises(ProviderDeferred):
            scheduler.reserve(**self.identity(2), tokens=50)
        self.send(scheduler, 3, 10)

    def test_headers_requests_are_daily_tokens_are_minute_and_daily_ledger_independent(self):
        scheduler = self.scheduler()
        op = scheduler.reserve(**self.identity(1), tokens=40)
        scheduler.mark_sent(op['id'])
        scheduler.finish(op['id'], result={'ok': True}, status=200, headers={
            'x-ratelimit-remaining-requests': '0', 'x-ratelimit-reset-requests': '2h',
            'x-ratelimit-remaining-tokens': '60', 'x-ratelimit-reset-tokens': '1m'})
        with self.assertRaises(ProviderDeferred) as caught:
            scheduler.reserve(**self.identity(2), tokens=40)
        self.assertEqual(caught.exception.next_eligible_at, self.clock() + 7200)
        self.assertEqual(caught.exception.reason, 'observed-rpd')

    def test_sent_429_contributes_attempt_and_blocks_until_safe_retry_after(self):
        scheduler = self.scheduler()
        op = scheduler.reserve(**self.identity(1), tokens=40)
        scheduler.mark_sent(op['id'])
        scheduler.finish(op['id'], status=429, headers={'Retry-After': '90061', 'authorization': 'PRIVATE'})
        with self.assertRaises(ProviderRecordedFailure):
            scheduler.reserve(**self.identity(1), tokens=40)
        with self.assertRaises(ProviderDeferred) as caught:
            scheduler.reserve(**self.identity(2), tokens=40)
        self.assertEqual(caught.exception.next_eligible_at, self.clock() + 90061)
        self.assertNotIn('PRIVATE', str(scheduler.lookup(**self.identity(1))))

    def test_malformed_429_metadata_cannot_cause_rapid_retry_polling(self):
        scheduler = self.scheduler()
        op = scheduler.reserve(**self.identity(1))
        scheduler.mark_sent(op['id'])
        scheduler.finish(op['id'], status=429, headers={'Retry-After': 'nan', 'x-ratelimit-reset-tokens': 'PRIVATE'})
        with self.assertRaises(ProviderDeferred) as caught:
            scheduler.reserve(**self.identity(2))
        self.assertGreaterEqual(caught.exception.next_eligible_at - self.clock(), 60)

    def test_safe_header_allowlist_rejects_booleans_negative_nonfinite_and_secrets(self):
        metadata = safe_quota_metadata({'Authorization': 'SECRET', 'x-request-id': 'SECRET',
            'x-ratelimit-limit-requests': '1000', 'x-ratelimit-remaining-requests': '-1',
            'x-ratelimit-remaining-tokens': True, 'x-ratelimit-reset-tokens': '1h2m3.5s',
            'retry-after': formatdate(self.clock() + 300, usegmt=True)}, now=self.clock())
        self.assertEqual(metadata, {'x-ratelimit-limit-requests': 1000,
            'x-ratelimit-reset-tokens-seconds': 3723.5, 'retry-after-seconds': 300})

    def test_exact_request_binding_and_separate_input_output_windows(self):
        scheduler = self.scheduler((QuotaWindow('input', 20, 60, 'input_tokens'), QuotaWindow('output', 10, 60, 'output_tokens')))
        operation = scheduler.reserve(**self.identity(1), tokens=25, input_tokens=20, output_tokens=5)
        changed = {**self.identity(1), 'request_sha256': fingerprint('different')}
        with self.assertRaises(RuntimeError):
            scheduler.lookup(**changed)
        with self.assertRaises(ProviderRequestTooLarge):
            scheduler.reserve(**self.identity(2), tokens=30, input_tokens=20, output_tokens=11)
        self.assertEqual(operation['state'], 'RESERVED')

    def test_config_change_is_explicit_and_accepted_result_keeps_conservative_charge(self):
        scheduler = self.scheduler()
        operation = scheduler.reserve(**self.identity(1), tokens=80)
        scheduler.mark_sent(operation['id'])
        scheduler.finish(operation['id'], result={'ok': True}, status=200, tokens=10)
        with self.assertRaises(ProviderDeferred):
            scheduler.reserve(**self.identity(2), tokens=30)
        with self.assertRaises(ValueError):
            self.scheduler((QuotaWindow('rpm', 100, 60),))

    def test_terminal_job_releases_pending_without_erasing_sent_unknown(self):
        scheduler = self.scheduler((QuotaWindow('rpm', 1, 60),))
        sent = scheduler.reserve(**self.identity(1))
        scheduler.mark_sent(sent['id'])
        with self.assertRaises(ProviderDeferred):
            scheduler.reserve(**self.identity(2))
        self.assertEqual(scheduler.abandon_pending('job2', 'owner'), 1)
        self.assertEqual(scheduler.abandon_pending('job1', 'owner'), 0)
        self.assertEqual(scheduler.lookup(**self.identity(1))['state'], 'SENT')
        with self.assertRaises(ProviderRecordedFailure):
            scheduler.reserve(**self.identity(2))
        self.clock.now += 60
        self.send(scheduler, 3, 0)

    def test_persisted_provenance_survives_new_instance_and_owner_isolation(self):
        scheduler = self.scheduler()
        receipt = {'owner_id': 'owner', 'job_id': 'job1', 'provider': 'groq',
                   'operation_mode': 'accepted-reconstruction', 'original_response_sha256': fingerprint('original')}
        scheduler.record_receipt(receipt)
        self.assertEqual(self.scheduler().job_receipts('job1', 'owner'), [receipt])
        self.assertEqual(scheduler.job_receipts('job1', 'other-owner'), [])


if __name__ == '__main__': unittest.main()
