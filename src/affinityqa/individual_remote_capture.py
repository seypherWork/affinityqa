"""Separately versioned remote capture; no inference during plan preparation.

Qloo/tool preflight and the unchanged causal operator run only after explicit
admission of the exact plan. Nothing is downloaded or loaded on the owner PC.
"""
import copy
from pathlib import Path
import re
import time

from .agents import strict_json
from .causal_agent import PROTOCOL, context_from_sample, profile_hash, validate_catalog
from .causal_runner import capture_pair, freeze_policy
from .errors import AffinityQAError
from .evidence import Ledger, fingerprint, utc_now
from .groq_agent import GroqToolContextMovieAgent, MODEL, contains_secret, model_manifest
from .individual_capture import canonical_name, execution_lease, need, resolve_music, safe_directory_path, sha
from .qloo import LiveTransport, QlooClient
from .remote_pacing import PacedRemoteAgent, pacing_policy

SOURCES = ('__init__.py', 'agents.py', 'errors.py', 'causal_agent.py', 'causal_runner.py',
           'causal_evaluator.py', 'ollama_agent.py', 'qloo.py', 'models.py', 'metrics.py',
           'evidence.py', 'individual_capture.py', 'groq_agent.py',
           'individual_remote_capture.py', 'individual_verify.py', 'individual_remote_verify.py', 'remote_pacing.py')
MODE = 'individual-remote-capture'
SOURCE = 'qloo-tool+groq-remote-llm'


def backend_comparability(observations):
    """Describe the bounded sample; fingerprints never attest immutable weights."""
    known = sorted({row['system_fingerprint'] for row in observations if row['system_fingerprint'] is not None})
    missing = sum(row['system_fingerprint'] is None for row in observations)
    status = ('NOT_EVALUATED' if len(observations) != 39 else
              'VARIED_AND_ABSENT' if len(known) > 1 and missing else
              'ABSENT' if missing else 'VARIED' if len(known) > 1 else 'STABLE_KNOWN')
    return {'schema_version': 1, 'status': status, 'expected_decisions': 39,
            'observed_decisions': len(observations), 'system_fingerprints': known,
            'missing_fingerprint_decisions': missing,
            'scope': 'Observed provider backend fingerprints across all 39 decisions; immutable weights are not attested.'}


def causal_gate(integration_gate, backend):
    if integration_gate == 'NOT_EVALUATED':
        return 'NOT_EVALUATED'
    if integration_gate == 'FAIL':
        return 'FAIL'
    return 'PASS' if backend['status'] == 'STABLE_KNOWN' else 'INCONCLUSIVE'


def validate_request(value):
    need(isinstance(value, dict) and set(value) == {'schema_version', 'artists', 'catalog', 'model'}, 'Unexpected remote request fields.')
    need(type(value['schema_version']) is int and value['schema_version'] == 2, 'Use remote request version2.')
    artists = value['artists']
    need(isinstance(artists, dict) and set(artists) == {'A', 'B'}, 'Exactly two explicit musical interests are required.')
    for name in artists.values():
        canonical_name(name)
    need(artists['A'].casefold() != artists['B'].casefold(), 'The two interests must differ.')
    validate_catalog(value['catalog'])
    for row in value['catalog']:
        canonical_name(row['name'])
    need(value['model'] == {'provider': 'groq', 'name': MODEL}, 'Only the reviewed remote model is admitted; no local digest.')
    return copy.deepcopy(value)


def read_request(path):
    path = safe_directory_path(Path(path))
    need(path.is_file() and path.stat().st_size <= 100_000, 'Unsafe or oversized remote request.')
    return validate_request(strict_json(path.read_bytes()))


def load_private_credential(path):
    """Explicit private file only: no process-env override or default discovery."""
    path = safe_directory_path(Path(path))
    need(path.is_file() and path.stat().st_size <= 100_000, 'Configure a private provider credential file.')
    values = []
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if separator and key.strip() == 'GROQ_API_KEY':
            values.append(value.strip().strip('\"\''))
    need(len(values) == 1 and re.fullmatch(r'[!-~]{20,512}', values[0]) is not None,
         'Exactly one valid GROQ_API_KEY is required in the private file.')
    return values[0]


