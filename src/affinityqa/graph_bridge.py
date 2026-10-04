"""A bounded cultural-graph experiment, separate from both closed studies.

The repair API deliberately cannot accept artist IDs or evaluation answers.
Direct artist references belong only to the evaluator called after capture.
"""
from __future__ import annotations

from itertools import product
import time

from .errors import AffinityQAError, SchemaError
from .evidence import fingerprint, utc_now
from .film_protocol import calibrate_reference
from .metrics import ndcg_at_k, max_repeat_jitter
from .models import canonical_id, context_issues, parse_entities
from .semantic_bridge import load_development, profile_delta


def validate_input(value):
    if not isinstance(value, dict) or set(value) != {'catalog', 'anchors', 'baseline'}:
        raise SchemaError('Graph repair accepts only catalog, external anchors and its own baseline.')
    catalog = value['catalog']
    if (not isinstance(catalog, list) or len(catalog) != 20
            or any(set(e) != {'entity_id', 'name', 'release_year'} for e in catalog)):
        raise SchemaError('Graph catalog must contain twenty minimal movie identities.')
    ids = [canonical_id(e['entity_id']) for e in catalog]
    if len(set(ids)) != 20 or any(not isinstance(e['name'], str) or type(e['release_year']) is not int for e in catalog):
        raise SchemaError('Graph catalog identities are invalid.')
    anchors = value['anchors']
    if (not isinstance(anchors, dict) or set(anchors) != {'A', 'B'}
            or any(not isinstance(v, list) or len(v) != 5 or len(set(v)) != 5 for v in anchors.values())):
        raise SchemaError('Each graph context needs five unique external movie IDs.')
    for rows in anchors.values():
        if any(canonical_id(i) != i or i in ids for i in rows):
            raise SchemaError('Graph anchors must exclude the whole evaluation catalog.')
    baseline = value['baseline']
    if (not isinstance(baseline, dict) or set(baseline) != {'A', 'B'}
            or any(not isinstance(rows, list) or len(rows) != 3 for rows in baseline.values())
            or any(len(row) != 20 or set(row) != set(ids) for rows in baseline.values() for row in rows)):
        raise SchemaError('Graph baseline needs three complete recorded rankings per profile.')
    return ids


def prepare_development(root, study):
    if (study.get('study_id') != 'disjoint-graph-bridge-v1' or study.get('baseline_weight') != .5
            or study.get('max_development_candidates') != 1 or study.get('max_qloo_requests') != 13
            or study.get('repeats') != 3 or study.get('max_profile_drop') != 0
            or study.get('minimum_mean_gain') != .02 or study.get('minimum_mean_gain_over_swapped') != .01
            or study.get('development_pair_ids') != ['mutation-01', 'mutation-03']):
        raise SchemaError('Unsupported frozen graph study.')
    bundle, baseline, contexts, _, _ = load_development(root, study)
    repair = {}
    for pair in bundle['pairs']:
        key = pair['pair_id']
        original = next(p for p in baseline['cases'] if p['pair_id'] == key)['rankings']['original']
        value = {'catalog': [{k: e[k] for k in ('entity_id', 'name', 'release_year')} for e in bundle['catalog']],
                 'anchors': contexts[key], 'baseline': original}
        validate_input(value)
        repair[key] = value
    if set(repair) != set(study['development_pair_ids']):
        raise SchemaError('All declared graph development cases are required.')
    return repair, bundle


def fuse_graph(baseline, graph, other=None):
    """Fixed equal ordinal fusion; neutral removes profile assignment."""
    if len(baseline) != 20 or len(set(baseline)) != 20 or len(graph) != 20 or set(graph) != set(baseline):
        raise SchemaError('Fusion requires complete equal catalogs.')
    if other is not None and (len(other) != 20 or set(other) != set(baseline)):
        raise SchemaError('Neutral fusion needs a complete counterpart.')
    local = {i: n for n, i in enumerate(baseline)}
    positions = {i: n for n, i in enumerate(graph)}
    neutral = {i: n for n, i in enumerate(other)} if other is not None else positions
    return sorted(baseline, key=lambda i: (.5 * local[i] + .25 * (positions[i] + neutral[i]), local[i], i))


