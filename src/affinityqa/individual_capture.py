"""One explicitly planned local capture, separate from frozen historical studies.

No network, credentials or filesystem writes occur while preparing a plan.
New decisions require an explicit execution call with that exact plan hash.
This module supplies no public HTTP execution endpoint.
"""
from contextlib import contextmanager
import copy
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import stat
import time
import unicodedata
from urllib.parse import urlsplit

from .agents import strict_json
from .causal_agent import PROTOCOL, ToolContextMovieAgent, context_from_sample, profile_hash, validate_catalog
from .causal_runner import capture_pair, freeze_policy
from .errors import AffinityQAError, SchemaError
from .evidence import Ledger, fingerprint, redact, utc_now
from .models import parse_entities, validate_response_envelope
from .qloo import LiveTransport, QlooClient

SOURCES = ('__init__.py', 'agents.py', 'errors.py', 'causal_agent.py', 'causal_runner.py',
           'causal_evaluator.py', 'ollama_agent.py', 'qloo.py', 'models.py', 'metrics.py',
           'evidence.py', 'individual_capture.py')
LOCK_MARKER = b'AffinityQA individual capture lock v1\n'
WINDOWS_PATHS = os.name == 'nt'


def need(condition, message):
    if not condition:
        raise SchemaError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical_name(value):
    need(isinstance(value, str) and 1 <= len(value) <= 300, 'A bounded explicit name is required.')
    need(value == ' '.join(unicodedata.normalize('NFKC', value).split())
         and not any(unicodedata.category(c).startswith('C') for c in value), 'Use a canonical printable name.')
    return value


def validate_request(value):
    need(isinstance(value, dict) and set(value) == {'schema_version', 'artists', 'catalog', 'model'}, 'Unexpected capture request fields.')
    need(type(value['schema_version']) is int and value['schema_version'] == 1, 'Unsupported capture request version.')
    artists = value['artists']
    need(isinstance(artists, dict) and set(artists) == {'A', 'B'}, 'Exactly two explicit musical interests are required.')
    for name in artists.values():
        canonical_name(name)
    need(artists['A'].casefold() != artists['B'].casefold(), 'The two interests must differ.')
    validate_catalog(value['catalog'])
    for row in value['catalog']:
        canonical_name(row['name'])
    model = value['model']
    need(isinstance(model, dict) and set(model) == {'name', 'digest'}, 'An installed model name and digest are required.')
    need(isinstance(model['name'], str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}', model['name'])
         and not model['name'].endswith(':cloud'), 'Use an explicitly installed local model.')
    need(isinstance(model['digest'], str) and re.fullmatch(r'[0-9a-f]{64}', model['digest']), 'An exact model SHA-256 digest is required.')
    return copy.deepcopy(value)


def read_request(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 100_000, 'Unsafe or oversized request file.')
    return validate_request(strict_json(path.read_bytes()))


def safe_directory_path(path):
    path = path.absolute()
    for member in (path, *path.parents):
        need(not member.is_symlink() and not (hasattr(member, 'is_junction') and member.is_junction()), 'Linked output paths are not accepted.')
    return path


def validate_capture_paths(output):
    """Reject unsupported Windows paths before keys, admission or inference."""
    if not WINDOWS_PATHS:
        return
    output=Path(output).absolute()
    run_id='20000101T000000Z-'+'0'*8  # Same fixed length as Ledger.run_id.
    directory=output/run_id
    names=('individual-plan.json','individual-report.json','individual-identities.json',
           'individual-tool-inputs.json','model-manifest.json','frozen-causal-policy.json',
           'ledger.jsonl','http-9999.json','causal-execution-039.json',
           'causal-pair-individual-'+run_id+'.json',
           'causal-summary-individual-'+run_id+'.json')
    units=lambda value:len(str(value).encode('utf-16-le'))//2
    need(all(units(member)<248 for member in (directory,*directory.parents))
         and all(units(directory/name)<260 for name in names)
         and all(units(part)<=255 for path in (directory,*(directory/name for name in names))
                 for part in path.parts),
         'Windows capture paths are too long. Choose a shorter storage or output root before execution.')


