"""Offline synthetic boundary fixtures; never participant or provider evidence."""
import copy
from email.message import Message
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from affinityqa.agents import AgentError
from affinityqa.errors import AffinityQAError, SchemaError, TransportError
from affinityqa.evidence import fingerprint
from affinityqa.qloo import Settings, Response
from affinityqa.open_movie_discovery import MODEL, make_decision
from affinityqa.open_movie_discovery_agent import OpenMovieAgent
from affinityqa.open_movie_discovery_capture import prepare_plan, search_identities, capture_confirmed
from affinityqa.open_movie_discovery_verify import verify_identity_search, verify_discoveries
from affinityqa.provider_runtime import ProviderRuntime
from affinityqa.provider_scheduler import ProviderScheduler, QuotaWindow
from affinityqa.provider_scheduler import ProviderUncertain

UNIT_SECRET = 'unit-model-private-credential-only'
QLOO_SECRET = 'unit-qloo-private-credential-only'
SEED_ID = str(UUID(int=10000))
OTHER_SEED_ID = str(UUID(int=10001))


def request_fixture(**overrides):
    value = {'schema_version': 8, 'movie_query': 'Synthetic seed 2000', 'intent_text': '',
             'excluded_entity_ids': [], 'model': dict(MODEL)}
    value.update(overrides)
    return value


def movie_row(i, *, seed=False):
    return {'entity_id': SEED_ID if seed else str(UUID(int=i)),
            'name': 'Synthetic seed' if seed else f'Synthetic candidate {i}',
            'types': ['urn:entity:movie'], 'properties': {'release_year': 2000 if seed else 2000+i},
            **({} if seed else {'query': {'affinity': round(0.95-i/100, 4)}})}


class MovieTransport:
    def __init__(self, *, count=20, search_status=200, insights_status=200,
                 search_mutation=None, insights_mutation=None, failure=None):
        self.count, self.search_status, self.insights_status = count, search_status, insights_status
        self.search_mutation, self.insights_mutation, self.failure = search_mutation, insights_mutation, failure
        self.calls = []

    def send(self, path, params):
        self.calls.append((path, copy.deepcopy(params)))
        if self.failure is not None:raise self.failure
        if path == '/search':
            body = {'results': [movie_row(0, seed=True)]}; status = self.search_status; mutation = self.search_mutation
        elif path == '/v2/insights':
            body = {'success': True, 'results': {'entities': [movie_row(i) for i in range(1, self.count+1)]}}
            status = self.insights_status; mutation = self.insights_mutation
        else:raise AssertionError('Unexpected provider endpoint')
        if mutation:mutation(body)
        return Response(status, body if status == 200 else {'fixture_error': True}, {}, 1.25)


class ModelResponse(io.BytesIO):
    def __init__(self, body):
        super().__init__(json.dumps(body).encode()); self.status = 200
        self.headers = Message(); self.headers['Content-Type'] = 'application/json'


class ModelOpener:
    def __init__(self, *, mutation=None, failure=None):
        self.calls = []; self.mutation, self.failure = mutation, failure

    def open(self, request, timeout):
        wire = json.loads(request.data); self.calls.append((request, wire, timeout))
        if self.failure is not None:raise self.failure
        data = json.loads(wire['messages'][1]['content'])
        order = list(reversed(range(len(data['catalog']))))
        delivered = [i for i in order if i in data['eligible_catalog_indices']][:5]
        reasons = [{'catalog_index': i, 'text': f"Podría encajar {data['catalog'][i]['name']} como lectura personal de {data['seed_movie']['name']}; es una interpretación sin verificar."} for i in delivered]
        body = {'id': 'synthetic-open-completion', 'object': 'chat.completion', 'created': 1791280000,
                'model': MODEL['name'], 'system_fingerprint': 'synthetic-fixture',
                'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant',
                    'content': json.dumps({'ordered_catalog_indices': {'ranking': order, 'reasons': reasons}})}}],
                'usage': {'prompt_tokens': 1000, 'completion_tokens': 300, 'total_tokens': 1300,
                          'completion_tokens_details': {'reasoning_tokens': 10}}}
        if self.mutation:self.mutation(body)
        return ModelResponse(body)