def prepare_plan(request, output, *, minimum_model_interval_seconds=None):
    request = validate_request(request)
    output = safe_directory_path(Path(output))
    from .individual_capture import validate_capture_paths
    validate_capture_paths(output)
    need(not output.exists() and output.parent.is_dir(), 'Choose a new output directory with an existing parent.')
    source = Path(__file__).resolve().parent
    root = source.parents[1]
    plan = {'schema_version': 3, 'protocol_version': PROTOCOL, 'mode': MODE,
            'request': request, 'output_directory': str(output),
            'remote_operator': model_manifest('remote-llm'),
            'execution_pacing': pacing_policy(minimum_model_interval_seconds),
            'source_sha256': {name: sha(source/name) for name in SOURCES},
            'driver_sha256': sha(root/'scripts/capture_individual_remote.py'),
            'verification_driver_sha256': sha(root/'scripts/verify_individual_remote.py'),
            'dependencies_lock_sha256': sha(root/'requirements-backend.lock.txt'),
            'maximum_qloo_requests': 4, 'maximum_attempts_per_request': 1,
            'maximum_model_decisions': 39, 'healthy_repeats_per_profile': 3,
            'faults': ['cache-omits-profile', 'stale-profile', 'wrong-tool-profile'],
            'new_model_metadata_requests': 0, 'startup_model_metadata_requests': 0,
            'runtime_model_metadata_requests': 0, 'model_load_requests': 0,
            'individual_demo_only': True, 'independent_validation_claim': False,
            'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
            'partial_failure_policy': 'Preserve all evidence, stop without retry or resume.'}
    plan['plan_sha256'] = fingerprint(plan)
    return plan