def capture_graph(client, repair_inputs, study, *, sleeper=time.sleep, progress=None):
    """Only repair-side inputs are in scope here; never accept evaluator data."""
    if (client.max_requests != 13 or client.max_attempts != 1 or client.requests
            or list(repair_inputs) != study['development_pair_ids']):
        raise SchemaError('Graph capture requires a fresh thirteen-request/no-retry client and both cases.')
    ids = None
    for value in repair_inputs.values():
        current = validate_input(value)
        if ids is not None and current != ids:
            raise SchemaError('Development catalog changed between graph cases.')
        ids = current
    ledger = client.ledger
    plan = {'study': study, 'study_sha256': fingerprint(study), 'repair_inputs_sha256': fingerprint(repair_inputs),
            'created_utc': utc_now(), 'request_cap': 13, 'max_attempts': 1, 'minimum_interval_seconds': 1,
            'provider_quota': 'UNKNOWN', 'reserved_inputs_executed': 0, 'local_inference_calls': 0,
            'oracle_inputs_received': False}
    plan['plan_sha256'] = fingerprint(plan)
    ledger.write('graph-plan.json', plan)
    ledger.write('graph-inputs.json', repair_inputs)
    ledger.record('graph_plan_frozen', {'plan_sha256': plan['plan_sha256'], 'requests': 0})
    report = {'status': 'INCOMPLETE', 'error': None, 'cases': [], 'ci_gate': 'NOT_VALIDATED',
              'plan_sha256': plan['plan_sha256'], 'reserved_inputs_executed': 0, 'oracle_inputs_received': False}
    last = None
    def get(path, params):
        nonlocal last
        if last is not None:
            sleeper(max(0, 1 - (time.monotonic() - last)))
        last = time.monotonic()
        return client.get(path, params, cache=False)
    try:
        entities = parse_entities(get('/entities', {'entity_ids': ','.join(ids)}), insights=False, synthetic=client.synthetic)
        catalog = next(iter(repair_inputs.values()))['catalog']
        expected = {e['entity_id']: e for e in catalog}
        if (len(entities) != 20 or {e.entity_id for e in entities} != set(ids)
                or context_issues(entities, {'filter_type': 'urn:entity:movie', 'filters': {}}, set())
                or any(e.name != expected[e.entity_id]['name'] or e.metadata.get('release_year') != expected[e.entity_id]['release_year'] for e in entities)):
            raise SchemaError('Graph catalog lookup changed identity or coverage.')
        for pair_id, value in repair_inputs.items():
            graphs = {'A': [], 'B': []}
            for repeat in range(3):
                for label in (('A', 'B') if repeat % 2 == 0 else ('B', 'A')):
                    anchors = sorted(value['anchors'][label])
                    if progress: progress(pair_id, label, repeat + 1, client.requests + 1)
                    params = {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': 20,
                              'filter.results.entities': ','.join(ids), 'signal.interests.entities': ','.join(anchors)}
                    rows = parse_entities(get('/v2/insights', params), insights=True, synthetic=client.synthetic)
                    if (len(rows) != 20 or {e.entity_id for e in rows} != set(ids)
                            or context_issues(rows, {'filter_type': 'urn:entity:movie', 'filters': {}}, set(anchors))
                            or any(e.affinity is None for e in rows)):
                        raise SchemaError('Graph output is incomplete, untyped or lacks finite affinities.')
                    graphs[label].append([e.entity_id for e in rows])
                    ledger.record('graph_decision', {'pair_id': pair_id, 'profile': label, 'repeat': repeat + 1,
                        'anchor_sha256': fingerprint(anchors), 'ranked_entity_ids': graphs[label][-1],
                        'reference_received': False, 'query_signal_type': 'external-movies'})
            ranks = {'baseline': value['baseline'], **{v: {'A': [], 'B': []} for v in ('neutral_graph', 'qloo_graph', 'swapped_graph')}}
            for repeat in range(3):
                for label in ('A', 'B'):
                    other = 'B' if label == 'A' else 'A'
                    original = value['baseline'][label][repeat]
                    ranks['qloo_graph'][label].append(fuse_graph(original, graphs[label][repeat]))
                    ranks['swapped_graph'][label].append(fuse_graph(original, graphs[other][repeat]))
                    ranks['neutral_graph'][label].append(fuse_graph(original, graphs[label][repeat], graphs[other][repeat]))
            row = {'pair_id': pair_id, 'graphs': graphs, 'rankings': ranks}
            ledger.write('graph-' + pair_id + '.json', row)
            report['cases'].append(row)
        report['status'] = 'COMPLETE_GRAPH_CAPTURE'
    except AffinityQAError as exc:
        report['error'] = str(exc)
        ledger.record('stopped', {'reason': str(exc)})
    report.update(real_qloo_requests=ledger.live_requests, transport_attempts=client.requests)
    ledger.write('graph-capture.json', report)
    return report


