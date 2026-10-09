"""Synthetic recorder/cache audit; network denied and no cultural conclusions."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from test_causal_agent import FakeLedger
from test_discovery_agent import Opener, TEST_SECRET, fixture_request
from affinityqa.cinema_discoveries import cache_key, make_request, qloo_cache_key
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent
from affinityqa.cinema_discovery_session import DiscoverySession
from affinityqa.cinema_discovery_verify import verify_packet, verify_complete_packet_set
from affinityqa.errors import SchemaError
from affinityqa.agents import AgentError
from affinityqa.evidence import fingerprint
from affinityqa.cinema_discovery_agent import model_manifest
from affinityqa.groq_agent import ENDPOINT
from affinityqa.remote_pacing import PacedRemoteAgent, pacing_policy


def sample_for(request):
    context, catalog = request['tool_context'], request['catalog']
    metadata = {r['entity_id']: r for r in catalog}
    body = {'success': True, 'results': {'entities': [
        {'entity_id': row['entity_id'], 'name': metadata[row['entity_id']]['name'], 'types': ['urn:entity:movie'],
         'properties': {'release_year': metadata[row['entity_id']]['release_year']}, 'query': {'affinity': row['affinity']}}
        for row in context['ranked_entities']]}}
    f = request['preferences']['favorite_entity_ids']
    d = sorted(r['entity_id'] for r in catalog if r['entity_id'] not in f)
    raw_request = {'method': 'GET', 'host': 'https://hackathon.api.qloo.com', 'path': '/v2/insights',
                   'params': {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': len(d),
                              'signal.interests.entities': ','.join(sorted([request['profile']['entity_id'], *f])),
                              'filter.results.entities': ','.join(d)}}
    sample = {'fixture_provenance': 'SYNTHETIC_UNIT_ONLY_NOT_LIVE_EVIDENCE', 'request': raw_request,
              'status': 200, 'attempt': 1, 'live_network_request': True,
              'response': body, 'response_sha256': fingerprint(body)}
    assert fingerprint(sample) == context['sample_sha256']
    return sample


class DiscoverySessionTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Denied network in synthetic recorder tests'))
            guard.start()
            self.addCleanup(guard.stop)

    def session(self, requests=None, *, opener=None, paced=False):
        requests = requests or [fixture_request(1)]
        engine = DiscoveryMovieAgent(TEST_SECRET, max_calls=2, _test_opener=opener or Opener())
        contexts = {qloo_cache_key(r['profile'], r['catalog'], r['preferences']): r['tool_context'] for r in requests}
        samples = {r['tool_context']['sample_sha256']: sample_for(r) for r in requests}
        ledger = FakeLedger()
        operator = PacedRemoteAgent(engine, pacing_policy(0.0), ledger) if paced else engine
        return DiscoverySession(requests[0]['catalog'], operator, ledger, contexts, samples), engine, ledger

    def test_recorded_execution_and_nonce_only_cache_reuse_are_explicit(self):
        request = fixture_request()
        session, engine, ledger = self.session([request])
        first = session.rank(request)
        second_request = make_request(request['catalog'], request['profile'], request['tool_context'],
                                      request['preferences'], 'different-nonce')
        cached = session.rank(second_request)
        self.assertEqual(engine.calls, 1)
        self.assertFalse(first['trace']['cache_hit'])
        self.assertTrue(cached['trace']['cache_hit'])
        self.assertNotEqual(cached['trace']['requested_request_sha256'], cached['trace']['execution_request_sha256'])
        self.assertEqual(first['ranking'], cached['ranking'])
        self.assertEqual(first['delivery'], cached['delivery'])
        self.assertEqual(len(ledger.files), 1)
        packet = ledger.files['discovery-execution-001.json']
        verified = verify_packet(packet, engine.manifest, engine.source, sample_for(request),
                                 request['tool_context']['sample_sha256'])
        expected = [r['entity_id'] for r in reversed(request['catalog'][1:19])][:5]
        self.assertEqual(verified['delivered_entity_ids'], expected)
        self.assertEqual(verified['baseline_delivered_entity_ids'], expected)
        self.assertFalse(verified['quality_validated'])
        self.assertFalse(verified['external_service_attested'])
        for name in ('profile_sha256', 'signal_sha256', 'preferences_sha256', 'intent_sha256'):
            self.assertEqual(first['trace']['requested_' + name], first['trace']['transmitted_' + name])

    def test_changed_exclusion_cannot_reuse_model_output_but_keeps_tool_context(self):
        request = fixture_request()
        session, engine, ledger = self.session([request])
        a = session.rank(request)
        prefs = copy.deepcopy(request['preferences'])
        prefs['excluded_entity_ids'] = [request['catalog'][18]['entity_id']]
        changed = make_request(request['catalog'], request['profile'], request['tool_context'], prefs, 'changed-x')
        b = session.rank(changed)
        self.assertEqual(engine.calls, 2)
        self.assertFalse(b['trace']['cache_hit'])
        self.assertNotEqual(a['delivery']['delivered_entity_ids'], b['delivery']['delivered_entity_ids'])
        self.assertEqual(a['trace']['tool_signal_sha256'], b['trace']['tool_signal_sha256'])
        self.assertNotEqual(a['trace']['requested_intent_sha256'], b['trace']['requested_intent_sha256'])
        self.assertEqual(len(ledger.files), 2)

    def test_changed_favorites_use_distinct_actual_tool_bundle_and_model_execution(self):
        a, b = fixture_request(1), fixture_request(5)
        session, engine, ledger = self.session([a, b])
        aa, bb = session.rank(a), session.rank(b)
        self.assertEqual(engine.calls, 2)
        self.assertEqual(len(aa['ranking']), 19)
        self.assertEqual(len(bb['ranking']), 15)
        self.assertNotEqual(aa['trace']['tool_signal_sha256'], bb['trace']['tool_signal_sha256'])
        self.assertEqual(len(ledger.files), 2)

    def test_rehashed_or_cross_intent_cache_tampering_is_rejected_and_stops_session(self):
        for damage in ('response', 'execution-id', 'cross-intent'):
            with self.subTest(damage=damage):
                request = fixture_request()
                session, engine, ledger = self.session([request])
                session.rank(request)
                key = cache_key(request, engine.manifest)
                if damage == 'response':
                    session.cache[key]['response']['ranked_entity_ids'].reverse()
                elif damage == 'execution-id':
                    session.cache[key]['execution_id'] = 'different-run/1'
                else:
                    prefs = copy.deepcopy(request['preferences'])
                    prefs['excluded_entity_ids'] = []
                    changed = make_request(request['catalog'], request['profile'], request['tool_context'], prefs, 'changed-x')
                    bad_key = cache_key(changed, engine.manifest)
                    session.cache[bad_key] = copy.deepcopy(session.cache[key])
                    session._packet_hashes[bad_key] = fingerprint(session.cache[bad_key])
                    request = changed
                with self.assertRaises(SchemaError):
                    session.rank(request)
                self.assertEqual(engine.calls, 1)
                with self.assertRaisesRegex(SchemaError, 'previous failure'):
                    session.rank(fixture_request())

    def test_packet_audit_rejects_rehashed_wrong_signal_seed_usage_and_payload(self):
        request = fixture_request()
        session, engine, ledger = self.session([request])
        session.rank(request)
        packet = ledger.files['discovery-execution-001.json']
        changes = [
            lambda p: p['model_payload'].update(signal_sha256='0' * 64),
            lambda p: p['effective_request'].update(signal_sha256='0' * 64),
            lambda p: p['observation'].update(input_sha256='0' * 64),
            lambda p: p['observation'].update(raw_discovery_count=20),
            lambda p: p['observation']['provider_envelope']['choice']['ordered_catalog_indices'].__setitem__('rank_01', 0),
            lambda p: p['observation']['provider_envelope']['usage'].update(total_tokens=42),
            lambda p: p['observation']['provider_envelope'].update(schema_version=1),
            lambda p: p['observation'].update(model_revision_attested=True),
        ]
        for change in changes:
            damaged = copy.deepcopy(packet)
            change(damaged)
            if damaged['model_payload'] != packet['model_payload']:
                damaged['observation']['input_sha256'] = fingerprint(damaged['model_payload'])
            damaged['observation']['provider_envelope_sha256'] = fingerprint(damaged['observation']['provider_envelope'])
            with self.assertRaises(SchemaError):
                verify_packet(damaged, engine.manifest, engine.source, sample_for(request), request['tool_context']['sample_sha256'])

    def test_missing_or_changed_sample_is_rejected_before_inference(self):
        request = fixture_request()
        engine = DiscoveryMovieAgent(TEST_SECRET, _test_opener=Opener())
        contexts = {qloo_cache_key(request['profile'], request['catalog'], request['preferences']): request['tool_context']}
        with self.assertRaises(SchemaError):
            DiscoverySession(request['catalog'], engine, FakeLedger(), contexts, {})
        sample = sample_for(request)
        sample['response']['results']['entities'][0]['query']['affinity'] = 0
        sample['response_sha256'] = fingerprint(sample['response'])
        with self.assertRaises(SchemaError):
            DiscoverySession(request['catalog'], engine, FakeLedger(), contexts, {request['tool_context']['sample_sha256']: sample})
        self.assertEqual(engine.calls, 0)

    def test_caller_cannot_mutate_saved_packet_or_frozen_sample_via_returned_data(self):
        request = fixture_request()
        session, engine, ledger = self.session([request])
        result = session.rank(request)
        result['ranking'].reverse()
        request['tool_context']['ranked_entities'][0]['affinity'] = 0
        clean = fixture_request()
        self.assertEqual(session.rank(clean)['ranking'], ledger.files['discovery-execution-001.json']['response']['ranked_entity_ids'])
        self.assertEqual(engine.calls, 1)

    def test_complete_set_rejects_duplicate_completions_partial_or_mixed_runs(self):
        a, b = fixture_request(1), fixture_request(5)
        session, engine, ledger = self.session([a, b])
        session.rank(a)
        session.rank(b)
        packets = [ledger.files[f'discovery-execution-{i:03d}.json'] for i in (1, 2)]
        samples = {r['tool_context']['sample_sha256']: sample_for(r) for r in (a, b)}
        self.assertEqual(len(verify_complete_packet_set(packets, engine.manifest, engine.source, samples)), 2)
        with self.assertRaises(SchemaError):
            verify_complete_packet_set(packets[:1], engine.manifest, engine.source, samples)
        for damage in ('same-completion', 'mixed-run', 'wrong-order'):
            mutated = copy.deepcopy(packets)
            if damage == 'same-completion':
                obs = mutated[1]['observation']
                obs['completion_id'] = packets[0]['observation']['completion_id']
                obs['provider_envelope']['id'] = obs['completion_id']
                obs['provider_envelope_sha256'] = fingerprint(obs['provider_envelope'])
            elif damage == 'mixed-run':
                mutated[1]['execution_id'] = 'different-run/2'
            else:
                mutated.reverse()
            with self.assertRaises(SchemaError):
                verify_complete_packet_set(mutated, engine.manifest, engine.source, samples)

    def test_real_source_without_durable_admission_is_rejected_before_dispatch(self):
        request = fixture_request()
        engine = DiscoveryMovieAgent(TEST_SECRET, _test_opener=Opener())
        # Deliberately fake a source flag only for a guard oracle; no dispatch.
        engine.source = 'remote-llm'
        engine.manifest = model_manifest(engine.source)
        contexts = {qloo_cache_key(request['profile'], request['catalog'], request['preferences']): request['tool_context']}
        samples = {request['tool_context']['sample_sha256']: sample_for(request)}
        with self.assertRaises(SchemaError):
            DiscoverySession(request['catalog'], engine, FakeLedger(), contexts, samples)
        self.assertEqual(engine.calls, 0)

    def test_failed_dispatch_has_terminal_counter_and_no_retry(self):
        request = fixture_request()
        session, engine, ledger = self.session([request], opener=Opener(
            failure=HTTPError(ENDPOINT, 429, 'synthetic private-looking error text', {}, None)))
        with self.assertRaises(AgentError):
            session.rank(request)
        stops = [data for kind, data in ledger.events if kind == 'discovery_session_stopped']
        self.assertEqual(len(stops), 1)
        self.assertEqual(stops[0]['model_attempts'], 1)
        self.assertEqual(stops[0]['recorded_successful_packets'], 0)
        self.assertEqual(session.last_failure['terminal_recording_state'], 'RECORDED')
        self.assertNotIn('private-looking', str(stops))
        with self.assertRaises(SchemaError):
            session.rank(request)
        self.assertEqual(engine.calls, 1)

    def test_pacing_admission_and_disk_failure_preserve_consumption_and_stop(self):
        request = fixture_request()
        for break_recording in (False, True):
            with self.subTest(break_recording=break_recording):
                session, engine, ledger = self.session([request], paced=True)
                pacer = session.engine
                if break_recording:
                    def fail_write(name, value):
                        raise OSError('synthetic disk failure')
                    ledger.write = fail_write
                    with self.assertRaises(OSError):
                        session.rank(request)
                    self.assertEqual(len(session.cache), 0)
                    self.assertEqual(session.last_failure['recorded_successful_packets'], 0)
                    self.assertEqual(session.last_failure['admitted_model_slots'], 1)
                    self.assertEqual(session.last_failure['terminal_recording_state'], 'RECORDED')
                    with self.assertRaises(SchemaError):
                        session.rank(request)
                else:
                    session.rank(request)
                    self.assertEqual(ledger.events[0][0], 'remote_model_attempt_admitted')
                self.assertEqual(engine.calls, 1)
                self.assertEqual(pacer.slots, 1)

    def test_changed_effective_source_stops_before_admission(self):
        request = fixture_request()
        session, engine, ledger = self.session([request], paced=True)
        engine.source = 'unsupported-source'
        with self.assertRaises(SchemaError):
            session.rank(request)
        self.assertEqual(engine.calls, 0)
        self.assertEqual(session.engine.slots, 0)
        self.assertFalse(any(kind == 'remote_model_attempt_admitted' for kind, _ in ledger.events))
        self.assertEqual(session.last_failure['stage'], 'preflight')
        self.assertEqual(session.last_failure['terminal_recording_state'], 'RECORDED')

    def test_invalid_attempt_counters_never_enter_admission_or_record_raw_state(self):
        request = fixture_request()
        private_marker = 'synthetic-private-counter-do-not-record'
        for damaged in (True, -1, 3, private_marker):
            with self.subTest(counter=type(damaged).__name__):
                session, engine, ledger = self.session([request], paced=True)
                engine.calls = damaged
                with self.assertRaises(SchemaError):
                    session.rank(request)
                self.assertEqual(session.engine.slots, 0)
                self.assertFalse(any(kind == 'remote_model_attempt_admitted' for kind, _ in ledger.events))
                self.assertIsNone(session.last_failure['model_attempts'])
                self.assertEqual(session.last_failure['attempt_count_state'], 'UNKNOWN')
                self.assertEqual(session.last_failure['terminal_recording_state'], 'RECORDED')
                self.assertNotIn(private_marker, str(ledger.events))
                self.assertNotIn(private_marker, str(session.last_failure))
                with self.assertRaisesRegex(SchemaError, 'previous failure'):
                    session.rank(request)

    def test_pacing_ledger_policy_and_slots_are_checked_before_dispatch(self):
        request = fixture_request()
        for damage in ('ledger', 'policy', 'boolean-slots', 'unmatched-slots'):
            with self.subTest(damage=damage):
                session, engine, ledger = self.session([request], paced=True)
                other_ledger = FakeLedger()
                if damage == 'ledger':
                    session.engine.ledger = other_ledger
                elif damage == 'policy':
                    session.engine.policy['minimum_interval_seconds'] = 1.0
                else:
                    session.engine.slots = True if damage == 'boolean-slots' else 1
                with self.assertRaises(SchemaError):
                    session.rank(request)
                self.assertEqual(engine.calls, 0)
                self.assertFalse(any(kind == 'remote_model_attempt_admitted' for kind, _ in ledger.events + other_ledger.events))
                self.assertEqual(session.last_failure['stage'], 'preflight')
                self.assertEqual(session.last_failure['terminal_recording_state'], 'RECORDED')

    def test_invalid_observations_still_leave_a_safe_terminal_receipt(self):
        request = fixture_request()
        for observations in (None, (), [{}]):
            with self.subTest(container=type(observations).__name__):
                session, engine, ledger = self.session([request], paced=True)
                engine.observations = observations
                with self.assertRaises((SchemaError, TypeError)):
                    session.rank(request)
                self.assertIsNotNone(session.last_failure)
                self.assertEqual(session.last_failure['terminal_recording_state'], 'RECORDED')
                self.assertEqual(engine.calls, 0)
                self.assertEqual(session.engine.slots, 0)
                self.assertFalse(any(kind == 'remote_model_attempt_admitted' for kind, _ in ledger.events))
                if type(observations) is not list:
                    self.assertIsNone(session.last_failure['observed_successes'])
                    self.assertEqual(session.last_failure['observation_count_state'], 'UNKNOWN')
                with self.assertRaisesRegex(SchemaError, 'previous failure'):
                    session.rank(request)

    def test_exhausted_model_budget_allows_valid_cache_without_new_admission(self):
        a, b = fixture_request(1), fixture_request(5)
        session, engine, ledger = self.session([a, b], paced=True)
        session.rank(a)
        session.rank(b)
        cached = make_request(a['catalog'], a['profile'], a['tool_context'], a['preferences'], 'budget-cache')
        self.assertTrue(session.rank(cached)['trace']['cache_hit'])
        prefs = copy.deepcopy(b['preferences'])
        prefs['excluded_entity_ids'] = []
        uncached = make_request(b['catalog'], b['profile'], b['tool_context'], prefs, 'budget-no-cache')
        with self.assertRaises(SchemaError):
            session.rank(uncached)
        self.assertEqual(engine.calls, 2)
        self.assertEqual(session.engine.slots, 2)
        self.assertEqual(sum(kind == 'remote_model_attempt_admitted' for kind, _ in ledger.events), 2)
        self.assertEqual(session.last_failure['stage'], 'preflight')


if __name__ == '__main__':
    unittest.main()
