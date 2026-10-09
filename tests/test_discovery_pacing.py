"""Recorded real-source identifiers without providers, credentials or transport."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from affinityqa.cinema_discovery_file_verify import verify_pacing
from affinityqa.errors import SchemaError
from affinityqa.individual_remote_verify import expected_pacing

SOURCE = 'qloo-tool+groq-remote-discovery-v2'


def fixture(source=SOURCE, complete=False):
    plan = {'execution_pacing': expected_pacing(22.0)}
    count = 2 if complete else 1
    report = {'source': source, 'admitted_model_slots': count, 'model_attempts': count,
              'status': 'COMPLETE' if complete else 'INCOMPLETE'}
    events = [{'kind': 'remote_model_attempt_admitted', 'sequence': 2 + 10*i, 'data': {
        'schema_version': 1, 'execution_source': 'test-double-only' if source == 'test-double-only' else 'remote-llm',
        'slot': i+1, 'adapter_calls_before_dispatch': i, 'relative_start_seconds': 22.0*i,
        'scheduled_wait_seconds': 0.0 if i == 0 else 22.0, 'minimum_interval_seconds': 22.0,
        'external_completion_attested': False}} for i in range(count)]
    observed = [{'sequence': 3 + 10*i} for i in range(count)] if complete else []
    return plan, events, report, observed, [{'sequence': 1}]


class DiscoveryPacingTests(unittest.TestCase):
    def test_actual_new_source_first_failed_attempt_preserves_valid_partial(self):
        verify_pacing(*fixture())

    def test_actual_complete_and_synthetic_sources_keep_the_same_cadence(self):
        verify_pacing(*fixture(complete=True))
        verify_pacing(*fixture(source='test-double-only', complete=True))

    def test_legacy_or_unknown_source_cannot_masquerade_as_discovery(self):
        for source in ('qloo-tool+groq-remote-llm', 'unknown-source'):
            with self.subTest(source=source), self.assertRaises(SchemaError):
                verify_pacing(*fixture(source))

    def test_wrong_engine_missing_pacing_or_early_second_slot_rejects(self):
        for change in ('wrong-engine', 'unconfigured', 'early-second-slot'):
            plan, events, report, observed, frozen = copy.deepcopy(fixture(complete=True))
            if change == 'wrong-engine': events[0]['data']['execution_source'] = 'test-double-only'
            elif change == 'unconfigured': plan['execution_pacing'] = expected_pacing(None)
            else: events[1]['data']['relative_start_seconds'] = 21.0
            with self.subTest(change=change), self.assertRaises(SchemaError):
                verify_pacing(plan, events, report, observed, frozen)


if __name__ == '__main__': unittest.main()
