"""Reusable SYNTHETIC capture for isolated integration/preview tests only.

No provider, model, SQLite or credential access occurs. Callers select the
reviewed source through PYTHONPATH and provide a NEW root inside their fixture
sandbox. The receipt below is fabricated test data, never empirical acceptance.
Do not install it in a real service. A browser harness must retain an explicit
SYNTHETIC banner: the production summary contains historical real-capture copy.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import test_causal_agent as fixture_module
from test_causal_agent import FakeEngine, FakeLedger
from affinityqa import causal_agent
from affinityqa.causal_agent import FAULTS, context_from_sample, profile_hash
from affinityqa.causal_runner import capture_pair, freeze_policy
from affinityqa.evidence import fingerprint

RUN_ID = '20261019T000000Z-00000000'
PAIR_ID = 'causal-development-01'
EXECUTION_ID = '20261019T000000Z-11111111'
SYNTHETIC = 'SYNTHETIC_TEST_ONLY_NO_PROVIDER_OR_MODEL_CALLS'
SOURCES = ('causal_agent.py', 'causal_runner.py', 'causal_evaluator.py',
           'ollama_agent.py', 'qloo.py', 'models.py', 'metrics.py', 'evidence.py')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       allow_nan=False, indent=2) + '\n').encode('utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _new(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as output:
        output.write(data)


def _events(rows):
    return b''.join((json.dumps({
        'sequence': number, 'timestamp_utc': '2026-10-19T00:00:00.000000Z',
        'kind': kind, 'data': value,
    }, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
        for number, (kind, value) in enumerate(rows, 1))


class SyntheticEngine(FakeEngine):
    """Deterministic fixture; complete canonical payload, no model transport."""

    def __init__(self):
        super().__init__()
        self.manifest = {'source': SYNTHETIC, 'model': 'synthetic-no-inference',
                         'options': {'num_ctx': 8192}}

    def rank(self, request):
        count = len(request['catalog'])
        schema = {'type': 'object', 'properties': {'ordered_catalog_indices': {
            'type': 'array', 'items': {'type': 'integer', 'enum': list(range(count))},
            'minItems': count, 'maxItems': count,
        }}, 'required': ['ordered_catalog_indices'], 'additionalProperties': False}
        self.calls += 1
        self.last_input = self.adapter.decision_input(request, schema)
        identities = [row['entity_id'] for row in request['catalog']]
        ranking = [identities[row['catalog_index']]
                   for row in self.last_input['provider_movie_context']]
        self.observations.append({
            'call': self.calls, 'input_sha256': fingerprint(self.last_input),
            'output_sha256': fingerprint(ranking), 'done': True,
            'done_reason': 'stop', 'private_thinking_recorded': False,
            'prompt_eval_count': 128,
        })
        return {'schema_version': 1, 'request_id': request['request_id'],
                'ranked_entity_ids': ranking}


@dataclass
class SyntheticCapture:
    root: Path
    source_root: Path
    profiles: dict

    @property
    def run_id(self):
        return RUN_ID

    @property
    def run(self):
        return self.root / 'runs' / RUN_ID

    @property
    def receipt_path(self):
        return self.root / 'evidence' / ('CAUSAL-REPAIR-' + RUN_ID + '.json')

    @property
    def receipt_sha256(self):
        return sha(self.receipt_path)

    @property
    def artists(self):
        return {label: profile['name'] for label, profile in self.profiles.items()}

    @property
    def profile_names(self):
        return {profile_hash(profile): profile['name']
                for profile in self.profiles.values()}

    @property
    def packet_paths(self):
        return sorted((self.run / 'pair-executions' / EXECUTION_ID)
                      .glob('causal-execution-*.json'))

    def inventory(self):
        return {path.relative_to(self.run).as_posix(): sha(path)
                for path in self.run.rglob('*') if path.is_file()}

    def _own(self):
        marker = json.loads((self.root / 'SYNTHETIC-FIXTURE.json').read_bytes())
        if marker != {'provenance': SYNTHETIC, 'run_id': RUN_ID}:
            raise ValueError('Only the exclusive synthetic fixture may be modified.')

    def rewrite_run_json(self, relative, transform):
        """Negative tests only: rewrite an existing JSON inside this fixture."""
        self._own()
        name = Path(relative)
        if name.is_absolute() or '..' in name.parts or name.suffix != '.json':
            raise ValueError('One fixture-local JSON is required.')
        path = self.run / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(self.run.resolve()):
            raise ValueError('Existing unlinked fixture JSON required.')
        value = json.loads(path.read_bytes())
        transform(value)
        path.write_bytes(encoded(value))

    def reseal_for_negative_test(self):
        """Rehash fabricated artifacts, preserving the fake report/source pins.

        This is deliberately NOT a verifier and must never touch a real receipt.
        It allows tests to reach semantic guards beyond byte-hash detection.
        """
        self._own()
        receipt = json.loads(self.receipt_path.read_bytes())
        receipt['artifact_sha256'] = self.inventory()
        self.receipt_path.write_bytes(encoded(receipt))


def build_synthetic_capture(root, source_root=None):
    """Create one fresh fixture compatible with _verified and replay_causal.

    Returns SyntheticCapture with receipt_path/receipt_sha256, artists,
    profile_names and paths usable by create_public_app(..., case_manager=None).
    The caller may pass its isolated production export as web_root for browser
    tests. No CLI capture/verifier main is called, and no realness is asserted.
    """
    installed = Path(causal_agent.__file__).resolve().parents[2]
    source = installed if source_root is None else Path(source_root).resolve()
    if any((source / 'src/affinityqa' / name).read_bytes() !=
           (installed / 'src/affinityqa' / name).read_bytes() for name in SOURCES):
        raise ValueError('Fixture source must match the selected installed operator.')
    root = Path(root).absolute()
    if not root.parent.is_dir() or root.exists():
        raise FileExistsError('A new fixture root with an existing sandbox parent is required.')
    for parent in [root.parent, *root.parent.parents]:
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise ValueError('Linked fixture parents are not accepted.')
    root.mkdir()
    _new(root / 'SYNTHETIC-FIXTURE.json', encoded({'provenance': SYNTHETIC, 'run_id': RUN_ID}))
    source_hashes = {}
    for name in SOURCES:
        original = source / 'src/affinityqa' / name
        _new(root / 'src/affinityqa' / name, original.read_bytes())
        source_hashes[name] = sha(original)
    driver = source / 'scripts/run_causal_repair.py'
    _new(root / 'scripts/run_causal_repair.py', driver.read_bytes())

    public = fixture_module.CausalAgentTests()
    public.setUp()
    profiles = dict(zip(('A', 'B'), copy.deepcopy(public.profiles)))
    for label, profile in profiles.items():
        profile['name'] = 'SYNTHETIC artist ' + label
    fixture = SyntheticCapture(root, source, profiles)
    catalog_path = root / 'synthetic/catalog.json'
    _new(catalog_path, encoded({'provenance': SYNTHETIC, 'catalog': public.catalog}))

    contexts = {}
    for number, profile in enumerate(profiles.values(), 1):
        sample = public.raw(profile, number - 1)
        sample['fixture_provenance'] = SYNTHETIC
        # True is needed by the legacy parser contract, not proof of a send.
        sample['live_network_request'] = True
        path = fixture.run / ('http-%04d.json' % number)
        _new(path, encoded(sample))
        contexts[profile_hash(profile)] = context_from_sample(
            profile, public.catalog, sample, sha(path))

    engine = SyntheticEngine()
    root_ledger, pair_ledger = FakeLedger(), FakeLedger()
    root_ledger.run_id, pair_ledger.run_id = RUN_ID, EXECUTION_ID
    pair = {'pair_id': PAIR_ID, 'artists': fixture.artists, 'split': 'development'}
    plan = {
        'schema_version': 1, 'protocol_version': 'causal-profile-integrity-v1',
        'fixture_provenance': SYNTHETIC, 'mode': 'SYNTHETIC_TEST_ONLY',
        'pairs': [pair], 'catalog': public.catalog,
        'catalog_sha256': fingerprint(public.catalog), 'manifest': engine.manifest,
        'source_sha256': source_hashes, 'driver_sha256': sha(driver),
        'source_artifact_sha256': {'synthetic/catalog.json': sha(catalog_path)},
        'maximum_model_calls': 39, 'maximum_qloo_requests': 2,
        'maximum_attempts_per_request': 1, 'faults': list(FAULTS), 'repeats': 3,
    }
    plan['plan_sha256'] = fingerprint(plan)
    root_ledger.write('causal-plan.json', plan)
    root_ledger.write('causal-tool-inputs.json', {
        PAIR_ID: {'profiles': profiles, 'contexts': contexts},
    })
    root_ledger.write('causal-execution-binding-' + PAIR_ID + '.json', {
        'pair_id': PAIR_ID, 'directory': 'pair-executions/' + EXECUTION_ID,
    })

    def freeze(noise, healthy, controls):
        return freeze_policy(noise, healthy, controls, plan=plan,
                             manifest=engine.manifest, ledger=root_ledger)

    record, summary, policy = capture_pair(
        engine, pair_ledger, pair, public.catalog, profiles, contexts, freeze=freeze)
    if engine.calls != 39 or len([n for n in pair_ledger.files if n.startswith('causal-execution-')]) != 39:
        raise AssertionError('Synthetic generator did not cover all 39 packets.')
    root_ledger.write('causal-pair-' + PAIR_ID + '.json', record)
    recoveries = sum(case['behavioral_recovery_observed_repeats'] for case in summary['cases'])
    report = {
        'schema_version': 1, 'protocol_version': 'causal-profile-integrity-v1',
        'run_id': RUN_ID, 'status': 'COMPLETE', 'mode': 'SYNTHETIC_TEST_ONLY',
        'source': SYNTHETIC, 'fixture_provenance': SYNTHETIC,
        'plan_sha256': plan['plan_sha256'], 'pairs': [summary],
        'model_calls': 39, 'qloo_requests': 2, 'total_qloo_requests': 2,
        'denominator': 3, 'passing': sum(case['passing'] for case in summary['cases']),
        'causal_gate': 'PASS' if all(case['passing'] for case in summary['cases']) else 'FAIL',
        'behavioral_gate': 'OBSERVED_RECOVERY' if recoveries else 'INCONCLUSIVE',
        'behavioral_recoveries_observed': recoveries,
        'policy_sha256': policy['policy_sha256'], 'noise_barrier': policy['noise_barrier'],
        'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
        'release_approved': False, 'error': None,
        'actual_external_model_calls': 0, 'actual_external_Qloo_calls': 0,
    }
    root_ledger.write('causal-report.json', report)
    for name, value in root_ledger.files.items():
        _new(fixture.run / name, encoded(value))
    _new(fixture.run / 'ledger.jsonl', _events(root_ledger.events))
    execution = fixture.run / 'pair-executions' / EXECUTION_ID
    for name, value in pair_ledger.files.items():
        _new(execution / name, encoded(value))
    _new(execution / 'model-manifest.json', encoded(engine.manifest))
    _new(execution / 'model-readiness.json', encoded({
        'status': 'SYNTHETIC_FIXTURE_ONLY', 'inference_calls': 0,
        'fixture_provenance': SYNTHETIC,
    }))
    _new(execution / 'ledger.jsonl', _events(pair_ledger.events))
    receipt = {
        **report, 'verified_utc': 'SYNTHETIC_FIXTURE_NOT_AN_AUDIT',
        'source_sha256': source_hashes, 'driver_sha256': sha(driver),
        'source_artifact_sha256': plan['source_artifact_sha256'],
        'artifact_sha256': fixture.inventory(),
        'verification_boundary': SYNTHETIC,
    }
    _new(fixture.receipt_path, encoded(receipt))
    _new(root / 'web/out/demo.html', b'<!doctype html><title>SYNTHETIC fixture</title><h1>SYNTHETIC TEST ONLY</h1>')
    return fixture
