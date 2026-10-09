"""Search, explicit identity confirmation, then cinema inference in one bounded run."""
import copy
from pathlib import Path
import re
import time
import unicodedata

from .agents import strict_json
from .causal_agent import context_from_sample, profile_hash
from .cinema_capture import SOURCES as CINEMA_SOURCES, validate_request as cinema_request, result_projection
from .cinema_preferences import CinemaMovieAgent, CinemaSession, baseline, make_request
from .errors import AffinityQAError, SchemaError
from .evidence import Ledger, fingerprint, utc_now
from .groq_agent import contains_secret, model_manifest
from .individual_capture import canonical_name, execution_lease, need, safe_directory_path, sha, validate_capture_paths
from .models import parse_entities
from .qloo import LiveTransport, QlooClient
from .remote_pacing import PacedRemoteAgent, pacing_policy

PROTOCOL = 'cinema-confirmed-identity-v1'
MODE = 'cinema-confirmed-identity-capture'
SOURCE = 'qloo-tool+groq-remote-llm'
SOURCES = tuple(dict.fromkeys((*CINEMA_SOURCES, 'cinema_identity_capture.py', 'cinema_identity_verify.py')))


def validate_request(value):
    need(isinstance(value, dict) and type(value.get('schema_version')) is int and value['schema_version'] == 4,
         'Use confirmed-identity cinema request version4.')
    result = cinema_request({**value, 'schema_version': 3})
    result['schema_version'] = 4
    return result


def prepare_plan(request, output, *, minimum_model_interval_seconds=None):
    request = validate_request(request)
    output = safe_directory_path(Path(output))
    validate_capture_paths(output)
    need(not output.exists() and output.parent.is_dir(), 'Choose a new output with an existing parent.')
    source = Path(__file__).resolve().parent
    plan = {'schema_version': 5, 'protocol_version': PROTOCOL, 'mode': MODE, 'request': request,
        'output_directory': str(output), 'remote_operator': model_manifest('remote-llm', max_calls=2, cinema=True),
        'execution_pacing': pacing_policy(minimum_model_interval_seconds),
        'source_sha256': {name: sha(source/name) for name in SOURCES},
        'driver_sha256': sha(source/'cinema_identity_capture.py'),
        'verification_driver_sha256': sha(source/'cinema_identity_verify.py'),
        'dependencies_lock_sha256': sha(source.parents[1]/'requirements-backend.lock.txt'),
        'maximum_qloo_requests': 4, 'maximum_identity_search_requests': 2, 'maximum_insights_requests': 2,
        'maximum_attempts_per_request': 1, 'maximum_model_decisions': 2, 'cache_checks_per_profile': 1,
        'faults': [], 'explicit_identity_confirmation_required': True,
        'new_model_metadata_requests': 0, 'startup_model_metadata_requests': 0,
        'runtime_model_metadata_requests': 0, 'model_load_requests': 0,
        'individual_demo_only': True, 'independent_validation_claim': False,
        'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
        'partial_failure_policy': 'Preserve all evidence, stop without retry or resume; only a successful identity search may continue after explicit confirmation.'}
    plan['plan_sha256'] = fingerprint(plan)
    return plan


def music_candidates(body):
    """Return provider identities, never turn a query spelling into an identity."""
    rows = parse_entities(body, insights=False)
    need(len(rows) <= 5, 'Identity search exceeded its declared result bound.')
    candidates = []
    norm = lambda v: ' '.join(unicodedata.normalize('NFKC', v).casefold().split())
    occupations = {'musician', 'singer', 'singer songwriter', 'songwriter', 'rapper', 'composer',
                   'pianist', 'guitarist', 'harpist', 'record producer', 'music producer'}
    for row in rows:
        kind = 'urn:entity:artist' if 'urn:entity:artist' in row.types else None
        if kind is None and 'urn:entity:person' in row.types:
            raw = row.metadata.get('occupations', row.metadata.get('occupation', []))
            raw = [raw] if isinstance(raw, str) else raw
            musical = isinstance(raw, list) and any(isinstance(v, str) and norm(re.sub(r'[_-]', ' ', v)) in occupations for v in raw)
            external = row.metadata.get('external', {})
            service = isinstance(external, dict) and any(isinstance(external.get(k), dict) and bool(external[k].get('id'))
                                                       for k in ('musicbrainz', 'lastfm', 'spotify'))
            if musical or service:
                kind = 'urn:entity:person'
        if kind is not None:
            canonical_name(row.name)
            profile = {'entity_id': row.entity_id, 'name': row.name, 'type': kind}
            profile_hash(profile)
            candidates.append(profile)
    need(candidates, 'No verified musical identity candidates were returned; no substitution.')
    return candidates


