"""Synthetic diagnostic contracts, never provider calls or empirical evidence.

Stage this new file in the reviewed candidate's tests/ before running it.
The public fixture's live_network_request flag is data for a parser contract;
it does not make these fabricated samples real network observations.
"""
import copy
import math
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'src')]

import test_causal_agent as fixture_module
from test_causal_agent import FakeEngine, FakeLedger
from affinityqa.causal_agent import (
    CausalMovieSession, ExecutionRecorder, ToolContextMovieAgent, diagnose,
    make_request, profile_hash,
)
from affinityqa.causal_evidence import (
    inspect_decision, plan_repair, session_state, verify_repair_transition,
)
from affinityqa.evidence import fingerprint
from affinityqa.errors import SchemaError


CHECKS = {
    'raw_qloo_request_bound', 'raw_qloo_response_bound',
    'context_projection_bound', 'model_payload_bound', 'observed_trace_bound',
}
EXPECTED = {
    'cache-omits-profile': ('CACHE_OMITS_PROFILE', 'set-profile-cache',
                            'cache_scope', 'task', 'profile'),
    'stale-profile': ('STALE_PROFILE', 'restore-request-profile',
                      'request_profile_current', False, True),
    'wrong-tool-profile': ('WRONG_TOOL_PROFILE', 'bind-request-tool',
                           'qloo_profile_current', False, True),
}


class CanonicalEngine(FakeEngine):
    """The public deterministic fixture with the actual twenty-index schema."""

    def rank(self, request):
        count = len(request['catalog'])
        schema = {
            'type': 'object',
            'properties': {'ordered_catalog_indices': {
                'type': 'array',
                'items': {'type': 'integer', 'enum': list(range(count))},
                'minItems': count, 'maxItems': count,
            }},
            'required': ['ordered_catalog_indices'],
            'additionalProperties': False,
        }
        self.calls += 1
        self.last_input = self.adapter.decision_input(request, schema)
        ids = [row['entity_id'] for row in request['catalog']]
        ranking = [ids[row['catalog_index']]
                   for row in self.last_input['provider_movie_context']]
        self.observations.append({
            'call': self.calls, 'input_sha256': fingerprint(self.last_input),
            'output_sha256': fingerprint(ranking),
        })
        return {'schema_version': 1, 'request_id': request['request_id'],
                'ranked_entity_ids': ranking}


