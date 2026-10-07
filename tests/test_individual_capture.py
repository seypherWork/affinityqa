"""Offline contract tests; synthetic packets never establish provider validation."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from affinityqa.individual_capture import prepare_plan, execute_capture, execution_lease, resolve_music
from affinityqa.errors import SchemaError, TransportError
from affinityqa.qloo import Response, Settings
from affinityqa.evidence import fingerprint
from affinityqa.individual_capture import sha
from test_causal_agent import FakeEngine


def fixture():
    return {'schema_version': 1, 'artists': {'A': 'Unit jazz', 'B': 'Unit pop'},
            'catalog': [{'entity_id': f'aaaaaaaa-0000-4000-8000-{i:012d}', 'name': f'Unit movie {i}', 'release_year': 2000+i} for i in range(20)],
            'model': {'name': 'unit-fake-model', 'digest': 'd'*64}}


class TransportDouble:
    def __init__(self, request, fail=False, mismatch=False, same=False):
        self.request = request
        self.fail, self.mismatch, self.same = fail, mismatch, same
        self.calls = []

    def send(self, path, params):
        self.calls.append((path, params))
        if self.fail:
            raise TransportError('Unit transport interruption.')
        if path == '/search':
            i = 0 if self.same or params['query'] == self.request['artists']['A'] else 1
            body = {'results': [{'entity_id': f'bbbbbbbb-0000-4000-8000-{i:012d}', 'name': params['query'], 'types': ['urn:entity:artist']} ]}
        else:
            rows = [{'entity_id': r['entity_id'], 'name': r['name'], 'types': ['urn:entity:movie'],
                     'properties': {'release_year': r['release_year']}, 'query': {'affinity': 1-i/20}}
                    for i, r in enumerate(self.request['catalog'])]
            if params['signal.interests.entities'].endswith('1'):
                rows.reverse()
            if self.mismatch:
                rows[0]['name'] = 'Wrong catalog movie'
            body = {'success': True, 'results': {'entities': rows}}
        return Response(200, body, {})


class EngineDouble(FakeEngine):
    def __init__(self, fail=False, digest='d'*64):
        super().__init__()
        self.manifest.update(model='unit-fake-model', model_digest=digest, max_inference_calls=39)
        self.fail = fail
        self.warmups = 0

    def warmup(self):
        self.warmups += 1
        return {'source': 'test-double-only'}

    def rank(self, request):
        if self.fail:
            self.calls += 1
            raise TransportError('Unit interrupted model response.')
        return super().rank(request)


class InsensitiveEngineDouble(EngineDouble):
    def rank(self, request):
        result = super().rank(request)
        ranking = [r['entity_id'] for r in request['catalog']]
        result['ranked_entity_ids'] = ranking
        self.observations[-1]['output_sha256'] = fingerprint(ranking)
        return result


class IndividualCaptureTests(unittest.TestCase):
    def setUp(self):
        temporary = ROOT / '.test-runs'
        temporary.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.output = self.parent / 'new-capture'
        self.request = fixture()
        self.url = 'http://127.0.0.1:11434'

    def run_capture(self, engine=None, transport=None, expected=None):
        engine = engine or EngineDouble()
        transport = transport or TransportDouble(self.request)
        plan = prepare_plan(self.request, self.output, self.url)
        with patch('affinityqa.individual_capture.time.sleep'):
            report, directory = execute_capture(self.request, self.output, self.url,
                expected or plan['plan_sha256'], Settings('unit-key-only'),
                _test_adapters=(lambda: engine, lambda: transport))
        return report, directory, engine, transport

    def test_plan_is_reproducible_and_creates_nothing(self):
        before = list(self.parent.iterdir())
        first = prepare_plan(self.request, self.output, self.url)
        self.assertEqual(first, prepare_plan(self.request, self.output, self.url))
        self.assertEqual(list(self.parent.iterdir()), before)
        self.assertEqual((first['maximum_qloo_requests'], first['maximum_model_decisions']), (4, 39))

    def test_driver_change_changes_plan_fingerprint(self):
        before = prepare_plan(self.request, self.output, self.url)
        def changed(path):
            return '0'*64 if path.name == 'capture_individual_pair.py' else sha(path)
        with patch('affinityqa.individual_capture.sha', side_effect=changed):
            after = prepare_plan(self.request, self.output, self.url)
        self.assertNotEqual(before['plan_sha256'], after['plan_sha256'])

    def test_cli_plan_does_not_need_historical_data_credentials_or_model(self):
        path = self.parent / 'request.json'
        path.write_text(json.dumps(self.request), 'utf-8')
        result = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/capture_individual_pair.py'),
            '--request', str(path), '--output', str(self.output), '--env-file', str(self.parent/'missing.env')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['request']['artists'], self.request['artists'])
        self.assertFalse(self.output.exists())
        self.assertFalse((self.parent/'.affinityqa-individual.lock').exists())

    def test_cli_inconclusive_behavior_is_visible_and_exit_fails(self):
        path = self.parent/'request.json'
        path.write_text(json.dumps(self.request), 'utf-8')
        plan = prepare_plan(self.request, self.output, self.url)
        report = {'run_id':'unit-only','status':'COMPLETE','causal_gate':'PASS','behavioral_gate':'INCONCLUSIVE',
            'source':'test-double-only','cultural_gate':'NOT_VALIDATED','independent_verification':'PENDING','error_class':None}
        command = [str(ROOT/'scripts/capture_individual_pair.py'),'--request',str(path),'--output',str(self.output),
                   '--execute','--plan-sha256',plan['plan_sha256']]
        stdout = io.StringIO()
        with (
            patch.object(sys, 'argv', command),
            patch('affinityqa.qloo.Settings.from_environment', return_value=Settings('unit-key-only')),
            patch('affinityqa.individual_capture.execute_capture', return_value=(report, self.output)),
            redirect_stdout(stdout),
        ):
            with self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(ROOT/'scripts/capture_individual_pair.py'),run_name='__main__')
        self.assertEqual(stopped.exception.code, 1)
        self.assertEqual(json.loads(stdout.getvalue())['behavioral_gate'], 'INCONCLUSIVE')

    def test_changed_plan_rejected_before_factories_and_writes(self):
        with self.assertRaises(SchemaError):
            self.run_capture(expected='0'*64)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_nonlocal_url_and_duplicate_input_are_rejected(self):
        with self.assertRaises(SchemaError):
            prepare_plan(self.request, self.output, 'https://model.example:443')
        request = copy.deepcopy(self.request)
        request['catalog'][1] = request['catalog'][0]
        with self.assertRaises(SchemaError):
            prepare_plan(request, self.output, self.url)

    def test_only_one_capture_per_parent_and_lease_reusable(self):
        with execution_lease(self.parent):
            with self.assertRaises(SchemaError):
                with execution_lease(self.parent):
                    self.fail('Second job entered lease.')
        with execution_lease(self.parent):
            pass

    def test_cross_process_lease_blocks_and_releases_after_exit(self):
        code = ('import sys;from pathlib import Path;'
                'sys.path.insert(0,sys.argv[1]);'
                'from affinityqa.individual_capture import execution_lease;'
                'lease=execution_lease(Path(sys.argv[2]));lease.__enter__();'
                'print("READY",flush=True);sys.stdin.readline();lease.__exit__(None,None,None)')
        process = subprocess.Popen([sys.executable, '-B', '-c', code, str(ROOT/'src'), str(self.parent)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'READY')
            with self.assertRaises(SchemaError):
                with execution_lease(self.parent):
                    self.fail('Concurrent process entered lease.')
        finally:
            _, error = process.communicate('\n', timeout=10)
        self.assertEqual(process.returncode, 0, error)
        with execution_lease(self.parent):
            pass

    def test_unrecognized_lock_marker_is_preserved(self):
        path = self.parent/'.affinityqa-individual.lock'
        original = b'Unrelated existing file'
        path.write_bytes(original)
        with self.assertRaises(SchemaError):
            with execution_lease(self.parent):
                self.fail('Unrecognized lock accepted.')
        self.assertEqual(path.read_bytes(), original)

    def test_all_three_incidents_get_fresh_fake_reruns_at_exact_budgets(self):
        report, directory, engine, transport = self.run_capture()
        self.assertEqual(report['source'], 'test-double-only')
        self.assertEqual(report['status'], 'COMPLETE')
        self.assertEqual(report['causal_gate'], 'PASS')
        self.assertEqual(report['behavioral_gate'], 'OBSERVED_RECOVERY')
        self.assertEqual(set(report['observed_recoveries_by_fault'].values()), {3})
        self.assertEqual(report['passing'], 3)
        self.assertEqual((engine.calls, len(transport.calls)), (39, 4))
        self.assertEqual([p for p, _ in transport.calls], ['/search', '/search', '/v2/insights', '/v2/insights'])
        self.assertEqual(len(list(directory.glob('causal-execution-*.json'))), 39)
        self.assertEqual(report['independent_verification'], 'PENDING')
        self.assertEqual(report['cultural_gate'], 'NOT_VALIDATED')
        self.assertEqual(report['release_gate'], 'BLOCKED')
        self.assertTrue(all(v is True for case in report['summary']['cases'] for v in case['checks'].values()))

    def test_no_output_effect_is_not_claimed_as_behavioral_recovery(self):
        report, _, _, _ = self.run_capture(engine=InsensitiveEngineDouble())
        self.assertEqual(report['status'], 'COMPLETE')
        self.assertEqual(report['behavioral_gate'], 'INCONCLUSIVE')
        self.assertEqual(set(report['observed_recoveries_by_fault'].values()), {0})

    def test_failed_tool_preserves_partial_evidence_without_retry_or_inference(self):
        report, directory, engine, transport = self.run_capture(transport=TransportDouble(self.request, fail=True))
        self.assertEqual((report['status'], engine.calls, engine.warmups, len(transport.calls)), ('INCOMPLETE', 0, 0, 1))
        self.assertTrue((directory/'individual-report.json').is_file())
        self.assertTrue((directory/'individual-plan.json').is_file())

    def test_wrong_model_stops_before_qloo(self):
        report, _, engine, transport = self.run_capture(engine=EngineDouble(digest='e'*64))
        self.assertEqual((report['status'], engine.calls, len(transport.calls)), ('INCOMPLETE', 0, 0))

    def test_catalog_mismatch_stops_before_model_load_and_decisions(self):
        report, _, engine, transport = self.run_capture(transport=TransportDouble(self.request, mismatch=True))
        self.assertEqual((report['status'], engine.calls, engine.warmups, len(transport.calls)), ('INCOMPLETE', 0, 0, 3))

    def test_two_names_resolving_to_same_identity_stop_before_contexts(self):
        report, _, engine, transport = self.run_capture(transport=TransportDouble(self.request, same=True))
        self.assertEqual((report['status'], engine.calls, len(transport.calls)), ('INCOMPLETE', 0, 2))

    def test_interrupted_model_stops_and_records_attempt_without_fill(self):
        report, directory, engine, transport = self.run_capture(engine=EngineDouble(fail=True))
        self.assertEqual((report['status'], engine.calls, len(transport.calls)), ('INCOMPLETE', 1, 4))
        self.assertFalse(list(directory.glob('causal-execution-*.json')))
        self.assertEqual(json.loads((directory/'individual-report.json').read_text())['model_attempts'], 1)

    def test_existing_output_is_not_overwritten(self):
        self.output.mkdir()
        original = self.output/'keep.txt'
        original.write_bytes(b'original')
        with self.assertRaises(SchemaError):
            self.run_capture()
        self.assertEqual(original.read_bytes(), b'original')

    def test_person_without_musical_metadata_is_rejected(self):
        body = {'results': [{'entity_id': 'bbbbbbbb-0000-4000-8000-000000000003', 'name': 'Unit actor', 'types': ['urn:entity:person']}]}
        with self.assertRaises(SchemaError):
            resolve_music('Unit actor', body)

    def test_missing_key_stops_before_model_factory_and_output_creation(self):
        plan = prepare_plan(self.request, self.output, self.url)
        with self.assertRaises(SchemaError):
            execute_capture(self.request, self.output, self.url, plan['plan_sha256'], Settings(''),
                _test_adapters=(lambda: self.fail('Model started without key.'), lambda: self.fail('Tool started without key.')))
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_credential_in_input_is_not_sent_to_provider_or_model(self):
        self.request['artists']['A'] = 'unit-key-only'
        plan = prepare_plan(self.request, self.output, self.url)
        with self.assertRaises(SchemaError):
            execute_capture(self.request, self.output, self.url, plan['plan_sha256'], Settings('unit-key-only'),
                _test_adapters=(lambda: self.fail('Secret reached model.'), lambda: self.fail('Secret reached tool.')))
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
