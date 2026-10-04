"""Synthetic contract fixtures, not empirical repair evidence."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from affinityqa.causal_evaluator import EXPECTED, evaluate_pair
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint


def fixture(same_ranking=False):
    ids = [str(n) for n in range(20)]
    profiles = {p: {'entity_id': p, 'name': 'Synthetic ' + p, 'type': 'urn:entity:artist'} for p in ('A', 'B')}
    hashes = {p: fingerprint(v) for p, v in profiles.items()}
    ranks = {'A': ids, 'B': ids if same_ranking else ids[::-1]}
    serial = 0

    def decision(p):
        nonlocal serial
        serial += 1
        return {'ranking': list(ranks[p]), 'trace': {
            **{k: hashes[p] for k in ('requested_profile_sha256', 'transmitted_profile_sha256', 'tool_profile_sha256', 'output_profile_sha256')},
            'cache_hit': False, 'execution_id': 'synthetic/' + str(serial), 'call': serial,
            'payload_sha256': fingerprint(['payload', p]), 'context_response_sha256': fingerprint(['context', p])}}

    def control(d, hit):
        c = copy.deepcopy(d); c['trace']['cache_hit'] = hit
        c.update(expected_cache_hit=hit, diagnosis={'diagnosis': 'NONE', 'operation': 'none'})
        return c

    healthy = {p: [decision(p) for _ in range(3)] for p in ('A', 'B')}
    controls = [control(d, False) for rows in healthy.values() for d in rows]
    controls += [control(healthy[p][r], True) for r, p in enumerate(('B', 'A', 'B'))]
    cases = []
    for fault, (diagnosis, operation) in EXPECTED.items():
        repeats = []
        for r in range(3):
            order = ['A', 'B'] if r != 1 else ['B', 'A']; lead, victim = order
            before = {lead: decision(lead), victim: decision(victim)}
            if fault == 'cache-omits-profile':
                before[victim] = copy.deepcopy(before[lead]); before[victim]['trace']['cache_hit'] = True
                before[victim]['trace']['requested_profile_sha256'] = hashes[victim]
            elif fault == 'stale-profile':
                before[victim]['ranking'] = list(ranks[lead])
                for k in ('transmitted_profile_sha256', 'tool_profile_sha256', 'output_profile_sha256'):
                    before[victim]['trace'][k] = hashes[lead]
            else:
                before[victim]['ranking'] = list(ranks[lead])
                before[victim]['trace']['tool_profile_sha256'] = hashes[lead]
            after = {p: decision(p) for p in ('A', 'B')}
            repeats.append({'repeat': r + 1, 'order': order, 'before': before, 'after': after,
                'diagnosis': {'diagnosis': diagnosis, 'operation': operation},
                'patch': {'operation': operation, 'attempt': 1, 'applied': True},
                'after_controls': [control(after[victim], True)]})
        cases.append({'fault': fault, 'repeats': repeats})
    return {'pair_id': 'synthetic-pair', 'artists': {p: profiles[p]['name'] for p in profiles},
        'split': 'synthetic-test-only', 'profiles': profiles,
        'catalog': [{'entity_id': i, 'name': 'Synthetic movie ' + i, 'release_year': 2000} for i in ids],
        'healthy': healthy, 'healthy_controls': controls, 'cases': cases, 'tool_signal_distance': .5}


class CausalEvaluatorTests(unittest.TestCase):
    def test_complete_three_cause_recovery_and_legitimate_cache(self):
        out = evaluate_pair(fixture(), 0)
        self.assertTrue(all(c['passing'] for c in out['cases']))
        self.assertEqual([c['behavioral_recovery_observed_repeats'] for c in out['cases']], [3, 3, 3])
        self.assertEqual([c['recovery_max_distance'] for c in out['cases']], [0, 0, 0])

    def test_no_effect_is_not_misrepresented_as_behavioral_recovery(self):
        out = evaluate_pair(fixture(same_ranking=True), 0)
        self.assertTrue(all(c['passing'] for c in out['cases']))
        self.assertEqual([c['behavioral_recovery_observed_repeats'] for c in out['cases']], [0, 0, 0])

    def test_wrong_diagnosis_cannot_pass_from_expected_scenario_label(self):
        f = fixture(); f['cases'][0]['repeats'][0]['diagnosis']['diagnosis'] = 'STALE_PROFILE'
        self.assertFalse(evaluate_pair(f, 0)['cases'][0]['checks']['correct_diagnosis'])

    def test_repair_must_reexecute_and_have_coherent_profile(self):
        f = fixture(); r = f['cases'][0]['repeats'][0]
        r['after']['B'] = copy.deepcopy(r['before']['B'])
        out = evaluate_pair(f, 0)['cases'][0]
        self.assertFalse(out['checks']['real_rerun']); self.assertFalse(out['checks']['profile_integrity_restored'])

    def test_new_execution_id_alone_cannot_hide_wrong_snapshot(self):
        f = fixture(); f['cases'][1]['repeats'][0]['after']['B']['trace']['context_response_sha256'] = '0' * 64
        self.assertFalse(evaluate_pair(f, 0)['cases'][1]['checks']['profile_integrity_restored'])

    def test_false_alarm_in_healthy_control_blocks_all_cases(self):
        f = fixture(); f['healthy_controls'][0]['diagnosis'] = {'diagnosis': 'STALE_PROFILE', 'operation': 'restore-request-profile'}
        self.assertTrue(all(not c['passing'] for c in evaluate_pair(f, 0)['cases']))

    def test_cache_reuse_requires_same_origin_and_output(self):
        f = fixture(); f['cases'][2]['repeats'][0]['after_controls'][0]['ranking'].reverse()
        self.assertFalse(evaluate_pair(f, 0)['cases'][2]['checks']['legitimate_cache_reuse'])

    def test_second_patch_attempt_does_not_pass(self):
        f = fixture(); f['cases'][0]['repeats'][0]['patch']['attempt'] = 2
        self.assertFalse(evaluate_pair(f, 0)['cases'][0]['checks']['repair_applied'])

    def test_all_healthy_repeats_bound_recovery_not_just_nearest(self):
        f = fixture(); f['cases'][0]['repeats'][0]['after']['A']['ranking'].reverse()
        self.assertFalse(evaluate_pair(f, 0)['cases'][0]['checks']['no_behavioral_regression'])

    def test_incomplete_or_duplicate_permutations_raise(self):
        for rank in (['0'] * 20, [str(n) for n in range(19)]):
            f = fixture(); f['cases'][0]['repeats'][0]['before']['B']['ranking'] = rank
            with self.assertRaises(SchemaError): evaluate_pair(f, 0)

    def test_missing_case_repeat_and_control_cannot_shrink_denominator(self):
        for key in ('case', 'repeat', 'control'):
            f = fixture()
            if key == 'case': f['cases'].pop()
            elif key == 'repeat': f['cases'][0]['repeats'].pop()
            else: f['healthy_controls'].pop()
            with self.assertRaises(SchemaError): evaluate_pair(f, 0)

    def test_invalid_noise_or_trace_schema_raise(self):
        for noise in (float('nan'), -1, True, 1.1):
            with self.assertRaises(SchemaError): evaluate_pair(fixture(), noise)
        f = fixture(); del f['healthy']['A'][0]['trace']['call']
        with self.assertRaises(SchemaError): evaluate_pair(f, 0)


if __name__ == '__main__':
    unittest.main()