class TokenEstimator:
    manifest = {'method': 'synthetic-offline-test-estimate', 'exact_provider_prompt_attested': False}
    def estimate(self, encoded):return {'tokens': 6024, 'input_tokens': 5000, 'output_tokens': 1024}


def adapters_fixture(transport=None, opener=None):
    transport, opener = transport or MovieTransport(), opener or ModelOpener()
    return (lambda: OpenMovieAgent(UNIT_SECRET, forbidden_secrets=(QLOO_SECRET,), _test_opener=opener,
                                  token_estimator=TokenEstimator()), lambda: transport)


class OpenMovieCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT.parent); self.addCleanup(self.tmp.cleanup); self.base = Path(self.tmp.name)
        self.settings = Settings(QLOO_SECRET)
        for name in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(name, side_effect=AssertionError('Network/DNS forbidden in synthetic fixture'))
            guard.start(); self.addCleanup(guard.stop)

    def search(self, request=None, transport=None, opener=None):
        self.request = request or request_fixture(); self.transport = transport or MovieTransport(); self.opener = opener or ModelOpener()
        self.adapters = adapters_fixture(self.transport, self.opener)
        output = self.base / ('capture-' + str(len(list(self.base.glob('capture-*')))))
        self.plan = prepare_plan(self.request, output)
        report, self.directory = search_identities(self.request, output, self.plan['plan_sha256'], self.settings, _test_adapters=self.adapters)
        return report, verify_identity_search(self.directory)

    def finish(self, **kwargs):
        _, receipt = self.search(**kwargs)
        report, _ = capture_confirmed(self.directory, SEED_ID, receipt, self.settings, UNIT_SECRET, _test_adapters=self.adapters)
        return report, verify_discoveries(self.directory)

    def test_complete_real_pool_and_exact_two_qloo_one_model(self):
        report, receipt = self.finish(request=request_fixture(intent_text='Humor absurdo, sin prometer un género.'))
        self.assertEqual((report['status'], receipt['verification_status']), ('COMPLETE', 'VERIFIED_COMPLETE'))
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (2, 1))
        self.assertEqual((receipt['qloo_attempts'], receipt['model_attempts']), (2, 1))
        result = receipt['open_movie_results']; self.assertEqual(len(result['candidate_catalog']), 20)
        self.assertEqual(len(result['delivered']), 5); self.assertNotEqual(result['delivered'], result['baseline_delivered'])
        self.assertFalse(result['information_policy']['same_explicit_information'])
        self.assertFalse(result['information_policy']['same_total_information_attested'])
        self.assertTrue(all(r['verification'] == 'NOT_FACT_CHECKED' for r in result['reasons']))
        self.assertEqual(receipt['provenance'], 'SIMULATION_ONLY'); self.assertEqual(receipt['cultural_gate'], 'NOT_VALIDATED')
        self.assertNotIn('filter.results.entities', self.transport.calls[1][1])

    def test_unicode_utf8_search_confirmation_and_full_verification_under_windows_locale(self):
        """Catches the Windows cp1252 default decoding of Ledger's UTF-8 bytes."""
        title = 'Björk / Amélie / 日本語'
        def search_titles(body):body['results'][0]['name'] = title
        def result_titles(body):
            for i, row in enumerate(body['results']['entities']):row['name'] = f'Amélie 日本語 {i}'
        transport = MovieTransport(count=7, search_mutation=search_titles, insights_mutation=result_titles)
        original_read_text = Path.read_text
        def windows_default(path, encoding=None, errors=None):
            return original_read_text(path, encoding=encoding or 'cp1252', errors=errors)
        with patch.object(Path, 'read_text', windows_default):
            report, receipt = self.finish(request=request_fixture(movie_query=title+' 2000'), transport=transport)
        self.assertEqual((report['status'], receipt['verification_status']), ('COMPLETE', 'VERIFIED_COMPLETE'))
        self.assertEqual(receipt['chosen_movie_input'], {'entity_id': SEED_ID, 'name': title,
            'release_year': 2000, 'type': 'urn:entity:movie'})
        self.assertEqual(receipt['open_movie_results']['candidate_catalog'][0]['name'], 'Amélie 日本語 0')
        self.assertEqual((len(transport.calls), len(self.opener.calls)), (2, 1))

    def test_utf8_candidate_array_reader_retains_duplicate_nonfinite_and_trailing_checks(self):
        from affinityqa.open_movie_discovery_verify import read
        path = self.base / 'strict-artifact.json'
        path.write_bytes('[{"name":"Björk / Amélie / 日本語"}]'.encode('utf-8'))
        self.assertEqual(read(path), [{'name':'Björk / Amélie / 日本語'}])
        for raw in (b'[{"name":"one","name":"two"}]', b'[NaN]', b'[],"injected":1', b'["\xff"]'):
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                with self.assertRaises(AffinityQAError):read(path)

    def test_search_has_zero_model_and_explicit_uuid_only(self):
        report, receipt = self.search(); self.assertEqual(report['status'], 'AWAITING_IDENTITY_CONFIRMATION')
        self.assertEqual(self.opener.calls, [])
        for selected in (None, '', OTHER_SEED_ID, SEED_ID.upper()):
            if selected == SEED_ID:continue
            with self.subTest(selected=selected), self.assertRaises(SchemaError):
                capture_confirmed(self.directory, selected, receipt, self.settings, UNIT_SECRET, _test_adapters=self.adapters)
        self.assertEqual(len(self.transport.calls), 1)

    def test_cross_bound_receipt_and_modified_search_artifact_rejected(self):
        _, receipt = self.search(); forged = copy.deepcopy(receipt); forged['run_id'] = 'different'
        with self.assertRaises(SchemaError):capture_confirmed(self.directory, SEED_ID, forged, self.settings, UNIT_SECRET, _test_adapters=self.adapters)
        target = self.directory / 'open-movie-candidates.json'; target.write_text('[]')
        with self.assertRaises(SchemaError):verify_identity_search(self.directory)
        self.assertEqual(len(self.transport.calls), 1)

    def test_search_non200_empty_album_missing_year_are_terminal(self):
        for transport in (MovieTransport(search_status=429), MovieTransport(search_mutation=lambda b:b.update(results=[])),
                MovieTransport(search_mutation=lambda b:b['results'][0].update(types=['urn:entity:album'])),
                MovieTransport(search_mutation=lambda b:b['results'][0]['properties'].pop('release_year'))):
            with self.subTest(transport=transport):
                report, receipt = self.search(transport=transport)
                self.assertEqual((report['status'], receipt['verification_status']), ('INCOMPLETE', 'VERIFIED_PARTIAL'))
                self.assertEqual((len(transport.calls), len(self.opener.calls)), (1, 0))

    def test_insights_non200_incomplete_or_seed_stop_before_model(self):
        for transport in (MovieTransport(insights_status=429), MovieTransport(count=4), MovieTransport(count=21),
                MovieTransport(insights_mutation=lambda b:b['results']['entities'][0]['properties'].pop('release_year')),
                MovieTransport(insights_mutation=lambda b:b['results']['entities'].__setitem__(0, {**movie_row(0, seed=True), 'query': {'affinity': 0.8}}))):
            with self.subTest(transport=transport):
                report, receipt = self.finish(transport=transport)
                self.assertEqual((report['status'], receipt['verification_status']), ('INCOMPLETE', 'VERIFIED_PARTIAL'))
                self.assertEqual((len(transport.calls), len(self.opener.calls)), (2, 0))

    def test_fewer_than_five_eligible_preserves_context_without_model(self):
        report, receipt = self.finish(request=request_fixture(excluded_entity_ids=[str(UUID(int=1))]), transport=MovieTransport(count=5))
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL'); self.assertEqual(report['model_attempts'], 0)
        self.assertTrue((self.directory / 'open-candidate-context.json').exists()); self.assertEqual(len(self.opener.calls), 0)

    def test_model_invalid_envelope_stops_once_with_partial_evidence(self):
        for mutate in (lambda b:b['choices'][0].update(finish_reason='length'),
                lambda b:b['choices'][0]['message'].update(content='{}')):
            with self.subTest(mutate=mutate):
                report, receipt = self.finish(opener=ModelOpener(mutation=mutate))
                self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
                self.assertEqual((report['qloo_attempts'], report['model_attempts'], len(self.opener.calls)), (2, 1, 1))

    def test_success_cannot_skip_model_or_result_event(self):
        self.finish()
        path = self.directory / 'ledger.jsonl'; original = path.read_bytes()
        for removed in ('open_model_execution_recorded', 'open_result_recorded'):
            events = [json.loads(v) for v in original.splitlines() if json.loads(v)['kind'] != removed]
            for i, event in enumerate(events, 1):event['sequence'] = i
            path.write_text(''.join(json.dumps(e)+'\n' for e in events))
            with self.assertRaises(SchemaError):verify_discoveries(self.directory)
        path.write_bytes(original)
        self.assertEqual(verify_discoveries(self.directory)['verification_status'], 'VERIFIED_COMPLETE')

    def test_changed_result_or_extra_artifact_rejected(self):
        self.finish(); path = self.directory / 'open-movie-result.json'; original = path.read_bytes()
        result = json.loads(original); result['delivered'][0] = SEED_ID; path.write_text(json.dumps(result))
        with self.assertRaises(SchemaError):verify_discoveries(self.directory)
        path.write_bytes(original); (self.directory / 'invented.json').write_text('{}')
        with self.assertRaises(SchemaError):verify_discoveries(self.directory)

    def test_actual_runtime_roundtrip_retains_nested_reasons_without_second_send(self):
        _, receipt = self.finish(); packet = json.loads((self.directory / 'open-movie-execution-001.json').read_bytes())
        decision = packet['effective_request']; opener = ModelOpener(); estimator = TokenEstimator()
        scheduler = ProviderScheduler(self.base / 'runtime.sqlite3', limits={'groq': (QuotaWindow('rpm', 10, 60), QuotaWindow('tpm', 8000, 60, 'tokens'))})
        runtimes = []; responses = []; observations = []
        for _ in range(2):
            runtime = ProviderRuntime(scheduler, 'synthetic-job', 'synthetic-owner', namespace={'protocol': 'open-offline'}, token_estimator=estimator)
            engine = OpenMovieAgent(UNIT_SECRET, _test_opener=opener, token_estimator=estimator)
            with runtime.activate('capture'):responses.append(engine.rank(decision))
            runtimes.append(runtime); observations.append(engine.observations[0])
        self.assertEqual(len(opener.calls), 1); self.assertEqual(responses[0], responses[1]); self.assertEqual(observations[0], observations[1])
        self.assertEqual(len(responses[1]['reasons']), 5)
        self.assertEqual(runtimes[0].counters['fresh_network_attempts'], 1)
        self.assertEqual(runtimes[1].counters['exact_reconstructions'], 1)
        self.assertIsInstance(observations[1]['provider_envelope']['choice']['ordered_catalog_indices'], dict)

    def test_real_runtime_capture_verifies_without_extra_event_assumptions(self):
        scheduler = ProviderScheduler(self.base / 'capture-runtime.sqlite3', limits={
            'groq': (QuotaWindow('rpm', 10, 60), QuotaWindow('tpm', 8000, 60, 'tokens')),
            'qloo': (QuotaWindow('rpm', 10, 60),)})
        runtime = ProviderRuntime(scheduler, 'synthetic-job', 'synthetic-owner', namespace={'protocol': 'offline'}, token_estimator=TokenEstimator())
        with runtime.activate('search'):_, identity = self.search()
        with runtime.activate('capture'):
            capture_confirmed(self.directory, SEED_ID, identity, self.settings, UNIT_SECRET, _test_adapters=self.adapters)
        self.assertEqual(verify_discoveries(self.directory)['verification_status'], 'VERIFIED_COMPLETE')
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (2, 1))

    def test_success_search_cannot_be_appended_after_failed_or_empty_first_search(self):
        for transport in (MovieTransport(search_status=429), MovieTransport(search_mutation=lambda b:b.update(results=[]))):
            with self.subTest(transport=transport):
                self.search(transport=transport)
                path = self.directory / 'ledger.jsonl'; events = [json.loads(v) for v in path.read_bytes().splitlines()]
                original = json.loads((self.directory / 'http-0002.json').read_bytes())
                forged = {**original, 'status': 200, 'response': {'results':[movie_row(0, seed=True)]}}
                forged['response_sha256'] = fingerprint(forged['response'])
                (self.directory / 'http-0003.json').write_text(json.dumps(forged))
                addition = {**events[1], 'sequence': 3, 'data': {'sample': 'http-0003.json', **{k:v for k,v in forged.items() if k!='response'}}}
                events.insert(2, addition); events[-1]['sequence'] = 4
                raw = ''.join(json.dumps(v)+'\n' for v in events)
                path.write_text(raw); (self.directory / 'identity-ledger.jsonl').write_text(raw)
                report_path = self.directory / 'open-search-report.json'; report = json.loads(report_path.read_bytes()); report['qloo_attempts'] = 2
                report_path.write_text(json.dumps(report))
                with self.assertRaises(SchemaError):verify_identity_search(self.directory)

    def test_failed_or_semantically_invalid_insights_cannot_freeze_context(self):
        for transport in (MovieTransport(insights_status=429), MovieTransport(count=4)):
            with self.subTest(transport=transport):
                self.finish(transport=transport)
                path = self.directory / 'ledger.jsonl'; events = [json.loads(v) for v in path.read_bytes().splitlines()]
                forged = {**events[-1], 'kind': 'open_candidate_context_frozen', 'data': {'sha256': 'a'*64}}
                events.insert(-1, forged)
                for i, event in enumerate(events, 1):event['sequence'] = i
                path.write_text(''.join(json.dumps(v)+'\n' for v in events))
                with self.assertRaises(SchemaError):verify_discoveries(self.directory)

    def test_os_packet_boundary_stays_partial_without_retry(self):
        from affinityqa.evidence import Ledger
        _, receipt = self.search(); original = Ledger.write
        def write(ledger, name, value):
            if name == 'open-movie-execution-001.json':raise OSError('Synthetic file boundary')
            return original(ledger, name, value)
        with patch.object(Ledger, 'write', write):
            report, _ = capture_confirmed(self.directory, SEED_ID, receipt, self.settings, UNIT_SECRET, _test_adapters=self.adapters)
        self.assertEqual(verify_discoveries(self.directory)['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual((report['model_attempts'], len(self.opener.calls)), (1, 1))

    def test_runtime_unknown_transport_is_partial_and_never_retry(self):
        _, receipt = self.search(); self.transport.failure = TransportError('Synthetic disconnected socket')
        scheduler = ProviderScheduler(self.base / 'unknown.sqlite3', limits={'qloo': (QuotaWindow('rpm',10,60),)})
        runtime = ProviderRuntime(scheduler, 'unknown-job', 'unknown-owner', namespace={'protocol':'open'})
        with runtime.activate('capture'), self.assertRaises(ProviderUncertain):
            capture_confirmed(self.directory, SEED_ID, receipt, self.settings, UNIT_SECRET, _test_adapters=self.adapters)
        verified = verify_discoveries(self.directory)
        self.assertEqual((verified['verification_status'], verified['qloo_attempts'], verified['model_attempts']), ('VERIFIED_PARTIAL', 2, 0))
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (2, 0))

    def test_pinned_real_tokenizer_admits_normal_fixture_wire_under8000(self):
        from affinityqa.provider_runtime import PinnedHarmonyTokenEstimator
        from affinityqa.open_movie_discovery_agent import wire
        self.finish(); packet = json.loads((self.directory / 'open-movie-execution-001.json').read_bytes())
        estimator = PinnedHarmonyTokenEstimator(ROOT / 'assets/tokenizers/o200k_base.tiktoken')
        payload = wire(packet['effective_request'], json.loads((self.directory / 'open-model-manifest.json').read_bytes()))
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',',':'), allow_nan=False).encode()
        reservation = estimator.estimate(encoded)
        self.assertLessEqual(reservation['tokens'],8000); self.assertEqual(reservation['output_tokens'],1024)


if __name__ == '__main__':unittest.main()