def search_identities(request, output, expected_plan_hash, settings, *, minimum_model_interval_seconds=None, _test_adapters=None):
    plan = prepare_plan(request, output, minimum_model_interval_seconds=minimum_model_interval_seconds)
    need(plan['plan_sha256'] == expected_plan_hash, 'The reviewed identity-search plan changed.')
    need(isinstance(settings.api_key, str) and settings.api_key.strip(), 'Configure Qloo privately.')
    need(not contains_secret(plan, (settings.api_key,)), 'Private credentials must never enter identity inputs.')
    output = safe_directory_path(Path(output))
    testing = _test_adapters is not None
    source = 'test-double-only' if testing else SOURCE
    transport_factory = _test_adapters[1] if testing else lambda: LiveTransport(settings, timeout=120)
    with execution_lease(output.parent):
        output.mkdir(mode=0o700)
        ledger = Ledger(output, source, (settings.api_key,))
        ledger.write('individual-plan.json', plan)
        ledger.record('individual_plan_frozen', {'plan_sha256': plan['plan_sha256'], 'model_calls': 0, 'qloo_calls': 0})
        report = {'schema_version': 5, 'created_utc': utc_now(), 'run_id': ledger.run_id, 'mode': MODE,
            'phase': 'IDENTITY_SEARCH', 'source': source, 'status': 'INCOMPLETE', 'plan_sha256': plan['plan_sha256'],
            'identity_queries': plan['request']['artists'], 'identity_candidates': {}, 'qloo_attempts': 0,
            'model_attempts': 0, 'model_load_attempts': 0, 'error_class': None,
            'causal_gate': 'NOT_EVALUATED', 'behavioral_gate': 'NOT_EVALUATED', 'integration_gate': 'NOT_EVALUATED',
            'preference_gate': 'NOT_EVALUATED', 'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
            'release_approved': False, 'independent_validation_claim': False, 'partial_evidence_preserved': True}
        client = None
        try:
            client = QlooClient(transport_factory(), ledger, max_requests=2, max_attempts=1)
            for label in ('A', 'B'):
                if label == 'B':
                    time.sleep(1)
                query = plan['request']['artists'][label]
                body = client.get('/search', {'query': query, 'take': 5, 'types': 'urn:entity:artist,urn:entity:person'}, cache=False)
                event = ledger.events[-1]
                candidates = music_candidates(body)
                ledger.record('identity_candidates_recorded', {'label': label, 'query': query,
                    'sample_sha256': sha(ledger.directory/event['data']['sample']), 'candidates_sha256': fingerprint(candidates)})
                report['identity_candidates'][label] = candidates
            ledger.record('identity_search_complete', {'plan_sha256': plan['plan_sha256'],
                'identity_candidates_sha256': fingerprint(report['identity_candidates']), 'qloo_calls': 2, 'model_calls': 0})
            report['status'] = 'AWAITING_IDENTITY_CONFIRMATION'
        except BaseException as exc:
            report['error_class'] = type(exc).__name__
            ledger.record('stopped_without_retry', {'error_class': type(exc).__name__})
            if not isinstance(exc, (AffinityQAError, OSError)):
                raise
        finally:
            report['qloo_attempts'] = getattr(client, 'requests', 0)
            # Immutable copy seals the exact search prefix before continuation.
            raw = (ledger.directory/'ledger.jsonl').read_bytes()
            with (ledger.directory/'identity-ledger.jsonl').open('xb') as handle:
                handle.write(raw)
            ledger.write('identity-report.json', report)
        return report, ledger.directory


