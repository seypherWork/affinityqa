"""Single confirmed movie, one open Qloo pool and at most one Groq decision."""
import copy
import json
from pathlib import Path

from .agents import strict_json
from .errors import AffinityQAError
from .evidence import Ledger, fingerprint, utc_now
from .groq_agent import contains_secret
from .individual_capture import safe_directory_path, validate_capture_paths, execution_lease, sha
from .qloo import QlooClient, LiveTransport
from .open_movie_discovery import (PROTOCOL, SOURCE, need, validate_request, movie_candidates, select_movie,
    qloo_request, context_from_sample, make_decision, result_for, cache_key)
from .open_movie_discovery_agent import OpenMovieAgent, model_manifest

SOURCES = ('open_movie_discovery.py', 'open_movie_discovery_agent.py', 'open_movie_discovery_capture.py',
           'open_movie_discovery_verify.py', 'qloo.py', 'models.py', 'evidence.py', 'errors.py', 'agents.py',
           'groq_agent.py', 'individual_capture.py', 'provider_runtime.py', 'provider_scheduler.py', 'qloo_cache.py')


def prepare_plan(request, output, *, minimum_model_interval_seconds=None):
    request = validate_request(request)
    output = safe_directory_path(Path(output)); validate_capture_paths(output)
    need(not output.exists() and output.parent.is_dir(), 'New capture path and existing parent required.')
    source = Path(__file__).resolve().parent
    plan = {'schema_version': 10, 'protocol_version': PROTOCOL, 'mode': 'open-movie-discovery', 'request': request,
        'output_directory': str(output), 'source_sha256': {n: sha(source / n) for n in SOURCES},
        'driver_sha256': sha(source / 'open_movie_discovery_capture.py'),
        'verification_driver_sha256': sha(source / 'open_movie_discovery_verify.py'),
        'dependencies_lock_sha256': sha(source.parents[1] / 'requirements-backend.lock.txt'),
        'remote_operator': model_manifest('remote-llm'), 'maximum_qloo_requests': 2,
        'maximum_identity_search_requests': 1, 'maximum_insights_requests': 1, 'maximum_model_decisions': 1,
        'maximum_attempts_per_request': 1, 'maximum_model_load_requests': 0, 'maximum_model_metadata_requests': 0,
        'candidate_policy': {'minimum': 5, 'maximum': 20, 'source': 'exact-recorded-open-qloo-response',
            'all_rows_typed_with_integer_year': True, 'fixed_catalog_fallback': False},
        'identity_candidate_contract': 'qloo-open-movie-title-year-slot-v1',
        'faults': [], 'execution_pacing': {'strategy': 'one-model-send-shared-provider-scheduler', 'minimum_interval_seconds': 0},
        'maximum_token_reservation': 8000, 'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED'}
    plan['plan_sha256'] = fingerprint(plan)
    return plan


def _snapshot(ledger):
    with (ledger.directory / 'identity-ledger.jsonl').open('xb') as handle:
        handle.write((ledger.directory / 'ledger.jsonl').read_bytes())


def search_identities(request, output, expected_plan_hash, settings, *, minimum_model_interval_seconds=None, _test_adapters=None):
    plan = prepare_plan(request, output, minimum_model_interval_seconds=minimum_model_interval_seconds)
    need(plan['plan_sha256'] == expected_plan_hash, 'Reviewed open plan changed.')
    need(isinstance(settings.api_key, str) and len(settings.api_key) >= 20
         and not contains_secret(plan, (settings.api_key,)), 'Private Qloo configuration must stay outside the plan.')
    testing = _test_adapters is not None
    output = Path(plan['output_directory']); output.mkdir(mode=0o700)
    ledger = Ledger(output, 'test-double-only' if testing else SOURCE, secrets=(settings.api_key,))
    ledger.write('open-plan.json', plan)
    report = {'schema_version': 10, 'protocol_version': PROTOCOL, 'run_id': ledger.run_id, 'phase': 'MOVIE_SEARCH',
        'plan_sha256': plan['plan_sha256'], 'status': 'INCOMPLETE', 'source': ledger.source,
        'movie_query': plan['request']['movie_query'], 'movie_candidates': [], 'qloo_attempts': 0,
        'model_attempts': 0, 'error_class': None, 'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED'}
    factory = _test_adapters[1] if testing else lambda: LiveTransport(settings, timeout=120)
    client = None
    try:
        client = QlooClient(factory(), ledger, synthetic=testing, max_requests=2, max_attempts=1)
        params = {'query': plan['request']['movie_query'], 'types': 'urn:entity:movie', 'take': 5}
        ledger.record('open_search_admitted', {'params': params})
        body = client.get('/search', params, cache=False)
        candidates = movie_candidates(body)
        ledger.write('open-movie-candidates.json', candidates)
        ledger.record('open_search_candidates_recorded', {'sha256': sha(ledger.directory / 'open-movie-candidates.json')})
        report.update(status='AWAITING_IDENTITY_CONFIRMATION', movie_candidates=candidates)
    except BaseException as exc:
        report['error_class'] = type(exc).__name__
        ledger.record('open_search_stopped', {'error_class': type(exc).__name__})
        if not isinstance(exc, (AffinityQAError, OSError)):
            raise
    finally:
        report['qloo_attempts'] = getattr(client, 'requests', 0)
        ledger.write('open-search-report.json', report)
        _snapshot(ledger)
    return report, ledger.directory