class CausalEvidenceTests(unittest.TestCase):
    def setUp(self):
        # Do not import this TestCase into the local module namespace: unittest
        # discovery should count only the new diagnostic tests here.
        fixture = fixture_module.CausalAgentTests()
        fixture.setUp()
        self.fixture = fixture
        self.profiles = dict(zip(('A', 'B'), fixture.profiles))
        self.contexts = copy.deepcopy(fixture.contexts)
        self.requests = dict(zip(('A', 'B'), fixture.requests))
        self.samples = {
            self.contexts[profile_hash(profile)]['sample_sha256']:
                fixture.raw(profile, index)
            for index, profile in enumerate(fixture.profiles)
        }

    def session(self, fault=None, contexts=None):
        engine, ledger = CanonicalEngine(), FakeLedger()
        session = CausalMovieSession(
            ExecutionRecorder(engine, ledger),
            self.contexts if contexts is None else contexts, fault=fault,
        )
        return session, engine, ledger

    def inspect(self, request, decision, ledger, **changes):
        values = {
            'profiles': self.profiles, 'contexts': self.contexts,
            'samples': self.samples,
        }
        values.update(changes)
        packets = values.pop('packets', list(ledger.files.values()))
        return inspect_decision(
            copy.deepcopy(request), copy.deepcopy(decision),
            copy.deepcopy(packets), **copy.deepcopy(values),
        )

    def healthy(self):
        session, engine, ledger = self.session()
        decision = session.rank(self.requests['A'])
        return session, engine, ledger, decision

    def assert_observation(self, observation, diagnosis='NONE', operation='none'):
        self.assertEqual(set(observation), {
            'diagnosis', 'operation', 'requested_profile_sha256',
            'tool_profile_sha256', 'checks',
        })
        self.assertEqual((observation['diagnosis'], observation['operation']),
                         (diagnosis, operation))
        self.assertEqual(set(observation['checks']), CHECKS)
        self.assertTrue(all(value is True
                            for value in observation['checks'].values()))

    @staticmethod
    def rehash_payload(packet, decision):
        digest = fingerprint(packet['model_payload'])
        packet['observation']['input_sha256'] = digest
        decision['trace']['payload_sha256'] = digest

    def test_healthy_fresh_profiles_have_complete_source_checks(self):
        session, _, ledger = self.session()
        for label in ('A', 'B'):
            decision = session.rank(self.requests[label])
            observation = self.inspect(self.requests[label], decision, ledger)
            self.assert_observation(observation)
            self.assertEqual(observation['requested_profile_sha256'],
                             profile_hash(self.profiles[label]))
            self.assertEqual(observation['tool_profile_sha256'],
                             profile_hash(self.profiles[label]))

    def test_all_three_faults_in_both_orders_are_observed_not_labelled(self):
        for fault, expected in EXPECTED.items():
            for lead, victim in (('A', 'B'), ('B', 'A')):
                with self.subTest(fault=fault, lead=lead):
                    session, _, ledger = self.session(fault)
                    session.rank(self.requests[lead])
                    decision = session.rank(self.requests[victim])
                    self.assertNotIn('fault', decision['trace'])
                    self.assertNotIn('diagnosis', decision['trace'])
                    observation = self.inspect(self.requests[victim], decision, ledger)
                    self.assert_observation(observation, *expected[:2])
                    self.assertEqual(observation['requested_profile_sha256'],
                                     profile_hash(self.profiles[victim]))
                    self.assertEqual(observation['tool_profile_sha256'],
                                     profile_hash(self.profiles[lead]))

    def test_all_repairs_require_exact_setting_then_restore_both_profiles(self):
        for fault, expected in EXPECTED.items():
            for order in (('A', 'B'), ('B', 'A')):
                with self.subTest(fault=fault, order=order):
                    session, _, ledger = self.session(fault)
                    session.rank(self.requests[order[0]])
                    decision = session.rank(self.requests[order[1]])
                    observation = self.inspect(self.requests[order[1]], decision, ledger)
                    before = session_state(session)
                    plan = plan_repair(observation, before)
                    self.assertEqual(set(plan),
                                     {'diagnosis', 'operation', 'setting', 'before', 'after'})
                    self.assertEqual((plan['diagnosis'], plan['operation'],
                                      plan['setting'], plan['before'], plan['after']), expected)
                    session.apply({'diagnosis': observation['diagnosis'],
                                   'operation': observation['operation']})
                    after = session_state(session)
                    self.assertEqual(after['patch_count'], 1)
                    self.assertEqual(after['cache_entries'], 0)
                    self.assertIsNone(verify_repair_transition(plan, before, after))
                    for label in order:
                        repaired = session.rank(self.requests[label])
                        self.assert_observation(self.inspect(self.requests[label], repaired, ledger))

    def test_legitimate_cache_accepts_new_nonce_without_new_execution(self):
        session, engine, ledger, first = self.healthy()
        request = make_request(
            self.requests['A']['task'], self.fixture.catalog,
            self.profiles['A'], self.contexts[profile_hash(self.profiles['A'])],
            'synthetic-equivalent-new-nonce',
        )
        self.assertNotEqual(request['request_id'], self.requests['A']['request_id'])
        cached = session.rank(request)
        self.assertTrue(cached['trace']['cache_hit'])
        self.assertEqual(cached['trace']['execution_id'], first['trace']['execution_id'])
        self.assertEqual(engine.calls, 1)
        self.assert_observation(self.inspect(request, cached, ledger))

    def test_inspection_does_not_mutate_inputs(self):
        _, _, ledger, decision = self.healthy()
        args = [copy.deepcopy(self.requests['A']), copy.deepcopy(decision),
                copy.deepcopy(list(ledger.files.values()))]
        kwargs = copy.deepcopy({'profiles': self.profiles,
                                'contexts': self.contexts, 'samples': self.samples})
        original = copy.deepcopy((args, kwargs))
        inspect_decision(*args, **kwargs)
        self.assertEqual((args, kwargs), original)

    def test_rehashed_affinity_payload_with_old_none_trace_is_rejected(self):
        _, _, ledger, decision = self.healthy()
        packets = copy.deepcopy(list(ledger.files.values()))
        packets[0]['model_payload']['provider_movie_context'][0]['affinity'] = .123
        self.rehash_payload(packets[0], decision)
        self.assertEqual(diagnose(decision['trace'])['diagnosis'], 'NONE')
        with self.assertRaises(SchemaError):
            self.inspect(self.requests['A'], decision, ledger, packets=packets)

    def test_rehashed_vector_index_order_omission_and_duplicates_are_rejected(self):
        for mode in ('index', 'order', 'missing', 'duplicate', 'bool-index'):
            with self.subTest(mode=mode):
                _, _, ledger, decision = self.healthy()
                packets = copy.deepcopy(list(ledger.files.values()))
                rows = packets[0]['model_payload']['provider_movie_context']
                if mode == 'index': rows[0]['catalog_index'] = 19
                elif mode == 'order': rows.reverse()
                elif mode == 'missing': rows.pop()
                elif mode == 'duplicate': rows[-1] = copy.deepcopy(rows[0])
                else: rows[0]['catalog_index'] = True
                self.rehash_payload(packets[0], decision)
                self.assertEqual(diagnose(decision['trace'])['diagnosis'], 'NONE')
                with self.assertRaises(SchemaError):
                    self.inspect(self.requests['A'], decision, ledger, packets=packets)

    def test_rehashed_model_catalog_schema_and_profile_are_rejected(self):
        for mode in ('catalog-year', 'catalog-name', 'schema', 'profile'):
            with self.subTest(mode=mode):
                _, _, ledger, decision = self.healthy()
                packets = copy.deepcopy(list(ledger.files.values()))
                payload = packets[0]['model_payload']
                if mode == 'catalog-year': payload['catalog'][0]['release_year'] = 1999
                elif mode == 'catalog-name': payload['catalog'][0]['name'] = 'Unbound synthetic title'
                elif mode == 'schema': payload['output_schema'] = {'type': 'object'}
                else: payload['profile'] = copy.deepcopy(self.profiles['B'])
                self.rehash_payload(packets[0], decision)
                with self.assertRaises(SchemaError):
                    self.inspect(self.requests['A'], decision, ledger, packets=packets)

    def test_rehashed_context_and_consistent_packet_cannot_replace_raw_source(self):
        for mode in ('affinity', 'order'):
            with self.subTest(mode=mode):
                contexts = copy.deepcopy(self.contexts)
                context = contexts[profile_hash(self.profiles['A'])]
                if mode == 'affinity': context['ranked_entities'][0]['affinity'] = .123
                else: context['ranked_entities'].reverse()
                context['context_sha256'] = fingerprint({
                    key: value for key, value in context.items() if key != 'context_sha256'
                })
                request = make_request(self.requests['A']['task'], self.fixture.catalog,
                                       self.profiles['A'], context, 'rehash-context')
                session, _, ledger = self.session(contexts=contexts)
                decision = session.rank(request)
                self.assertEqual(diagnose(decision['trace'])['diagnosis'], 'NONE')
                with self.assertRaises(SchemaError):
                    self.inspect(request, decision, ledger, contexts=contexts)

    def test_wrong_raw_profile_request_status_or_response_hash_is_rejected(self):
        for mode in ('profile', 'host', 'path', 'take', 'status', 'attempt', 'response-hash'):
            with self.subTest(mode=mode):
                _, _, ledger, decision = self.healthy()
                samples = copy.deepcopy(self.samples)
                sample = samples[self.contexts[profile_hash(self.profiles['A'])]['sample_sha256']]
                if mode == 'profile': sample['request']['params']['signal.interests.entities'] = self.profiles['B']['entity_id']
                elif mode == 'host': sample['request']['host'] = 'https://synthetic.invalid'
                elif mode == 'path': sample['request']['path'] = '/search'
                elif mode == 'take': sample['request']['params']['take'] = True
                elif mode == 'status': sample['status'] = 500
                elif mode == 'attempt': sample['attempt'] = 2
                else: sample['response_sha256'] = '0' * 64
                with self.assertRaises(SchemaError):
                    self.inspect(self.requests['A'], decision, ledger, samples=samples)

    def test_raw_response_identity_coverage_and_numeric_types_are_rejected(self):
        for mode in ('missing', 'duplicate', 'name', 'year', 'bool', 'nan'):
            with self.subTest(mode=mode):
                _, _, ledger, decision = self.healthy()
                samples = copy.deepcopy(self.samples)
                sample = samples[self.contexts[profile_hash(self.profiles['A'])]['sample_sha256']]
                rows = sample['response']['results']['entities']
                if mode == 'missing': rows.pop()
                elif mode == 'duplicate': rows[-1] = copy.deepcopy(rows[0])
                elif mode == 'name': rows[0]['name'] = 'Different synthetic name'
                elif mode == 'year': rows[0]['properties']['release_year'] = True
                elif mode == 'bool': rows[0]['query']['affinity'] = True
                else: rows[0]['query']['affinity'] = math.nan
                if mode != 'nan': sample['response_sha256'] = fingerprint(sample['response'])
                with self.assertRaises(SchemaError):
                    self.inspect(self.requests['A'], decision, ledger, samples=samples)

    def test_missing_sample_or_context_cannot_count_as_verified(self):
        _, _, ledger, decision = self.healthy()
        for changes in ({'samples': {}}, {'contexts': {}}):
            with self.subTest(changes=list(changes)), self.assertRaises(SchemaError):
                self.inspect(self.requests['A'], decision, ledger, **changes)

    def test_duplicate_missing_or_unselected_execution_packet_is_rejected(self):
        _, _, ledger, decision = self.healthy()
        packet = copy.deepcopy(next(iter(ledger.files.values())))
        other = copy.deepcopy(packet)
        other['execution_id'] = 'synthetic-other-run/1'
        for packets in ([], [packet, copy.deepcopy(packet)], [other]):
            with self.subTest(count=len(packets)), self.assertRaises(SchemaError):
                self.inspect(self.requests['A'], decision, ledger, packets=packets)

    def test_observation_and_response_request_bindings_are_rejected(self):
        for mode in ('input', 'output', 'call', 'response-request'):
            with self.subTest(mode=mode):
                _, _, ledger, decision = self.healthy()
                packets = copy.deepcopy(list(ledger.files.values()))
                packet = packets[0]
                if mode == 'input': packet['observation']['input_sha256'] = '0' * 64
                elif mode == 'output': packet['observation']['output_sha256'] = '0' * 64
                elif mode == 'call': packet['observation']['call'] = True
                else: packet['response']['request_id'] = self.requests['B']['request_id']
                with self.assertRaises(SchemaError):
                    self.inspect(self.requests['A'], decision, ledger, packets=packets)

    def test_invalid_rankings_remain_rejected_after_hash_updates(self):
        for mode in ('short', 'duplicate', 'outside', 'bool'):
            with self.subTest(mode=mode):
                _, _, ledger, decision = self.healthy()
                packets = copy.deepcopy(list(ledger.files.values()))
                ranking = packets[0]['response']['ranked_entity_ids']
                if mode == 'short': ranking.pop()
                elif mode == 'duplicate': ranking[-1] = ranking[0]
                elif mode == 'outside': ranking[-1] = 'ffffffff-ffff-4fff-8fff-ffffffffffff'
                else: ranking[-1] = True
                decision['ranking'] = copy.deepcopy(ranking)
                digest = fingerprint(ranking)
                packets[0]['observation']['output_sha256'] = digest
                decision['trace']['output_sha256'] = digest
                with self.assertRaises(SchemaError):
                    self.inspect(self.requests['A'], decision, ledger, packets=packets)

    def test_trace_cannot_misstate_actual_packet_boundary(self):
        for key, value in (
            ('tool_profile_sha256', profile_hash({'entity_id': 'bbbbbbbb-0000-4000-8000-000000000001', 'name': 'Unit artist 1', 'type': 'urn:entity:artist'})),
            ('payload_sha256', '0' * 64), ('context_response_sha256', '0' * 64),
            ('output_sha256', '0' * 64), ('cache_hit', 1),
        ):
            with self.subTest(key=key):
                _, _, ledger, decision = self.healthy()
                decision['trace'][key] = value
                with self.assertRaises(SchemaError):
                    self.inspect(self.requests['A'], decision, ledger)

    def test_session_state_captures_actual_settings_and_counts(self):
        session, _, _, _ = self.healthy()
        self.assertEqual(session_state(session), {
            'cache_scope': 'profile', 'request_profile_current': True,
            'qloo_profile_current': True, 'patch_count': 0, 'cache_entries': 1,
        })

    def test_none_plan_and_transition_preserve_existing_healthy_cache(self):
        session, engine, ledger, decision = self.healthy()
        observation = self.inspect(self.requests['A'], decision, ledger)
        before = session_state(session)
        plan = plan_repair(observation, before)
        self.assertEqual(plan, {'diagnosis': 'NONE', 'operation': 'none',
                                'setting': 'none', 'before': None, 'after': None})
        patch = session.apply({'diagnosis': 'NONE', 'operation': 'none'})
        self.assertFalse(patch['applied'])
        self.assertEqual(engine.calls, 1)
        self.assertEqual(session_state(session), before)
        self.assertIsNone(verify_repair_transition(plan, before, session_state(session)))

    def test_unsupported_or_contradictory_observation_never_plans_a_patch(self):
        session, _, ledger, decision = self.healthy()
        observation = self.inspect(self.requests['A'], decision, ledger)
        for updates in (
            {'diagnosis': 'UNSUPPORTED', 'operation': 'none'},
            {'diagnosis': 'STALE_PROFILE', 'operation': 'bind-request-tool'},
            {'diagnosis': 'NONE', 'operation': 'restore-request-profile'},
        ):
            with self.subTest(updates=updates), self.assertRaises(SchemaError):
                plan_repair({**observation, **updates}, session_state(session))

    def test_multiple_fault_settings_and_already_patched_state_are_rejected(self):
        session, _, ledger = self.session('stale-profile')
        session.rank(self.requests['A'])
        decision = session.rank(self.requests['B'])
        observation = self.inspect(self.requests['B'], decision, ledger)
        before = session_state(session)
        for updates in ({'cache_scope': 'task'}, {'qloo_profile_current': False},
                        {'patch_count': 1}):
            with self.subTest(updates=updates), self.assertRaises(SchemaError):
                plan_repair(observation, {**before, **updates})

    def test_transition_rejects_wrong_setting_uncleared_cache_or_patch_count(self):
        session, _, ledger = self.session('stale-profile')
        session.rank(self.requests['A'])
        decision = session.rank(self.requests['B'])
        observation = self.inspect(self.requests['B'], decision, ledger)
        before = session_state(session)
        plan = plan_repair(observation, before)
        correct = {**before, 'request_profile_current': True,
                   'cache_entries': 0, 'patch_count': 1}
        for updates in ({'request_profile_current': False}, {'cache_entries': 1},
                        {'patch_count': 0}, {'patch_count': 2},
                        {'qloo_profile_current': False}, {'cache_scope': 'task'}):
            with self.subTest(updates=updates), self.assertRaises(SchemaError):
                verify_repair_transition(plan, before, {**correct, **updates})

    def test_none_transition_rejects_any_setting_or_count_change(self):
        session, _, ledger, decision = self.healthy()
        before = session_state(session)
        plan = plan_repair(self.inspect(self.requests['A'], decision, ledger), before)
        for key, value in (('cache_scope', 'task'), ('request_profile_current', False),
                           ('qloo_profile_current', False), ('patch_count', 1),
                           ('cache_entries', 0)):
            with self.subTest(key=key), self.assertRaises(SchemaError):
                verify_repair_transition(plan, before, {**before, key: value})

    def test_malformed_state_and_false_evidence_checks_are_rejected(self):
        session, _, ledger, decision = self.healthy()
        observation = self.inspect(self.requests['A'], decision, ledger)
        before = session_state(session)
        states = [
            {**before, 'patch_count': True}, {**before, 'cache_entries': -1},
            {**before, 'request_profile_current': 1},
            {**before, 'cache_scope': 'unknown'}, {**before, 'extra': 'no'},
        ]
        for state in states:
            with self.subTest(state=state), self.assertRaises(SchemaError):
                plan_repair(observation, state)
        for checks in ({}, {**observation['checks'], 'raw_qloo_request_bound': False},
                       {key: 1 for key in CHECKS}):
            with self.subTest(checks=checks), self.assertRaises(SchemaError):
                plan_repair({**observation, 'checks': checks}, before)


    def test_healthy_none_after_one_completed_repair_is_a_valid_noop(self):
        session, _, ledger = self.session('stale-profile')
        session.rank(self.requests['A'])
        broken = session.rank(self.requests['B'])
        observation = self.inspect(self.requests['B'], broken, ledger)
        before = session_state(session)
        plan = plan_repair(observation, before)
        session.apply({'diagnosis': observation['diagnosis'],
                       'operation': observation['operation']})
        self.assertIsNone(verify_repair_transition(plan, before, session_state(session)))
        for label in ('A', 'B'):
            current = session.rank(self.requests[label])
        healthy = self.inspect(self.requests['B'], current, ledger)
        state = session_state(session)
        self.assertEqual(state['patch_count'], 1)
        noop = plan_repair(healthy, state)
        self.assertEqual(noop, {'diagnosis': 'NONE', 'operation': 'none',
                               'setting': 'none', 'before': None, 'after': None})
        self.assertIsNone(verify_repair_transition(noop, state, copy.deepcopy(state)))

    def test_transition_itself_rejects_multiple_faulty_preconditions(self):
        session, _, ledger = self.session('stale-profile')
        session.rank(self.requests['A'])
        broken = session.rank(self.requests['B'])
        observation = self.inspect(self.requests['B'], broken, ledger)
        before = session_state(session)
        plan = plan_repair(observation, before)
        for extra_fault in ({'cache_scope': 'task'}, {'qloo_profile_current': False}):
            bad_before = {**before, **extra_fault}
            after = {**bad_before, 'request_profile_current': True,
                     'patch_count': 1, 'cache_entries': 0}
            with self.subTest(extra_fault=extra_fault), self.assertRaises(SchemaError):
                verify_repair_transition(plan, bad_before, after)


if __name__ == '__main__':
    unittest.main()
