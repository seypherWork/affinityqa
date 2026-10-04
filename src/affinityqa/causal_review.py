"""Verified causal evidence and an offline, explicitly recorded-decision replay."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .causal_agent import (FAULTS, CausalMovieSession, ExecutionRecorder,
                           ToolContextMovieAgent, diagnose, make_request, profile_hash)
from .causal_evaluator import evaluate_pair
from .causal_runner import TASK
from .errors import SchemaError
from .evidence import fingerprint
from .metrics import rank_distance
from .store import RUN_ID


def _file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise SchemaError('Evidence path is outside its root.')
    candidate = root / relative
    for parent in [candidate, *candidate.parents]:
        if parent == root.parent:
            break
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise SchemaError('Linked evidence is not accepted.')
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise SchemaError('Evidence path escaped its root.')
    return candidate


def _read(path: Path):
    if path.stat().st_size > 16_000_000:
        raise SchemaError('Evidence file exceeds the read bound.')
    return json.loads(path.read_text(encoding='utf8'))


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verified(root: Path, receipt_path: Path):
    receipt = _read(receipt_path)
    run_id = receipt.get('run_id', '')
    if not RUN_ID.fullmatch(run_id) or receipt_path.name != f'CAUSAL-REPAIR-{run_id}.json':
        raise SchemaError('Receipt identity differs from its filename.')
    run = _file(root, 'runs/' + run_id)
    actual_files = {p.relative_to(run).as_posix() for p in run.rglob('*') if p.is_file()}
    if set(receipt['artifact_sha256']) != actual_files:
        raise SchemaError('The receipt must cover the complete captured artifact tree.')
    if not {'causal-plan.json', 'causal-report.json', 'ledger.jsonl'} <= actual_files:
        raise SchemaError('Required recorded artifacts are missing.')
    for name, expected in receipt['artifact_sha256'].items():
        if _sha(_file(run, name)) != expected:
            raise SchemaError('Recorded causal evidence has changed; verification required.')
    for name, expected in receipt['source_sha256'].items():
        if _sha(_file(root / 'src/affinityqa', name)) != expected:
            raise SchemaError('The recorded causal operator differs from the installed source.')
    required_sources = {'causal_agent.py', 'causal_runner.py', 'causal_evaluator.py', 'ollama_agent.py',
                        'qloo.py', 'models.py', 'metrics.py', 'evidence.py'}
    if set(receipt['source_sha256']) != required_sources:
        raise SchemaError('Receipt source coverage is incomplete.')
    plan = _read(_file(run, 'causal-plan.json'))
    if plan['plan_sha256'] != fingerprint({k: v for k, v in plan.items() if k != 'plan_sha256'}):
        raise SchemaError('Capture plan fingerprint differs.')
    if plan['source_sha256'] != receipt['source_sha256'] or plan['driver_sha256'] != receipt['driver_sha256']:
        raise SchemaError('Receipt and plan source bindings disagree.')
    if not any(_sha(p) == plan['driver_sha256'] for p in (root / 'scripts').glob('*causal*.py')):
        raise SchemaError('The exact capture driver is not installed.')
    if receipt['source_artifact_sha256'] != plan['source_artifact_sha256']:
        raise SchemaError('Catalog provenance bindings disagree.')
    for name, expected in receipt['source_artifact_sha256'].items():
        if _sha(_file(root, name)) != expected:
            raise SchemaError('Original source evidence differs.')
    report = _read(_file(run, 'causal-report.json'))
    if any(receipt.get(k) != v for k, v in report.items()):
        raise SchemaError('Verified report and receipt disagree.')
    if report['status'] == 'COMPLETE':
        if not {'causal-tool-inputs.json', 'frozen-causal-policy.json'} <= actual_files:
            raise SchemaError('Complete evidence is missing inputs or policy.')
        policy = _read(_file(run, 'frozen-causal-policy.json'))
        if policy['policy_sha256'] != fingerprint({k: v for k, v in policy.items() if k != 'policy_sha256'}) or policy['policy_sha256'] != report['policy_sha256']:
            raise SchemaError('Frozen policy fingerprint differs.')
        for summary in report['pairs']:
            required = {f'causal-pair-{summary["pair_id"]}.json', f'causal-execution-binding-{summary["pair_id"]}.json'}
            if not required <= actual_files:
                raise SchemaError('Pair evidence is not covered by the receipt.')
            record = _read(_file(run, 'causal-pair-' + summary['pair_id'] + '.json'))
            if evaluate_pair(record, report['noise_barrier']) != summary:
                raise SchemaError('Independent replay of the evaluator differs from the report.')
    return run, report, receipt


def _selection(root: Path):
    receipts = sorted((root / 'evidence').glob('CAUSAL-REPAIR-*.json'), reverse=True)
    if not receipts:
        return None, None
    # Never hide a failed complete run behind an older successful one.
    latest = _verified(root, receipts[0])
    if latest[1]['status'] == 'COMPLETE':
        return latest, latest
    for path in receipts[1:]:
        candidate = _verified(root, path)
        if candidate[1]['status'] == 'COMPLETE':
            return candidate, latest
    return latest, latest


def _films(rows):
    return [{'id': r['entity_id'], 'title': r['name'], 'year': r['release_year']} for r in rows]


def causal_snapshot(root: Path):
    selected, latest = _selection(root)
    if selected is None:
        return {'schema_version': 1, 'status': 'UNAVAILABLE', 'causal_gate': 'NOT_EVALUATED',
                'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
                'notice': 'No independently verified causal record is installed.'}
    _, original, _ = selected
    report = copy.deepcopy(original)
    report['capture_schema_version'] = report['schema_version']
    report['schema_version'] = 1
    report['behavioral_recoveries'] = report.get('behavioral_recoveries_observed', 0)
    report['latest_attempt'] = {k: latest[1].get(k) for k in ('run_id', 'mode', 'status', 'error', 'model_calls', 'qloo_requests')}
    report['notice'] = ('Verified ' + report['mode'] + ' capture. Recorded local model decisions and Qloo tool inputs. '
                        'Replay executes the routing, diagnosis and repair using those saved decisions; it makes no new model or Qloo calls. '
                        'Cultural quality remains independently unvalidated.')
    if latest[1]['run_id'] != report['run_id']:
        report['notice'] += ' The newer validation attempt is incomplete: ' + str(latest[1].get('error'))
    for pair in report.get('pairs', []):
        for case in pair['cases']:
            for view in case['views']:
                for key in ('healthy', 'before', 'after'):
                    view[key] = _films(view[key])
    return report


class _MemoryLedger:
    def __init__(self):
        self.run_id = 'recorded-replay'
        self.packets = []

    def write(self, name, value):
        self.packets.append(copy.deepcopy(value))

    def record(self, kind, value):
        pass


class _ReplayEngine:
    """Lookup by the actual model payload, never by an expected healthy answer."""
    def __init__(self, manifest, packets):
        self.manifest = copy.deepcopy(manifest)
        self.observations = []
        self.calls = 0
        self.last_input = None
        self.sources = []
        self.by_payload = {}
        for packet in packets:
            key = fingerprint(packet['model_payload'])
            self.by_payload.setdefault(key, []).append(packet)
        self.payload_builder = ToolContextMovieAgent.__new__(ToolContextMovieAgent)

    def rank(self, request):
        n = len(request['catalog'])
        schema = {'type': 'object', 'properties': {'ordered_catalog_indices': {'type': 'array',
                  'items': {'type': 'integer', 'enum': list(range(n))}, 'minItems': n, 'maxItems': n}},
                  'required': ['ordered_catalog_indices'], 'additionalProperties': False}
        payload = self.payload_builder.decision_input(request, schema)
        matches = self.by_payload.get(fingerprint(payload), [])
        if not matches:
            raise SchemaError('This model payload has no captured decision; live inference was not attempted.')
        # A deterministic replay is meaningful only when the saved outputs agree.
        if len({fingerprint(p['response']['ranked_entity_ids']) for p in matches}) != 1:
            raise SchemaError('Captured decisions vary for this input; deterministic replay is unavailable.')
        packet = matches[0]
        self.calls += 1
        self.last_input = copy.deepcopy(payload)
        self.sources.append(packet['execution_id'])
        ranking = copy.deepcopy(packet['response']['ranked_entity_ids'])
        self.observations.append({'call': self.calls, 'input_sha256': fingerprint(payload),
                                  'output_sha256': fingerprint(ranking), 'source_execution_id': packet['execution_id'],
                                  'source': 'recorded-local-llm-replay'})
        return {'schema_version': 1, 'request_id': request['request_id'], 'ranked_entity_ids': ranking}


def replay_causal(root: Path, pair_id: str, fault: str, repeat: int):
    selected, _ = _selection(root)
    if selected is None or selected[1]['status'] != 'COMPLETE':
        raise SchemaError('A complete verified capture is required for replay.')
    run, report, receipt = selected
    if fault not in FAULTS or type(repeat) is not int or not 1 <= repeat <= 3:
        raise SchemaError('Select a recorded fault and repeat.')
    pair = next((p for p in report['pairs'] if p['pair_id'] == pair_id), None)
    if pair is None:
        raise SchemaError('Select a recorded artist pair.')
    record = _read(_file(run, f'causal-pair-{pair_id}.json'))
    bundle = _read(_file(run, 'causal-tool-inputs.json'))[pair_id]
    binding = _read(_file(run, f'causal-execution-binding-{pair_id}.json'))
    directory = _file(run, binding['directory'])
    packet_paths = sorted(directory.glob('causal-execution-*.json'))
    if len(packet_paths) != 39 or any(p.relative_to(run).as_posix() not in receipt['artifact_sha256'] for p in packet_paths):
        raise SchemaError('Replay decisions are not all covered by the verified receipt.')
    engine = _ReplayEngine(_read(_file(directory, 'model-manifest.json')), [_read(p) for p in packet_paths])
    session = CausalMovieSession(ExecutionRecorder(engine, _MemoryLedger()), bundle['contexts'], fault=fault)
    order = ['A', 'B'] if repeat % 2 else ['B', 'A']
    def request(p, phase):
        profile = bundle['profiles'][p]
        return make_request(TASK, record['catalog'], profile, bundle['contexts'][profile_hash(profile)], f'replay-{phase}-{p}')
    before = {p: session.rank(request(p, 'before')) for p in order}
    diagnostic = diagnose(before[order[1]]['trace'])
    patch = session.apply(diagnostic)
    after = {p: session.rank(request(p, 'after')) for p in order}
    healthy = record['healthy']
    barrier = report['noise_barrier']
    expected = {'cache-omits-profile': ('CACHE_OMITS_PROFILE', 'set-profile-cache'),
                'stale-profile': ('STALE_PROFILE', 'restore-request-profile'),
                'wrong-tool-profile': ('WRONG_TOOL_PROFILE', 'bind-request-tool')}[fault]
    checks = {'supported_diagnosis': (diagnostic['diagnosis'], patch['operation']) == expected,
              'repair_applied': patch['applied'],
              'profile_integrity_restored': all(diagnose(after[p]['trace'])['diagnosis'] == 'NONE' for p in order),
              'decision_redispatched': all(not after[p]['trace']['cache_hit'] and after[p]['trace']['execution_id'] != before[p]['trace']['execution_id'] for p in order),
              'matches_recorded_healthy': all(rank_distance(after[p]['ranking'], h['ranking'], 5) <= barrier for p in order for h in healthy[p])}
    control = session.rank(request(order[0], 'equivalent'))
    checks['legitimate_cache_reuse'] = control['trace']['cache_hit'] and diagnose(control['trace'])['diagnosis'] == 'NONE'
    movie_map = {r['entity_id']: r for r in record['catalog']}
    def films(ranking): return _films([movie_map[i] for i in ranking[:5]])
    p = order[1]
    return {'schema_version': 1, 'status': 'PASS' if all(checks.values()) else 'FAIL',
            'replay_gate': 'PASS' if all(checks.values()) else 'FAIL', 'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
            'run_id': report['run_id'], 'pair_id': pair_id, 'fault': fault, 'repeat': repeat,
            'source': 'recorded-local-llm-replay', 'new_model_calls': 0, 'new_qloo_calls': 0,
            'recorded_decision_dispatches': engine.calls, 'source_execution_ids': engine.sources,
            'diagnosis': diagnostic['diagnosis'], 'repair': patch['operation'], 'checks': checks,
            'before': films(before[p]['ranking']), 'after': films(after[p]['ranking']), 'healthy': films(healthy[p][0]['ranking']),
            'trace': before[p]['trace'], 'repaired_trace': after[p]['trace'],
            'notice': 'Pipeline executed now with verified recorded model decisions. No new inference or cultural-quality validation.'}


def export_causal(root: Path):
    selected, latest = _selection(root)
    if selected is None:
        raise SchemaError('No verified causal evidence is installed.')
    run, report, receipt = selected
    return {'schema_version': 1, 'report': report, 'verification_receipt': receipt,
            'latest_attempt': latest[1], 'policy': _read(_file(run, 'frozen-causal-policy.json')) if report['status'] == 'COMPLETE' else None,
            'boundary': 'Review summary and integrity manifest. Original captured inputs and decisions belong in the portable source package.'}