def capture_confirmed(directory, selected_movie_entity_id, identity_receipt, settings, remote_key, *,
                      _test_adapters=None, _test_pacing_clock=None):
    from .open_movie_discovery_verify import verify_identity_search
    need(_test_pacing_clock is None, 'This one-send protocol has no simulated intercall clock.')
    directory = safe_directory_path(Path(directory))
    with execution_lease(directory.parent.parent):
        current = verify_identity_search(directory)
        clean = lambda value: {k: v for k, v in value.items() if k != 'verified_utc'}
        need(fingerprint(clean(current)) == fingerprint(clean(identity_receipt)), 'Saved search receipt changed.')
        seed = select_movie(current, selected_movie_entity_id)
        plan = strict_json((directory / 'open-plan.json').read_bytes())
        testing = _test_adapters is not None
        need(current['provenance'] == ('SIMULATION_ONLY' if testing else 'RECORDED_REMOTE_EXECUTION'), 'Mixed capture provenance.')
        secrets = (settings.api_key, remote_key)
        need(all(isinstance(v, str) and len(v) >= 20 for v in secrets)
             and not contains_secret((plan, identity_receipt, seed), secrets), 'Private provider configuration required outside evidence.')
        ledger = Ledger.__new__(Ledger)
        ledger.directory, ledger.run_id, ledger.source, ledger.secrets = directory, directory.name, current['source'], secrets
        ledger.events = [strict_json(row) for row in (directory / 'ledger.jsonl').read_bytes().splitlines()]
        ledger.live_requests = current['qloo_attempts'] if not testing else 0
        confirmation = {'schema_version': 1, 'protocol': PROTOCOL, 'plan_sha256': plan['plan_sha256'],
            'identity_receipt': copy.deepcopy(identity_receipt), 'selected_movie_entity_id': selected_movie_entity_id, 'seed_movie': seed}
        ledger.write('open-confirmation.json', confirmation)
        ledger.record('open_movie_confirmed', {'sha256': sha(directory / 'open-confirmation.json')})
        report = {'schema_version': 10, 'protocol_version': PROTOCOL, 'run_id': directory.name,
            'phase': 'CONFIRMED_OPEN_MOVIES', 'plan_sha256': plan['plan_sha256'], 'status': 'INCOMPLETE',
            'source': ledger.source, 'qloo_attempts': current['qloo_attempts'], 'model_attempts': 0,
            'error_class': None, 'open_movie_results': None, 'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED'}
        factories = _test_adapters or (lambda: OpenMovieAgent(remote_key, forbidden_secrets=(settings.api_key,)),
                                      lambda: LiveTransport(settings, timeout=120))
        client = engine = None
        try:
            client = QlooClient(factories[1](), ledger, synthetic=testing, max_requests=2, max_attempts=1)
            client.requests = current['qloo_attempts']
            params = qloo_request(seed)['params']
            ledger.record('open_insights_admitted', {'params': params})
            client.get('/v2/insights', params, cache=False)
            sample_path = directory / ledger.events[-1]['data']['sample']
            context = context_from_sample(seed, strict_json(sample_path.read_bytes()), sha(sample_path))
            ledger.write('open-candidate-context.json', context)
            ledger.record('open_candidate_context_frozen', {'sha256': sha(directory / 'open-candidate-context.json')})
            decision = make_decision(plan['request'], context, 'open-' + directory.name)
            engine = factories[0]()
            need(engine.calls == 0 and fingerprint(engine.manifest) == fingerprint(model_manifest('test-double-only' if testing else 'remote-llm')),
                 'Frozen unused single-send operator required.')
            engine.dispatch_ledger = ledger
            ledger.write('open-model-manifest.json', engine.manifest)
            response = engine.rank(decision)
            packet = {'execution_id': directory.name + '/1', 'effective_request': decision,
                'model_payload': copy.deepcopy(engine.last_input), 'response': copy.deepcopy(response),
                'observation': copy.deepcopy(engine.observations[-1]), 'cache_key_sha256': cache_key(decision, engine.manifest)}
            ledger.write('open-movie-execution-001.json', packet)
            ledger.record('open_model_execution_recorded', {'sha256': sha(directory / 'open-movie-execution-001.json')})
            output = {'ordered_catalog_indices': packet['observation']['provider_envelope']['choice']['ordered_catalog_indices']}
            result = result_for(decision, output)
            need(response['ranked_entity_ids'] == result['raw_ranking'] and response['reasons'] == output['ordered_catalog_indices']['reasons'],
                 'Observed response and guarded result disagree.')
            ledger.write('open-movie-result.json', result)
            ledger.record('open_result_recorded', {'sha256': sha(directory / 'open-movie-result.json')})
            report.update(status='COMPLETE', open_movie_results=result)
            ledger.record('open_complete', {'candidate_count': len(result['candidate_catalog']), 'delivered_count': 5})
        except BaseException as exc:
            report.update(status='INCOMPLETE', open_movie_results=None, error_class=type(exc).__name__)
            ledger.record('open_capture_stopped', {'error_class': type(exc).__name__})
            if not isinstance(exc, (AffinityQAError, OSError)):
                raise
        finally:
            report['qloo_attempts'] = getattr(client, 'requests', current['qloo_attempts'])
            report['model_attempts'] = getattr(engine, 'calls', 0)
            ledger.write('open-report.json', report)
        return report, directory
