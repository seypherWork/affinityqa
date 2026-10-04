"""Capture held-out Qloo references and score already sealed model decisions.

No model is called, and no reserved reference can modify the earlier repair.
"""
from __future__ import annotations

from itertools import product
import hashlib
import json
from pathlib import Path
from statistics import median
import time

from .errors import AffinityQAError, SchemaError
from .evidence import fingerprint, utc_now
from .film_protocol import calibrate_reference, validate_suite
from .local_suite import validate_policy
from .metrics import ndcg_at_k, directional_alignment
from .models import context_issues, parse_entities, resolve_seed


def load_sealed_run(directory: Path, verification_path: Path):
    """Check original phase-two receipt before accepting decisions for new scoring."""
    verification = json.loads(verification_path.read_text(encoding='utf-8'))
    if verification.get('run_id') != directory.name or verification.get('status') != 'COMPLETE_LOCAL_SUITE':
        raise SchemaError('Verification receipt does not match the completed local run.')
    values = []
    for name in ('suite-report.json', 'frozen-policy.json', 'suite.json', 'agent-manifest.json', 'catalog.json'):
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
            raise SchemaError('Unsafe or missing sealed local evidence.')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != verification.get('run_artifact_sha256', {}).get(name):
            raise SchemaError('Recorded local evidence changed since its verification receipt.')
        values.append(json.loads(data.decode('utf-8')))
    prepare_plan(*values)
    return values


def prepare_plan(local, policy, suite, manifest, catalog):
    validate_suite(suite)
    validate_policy(policy, suite=suite, manifest=manifest, catalog=catalog)
    pairs = [p for p in suite['pairs'] if p['split'] == 'reserved']
    ids = [e['entity_id'] for e in catalog]
    if (local.get('status') != 'COMPLETE_LOCAL_SUITE' or local.get('source') != 'qloo-catalog+local-llm'
            or local.get('suite_sha256') != fingerprint(suite)
            or local.get('model_manifest_sha256') != fingerprint(manifest)
            or local.get('frozen_policy_sha256') != policy['policy_sha256']
            or fingerprint(local.get('development')) != policy['development_evidence_sha256']
            or fingerprint(local.get('invariance')) != policy['invariance_evidence_sha256']
            or local.get('local_inference_attempts') != 98 or local.get('denominator') != 6
            or [r.get('pair_id') for r in local.get('reserved', [])] != [p['id'] for p in pairs]
            or len(ids) != 20 or len(set(ids)) != 20 or suite['repeats'] != 3
            or any(len(p[label]) != 1 for p in pairs for label in ('A', 'B'))):
        raise SchemaError('Completed local suite, frozen policy and reserved denominator must match.')
    for row in local['reserved']:
        if row.get('policy_sha256') != policy['policy_sha256']:
            raise SchemaError('Reserved decision used a different policy.')
        for version in ('candidate', 'repaired'):
            ranks = row.get(version, {})
            if set(ranks) != {'A', 'B'} or any(len(ranks[label]) != 3 for label in ('A', 'B')):
                raise SchemaError('Every recorded version needs three decisions per profile.')
            for ranking in ranks['A'] + ranks['B']:
                if len(ranking) != len(ids) or set(ranking) != set(ids):
                    raise SchemaError('Stored decisions must be complete catalog permutations.')
    plan = {'schema_version': 1, 'created_utc': utc_now(), 'suite_sha256': fingerprint(suite),
            'local_report_sha256': fingerprint(local), 'policy_sha256': policy['policy_sha256'],
            'catalog_sha256': fingerprint(catalog), 'reserved_pair_ids': [p['id'] for p in pairs],
            'request_cap': 49, 'minimum_interval_seconds': 1, 'retry_attempts': 1,
            'event_quota': 'UNKNOWN_NOT_ASSUMED_UNLIMITED', 'model_calls': 0,
            'method': 'paired mean ordinal NDCG@5 delta across both profiles, all three agent repeats and all nine Qloo reference combinations',
            'delta_tolerance': 0, 'classification': 'improved if minimum delta > 0; regressed if maximum < 0; unchanged if all zero; otherwise mixed',
            'reference_rule': 'informative only when minimum cross-distance exceeds maximum observed within-distance plus suite practical tolerance',
            'denominator': 6, 'ci_gate': 'NOT_VALIDATED',
            'notice': 'Descriptive reserved evaluation; no new model tuning, absolute release threshold, population confidence or human-preference claim.'}
    plan['plan_sha256'] = fingerprint(plan)
    return plan