def prepare_plan(request, output, url):
    request = validate_request(request)
    parsed = urlsplit(url)
    try:
        address = ipaddress.ip_address(parsed.hostname or '')
        port = parsed.port
    except ValueError:
        raise SchemaError('Use an explicit loopback Ollama URL.') from None
    need(parsed.scheme == 'http' and address.is_loopback and port is not None and 1024 <= port <= 65535
         and not parsed.username and not parsed.password and parsed.path in ('', '/')
         and not parsed.query and not parsed.fragment, 'Only explicit local loopback Ollama is accepted.')
    output = safe_directory_path(output)
    validate_capture_paths(output)
    need(not output.exists() and output.parent.is_dir(), 'Choose a new output directory with an existing parent.')
    source = Path(__file__).resolve().parent
    plan = {'schema_version': 1, 'protocol_version': PROTOCOL, 'mode': 'individual-local-capture',
            'request': request, 'output_directory': str(output), 'ollama_url': url.rstrip('/'),
            'source_sha256': {name: sha(source / name) for name in SOURCES},
            'driver_sha256': sha(source.parents[1] / 'scripts/capture_individual_pair.py'),
            'dependencies_lock_sha256': sha(source.parents[1] / 'requirements-backend.lock.txt'),
            'maximum_qloo_requests': 4, 'maximum_attempts_per_request': 1,
            'maximum_model_decisions': 39, 'healthy_repeats_per_profile': 3,
            'faults': ['cache-omits-profile', 'stale-profile', 'wrong-tool-profile'],
            'new_model_metadata_requests': 3, 'startup_model_metadata_requests': 2,
            'runtime_model_metadata_requests': 1, 'model_load_requests': 1,
            'individual_demo_only': True, 'independent_validation_claim': False,
            'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
            'partial_failure_policy': 'Preserve all evidence, stop without retry or resume.'}
    plan['plan_sha256'] = fingerprint(plan)
    return plan


@contextmanager
def execution_lease(parent):
    """OS lock, released on process exit. Marker is retained without replacement."""
    path = safe_directory_path(parent) / '.affinityqa-individual.lock'
    flags = os.O_RDWR | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            need(os.write(fd, LOCK_MARKER) == len(LOCK_MARKER), 'Execution lock initialization was incomplete.')
        except BaseException:
            os.close(fd)
            raise
    except FileExistsError:
        need(not path.is_symlink() and not (hasattr(path, 'is_junction') and path.is_junction()), 'Unsafe execution lock.')
        fd = os.open(path, flags)
    locked = False
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SchemaError('Another individual capture uses this output parent. No provider call started.') from None
        locked = True
        need(stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_size == len(LOCK_MARKER)
             and os.read(fd, len(LOCK_MARKER)) == LOCK_MARKER, 'Unrecognized execution lock file.')
        yield
    finally:
        if locked:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def resolve_music(name, body):
    """Exact observations only; retain disjoint types, never merge metadata."""
    validate_response_envelope(body, insights=False)
    observations = []
    for raw in body['results']:
        entity = parse_entities({'results': [raw]}, insights=False)[0]
        duplicate = False
        for old_raw, old in observations:
            if old.entity_id != entity.entity_id:
                continue
            if old_raw == raw:
                duplicate = True
                break
            need(old.name.casefold() == entity.name.casefold() and not set(old.types).intersection(entity.types), 'Conflicting identity observations.')
        if not duplicate:
            observations.append((raw, entity))
    normalize = lambda text: ' '.join(unicodedata.normalize('NFKC', text).casefold().split())
    exact = [e for _, e in observations if normalize(e.name) == normalize(name)]
    artists = [e for e in exact if 'urn:entity:artist' in e.types]
    need(len(artists) <= 1, 'Ambiguous exact artist identity.')
    if artists:
        selected = artists[0]
        return {'entity_id': selected.entity_id, 'name': name, 'type': 'urn:entity:artist'}
    people = [e for e in exact if 'urn:entity:person' in e.types]
    need(len(people) == 1, 'No unique exact musical identity.')
    selected = people[0]
    occupations = selected.metadata.get('occupations', selected.metadata.get('occupation', []))
    if isinstance(occupations, str):
        occupations = [occupations]
    occupations = occupations if isinstance(occupations, list) else []
    musical = {'musician', 'singer', 'singer songwriter', 'songwriter', 'rapper', 'composer', 'pianist',
               'guitarist', 'harpist', 'record producer', 'music producer'}
    accepted = any(isinstance(v, str) and normalize(re.sub(r'[_-]', ' ', v)) in musical for v in occupations)
    external = selected.metadata.get('external', {})
    service = isinstance(external, dict) and any(isinstance(external.get(k), dict) and bool(external[k].get('id')) for k in ('musicbrainz', 'lastfm', 'spotify'))
    need(accepted or service, 'A person requires explicit musical metadata; no guessing.')
    return {'entity_id': selected.entity_id, 'name': name, 'type': 'urn:entity:person'}


