"""Two explicit cinema decisions; separate from the unchanged 39-call fault experiment."""
import copy
from pathlib import Path
import re
import time

from .agents import strict_json
from .causal_agent import context_from_sample, profile_hash
from .cinema_preferences import CINEMA_PROTOCOL, CinemaMovieAgent, CinemaSession, baseline, make_request, validate_preferences
from .errors import AffinityQAError
from .evidence import Ledger, fingerprint, utc_now
from .groq_agent import contains_secret, model_manifest
from .individual_capture import execution_lease, need, resolve_music, safe_directory_path, sha, validate_capture_paths
from .individual_remote_capture import SOURCES as REMOTE_SOURCES, validate_request as artist_request
from .qloo import LiveTransport, QlooClient
from .remote_pacing import PacedRemoteAgent, pacing_policy

SOURCES = tuple(dict.fromkeys((*REMOTE_SOURCES, 'cinema_preferences.py', 'cinema_capture.py', 'cinema_verify.py')))
MODE = 'cinema-preferences-capture'
SOURCE = 'qloo-tool+groq-remote-llm'


def validate_request(value):
    need(isinstance(value, dict) and set(value) == {'schema_version', 'artists', 'catalog', 'model', 'preferences'},
         'Unexpected cinema capture fields.')
    need(type(value['schema_version']) is int and value['schema_version'] == 3, 'Use cinema capture request version3.')
    base = artist_request({k: copy.deepcopy(v) for k, v in value.items() if k != 'preferences'} | {'schema_version': 2})
    preferences = value['preferences']
    need(isinstance(preferences, dict) and set(preferences) == {'A', 'B'}, 'Declare cinema preferences for both profiles.')
    return {**base, 'schema_version': 3, 'artists': {label: base['artists'][label] for label in ('A', 'B')},
            'preferences': {label: validate_preferences(preferences[label], base['catalog']) for label in ('A', 'B')}}


def prepare_plan(request, output, *, minimum_model_interval_seconds=None):
    request = validate_request(request)
    output = safe_directory_path(Path(output))
    validate_capture_paths(output)
    need(not output.exists() and output.parent.is_dir(), 'Choose a new output directory with an existing parent.')
    source = Path(__file__).resolve().parent
    root = source.parents[1]
    plan = {'schema_version': 4, 'protocol_version': CINEMA_PROTOCOL, 'mode': MODE,
            'request': request, 'output_directory': str(output),
            'remote_operator': model_manifest('remote-llm', max_calls=2, cinema=True),
            'execution_pacing': pacing_policy(minimum_model_interval_seconds),
            'source_sha256': {name: sha(source/name) for name in SOURCES},
            'driver_sha256': sha(source/'cinema_capture.py'),
            'verification_driver_sha256': sha(source/'cinema_verify.py'),
            'dependencies_lock_sha256': sha(root/'requirements-backend.lock.txt'),
            'maximum_qloo_requests': 4, 'maximum_attempts_per_request': 1,
            'maximum_model_decisions': 2, 'cache_checks_per_profile': 1, 'faults': [],
            'new_model_metadata_requests': 0, 'startup_model_metadata_requests': 0,
            'runtime_model_metadata_requests': 0, 'model_load_requests': 0,
            'individual_demo_only': True, 'independent_validation_claim': False,
            'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
            'partial_failure_policy': 'Preserve all evidence, stop without retry or resume.'}
    plan['plan_sha256'] = fingerprint(plan)
    return plan


def result_projection(profile, preferences, uncached, reference):
    delivery = uncached['delivery']
    return {'profile': copy.deepcopy(profile), 'preferences': copy.deepcopy(preferences),
            'preferences_sha256': uncached['trace']['requested_preferences_sha256'],
            'intent_sha256': uncached['trace']['requested_intent_sha256'],
            'raw_ranking': delivery['raw_ranked_entity_ids'], 'delivered': delivery['delivered_entity_ids'],
            'baseline_delivered': reference['delivery']['delivered_entity_ids'],
            'delivery_sha256': delivery['delivered_output_sha256'], 'raw_ranking_sha256': delivery['raw_output_sha256'],
            'eligible_count': delivery['eligible_movies'], 'excluded_removed': delivery['excluded_entity_ids'],
            'preference_gate': 'PASS', 'delivery_policy': delivery['policy'],
            'selection_changed': delivery['selection_changed'], 'baseline_information_policy': reference['information_policy'],
            'baseline_delivery_sha256': reference['delivery']['delivered_output_sha256'],
            'human_quality_validated': False, 'satisfaction_score': None}


