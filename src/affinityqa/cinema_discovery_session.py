"""Recorded discovery decisions and cache boundaries; no repair/quality claim."""
import copy
import re
import threading

from .cinema_discoveries import (
    cache_key, deliver, qloo_cache_key, validate_request,
)
from .cinema_discovery_verify import expected_manifest, verify_context, verify_packet, need
from .causal_agent import validate_catalog
from .evidence import fingerprint
from .remote_pacing import PacedRemoteAgent
from .cinema_discovery_agent import DiscoveryMovieAgent, DiscoveryHTTPError
from .cinema_discovery_diagnostics import closed_http


def _safe_count(read, maximum):
    """Do not let an unusable internal attribute suppress a failure receipt."""
    try:
        value = read()
        return value if type(value) is int and 0 <= value <= maximum else None
    except BaseException:
        return None


def _observations_count(engine):
    observations = engine.observations
    return len(observations) if type(observations) is list else None


class DiscoverySession:
    def __init__(self, catalog, engine, ledger, contexts, samples):
        validate_catalog(catalog)
        need(isinstance(contexts, dict) and bool(contexts) and isinstance(samples, dict), 'frozen tool bundle')
        need(isinstance(ledger.run_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', ledger.run_id), 'bounded run identity')
        need(type(engine.calls) is int and engine.calls == 0
             and type(engine.observations) is list and engine.observations == [], 'unused operator')
        need(engine.source == 'test-double-only' or isinstance(engine, PacedRemoteAgent)
             and engine.ledger is ledger and engine.policy['configured'] is True,
             'real execution requires its durable pacing admission on the same ledger')
        self.catalog, self.contexts, self.samples = copy.deepcopy((catalog, contexts, samples))
        self.engine, self.ledger = engine, ledger
        self.manifest = copy.deepcopy(engine.manifest)
        need(fingerprint(self.manifest) == fingerprint(expected_manifest(engine.source,
             max_calls=self.manifest['max_inference_calls'], timeout=self.manifest['inference_timeout_seconds'])),
             'reviewed discovery operator contract')
        self._max_calls = self.manifest['max_inference_calls']
        self._pacing_policy_sha = fingerprint(engine.policy) if isinstance(engine, PacedRemoteAgent) else None
        for key, context in self.contexts.items():
            prefs = {'schema_version': 1, 'favorite_entity_ids': context['favorite_entity_ids'], 'excluded_entity_ids': []}
            need(key == qloo_cache_key(context['profile'], self.catalog, prefs), 'tool bundle key')
            digest = context['sample_sha256']
            need(digest in self.samples, 'missing actual recorded sample')
            verify_context(context, self.catalog, context['profile'], prefs, self.samples[digest], digest)
        self._bundle_sha = self._bundle_hash()
        self.cache, self._completion_ids, self._packet_hashes = {}, set(), {}
        self._stopped = False
        self.last_failure = None
        self._stage = 'preflight'
        self._lock = threading.Lock()
        adapter = engine.engine if isinstance(engine,PacedRemoteAgent) else engine
        if isinstance(adapter,DiscoveryMovieAgent):
            adapter.bind_dispatch_ledger(ledger)

    def _bundle_hash(self):
        return fingerprint({'catalog': self.catalog, 'contexts': self.contexts,
                            'samples': self.samples, 'manifest': self.manifest})

    def rank(self, request):
        with self._lock:
            need(not self._stopped, 'previous failure stopped this session; no retry')
            try:
                return self._rank(request)
            except BaseException as exc:
                self._stopped = True
                adapter = self.engine.engine if isinstance(self.engine,PacedRemoteAgent) else self.engine
                prepared = adapter.last_prepared if isinstance(adapter,DiscoveryMovieAgent) and self._stage == 'model_dispatch' else None
                diagnostic = closed_http(exc.http_diagnostic) if isinstance(exc,DiscoveryHTTPError) and self._stage == 'model_dispatch' else None
                failure = {'schema_version': 2, 'stage': self._stage, 'error_class': type(exc).__name__,
                           'model_attempts': None, 'attempt_count_state': 'UNKNOWN',
                           'observed_successes': None, 'observation_count_state': 'UNKNOWN',
                           'recorded_successful_packets': None,
                           'admitted_model_slots': None, 'admission_count_state': 'UNKNOWN',
                           'automatic_retry': False, 'external_service_attested': False,
                           'http_failure': diagnostic,
                           'prepared_receipt_sha256':fingerprint(prepared) if prepared is not None else None}
                self.last_failure = {**failure, 'terminal_recording_state': 'PENDING'}
                calls = _safe_count(lambda: self.engine.calls, self._max_calls)
                observations = _safe_count(lambda: _observations_count(self.engine), self._max_calls)
                slots = _safe_count(lambda: self.engine.slots, self._max_calls) if isinstance(self.engine, PacedRemoteAgent) else None
                failure.update(model_attempts=calls, attempt_count_state='KNOWN' if calls is not None else 'UNKNOWN',
                               observed_successes=observations, observation_count_state='KNOWN' if observations is not None else 'UNKNOWN',
                               recorded_successful_packets=_safe_count(lambda: len(self._packet_hashes), self._max_calls),
                               admitted_model_slots=slots, admission_count_state='KNOWN' if slots is not None else 'UNKNOWN')
                self.last_failure.update(failure)
                try:
                    self.ledger.record('discovery_session_stopped', failure)
                    self.last_failure['terminal_recording_state'] = 'RECORDED'
                except BaseException as close_error:
                    self.last_failure.update(terminal_recording_state='UNKNOWN', close_error_class=type(close_error).__name__)
                    raise exc from close_error
                raise

    def _rank(self, request):
        self._stage = 'preflight'
        need(self._bundle_hash() == self._bundle_sha
             and fingerprint(self.engine.manifest) == fingerprint(self.manifest), 'frozen bundle/operator changed')
        need(self.engine.source == self.manifest['execution_source'], 'effective execution source changed')
        need(type(self.engine.calls) is int and 0 <= self.engine.calls <= self._max_calls
             and type(self.engine.observations) is list and len(self.engine.observations) == self.engine.calls,
             'operator attempts and observations are not a bounded completed state')
        if isinstance(self.engine, PacedRemoteAgent):
            need(self.engine.ledger is self.ledger and self.engine.policy['configured'] is True
                 and fingerprint(self.engine.policy) == self._pacing_policy_sha
                 and type(self.engine.slots) is int and 0 <= self.engine.slots <= self._max_calls
                 and self.engine.slots == self.engine.calls, 'effective durable pacing admission changed')
        else:
            need(self.engine.source == 'test-double-only' and self._pacing_policy_sha is None,
                 'real execution requires its original durable pacing admission')
        request = validate_request(request)
        need(fingerprint(request['catalog']) == fingerprint(self.catalog), 'different reference catalog')
        tool_key = qloo_cache_key(request['profile'], self.catalog, request['preferences'])
        need(self.contexts.get(tool_key) == request['tool_context'], 'request left its actual tool bundle')
        key = cache_key(request, self.manifest)
        hit = key in self.cache
        if hit:
            self._stage = 'cache_verification'
            packet = copy.deepcopy(self.cache[key])
            need(self._packet_hashes.get(key) == fingerprint(packet), 'recorded cache packet changed')
            need(cache_key(packet['effective_request'], self.manifest) == key, 'cache entry belongs to another intent')
        else:
            need(self.engine.calls < self._max_calls, 'model attempt budget exhausted before admission')
            self._stage = 'model_dispatch'
            previous_calls, previous_observations = self.engine.calls, len(self.engine.observations)
            adapter = self.engine.engine if isinstance(self.engine, PacedRemoteAgent) else self.engine
            if isinstance(adapter, DiscoveryMovieAgent):
                adapter.last_prepared = None
            response = self.engine.rank(request)
            need(type(self.engine.calls) is int and self.engine.calls == previous_calls + 1
                 and len(self.engine.observations) == previous_observations + 1, 'exactly one observed attempt')
            packet = {'execution_id': self.ledger.run_id + '/' + str(self.engine.calls),
                      'effective_request': copy.deepcopy(request), 'model_payload': copy.deepcopy(self.engine.last_input),
                      'response': copy.deepcopy(response), 'observation': copy.deepcopy(self.engine.observations[-1])}
        effective = packet['effective_request']
        self._stage = 'packet_verification'
        need(packet['execution_id'] == self.ledger.run_id + '/' + str(packet['observation']['call']),
             'execution identity belongs to another session')
        digest = effective['tool_context']['sample_sha256']
        need(digest in self.samples, 'execution sample left its immutable bundle')
        verified = verify_packet(packet, self.manifest, self.engine.source, self.samples[digest], digest)
        if not hit:
            need(packet['observation']['call'] == self.engine.calls
                 and verified['completion_id'] not in self._completion_ids, 'duplicated or mismatched observed execution')
            self._stage = 'packet_recording'
            self.ledger.write(f'discovery-execution-{self.engine.calls:03d}.json', packet)
            self._stage = 'execution_event_recording'
            self.ledger.record('observed_discovery_execution', {
                'execution_id': packet['execution_id'], 'request_sha256': fingerprint(effective),
                'payload_sha256': fingerprint(packet['model_payload']), 'output_sha256': fingerprint(verified['raw_ranking'])})
            self._completion_ids.add(verified['completion_id'])
            self.cache[key] = copy.deepcopy(packet)
            self._packet_hashes[key] = fingerprint(packet)
        need(verified['completion_id'] in self._completion_ids, 'cache execution was never recorded')
        self._stage = 'delivery_boundary'
        delivery = deliver(verified['raw_ranking'], self.catalog, request['preferences'])
        need(delivery['delivered_entity_ids'] == verified['delivered_entity_ids'], 'delivery differs from independent guard')
        payload = packet['model_payload']
        trace = {
            'requested_profile_sha256': request['profile_sha256'], 'transmitted_profile_sha256': payload['profile_sha256'],
            'tool_profile_sha256': effective['tool_context']['profile_sha256'],
            'requested_signal_sha256': request['signal_sha256'], 'transmitted_signal_sha256': payload['signal_sha256'],
            'tool_signal_sha256': effective['tool_context']['signal_sha256'],
            'requested_preferences_sha256': request['preferences_sha256'],
            'transmitted_preferences_sha256': payload['preferences_sha256'],
            'delivered_preferences_sha256': delivery['preferences_sha256'],
            'requested_intent_sha256': request['intent_sha256'], 'transmitted_intent_sha256': payload['intent_sha256'],
            'cache_hit': hit, 'cache_key_sha256': key, 'execution_id': packet['execution_id'],
            'call': packet['observation']['call'], 'payload_sha256': fingerprint(payload),
            'requested_request_sha256': fingerprint(request), 'execution_request_sha256': fingerprint(effective),
            'context_response_sha256': effective['tool_context']['response_sha256'],
            'raw_output_sha256': delivery['raw_output_sha256'], 'delivered_output_sha256': delivery['delivered_output_sha256'],
            'delivery_policy': delivery['policy'], 'qloo_signal_scope': 'Confirmed musical identity and known favorite IDs; exclusions are delivery-only.',
        }
        self.ledger.record('observed_discovery_boundary', trace)
        return {'ranking': copy.deepcopy(verified['raw_ranking']), 'delivery': delivery, 'trace': trace}