def selection_profiles(receipt, selected_entity_ids):
    from .cinema_identity_verify import selection_profiles as verified_selection
    return verified_selection(receipt, selected_entity_ids)


def capture_confirmed(directory, selected_entity_ids, identity_receipt, settings, remote_key, *, _test_adapters=None, _test_pacing_clock=None):
    from .cinema_identity_verify import verify_identity_search
    directory = safe_directory_path(Path(directory))
    need(isinstance(settings.api_key, str) and settings.api_key.strip(), 'Configure Qloo privately.')
    need(isinstance(remote_key, str) and re.fullmatch(r'[!-~]{20,512}', remote_key), 'Configure Groq privately.')
    secrets = (settings.api_key, remote_key)
    with execution_lease(directory.parent.parent):
        current = verify_identity_search(directory)
        need(isinstance(identity_receipt, dict), 'A verified identity receipt is required.')
        from .individual_verify import instant
        need('verified_utc' in identity_receipt, 'A verified identity receipt timestamp is required.')
        try:
            instant(identity_receipt['verified_utc'])
        except (ValueError, TypeError):
            raise SchemaError('A valid UTC identity receipt timestamp is required.') from None
        need(fingerprint({k: v for k, v in current.items() if k != 'verified_utc'})
             == fingerprint({k: v for k, v in identity_receipt.items() if k != 'verified_utc'}), 'Identity receipt or search artifacts changed.')
        profiles = selection_profiles(current, selected_entity_ids)
        plan = strict_json((directory/'individual-plan.json').read_bytes())
        testing = _test_adapters is not None
        need(current['source'] == ('test-double-only' if testing else SOURCE), 'Mixed search/inference provenance is forbidden.')
        need(testing or plan['execution_pacing']['configured'], 'Real inference requires reviewed pacing.')
        need(_test_pacing_clock is None or testing, 'Simulated pacing cannot enter real execution.')
        need(not contains_secret((plan, identity_receipt, profiles), secrets), 'Private credentials must not enter confirmed inputs.')
        ledger = Ledger.__new__(Ledger)
        ledger.directory, ledger.run_id, ledger.source, ledger.secrets = directory, directory.name, current['source'], secrets
        ledger.events = [strict_json(line) for line in (directory/'ledger.jsonl').read_bytes().splitlines() if line.strip()]
        ledger.live_requests = current['qloo_attempts']
        report = {'schema_version': 5, 'created_utc': utc_now(), 'run_id': directory.name, 'mode': MODE,
            'phase': 'CONFIRMED_CINEMA', 'source': ledger.source, 'status': 'INCOMPLETE', 'plan_sha256': plan['plan_sha256'],
            'identity_queries': plan['request']['artists'], 'chosen_identities': profiles,
            'causal_gate': 'NOT_EVALUATED', 'behavioral_gate': 'NOT_EVALUATED', 'integration_gate': 'NOT_EVALUATED',
            'preference_gate': 'NOT_EVALUATED', 'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
            'release_approved': False, 'independent_validation_claim': False, 'independent_verification': 'PENDING',
            'error_class': None, 'qloo_attempts': 2, 'model_attempts': 0, 'model_load_attempts': 0,
            'admitted_model_slots': 0, 'requested_profiles': 2, 'successful_profiles': 0, 'failed_model_attempts': 0,
            'unattempted_profiles': 2, 'cinema_results': {}, 'partial_evidence_preserved': True}
        engine = client = pacer = None
        engine_source = 'test-double-only' if testing else 'remote-llm'
        engine_factory, transport_factory = _test_adapters or (
            lambda: CinemaMovieAgent(remote_key, forbidden_secrets=(settings.api_key,)),
            lambda: LiveTransport(settings, timeout=120))
        try:
            confirmation = {'schema_version': 1, 'protocol_version': PROTOCOL, 'run_id': directory.name,
                'plan_sha256': plan['plan_sha256'], 'identity_search_receipt': copy.deepcopy(identity_receipt),
                'identity_search_receipt_sha256': fingerprint(identity_receipt),
                'selected_entity_ids': dict(selected_entity_ids), 'selected_profiles': profiles}
            ledger.write('confirmation.json', confirmation)
            ledger.record('identities_confirmed', {'confirmation_sha256': sha(directory/'confirmation.json'),
                'identity_search_receipt_sha256': fingerprint(identity_receipt), 'selected_profiles_sha256': fingerprint(profiles)})
            ledger.write('individual-identities.json', profiles)
            engine = engine_factory()
            need(engine.source == engine_source and engine.calls == 0
                 and fingerprint(engine.manifest) == fingerprint(model_manifest(engine_source, max_calls=2, cinema=True)),
                 'Confirmed cinema operator differs from the reviewed contract.')
            ledger.write('model-manifest.json', engine.manifest)
            client = QlooClient(transport_factory(), ledger, max_requests=4, max_attempts=1)
            client.requests = 2
            contexts = {}
            for label in ('A', 'B'):
                time.sleep(1)
                profile = profiles[label]
                client.get('/v2/insights', {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': 20,
                    'signal.interests.entities': profile['entity_id'],
                    'filter.results.entities': ','.join(sorted(r['entity_id'] for r in plan['request']['catalog']))}, cache=False)
                sample_path = directory/ledger.events[-1]['data']['sample']
                sample = strict_json(sample_path.read_bytes())
                contexts[profile_hash(profile)] = context_from_sample(profile, plan['request']['catalog'], sample, sha(sample_path))
            need(not contains_secret(contexts, secrets), 'Private data must not enter the model context.')
            ledger.write('individual-tool-inputs.json', contexts)
            ledger.record('all_tool_inputs_frozen', {'sha256': fingerprint(contexts), 'model_calls': 0, 'qloo_calls': 4})
            pacer = PacedRemoteAgent(engine, plan['execution_pacing'], ledger, _test_clock=_test_pacing_clock)
            session = CinemaSession(pacer, ledger, contexts)
            for label in ('A', 'B'):
                profile, preferences = profiles[label], plan['request']['preferences'][label]
                request = make_request(plan['request']['catalog'], profile, contexts[profile_hash(profile)], preferences,
                                       'cinema-' + directory.name + '-' + label)
                uncached, cached = session.rank(request), session.rank(request)
                need(not uncached['trace']['cache_hit'] and cached['trace']['cache_hit']
                     and uncached['ranking'] == cached['ranking'] and uncached['delivery'] == cached['delivery'],
                     'Confirmed cinema cache changed the intent or raw decision.')
                reference = baseline(contexts[profile_hash(profile)], plan['request']['catalog'], preferences)
                result = result_projection(profile, preferences, uncached, reference)
                ledger.write('cinema-result-' + label + '.json', {'schema_version': 1, 'label': label,
                    'effective_request': request, 'uncached_boundary': uncached, 'cached_boundary': cached,
                    'baseline': reference, 'result': result})
                report['cinema_results'][label] = result
            report.update(status='COMPLETE', preference_gate='PASS')
        except BaseException as exc:
            report['error_class'] = type(exc).__name__
            ledger.record('stopped_without_retry', {'error_class': type(exc).__name__})
            if not isinstance(exc, (AffinityQAError, OSError)):
                raise
        finally:
            report['qloo_attempts'] = getattr(client, 'requests', 2)
            report['model_attempts'] = getattr(engine, 'calls', 0)
            report['admitted_model_slots'] = getattr(pacer, 'slots', 0)
            report['successful_profiles'] = len(report['cinema_results'])
            report['failed_model_attempts'] = report['model_attempts'] - len(getattr(engine, 'observations', []))
            report['unattempted_profiles'] = 2 - report['model_attempts']
            ledger.write('individual-report.json', report)
        return report, directory
