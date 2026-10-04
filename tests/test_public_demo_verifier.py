"""Synthetic response mutations only; no provider captures or network calls."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('public_verifier', Path(__file__).resolve().parents[1] / 'scripts/verify_public_demo.py')
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def fixture(fault='stale-profile', repeat=1):
    expected = {'run_id': '20261004T000000Z-00000000', 'pair_id': 'causal-validation-01',
                'fault': fault, 'repeat': repeat, 'artists': {'A': 'Synthetic A', 'B': 'Synthetic B'}}
    artist = expected['artists']['A' if repeat == 2 else 'B']
    diagnosis, repair, dispatches = verifier.OPERATIONS[fault]
    films = [{'position': i, 'title': f'Synthetic film {i}', 'year': 2000+i} for i in range(1, 6)]
    trace = {key: 'a'*64 for key in verifier.TRACE_HASHES}
    trace['cache_hit'] = False
    value = {k: v for k, v in expected.items() if k != 'artists'}
    value.update(schema_version=1, status='PASS', replay_gate='PASS', source='recorded-local-llm-replay',
                 new_model_calls=0, new_qloo_calls=0, recorded_decision_dispatches=dispatches,
                 diagnosis=diagnosis, repair=repair, checks={key: True for key in verifier.CHECKS},
                 cultural_gate='NOT_VALIDATED', release_gate='BLOCKED', notice='Synthetic test only.',
                 requested_artist=artist, identity_before={key: artist for key in verifier.TRACE_HASHES},
                 identity_after={key: artist for key in verifier.TRACE_HASHES}, before=copy.deepcopy(films),
                 after=copy.deepcopy(films), healthy=copy.deepcopy(films), trace=copy.deepcopy(trace),
                 repaired_trace=copy.deepcopy(trace))
    return value, expected


class PublicVerifierTests(unittest.TestCase):
    def test_all_supported_selection_shapes(self):
        for fault in verifier.OPERATIONS:
            for repeat in (1, 2, 3):
                value, expected = fixture(fault, repeat)
                verifier.validate_replay(value, **expected)

    def test_other_incident_cannot_count_as_requested_incident(self):
        for key, bad in (('run_id', 'other-run'), ('pair_id', 'causal-validation-02'),
                         ('fault', 'cache-omits-profile'), ('repeat', 2), ('repeat', True)):
            with self.subTest(key=key, bad=bad):
                value, expected = fixture(); value[key] = bad
                with self.assertRaises(RuntimeError): verifier.validate_replay(value, **expected)

    def test_checks_are_exact_true_booleans_not_vacuous_or_truthy(self):
        for checks in ({}, {'repair_applied': True}, {k: 1 for k in verifier.CHECKS},
                       {**dict.fromkeys(verifier.CHECKS, True), 'extra': True},
                       {**dict.fromkeys(verifier.CHECKS, True), 'repair_applied': False}):
            with self.subTest(checks=checks):
                value, expected = fixture(); value['checks'] = checks
                with self.assertRaises(RuntimeError): verifier.validate_replay(value, **expected)

    def test_exact_source_and_integer_counters(self):
        for key, bad in (('source', 'live'), ('new_model_calls', False), ('new_qloo_calls', 1),
                         ('recorded_decision_dispatches', 3), ('schema_version', True),
                         ('replay_gate', 'FAIL'), ('repair', 'none')):
            with self.subTest(key=key):
                value, expected = fixture(); value[key] = bad
                with self.assertRaises(RuntimeError): verifier.validate_replay(value, **expected)

    def test_top_five_is_complete_and_ordered(self):
        for mode in ('empty', 'four', 'six', 'position', 'title', 'year'):
            value, expected = fixture()
            for view in ('before', 'after', 'healthy'):
                if mode == 'empty': value[view] = []
                elif mode == 'four': value[view].pop()
                elif mode == 'six': value[view].append(copy.deepcopy(value[view][-1]))
                elif mode == 'position': value[view][0]['position'] = True
                elif mode == 'title': value[view][0]['title'] = ''
                else: value[view][0]['year'] = True
            with self.subTest(mode=mode), self.assertRaises(RuntimeError): verifier.validate_replay(value, **expected)

    def test_private_fields_rejected_at_each_projection(self):
        for field in ('root', 'film', 'trace', 'identity'):
            value, expected = fixture()
            target = {'root': value, 'film': value['before'][0], 'trace': value['trace'],
                      'identity': value['identity_before']}[field]
            target['private_packet'] = 'SYNTHETIC PRIVATE FIELD'
            with self.subTest(field=field), self.assertRaises(RuntimeError): verifier.validate_replay(value, **expected)

    def test_identity_labels_and_hash_schema(self):
        for mode in ('requested', 'conflict', 'hash', 'boolean'):
            value, expected = fixture()
            if mode == 'requested': value['requested_artist'] = 'Synthetic A'
            elif mode == 'conflict': value['identity_before']['tool_profile_sha256'] = 'Synthetic A'
            elif mode == 'hash': value['trace']['tool_profile_sha256'] = 'not-a-hash'
            else: value['trace']['cache_hit'] = 0
            with self.subTest(mode=mode), self.assertRaises(RuntimeError): verifier.validate_replay(value, **expected)


if __name__ == '__main__': unittest.main()