def compare_pair(decisions, reference, k):
    ranks = reference['rankings']
    deltas, candidate_scores, repaired_scores, alignment = [], [], [], []
    for repeat in range(3):
        for ref_a, ref_b in product(ranks['A'], ranks['B']):
            scores = {}
            for version in ('candidate', 'repaired'):
                scores[version] = (ndcg_at_k(decisions[version]['A'][repeat], ref_a, k)
                                   + ndcg_at_k(decisions[version]['B'][repeat], ref_b, k)) / 2
            candidate_scores.append(scores['candidate'])
            repaired_scores.append(scores['repaired'])
            deltas.append(scores['repaired'] - scores['candidate'])
            alignment.append(directional_alignment(decisions['repaired']['A'][repeat],
                decisions['repaired']['B'][repeat], ref_a, ref_b, k))
    def summary(values):
        return {'min': min(values), 'median': median(values), 'max': max(values)}
    informative = reference['calibration_policy']['informative']
    if not informative:
        outcome = 'INCONCLUSIVE_REFERENCE'
    elif min(deltas) > 0:
        outcome = 'OBSERVED_AGREEMENT_IMPROVEMENT'
    elif max(deltas) < 0:
        outcome = 'OBSERVED_AGREEMENT_REGRESSION'
    elif all(d == 0 for d in deltas):
        outcome = 'UNCHANGED'
    else:
        outcome = 'MIXED'
    return {'pair_id': decisions['pair_id'], 'outcome': outcome, 'comparisons': len(deltas),
            'candidate_agreement': summary(candidate_scores), 'repaired_agreement': summary(repaired_scores),
            'paired_agreement_delta': summary(deltas), 'repaired_own_profile_advantage': summary(alignment),
            'reference_informative': informative, 'ci_gate': 'NOT_VALIDATED'}


