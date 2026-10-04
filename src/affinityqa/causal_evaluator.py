"""Independent evaluator of bounded integration repair, never cultural quality."""
import math
import re
from itertools import combinations

from .errors import SchemaError
from .evidence import fingerprint
from .metrics import rank_distance

EXPECTED = {
    'cache-omits-profile': ('CACHE_OMITS_PROFILE', 'set-profile-cache'),
    'stale-profile': ('STALE_PROFILE', 'restore-request-profile'),
    'wrong-tool-profile': ('WRONG_TOOL_PROFILE', 'bind-request-tool'),
}
HASHES = ('requested_profile_sha256', 'transmitted_profile_sha256',
          'tool_profile_sha256', 'output_profile_sha256', 'payload_sha256',
          'context_response_sha256')


def _require(ok, message):
    if not ok:
        raise SchemaError('Causal evaluation: ' + message)


def _diagnose(t):
    r, sent, tool, out = [t[k] for k in HASHES[:4]]
    if t['cache_hit']:
        return 'CACHE_OMITS_PROFILE' if r != out and sent == tool == out else ('NONE' if r == sent == tool == out else 'UNSUPPORTED')
    if r != sent and sent == tool == out:
        return 'STALE_PROFILE'
    if r == sent == out and r != tool:
        return 'WRONG_TOOL_PROFILE'
    return 'NONE' if r == sent == tool == out else 'UNSUPPORTED'


