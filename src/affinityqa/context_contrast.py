"""A bounded, recorded context swap; never a cultural-quality score.

The caller first verifies the complete receipt and its original source bindings.
Only consumed model inputs are compared: transport IDs/nonces are not inputs.
No IO, provider access or changes to the captured experiment occur here.
"""
from __future__ import annotations

import math

from .causal_evidence import inspect_decision
from .errors import SchemaError
from .evidence import fingerprint
from .metrics import rank_distance

SOURCE = 'saved-qloo-context-contrast'
EPSILON = 1e-12
CHECKS = ('saved_decisions_bound', 'requested_profile_fixed',
          'consumed_profile_fixed', 'task_fixed', 'catalog_fixed',
          'output_schema_fixed', 'tool_notice_fixed', 'model_manifest_fixed',
          'fresh_decisions', 'only_qloo_context_changed',
          'healthy_reference_fixed', 'healthy_variation_within_frozen_noise',
          'display_identities_unique')
METRICS = {'ranking_distance', 'recorded_noise_barrier',
           'maximum_after_healthy_distance', 'minimum_before_healthy_distance',
           'changed_top_five', 'top_five_order_changed',
           'recovery_verified', 'recovery_observed'}


def _need(value, message):
    if not value:
        raise SchemaError('Context contrast: ' + message)


def _same(left, right):
    return fingerprint(left) == fingerprint(right)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def validate_context_contrast(value, fault, *, before=None, after=None):
    """Closed public contract, including consistency of every numeric claim."""
    _need(type(value) is dict and set(value) == {
        'schema_version', 'source', 'status', 'behavioral_effect', 'checks', 'metrics'},
        'unexpected projection.')
    _need(type(value['schema_version']) is int and value['schema_version'] == 1
          and value['source'] == SOURCE, 'unexpected protocol.')
    status, effect = value['status'], value['behavioral_effect']
    checks, metrics = value['checks'], value['metrics']
    if fault != 'wrong-tool-profile':
        _need(status == 'NOT_APPLICABLE' and effect == 'NOT_EVALUATED'
              and checks is None and metrics is None, 'contrast is not applicable.')
        return value
    _need(type(checks) is dict and set(checks) == set(CHECKS)
          and all(type(v) is bool for v in checks.values()), 'incomplete fixed-input checks.')
    if status == 'CONFOUNDED':
        _need(not all(checks.values()) and effect == 'NOT_EVALUATED'
              and metrics is None, 'confounded input cannot claim an effect.')
        return value
    _need(status == 'CONTRAST_AVAILABLE' and all(checks.values())
          and type(metrics) is dict and set(metrics) == METRICS,
          'unverified contrast.')
    _need(all(_number(metrics[key]) for key in (
        'ranking_distance', 'recorded_noise_barrier',
        'maximum_after_healthy_distance', 'minimum_before_healthy_distance')),
        'invalid ordinal distances.')
    _need(type(metrics['changed_top_five']) is int
          and 0 <= metrics['changed_top_five'] <= 5
          and all(type(metrics[key]) is bool for key in (
              'top_five_order_changed', 'recovery_verified', 'recovery_observed')),
          'invalid displayed comparison.')
    _need((metrics['changed_top_five'] == 0 or metrics['top_five_order_changed'])
          and metrics['top_five_order_changed'] is (metrics['ranking_distance'] > 0),
          'changed films contradict their order or distance.')
    if before is not None or after is not None:
        def identities(rows):
            _need(type(rows) is list and len(rows) == 5, 'five displayed films required.')
            keys=[]
            for position,row in enumerate(rows,1):
                _need(type(row) is dict and set(row) == {'position','title','year'}
                      and type(row['position']) is int and row['position'] == position
                      and type(row['title']) is str and bool(row['title'].strip())
                      and type(row['year']) is int, 'invalid film display.')
                keys.append((row['title'],row['year']))
            _need(len(set(keys)) == 5, 'display identities are ambiguous.')
            return keys
        left,right=identities(before),identities(after)
        _need(metrics['changed_top_five'] == 5-len(set(left)&set(right))
              and metrics['top_five_order_changed'] is (left != right),
              'displayed films contradict the comparison.')
    threshold = metrics['recorded_noise_barrier'] + EPSILON
    observed = metrics['ranking_distance'] > threshold
    recovered = metrics['maximum_after_healthy_distance'] <= threshold
    _need(effect == ('OBSERVED_CHANGE' if observed else 'NO_OBSERVED_EFFECT')
          and metrics['recovery_verified'] is recovered
          and metrics['recovery_observed'] is (
              observed and recovered and metrics['minimum_before_healthy_distance'] > threshold),
          'effect or recovery contradicts its recorded bound.')
    return value


def _packet(packets, execution_id):
    matches = [p for p in packets if p['execution_id'] == execution_id]
    _need(len(matches) == 1, 'one execution packet is required.')
    return matches[0]


def _bound_replay(packet, captured):
    original = _packet(captured, packet['observation']['source_execution_id'])
    return (_same(packet['model_payload'], original['model_payload'])
            and _same(packet['response']['ranked_entity_ids'],
                      original['response']['ranked_entity_ids']))