def execute_capture(request, output, url, expected_plan_hash, settings, *, _test_adapters=None):
    plan = prepare_plan(request, output, url)
    need(plan['plan_sha256'] == expected_plan_hash, 'Request, operator, output or model plan changed. No execution.')
    need(isinstance(settings.api_key, str) and bool(settings.api_key.strip()), 'Configure the Qloo credential locally before execution.')
    request = copy.deepcopy(plan['request'])
    need(redact(request, (settings.api_key,)) == request, 'A credential must never appear in capture inputs.')
    output = safe_directory_path(output)
    testing = _test_adapters is not None
    engine_factory, transport_factory = _test_adapters or (
        lambda: ToolContextMovieAgent(url, request['model']['name'], timeout=45, max_calls=39),
        lambda: LiveTransport(settings, timeout=120))
    with execution_lease(output.parent):
        output.mkdir(mode=0o700)
        ledger = Ledger(output, 'test-double-only' if testing else 'qloo-tool+local-llm', (settings.api_key,))
        ledger.write('individual-plan.json', plan)
        ledger.record('individual_plan_frozen', {'plan_sha256': plan['plan_sha256'], 'model_calls': 0, 'qloo_calls': 0})
        report = {'schema_version': 1, 'created_utc': utc_now(), 'run_id': ledger.run_id,
                  'mode': 'individual-local-capture', 'source': ledger.source,
                  'status': 'INCOMPLETE', 'causal_gate': 'NOT_EVALUATED', 'behavioral_gate': 'NOT_EVALUATED',
                  'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED', 'release_approved': False,
                  'plan_sha256': plan['plan_sha256'], 'model_attempts': 0, 'qloo_attempts': 0,
                  'model_attempts_scope': 'Ranking decisions only; startup metadata and loading are separate.',
                  'model_load_attempts': 0,
                  'behavioral_gate_scope': 'All three declared faults; at least one observed recovery repeat for each.',
                  'independent_verification': 'PENDING', 'error_class': None}
        engine = client = None
        try:
            engine = engine_factory()
            need(engine.manifest.get('model') == request['model']['name'] and engine.manifest.get('model_digest') == request['model']['digest']
                 and engine.manifest.get('max_inference_calls') == 39, 'Installed model identity or budget differs from the frozen plan.')
            ledger.write('model-manifest.json', engine.manifest)
            client = QlooClient(transport_factory(), ledger, max_requests=4, max_attempts=1)
            last = None
            def get(path, params):
                nonlocal last
                if last is not None:
                    time.sleep(max(0, 1 - (time.monotonic() - last)))
                last = time.monotonic()
                body = client.get(path, params, cache=False)
                event = next(e for e in reversed(ledger.events) if e['kind'] == 'tool_call')
                sample_path = ledger.directory / event['data']['sample']
                return body, strict_json(sample_path.read_bytes()), sha(sample_path)
            profiles = {p: resolve_music(name, get('/search', {'query': name, 'take': 5})[0]) for p, name in request['artists'].items()}
            need(len({p['entity_id'] for p in profiles.values()}) == 2, 'Resolved profiles coincide; no substitution.')
            ledger.write('individual-identities.json', profiles)
            contexts = {}
            for profile in profiles.values():
                _, sample, digest = get('/v2/insights', {'filter.type': 'urn:entity:movie', 'bias.trends': 'off', 'take': 20,
                    'signal.interests.entities': profile['entity_id'], 'filter.results.entities': ','.join(sorted(r['entity_id'] for r in request['catalog']))})
                contexts[profile_hash(profile)] = context_from_sample(profile, request['catalog'], sample, digest)
            ledger.write('individual-tool-inputs.json', contexts)
            ledger.record('all_tool_inputs_frozen', {'sha256': fingerprint(contexts), 'model_calls': 0, 'qloo_calls': client.requests})
            report['model_load_attempts'] += 1
            ledger.write('model-readiness.json', engine.warmup())
            pair = {'pair_id': 'individual-' + ledger.run_id, 'artists': request['artists'], 'split': 'individual-demonstration'}
            policy_plan = {'pairs': [pair], 'catalog_sha256': fingerprint(request['catalog']), 'source_sha256': plan['source_sha256']}
            def freeze(noise, healthy, controls):
                return freeze_policy(noise, healthy, controls, plan=policy_plan, manifest=engine.manifest, ledger=ledger)
            record, summary, policy = capture_pair(engine, ledger, pair, request['catalog'], profiles, contexts, freeze=freeze)
            recovered = {c['fault']: c['behavioral_recovery_observed_repeats'] for c in summary['cases']}
            report.update(status='COMPLETE', passing=sum(c['passing'] for c in summary['cases']), denominator=3,
                          causal_gate='PASS' if all(c['passing'] for c in summary['cases']) else 'FAIL',
                          behavioral_gate='OBSERVED_RECOVERY' if all(recovered.values()) else 'INCONCLUSIVE',
                          observed_recoveries_by_fault=recovered,
                          summary=summary, policy_sha256=policy['policy_sha256'])
        except BaseException as exc:
            report['error_class'] = type(exc).__name__
            ledger.record('stopped_without_retry', {'error_class': type(exc).__name__})
            if not isinstance(exc, (AffinityQAError, OSError)):
                raise
        finally:
            report['model_attempts'] = getattr(engine, 'calls', 0)
            report['qloo_attempts'] = getattr(client, 'requests', 0)
            report['partial_evidence_preserved'] = True
            ledger.write('individual-report.json', report)
        return report, ledger.directory