def evaluate_pair(record, noise_barrier):
    """All cases mandatory; a pass concerns this causal sample only."""
    _require(type(noise_barrier) in (int, float) and math.isfinite(noise_barrier)
             and 0 <= noise_barrier <= 1, 'invalid frozen noise barrier')
    _require(isinstance(record, dict), 'record must be an object')
    for key in ('pair_id', 'artists', 'split', 'catalog', 'profiles', 'healthy', 'healthy_controls', 'cases', 'tool_signal_distance'):
        _require(key in record, 'missing ' + key)
    _require(isinstance(record['pair_id'], str) and bool(record['pair_id']) and isinstance(record['split'], str), 'invalid identity')
    distance = record['tool_signal_distance']
    _require(type(distance) in (int, float) and math.isfinite(distance) and 0 <= distance <= 1, 'invalid tool distance')
    catalog = record['catalog']
    _require(isinstance(catalog, list) and len(catalog) == 20, 'catalog requires twenty movies')
    _require(all(isinstance(e, dict) and isinstance(e.get('entity_id'), str) and e['entity_id']
                 and isinstance(e.get('name'), str) and type(e.get('release_year')) is int for e in catalog), 'invalid catalog identity')
    ids = {e['entity_id'] for e in catalog}
    _require(len(ids) == 20, 'duplicate catalog identity')
    for field in ('profiles', 'healthy', 'artists'):
        _require(isinstance(record[field], dict) and set(record[field]) == {'A', 'B'}, 'both profiles required in ' + field)
    profiles = record['profiles']
    _require(all(isinstance(p, dict) and set(p) == {'entity_id', 'name', 'type'} and all(isinstance(v, str) and v for v in p.values()) for p in profiles.values()), 'invalid profiles')
    hashes = {p: fingerprint(profiles[p]) for p in ('A', 'B')}
    _require(len(set(hashes.values())) == 2, 'profiles must differ')

    def decision(d):
        _require(isinstance(d, dict) and isinstance(d.get('ranking'), list) and isinstance(d.get('trace'), dict), 'missing decision')
        ranking, t = d['ranking'], d['trace']
        _require(len(ranking) == 20 and all(isinstance(i, str) for i in ranking) and set(ranking) == ids, 'incomplete ranking permutation')
        _require(all(isinstance(t.get(k), str) and re.fullmatch('[0-9a-f]{64}', t[k]) for k in HASHES), 'invalid trace hashes')
        _require(type(t.get('cache_hit')) is bool and isinstance(t.get('execution_id'), str) and bool(t['execution_id'])
                 and type(t.get('call')) is int and t['call'] > 0, 'invalid execution trace')
        return t

    def coherent(t, p):
        return all(t[k] == hashes[p] for k in HASHES[:4])

    def same_output(d, source):
        return d['ranking'] == source['ranking'] and all(d['trace'][k] == source['trace'][k]
            for k in ('execution_id', 'call', 'payload_sha256', 'context_response_sha256', 'output_profile_sha256'))

    def diagnostic(d, expected):
        _require(isinstance(d, dict) and set(d) == {'diagnosis', 'operation'} and all(isinstance(v, str) for v in d.values()), 'invalid diagnosis')
        return (d['diagnosis'], d['operation']) == expected

    healthy = record['healthy']; origin = {}; healthy_ok = True
    for p in ('A', 'B'):
        _require(isinstance(healthy[p], list) and len(healthy[p]) == 3, 'three healthy repeats required')
        for d in healthy[p]:
            t = decision(d)
            _require(t['execution_id'] not in origin, 'duplicate healthy execution')
            origin[t['execution_id']] = d
            healthy_ok &= coherent(t, p) and not t['cache_hit']
        healthy_ok &= all(rank_distance(a['ranking'], b['ranking'], 5) <= noise_barrier + 1e-12 for a, b in combinations(healthy[p], 2))

    def control(c, sources):
        t = decision(c)
        _require(type(c.get('expected_cache_hit')) is bool, 'control missing expected cache behavior')
        p = next((p for p in hashes if hashes[p] == t['requested_profile_sha256']), None)
        good = p is not None and coherent(t, p) and _diagnose(t) == 'NONE'
        good &= diagnostic(c.get('diagnosis'), ('NONE', 'none')) and t['cache_hit'] == c['expected_cache_hit']
        source = sources.get(t['execution_id'])
        good &= source is not None and same_output(c, source)
        return bool(good)

    controls = record['healthy_controls']
    _require(isinstance(controls, list) and len(controls) == 9, 'nine healthy controls required')
    healthy_controls_ok = all([control(c, origin) for c in controls])
    _require(sum(c['expected_cache_hit'] for c in controls) == 3, 'six fresh and three cache controls required')
    _require({c['trace']['execution_id'] for c in controls if not c['expected_cache_hit']} == set(origin), 'healthy fresh control coverage incomplete')
    cases = record['cases']
    _require(isinstance(cases, list) and len(cases) == 3 and all(isinstance(c, dict) for c in cases)
             and {c.get('fault') for c in cases} == set(EXPECTED), 'exactly three declared faults required')
    summaries = []; rerun_ids = set(origin)
    for case in cases:
        fault = case['fault']; expected = EXPECTED[fault]; repeats = case.get('repeats')
        _require(isinstance(repeats, list) and len(repeats) == 3 and all(isinstance(r, dict) for r in repeats)
                 and {r.get('repeat') for r in repeats} == {1, 2, 3}, 'three unique incident repeats required')
        checks = dict.fromkeys(('complete_repeats', 'correct_diagnosis', 'repair_applied', 'profile_integrity_restored',
            'real_rerun', 'healthy_stable', 'no_behavioral_regression', 'no_false_alarm', 'legitimate_cache_reuse'), True)
        checks['healthy_stable'] = bool(healthy_ok); checks['no_false_alarm'] = healthy_controls_ok
        changed = recovered = 0; max_after = max_before = full_after = 0.; views = []
        for r in sorted(repeats, key=lambda x: x['repeat']):
            order = r.get('order')
            _require(order in (['A', 'B'], ['B', 'A']), 'invalid incident order')
            for state in ('before', 'after'):
                _require(isinstance(r.get(state), dict) and set(r[state]) == {'A', 'B'}, 'missing both incident profiles')
                for d in r[state].values(): decision(d)
            before, after = r['before'], r['after']; victim = order[1]
            checks['correct_diagnosis'] &= diagnostic(r.get('diagnosis'), expected) and _diagnose(before[victim]['trace']) == expected[0]
            checks['correct_diagnosis'] &= coherent(before[order[0]]['trace'], order[0]) and before[victim]['trace']['requested_profile_sha256'] == hashes[victim]
            wrong = before[victim]['trace']
            wrong_keys = ('tool_profile_sha256',) if fault == 'wrong-tool-profile' else ('transmitted_profile_sha256', 'tool_profile_sha256', 'output_profile_sha256')
            checks['correct_diagnosis'] &= all(wrong[k] == hashes[order[0]] for k in wrong_keys)
            if fault == 'cache-omits-profile':
                checks['correct_diagnosis'] &= same_output(before[victim], before[order[0]])
            patch = r.get('patch')
            _require(isinstance(patch, dict), 'missing patch')
            checks['repair_applied'] &= patch.get('operation') == expected[1] and type(patch.get('attempt')) is int and patch['attempt'] == 1 and patch.get('applied') is True
            before_ids = {d['trace']['execution_id'] for d in before.values()}
            repeat_after = 0.
            for p in ('A', 'B'):
                t = after[p]['trace']
                checks['profile_integrity_restored'] &= coherent(t, p) and all(t[k] == healthy[p][0]['trace'][k] for k in ('payload_sha256', 'context_response_sha256'))
                checks['real_rerun'] &= not t['cache_hit'] and t['execution_id'] not in before_ids and t['execution_id'] not in rerun_ids
                rerun_ids.add(t['execution_id'])
                d5 = max(rank_distance(after[p]['ranking'], h['ranking'], 5) for h in healthy[p])
                repeat_after = max(repeat_after, d5); max_after = max(max_after, d5)
                full_after = max(full_after, *(rank_distance(after[p]['ranking'], h['ranking'], 20) for h in healthy[p]))
            checks['no_behavioral_regression'] &= repeat_after <= noise_barrier + 1e-12
            bdist = min(rank_distance(before[victim]['ranking'], h['ranking'], 5) for h in healthy[victim])
            max_before = max(max_before, bdist)
            changed += bdist > noise_barrier + 1e-12
            recovered += bdist > noise_barrier + 1e-12 and repeat_after <= noise_barrier + 1e-12
            ac = r.get('after_controls')
            _require(isinstance(ac, list) and len(ac) == 1, 'one post-repair reuse control required')
            reuse = control(ac[0], {d['trace']['execution_id']: d for d in after.values()}) and ac[0]['expected_cache_hit']
            checks['legitimate_cache_reuse'] &= reuse; checks['no_false_alarm'] &= reuse
            lookup = {e['entity_id']: e for e in catalog}
            views.append({'repeat': r['repeat'], 'order': order, 'profile': victim,
                'healthy': [lookup[i] for i in healthy[victim][0]['ranking'][:5]],
                'before': [lookup[i] for i in before[victim]['ranking'][:5]],
                'after': [lookup[i] for i in after[victim]['ranking'][:5]],
                'trace': before[victim]['trace'], 'repaired_trace': after[victim]['trace']})
        checks = {k: bool(v) for k, v in checks.items()}
        summaries.append({'fault': fault, 'diagnosis': expected[0], 'repair_operation': expected[1],
            'passing': all(checks.values()), 'checks': checks, 'behavior_changed_repeats': changed,
            'behavioral_recovery_observed_repeats': recovered, 'recovery_max_distance': max_after,
            'before_max_distance': max_before, 'full_ranking_recovery_max_distance': full_after,
            'repeat_count': 3, 'views': views})
    return {k: record[k] for k in ('pair_id', 'artists', 'split', 'tool_signal_distance')} | {'cases': summaries}