def execute_capture(request, output, expected_plan_hash, settings, remote_key, *,
                    minimum_model_interval_seconds=None, _test_adapters=None, _test_pacing_clock=None):
    plan = prepare_plan(request, output, minimum_model_interval_seconds=minimum_model_interval_seconds)
    need(plan['plan_sha256'] == expected_plan_hash, 'The reviewed cinema plan changed. No execution.')
    need(_test_adapters is not None or plan['execution_pacing']['configured'], 'Real cinema execution requires reviewed model pacing.')
    need(_test_pacing_clock is None or _test_adapters is not None, 'Simulated pacing cannot enter real execution.')
    need(isinstance(settings.api_key, str) and settings.api_key.strip(), 'Configure Qloo privately.')
    need(isinstance(remote_key, str) and re.fullmatch(r'[!-~]{20,512}', remote_key), 'Configure Groq privately.')
    secrets = (settings.api_key, remote_key)
    need(not contains_secret(plan, secrets), 'Private credentials must never enter cinema inputs.')
    request = copy.deepcopy(plan['request'])
    output = safe_directory_path(Path(output))
    testing = _test_adapters is not None
    source = 'test-double-only' if testing else SOURCE
    engine_source = 'test-double-only' if testing else 'remote-llm'
    engine_factory, transport_factory = _test_adapters or (
        lambda: CinemaMovieAgent(remote_key, forbidden_secrets=(settings.api_key,)),
        lambda: LiveTransport(settings, timeout=120))
    with execution_lease(output.parent):
        output.mkdir(mode=0o700)
        ledger = Ledger(output, source, secrets)
        ledger.write('individual-plan.json', plan)
        ledger.record('individual_plan_frozen', {'plan_sha256': plan['plan_sha256'], 'model_calls': 0, 'qloo_calls': 0})
        report = {'schema_version': 4, 'created_utc': utc_now(), 'run_id': ledger.run_id,
                  'mode': MODE, 'source': source, 'status': 'INCOMPLETE', 'plan_sha256': plan['plan_sha256'],
                  'causal_gate': 'NOT_EVALUATED', 'behavioral_gate': 'NOT_EVALUATED', 'integration_gate': 'NOT_EVALUATED',
                  'preference_gate': 'NOT_EVALUATED', 'cultural_gate': 'NOT_VALIDATED',
                  'release_gate': 'BLOCKED', 'release_approved': False, 'independent_validation_claim': False,
                  'independent_verification': 'PENDING', 'error_class': None,
                  'model_attempts': 0, 'qloo_attempts': 0, 'model_load_attempts': 0, 'admitted_model_slots': 0,
                  'requested_profiles': 2, 'successful_profiles': 0, 'failed_model_attempts': 0, 'unattempted_profiles': 2,
                  'cinema_results': {}, 'preferences_gate_scope': 'Explicit excluded catalog IDs only; delivered outputs and completeness are counted separately.',
                  'partial_evidence_preserved': True}
        engine = client = pacer = None
        try:
            engine = engine_factory()
            need(engine.source == engine_source
                 and fingerprint(engine.manifest) == fingerprint(model_manifest(engine_source, max_calls=2, cinema=True))
                 and engine.calls == 0, 'Cinema operator identity, prompt, budget or provenance differs.')
            ledger.write('model-manifest.json', engine.manifest)
            client = QlooClient(transport_factory(), ledger, max_requests=4, max_attempts=1)
            last = None

            def get(path, params):
                nonlocal last
                if last is not None:
                    time.sleep(max(0, 1-(time.monotonic()-last)))
                last = time.monotonic()
                body = client.get(path, params, cache=False)
                event = next(e for e in reversed(ledger.events) if e['kind'] == 'tool_call')
                sample_path = ledger.directory/event['data']['sample']
                return body, strict_json(sample_path.read_bytes()), sha(sample_path)

            profiles = {label: resolve_music(name, get('/search', {'query': name, 'take': 5})[0])
                        for label, name in request['artists'].items()}
            need(len({p['entity_id'] for p in profiles.values()}) == 2, 'Resolved artists coincide; no substitution.')
            ledger.write('individual-identities.json', profiles)
            contexts = {}
            for profile in profiles.values():
                _, sample, digest = get('/v2/insights', {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': 20,
                    'signal.interests.entities': profile['entity_id'],
                    'filter.results.entities': ','.join(sorted(r['entity_id'] for r in request['catalog']))})
                contexts[profile_hash(profile)] = context_from_sample(profile, request['catalog'], sample, digest)
            need(not contains_secret(contexts, secrets), 'Private data must not enter the model context.')
            ledger.write('individual-tool-inputs.json', contexts)
            ledger.record('all_tool_inputs_frozen', {'sha256': fingerprint(contexts), 'model_calls': 0, 'qloo_calls': client.requests})
            pacer = PacedRemoteAgent(engine, plan['execution_pacing'], ledger, _test_clock=_test_pacing_clock)
            session = CinemaSession(pacer, ledger, contexts)
            for label in ('A', 'B'):
                profile, preferences = profiles[label], request['preferences'][label]
                effective = make_request(request['catalog'], profile, contexts[profile_hash(profile)], preferences,
                                         'cinema-' + ledger.run_id + '-' + label)
                uncached = session.rank(effective)
                cached = session.rank(effective)
                need(cached['trace']['cache_hit'] is True and uncached['trace']['cache_hit'] is False
                     and cached['ranking'] == uncached['ranking'] and cached['delivery'] == uncached['delivery'],
                     'Cinema cache did not preserve the exact intent and raw decision.')
                reference = baseline(contexts[profile_hash(profile)], request['catalog'], preferences)
                result = result_projection(profile, preferences, uncached, reference)
                ledger.write('cinema-result-' + label + '.json', {'schema_version': 1, 'label': label,
                    'effective_request': effective, 'uncached_boundary': uncached, 'cached_boundary': cached,
                    'baseline': reference, 'result': result})
                report['cinema_results'][label] = result
            report.update(status='COMPLETE', preference_gate='PASS')
        except BaseException as exc:
            report['error_class'] = type(exc).__name__
            ledger.record('stopped_without_retry', {'error_class': type(exc).__name__})
            if not isinstance(exc, (AffinityQAError, OSError)):
                raise
        finally:
            report['model_attempts'] = getattr(engine, 'calls', 0)
            report['admitted_model_slots'] = getattr(pacer, 'slots', 0)
            report['qloo_attempts'] = getattr(client, 'requests', 0)
            report['successful_profiles'] = len(report['cinema_results'])
            report['failed_model_attempts'] = report['model_attempts'] - len(getattr(engine, 'observations', []))
            report['unattempted_profiles'] = 2 - report['model_attempts']
            ledger.write('individual-report.json', report)
        return report, ledger.directory