def execute_capture(request, output, expected_plan_hash, settings, remote_key, *,
                    minimum_model_interval_seconds=None, _test_adapters=None, _test_pacing_clock=None):
    plan = prepare_plan(request, output, minimum_model_interval_seconds=minimum_model_interval_seconds)
    need(plan['plan_sha256'] == expected_plan_hash, 'The frozen remote plan changed. No execution.')
    need(_test_adapters is not None or plan['execution_pacing']['configured'],
         'Real remote execution requires an explicitly reviewed model interval.')
    need(_test_pacing_clock is None or _test_adapters is not None,'Simulated pacing cannot enter real execution.')
    need(isinstance(settings.api_key, str) and bool(settings.api_key.strip()), 'Configure Qloo privately before execution.')
    need(isinstance(remote_key, str) and re.fullmatch(r'[!-~]{20,512}', remote_key), 'Configure the remote provider privately before execution.')
    secrets = (settings.api_key, remote_key)
    need(not contains_secret(plan, secrets), 'Private credentials must never enter capture inputs.')
    request = copy.deepcopy(plan['request'])
    output = safe_directory_path(Path(output))
    testing = _test_adapters is not None
    ledger_source = 'test-double-only' if testing else SOURCE
    engine_source = 'test-double-only' if testing else 'remote-llm'
    engine_factory, transport_factory = _test_adapters or (
        lambda: GroqToolContextMovieAgent(remote_key, forbidden_secrets=(settings.api_key,)),
        lambda: LiveTransport(settings, timeout=120))
    with execution_lease(output.parent):
        output.mkdir(mode=0o700)
        ledger = Ledger(output, ledger_source, secrets)
        ledger.write('individual-plan.json', plan)
        ledger.record('individual_plan_frozen', {'plan_sha256': plan['plan_sha256'], 'model_calls': 0, 'qloo_calls': 0})
        report = {'schema_version': 3, 'created_utc': utc_now(), 'run_id': ledger.run_id,
                  'mode': MODE, 'source': ledger.source, 'status': 'INCOMPLETE',
                  'causal_gate': 'NOT_EVALUATED', 'behavioral_gate': 'NOT_EVALUATED',
                  'integration_gate': 'NOT_EVALUATED', 'backend_comparability': backend_comparability([]),
                  'integration_gate_scope': 'All nine unchanged checks for all three declared faults; a failure is an observed checklist failure, not attribution of its cause.',
                  'causal_gate_scope': 'Integration checks pass and all 39 observed backend fingerprints are known and identical; fingerprints do not attest immutable weights.',
                  'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED', 'release_approved': False,
                  'plan_sha256': plan['plan_sha256'], 'model_attempts': 0, 'qloo_attempts': 0,
                  'model_attempts_scope': 'Remote ranking requests, including the first failed attempt; no startup calls or loading.',
                  'model_load_attempts': 0,
                  'behavioral_gate_scope': 'All three declared faults; at least one observed recovery repeat for each. Observed behavior alone does not causally attribute a recovery to repair.',
                  'independent_verification': 'PENDING', 'error_class': None}
        engine = client = pacer = None
        try:
            engine = engine_factory()
            need(engine.source == engine_source and fingerprint(engine.manifest) == fingerprint(model_manifest(engine_source)),
                 'Remote operator identity, options, budget or provenance differs from the plan.')
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
            profiles = {p: resolve_music(name, get('/search', {'query': name, 'take': 5})[0]) for p, name in request['artists'].items()}
            need(len({p['entity_id'] for p in profiles.values()}) == 2, 'Resolved profiles coincide; no substitution.')
            ledger.write('individual-identities.json', profiles)
            contexts = {}
            for profile in profiles.values():
                _, sample, digest = get('/v2/insights', {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': 20,
                    'signal.interests.entities': profile['entity_id'], 'filter.results.entities': ','.join(sorted(r['entity_id'] for r in request['catalog']))})
                contexts[profile_hash(profile)] = context_from_sample(profile, request['catalog'], sample, digest)
            need(not contains_secret(contexts, secrets), 'Private data must not enter the model context.')
            ledger.write('individual-tool-inputs.json', contexts)
            ledger.record('all_tool_inputs_frozen', {'sha256': fingerprint(contexts), 'model_calls': 0, 'qloo_calls': client.requests})
            pair = {'pair_id': 'individual-'+ledger.run_id, 'artists': request['artists'], 'split': 'individual-demonstration'}
            policy_plan = {'pairs': [pair], 'catalog_sha256': fingerprint(request['catalog']), 'source_sha256': plan['source_sha256']}
            def freeze(noise, healthy, controls):
                return freeze_policy(noise, healthy, controls, plan=policy_plan, manifest=engine.manifest, ledger=ledger)
            pacer = PacedRemoteAgent(engine, plan['execution_pacing'], ledger, _test_clock=_test_pacing_clock)
            _, summary, policy = capture_pair(pacer, ledger, pair, request['catalog'], profiles, contexts, freeze=freeze)
            recovered = {c['fault']: c['behavioral_recovery_observed_repeats'] for c in summary['cases']}
            integration = 'PASS' if all(c['passing'] for c in summary['cases']) else 'FAIL'
            backend = backend_comparability(engine.observations)
            report.update(status='COMPLETE', passing=sum(c['passing'] for c in summary['cases']), denominator=3,
                          integration_gate=integration, backend_comparability=backend,
                          causal_gate=causal_gate(integration, backend),
                          behavioral_gate='OBSERVED_RECOVERY' if all(recovered.values()) else 'INCONCLUSIVE',
                          observed_recoveries_by_fault=recovered, summary=summary, policy_sha256=policy['policy_sha256'])
        except BaseException as exc:
            report['error_class'] = type(exc).__name__
            ledger.record('stopped_without_retry', {'error_class': type(exc).__name__})
            if not isinstance(exc, (AffinityQAError, OSError)):
                raise
        finally:
            report['backend_comparability'] = backend_comparability(getattr(engine, 'observations', []))
            report['model_attempts'] = getattr(engine, 'calls', 0)
            report['admitted_model_slots'] = getattr(pacer, 'slots', 0)
            report['qloo_attempts'] = getattr(client, 'requests', 0)
            report['partial_evidence_preserved'] = True
            ledger.write('individual-report.json', report)
        return report, ledger.directory