def context_contrast(fault, requested_before, requested_after, before, after, replay_packets, captured_packets,
                     *, profiles, contexts, samples, healthy, plan, policy,
                     manifest, noise_barrier):
    """Compare verified replay decisions against the existing three fresh controls.

    A changed ranking can be observed without recovery. An unchanged ranking is
    a valid negative result. CONFOUNDED suppresses all metrics/positive claims.
    """
    result = {'schema_version': 1, 'source': SOURCE, 'status': 'NOT_APPLICABLE',
              'behavioral_effect': 'NOT_EVALUATED', 'checks': None, 'metrics': None}
    if fault != 'wrong-tool-profile':
        return validate_context_contrast(result, fault)
    try:
        _need(_number(noise_barrier) and _same(noise_barrier, policy['noise_barrier'])
              and policy['policy_sha256'] == fingerprint({k: v for k, v in policy.items()
                                                          if k != 'policy_sha256'})
              and plan['plan_sha256'] == fingerprint({k: v for k, v in plan.items()
                                                      if k != 'plan_sha256'}),
              'frozen policy or plan changed.')
        requested = requested_before
        for requested_phase,decision in ((requested_before,before),(requested_after,after)):
            inspect_decision(requested_phase, decision, replay_packets,
                             profiles=profiles, contexts=contexts, samples=samples)
        left = _packet(replay_packets, before['trace']['execution_id'])
        right = _packet(replay_packets, after['trace']['execution_id'])
        a, b = left['model_payload'], right['model_payload']
        source_bound = _bound_replay(left, captured_packets) and _bound_replay(right, captured_packets)
        _need(source_bound, 'replay decisions differ from captured decisions.')
        _need(type(healthy) is list and len(healthy) == 3
              and len({v['trace']['execution_id'] for v in healthy}) == 3,
              'three distinct recorded healthy decisions are required.')
        healthy_fixed = True
        for control in healthy:
            packet = _packet(captured_packets, control['trace']['execution_id'])
            observed = inspect_decision(packet['effective_request'], control, captured_packets,
                                        profiles=profiles, contexts=contexts, samples=samples)
            healthy_fixed = healthy_fixed and (
                not control['trace']['cache_hit'] and observed['diagnosis'] == 'NONE'
                and _same(packet['model_payload'], b)
                and _same(packet['effective_request']['profile'], requested['profile']))
        changed = {key for key in set(a) | set(b)
                   if key not in a or key not in b or not _same(a[key], b[key])}
        checks = {
            'saved_decisions_bound': source_bound,
            'requested_profile_fixed': _same(requested_before['profile'], requested_after['profile'])
                and _same(left['effective_request']['profile'], requested['profile'])
                and _same(right['effective_request']['profile'], requested['profile']),
            'consumed_profile_fixed': _same(a['profile'], b['profile'])
                and _same(a['profile'], requested['profile']),
            'task_fixed': _same(a['task'], b['task']),
            'catalog_fixed': _same(a['catalog'], b['catalog'])
                and policy['catalog_sha256'] == fingerprint(requested['catalog'])
                and plan['catalog_sha256'] == policy['catalog_sha256'],
            'output_schema_fixed': _same(a['output_schema'], b['output_schema']),
            'tool_notice_fixed': _same(a['tool_notice'], b['tool_notice']),
            'model_manifest_fixed': type(manifest) is dict and bool(manifest)
                and _same(plan['manifest'], manifest) and _same(policy['model_manifest'], manifest),
            'fresh_decisions': not before['trace']['cache_hit'] and not after['trace']['cache_hit']
                and left['execution_id'] != right['execution_id'],
            'only_qloo_context_changed': changed == {'provider_movie_context'},
            'healthy_reference_fixed': healthy_fixed,
            'healthy_variation_within_frozen_noise': all(
                rank_distance(x['ranking'],y['ranking'],5) <= noise_barrier + EPSILON
                for x in healthy for y in healthy),
            'display_identities_unique': len({(row['name'],row['release_year'])
                for row in requested['catalog']}) == len(requested['catalog']),
        }
        result.update(status='CONFOUNDED', checks=checks)
        if all(checks.values()):
            old, new = before['ranking'], after['ranking']
            distance = rank_distance(old, new, 5)
            maximum_after = max(rank_distance(new, h['ranking'], 5) for h in healthy)
            minimum_before = min(rank_distance(old, h['ranking'], 5) for h in healthy)
            observed = distance > noise_barrier + EPSILON
            recovered = maximum_after <= noise_barrier + EPSILON
            result.update(status='CONTRAST_AVAILABLE',
                behavioral_effect='OBSERVED_CHANGE' if observed else 'NO_OBSERVED_EFFECT',
                metrics={'ranking_distance': distance, 'recorded_noise_barrier': noise_barrier,
                    'maximum_after_healthy_distance': maximum_after,
                    'minimum_before_healthy_distance': minimum_before,
                    'changed_top_five': 5 - len(set(old[:5]) & set(new[:5])),
                    'top_five_order_changed': old[:5] != new[:5],
                    'recovery_verified': recovered,
                    'recovery_observed': observed and recovered and minimum_before > noise_barrier + EPSILON})
        return validate_context_contrast(result, fault)
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        raise SchemaError('Context contrast: malformed evidence; no effect attributed.') from None