def capture_reserved(client, ledger, local, policy, suite, manifest, catalog, *, progress=None, sleeper=time.sleep):
    # Validation and a durable pre-analysis plan precede the first provider call.
    plan = prepare_plan(local, policy, suite, manifest, catalog)
    if client.max_attempts != 1 or client.max_requests > 49 or client.max_requests < 49:
        raise SchemaError('Reserved capture requires a fixed 49-request cap and no retry.')
    if not client.synthetic and ledger.source != 'qloo-live-reserved-evaluation':
        raise SchemaError('Live reserved capture needs explicit provenance.')
    for name, value in (('evaluation-plan.json', plan), ('local-decisions.json', local), ('suite.json', suite),
                        ('model-policy.json', policy), ('agent-manifest.json', manifest), ('catalog.json', catalog)):
        ledger.write(name, value)
    ledger.record('evaluation_plan_frozen', {'plan_sha256': plan['plan_sha256'], 'network_requests': 0})
    report = {'schema_version': 1, 'run_id': ledger.run_id, 'source': ledger.source,
              'status': 'INCOMPLETE', 'error': None, 'denominator': 6, 'cases': [],
              'plan_sha256': plan['plan_sha256'], 'local_report_sha256': fingerprint(local),
              'ci_gate': 'NOT_VALIDATED', 'new_model_calls': 0}
    ids = [e['entity_id'] for e in catalog]
    previous_request = None
    def get(path, params):
        nonlocal previous_request
        if previous_request is not None:
            sleeper(max(0, 1 - (time.monotonic() - previous_request)))
        previous_request = time.monotonic()
        return client.get(path, params, cache=False)
    try:
        entities = parse_entities(get('/entities', {'entity_ids': ','.join(ids)}), insights=False, synthetic=client.synthetic)
        if len(entities) != len(ids) or {e.entity_id for e in entities} != set(ids):
            raise SchemaError('Fixed catalog metadata is incomplete.')
        for entity in entities:
            expected = next(e for e in catalog if e['entity_id'] == entity.entity_id)
            if entity.name != expected['name'] or entity.metadata.get('release_year') != expected.get('release_year'):
                raise SchemaError('Catalog identity changed since the sealed model evaluation.')
        scenario = {'filter_type': 'urn:entity:movie', 'filters': {}}
        if context_issues(entities, scenario, set()):
            raise SchemaError('Fixed catalog type changed.')
        for pair in (p for p in suite['pairs'] if p['split'] == 'reserved'):
            if progress:
                progress(pair['id'], client.requests)
            personas = {}
            for label in ('A', 'B'):
                personas[label] = []
                for seed in pair[label]:
                    body = get('/search', {'query': seed['query'], 'types': seed['search_type'], 'take': 5})
                    entity = resolve_seed(seed, parse_entities(body, insights=False, synthetic=client.synthetic), synthetic=client.synthetic)
                    personas[label].append(entity.entity_id)
                    ledger.record('entity_resolution', {'pair_id': pair['id'], 'profile': label, 'entity': entity.as_dict()})
            if len(personas['A']) != 1 or len(personas['B']) != 1 or personas['A'] == personas['B']:
                raise SchemaError('Reserved profiles must differ by one resolved artist.')
            rankings = {'A': [], 'B': []}
            for repeat in range(3):
                for label in (('A', 'B') if repeat % 2 == 0 else ('B', 'A')):
                    rows = parse_entities(get('/v2/insights', {'filter.type': 'urn:entity:movie', 'bias.trends': 'off',
                        'take': len(ids), 'filter.results.entities': ','.join(ids),
                        'signal.interests.entities': ','.join(personas[label])}), insights=True, synthetic=client.synthetic)
                    if len(rows) != len(ids) or {e.entity_id for e in rows} != set(ids):
                        raise SchemaError('Reserved reference coverage is incomplete; remaining calls stopped.')
                    if context_issues(rows, scenario, set(personas['A'] + personas['B'])):
                        raise SchemaError('Reserved reference type/exclusion contract failed.')
                    rankings[label].append([e.entity_id for e in rows])
                    ledger.record('reference_repeat', {'pair_id': pair['id'], 'profile': label, 'repeat': repeat + 1})
            reference = {'pair_id': pair['id'], 'source': ledger.source, 'suite_sha256': fingerprint(suite),
                         'catalog_ids': ids, 'personas': personas, 'rankings': rankings,
                         'calibration_policy': calibrate_reference(rankings, ids, suite['top_k'], suite['practical_tolerance'])}
            reference['reference_sha256'] = fingerprint(reference)
            ledger.write('reference-' + pair['id'] + '.json', reference)
            decisions = next(r for r in local['reserved'] if r['pair_id'] == pair['id'])
            result = compare_pair(decisions, reference, suite['top_k'])
            result['reference_sha256'] = reference['reference_sha256']
            result['source'] = ledger.source
            ledger.write('comparison-' + pair['id'] + '.json', result)
            report['cases'].append(result)
        report['status'] = 'COMPLETE_SYNTHETIC' if client.synthetic else 'COMPLETE_RESERVED_COMPARISON'
    except AffinityQAError as exc:
        report['error'] = str(exc)
        ledger.record('stopped', {'reason': str(exc)})
    completed = {r['pair_id'] for r in report['cases']}
    report['missing_pair_ids'] = [p for p in plan['reserved_pair_ids'] if p not in completed]
    report['real_qloo_requests'] = ledger.live_requests
    report['transport_attempts'] = client.requests
    report['outcome_counts'] = {label: sum(r['outcome'] == label for r in report['cases']) for label in
        ('OBSERVED_AGREEMENT_IMPROVEMENT', 'OBSERVED_AGREEMENT_REGRESSION', 'UNCHANGED', 'MIXED', 'INCONCLUSIVE_REFERENCE')}
    report['report_sha256'] = fingerprint(report)
    ledger.write('reserved-comparison.json', report)
    return report