def evaluate_graph(capture, evaluator_bundle, study, ledger):
    """Evaluator-only: called after the immutable repair decisions exist."""
    if capture['status'] != 'COMPLETE_GRAPH_CAPTURE' or [p['pair_id'] for p in capture['cases']] != study['development_pair_ids']:
        raise SchemaError('Incomplete graph captures cannot enter selection.')
    result = {'status': 'COMPLETE_GRAPH_DEVELOPMENT', 'candidate_gate': 'NOT_VALIDATED', 'ci_gate': 'NOT_VALIDATED',
              'cases': [], 'reserved_inputs_executed': 0, 'plan_sha256': capture['plan_sha256'],
              'real_qloo_requests': capture['real_qloo_requests'], 'local_inference_calls': 0,
              'interpretation': study['interpretation']}
    ids = [e['entity_id'] for e in evaluator_bundle['catalog']]
    for case in capture['cases']:
        ref = next(p for p in evaluator_bundle['pairs'] if p['pair_id'] == case['pair_id'])
        ranks = case['rankings']
        comparisons = {v: {label: profile_delta(ranks['qloo_graph'][label], ranks[v][label], ref['rankings'][label])
                          for label in ('A', 'B')} for v in ('baseline', 'neutral_graph', 'swapped_graph')}
        means = {v: min((a+b)/2 for a,b in product(*[
            [ndcg_at_k(c,r,5)-ndcg_at_k(b,r,5) for c,b,r in product(ranks['qloo_graph'][p],ranks[v][p],ref['rankings'][p])]
            for p in ('A','B')])) for v in comparisons}
        checks = {'reference_informative': calibrate_reference(ref['rankings'], ids, 5, 0)['informative'],
                  'no_profile_loss': all(comparisons[v][p]['min'] >= -1e-12 for v in ('baseline','neutral_graph') for p in ('A','B')),
                  'benefit_beyond_baseline': means['baseline'] >= .02,
                  'benefit_beyond_neutral': means['neutral_graph'] >= .02,
                  'beats_swapped_context': means['swapped_graph'] >= .01,
                  'stable': all(max_repeat_jitter(ranks['qloo_graph'][p],5) <= 1e-12 for p in ('A','B'))}
        result['cases'].append({'pair_id': case['pair_id'], 'comparisons': comparisons,
                               'minimum_pair_mean_delta': means, 'checks': checks})
    result['candidate_gate'] = 'PROMISING_DEVELOPMENT_CANDIDATE' if all(all(c['checks'].values()) for c in result['cases']) else 'REJECTED_DEVELOPMENT_CANDIDATE'
    ledger.write('graph-development.json', result)
    return result
