"""Strict target identity, explicit contract data and sealed historical decoders."""
import copy
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from affinityqa.agents import AgentError
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
from affinityqa.wide_cinema_tokens import WideHarmonyTokenEstimator
from affinityqa.wide_cinema_agent import WideCinemaAgent, model_manifest, wire
from affinityqa.wide_cinema_capture import capture_confirmed
from affinityqa.wide_cinema_discovery import PROMPT, make_decision, model_input, output_schema, validate_output
from affinityqa.wide_cinema_verify import _wire, _reservation, verify_discoveries, verify_packet
from affinityqa.wide_cinema_v3_compat import FROZEN_SOURCE_SHA256, validate_frozen_sources
from affinityqa import wide_cinema_v4_compat as v4_sources
from affinityqa import wide_cinema_v5_compat as v5_sources
from affinityqa import wide_cinema_v6_compat as v6_sources
from affinityqa import wide_cinema_v7_compat as v7_sources
import test_wide_cinema_capture as capture_fixtures
from test_wide_cinema_capture import (WideOpener, context_fixture,
    request_fixture, UNIT_SECRET, QLOO_SECRET, SEED_ID)
from test_wide_cinema_discovery import output_fixture, choice_fixture


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')


class StrictOutputWireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.estimator = WideHarmonyTokenEstimator(ROOT / 'assets/tokenizers/o200k_base.tiktoken')

    def decision(self):
        return make_decision(request_fixture(excluded_entity_ids=[str(UUID(int=99)), str(UUID(int=100))]),
                             context_fixture(), 'strict-synthetic-only')

    def test_exact_closed_schema_and_wire_preserve_model_options_and_eligible_set(self):
        decision = self.decision()
        manifest = model_manifest('test-double-only')
        schema = {'type': 'object', 'properties': {'ordered_catalog_indices': {
            'type': 'array', 'items': {'type': 'object', 'properties': {
                'catalog_index': {'type': 'integer', 'enum': list(range(98))}},
                'required': ['catalog_index'], 'additionalProperties': False},
            'minItems': 5, 'maxItems': 5}},
            'required': ['ordered_catalog_indices'], 'additionalProperties': False}
        response_format = {'type': 'text'}
        expected = {'model': 'openai/gpt-oss-20b', 'messages': [
            {'role': 'system', 'content': PROMPT},
            {'role': 'user', 'content': encoded(model_input(decision)).decode('utf8')}],
            'response_format': response_format,
            'temperature': 0, 'seed': 7, 'reasoning_effort': 'low', 'include_reasoning': False,
            'stream': False, 'max_completion_tokens': 2048}
        self.assertEqual(output_schema(decision), schema)
        self.assertEqual(wire(decision, manifest), expected)
        self.assertEqual(_wire(decision, manifest), expected)
        self.assertEqual(manifest['max_inference_calls'], 1)
        self.assertEqual(manifest['maximum_token_reservation'], 8000)
        self.assertFalse(manifest['automatic_retry'])
        self.assertFalse(manifest['automatic_model_or_schema_fallback'])
        self.assertEqual(manifest['provider_response_format'], {'type':'text'})
        self.assertIn('only the ordered_catalog_indices key', expected['messages'][0]['content'])
        self.assertEqual(json.loads(expected['messages'][1]['content'])['output_contract'], schema)
        candidates=json.loads(expected['messages'][1]['content'])['candidates']
        self.assertEqual(len(candidates),98)
        self.assertEqual(candidates[0],{'catalog_index':0,'title':'Synthetic film 1','release_year':1951,
            'observed_affinity':0.995,'provider_order':0})
        self.assertNotIn('candidate_columns',model_input(decision))
        for typed_rule in ('integer present', 'only catalog_index', 'duplicate keys', 'extra keys'):
            self.assertIn(typed_rule, PROMPT)

    def test_token_estimator_sees_exact_strict_utf8_wire_that_is_sent(self):
        calls = []
        delegate = self.estimator
        class RecordingEstimator:
            def estimate(self, data):
                calls.append(data)
                return delegate.estimate(data)
        decision = self.decision()
        opener = WideOpener()
        engine = WideCinemaAgent(UNIT_SECRET, _test_opener=opener, token_estimator=RecordingEstimator())
        engine.rank(decision)
        self.assertEqual(len(calls), 1)
        actual_request = opener.calls[0][0]
        self.assertEqual(calls[0], actual_request.data)
        self.assertEqual(actual_request.data, encoded(_wire(decision, engine.manifest)))
        self.assertEqual(engine.last_prepared['wire_sha256'], hashlib.sha256(calls[0]).hexdigest())
        self.assertEqual(engine.last_prepared['provider_request_sha256'], fingerprint(json.loads(calls[0])))
        self.assertEqual(engine.last_prepared['request_bytes'], len(calls[0]))
        total = self.estimator.estimate(calls[0])
        without_schema = json.loads(calls[0])
        content = json.loads(without_schema['messages'][1]['content'])
        content.pop('output_contract')
        without_schema['messages'][1]['content'] = encoded(content).decode('utf8')
        legacy_size = self.estimator.estimate(encoded(without_schema))
        self.assertGreater(total['input_tokens'], legacy_size['input_tokens'])
        self.assertEqual(engine.last_prepared['reservation'], total)
        self.assertEqual(total['output_tokens'], 2048)
        self.assertLessEqual(total['tokens'], 8000)

    def test_invalid_or_oversized_reservations_fail_before_model_send(self):
        reservations = [dict(tokens=8001, input_tokens=5953, output_tokens=2048),
                        dict(tokens=3071, input_tokens=1024, output_tokens=2047),
                        dict(tokens=True, input_tokens=1024, output_tokens=2048),
                        dict(tokens=3071, input_tokens=1023, output_tokens=2048),
                        dict(tokens=3072, input_tokens=1024, output_tokens=2048, discount=True)]
        for reservation in reservations:
            with self.subTest(reservation=reservation):
                estimator = Mock()
                estimator.estimate.return_value = reservation
                opener = WideOpener()
                engine = WideCinemaAgent(UNIT_SECRET, _test_opener=opener, token_estimator=estimator)
                with self.assertRaises(AgentError):
                    engine.rank(self.decision())
                self.assertEqual((engine.calls, len(opener.calls)), (0, 0))

    def test_any_model_text_is_forbidden_including_former_unicode_and_length_boundaries(self):
        decision=self.decision()
        for raw in ('x'*40,'x'*240,'x'*39,'x'*241,' '+'x'*39,'\ufb03'*81):
            value=output_fixture(decision);value['ordered_catalog_indices'][0]['text']=raw
            with self.subTest(raw_length=len(raw)),self.assertRaisesRegex(SchemaError,'OUTPUT_CHOICE_SHAPE'):validate_output(decision,value)

    def test_malformed_refused_and_truncated_completions_never_fallback_or_retry(self):
        cases = [
            ('FINAL_MESSAGE', lambda body: body['choices'][0]['message'].update(refusal='PRIVATE_REFUSAL_CANARY')),
            ('FINISH_REASON', lambda body: body['choices'][0].update(finish_reason='content_filter')),
            ('OUTPUT_JSON', lambda body: body['choices'][0]['message'].update(content='{"PRIVATE_TRUNCATED_CANARY":')),
        ]
        for code, mutation in cases:
            with self.subTest(code=code):
                opener = WideOpener(mutation=mutation)
                engine = WideCinemaAgent(UNIT_SECRET, _test_opener=opener, token_estimator=self.estimator)
                with self.assertRaises(Exception):
                    engine.rank(self.decision())
                self.assertEqual(engine.last_rejection['code'], code)
                self.assertFalse(engine.last_rejection['accepted'])
                self.assertNotIn('PRIVATE_', json.dumps(engine.last_rejection))
                self.assertEqual(engine.observations, [])
                with self.assertRaises(AgentError):
                    engine.rank(self.decision())
                self.assertEqual((engine.calls, len(opener.calls)), (1, 1))
                self.assertEqual(opener.calls[0][1]['response_format'], {'type':'text'})

    def test_frozen_v3_sources_are_exact_and_physical_tamper_is_rejected(self):
        original = ROOT / 'src/affinityqa/wide_cinema_v3_source'
        self.assertEqual({path.name for path in original.iterdir()}, set(FROZEN_SOURCE_SHA256))
        self.assertEqual({name: hashlib.sha256((original / name).read_bytes()).hexdigest()
                          for name in FROZEN_SOURCE_SHA256}, FROZEN_SOURCE_SHA256)
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            copied = Path(temp) / 'snapshot'
            shutil.copytree(original, copied)
            validate_frozen_sources(snapshot_directory=copied)
            changed = copied / 'wide_cinema_agent.py'
            changed.write_bytes(changed.read_bytes() + b'\n# private tamper negative\n')
            with self.assertRaisesRegex(SchemaError, 'frozen source snapshot changed'):
                validate_frozen_sources(snapshot_directory=copied)

    def test_v4_snapshots_are_physical_and_do_not_override_nested_v3_basenames(self):
        package = ROOT / 'src/affinityqa'
        v4_sources.validate_frozen_sources()
        for name, expected in v4_sources.FROZEN_SOURCE_SHA256.items():
            self.assertEqual(v4_sources.legacy_source_sha(package/name), expected)
            self.assertNotEqual(hashlib.sha256((package/name).read_bytes()).hexdigest(), expected)
        nested = package/'wide_cinema_v3_source/wide_cinema_agent.py'
        self.assertEqual(v4_sources.legacy_source_sha(nested), hashlib.sha256(nested.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            copied = Path(temp)/'snapshot'
            shutil.copytree(package/'wide_cinema_v4_source', copied)
            for name in v4_sources.FROZEN_SOURCE_SHA256:
                with self.subTest(name=name):
                    path=copied/name;before=path.read_bytes();path.write_bytes(before+b'\n# synthetic tamper\n')
                    with self.assertRaisesRegex(SchemaError,'frozen source snapshot changed'):
                        v4_sources.validate_frozen_sources(snapshot_directory=copied)
                    path.write_bytes(before)
                    v4_sources.validate_frozen_sources(snapshot_directory=copied)

    def test_v5_snapshots_are_exact_and_nested_v3_v4_hashes_are_physical(self):
        package=ROOT/'src/affinityqa'
        v5_sources.validate_frozen_sources()
        for name,expected in v5_sources.FROZEN_SOURCE_SHA256.items():
            self.assertEqual(v5_sources.legacy_source_sha(package/name),expected)
            self.assertNotEqual(hashlib.sha256((package/name).read_bytes()).hexdigest(),expected)
        for version in (3,4):
            for name in v5_sources.FROZEN_SOURCE_SHA256:
                path=package/f'wide_cinema_v{version}_source'/name
                self.assertEqual(v5_sources.legacy_source_sha(path),hashlib.sha256(path.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            copied=Path(temp)/'snapshot';shutil.copytree(package/'wide_cinema_v5_source',copied)
            for name in v5_sources.FROZEN_SOURCE_SHA256:
                with self.subTest(name=name):
                    path=copied/name;before=path.read_bytes();path.write_bytes(before+b'\n# physical tamper\n')
                    with self.assertRaisesRegex(SchemaError,'frozen source snapshot changed'):
                        v5_sources.validate_frozen_sources(snapshot_directory=copied)
                    path.write_bytes(before);v5_sources.validate_frozen_sources(snapshot_directory=copied)

    def test_v6_snapshots_are_exact_and_nested_historical_hashes_remain_physical(self):
        package=ROOT/'src/affinityqa'
        v6_sources.validate_frozen_sources()
        for name,expected in v6_sources.FROZEN_SOURCE_SHA256.items():
            self.assertEqual(v6_sources.legacy_source_sha(package/name),expected)
            self.assertNotEqual(hashlib.sha256((package/name).read_bytes()).hexdigest(),expected)
        for version in (3,4,5):
            for name in v6_sources.FROZEN_SOURCE_SHA256:
                path=package/f'wide_cinema_v{version}_source'/name
                self.assertEqual(v6_sources.legacy_source_sha(path),hashlib.sha256(path.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            copied=Path(temp)/'snapshot';shutil.copytree(package/'wide_cinema_v6_source',copied)
            for name in v6_sources.FROZEN_SOURCE_SHA256:
                with self.subTest(name=name):
                    path=copied/name;before=path.read_bytes();path.write_bytes(before+b'\n# physical tamper\n')
                    with self.assertRaisesRegex(SchemaError,'frozen source snapshot changed'):
                        v6_sources.validate_frozen_sources(snapshot_directory=copied)
                    path.write_bytes(before);v6_sources.validate_frozen_sources(snapshot_directory=copied)

    def test_v7_snapshots_are_exact_and_nested_historical_hashes_remain_physical(self):
        package=ROOT/'src/affinityqa'
        v7_sources.validate_frozen_sources()
        for name,expected in v7_sources.FROZEN_SOURCE_SHA256.items():
            self.assertEqual(v7_sources.legacy_source_sha(package/name),expected)
            self.assertNotEqual(hashlib.sha256((package/name).read_bytes()).hexdigest(),expected)
        for version in (3,4,5,6):
            for name in v7_sources.FROZEN_SOURCE_SHA256:
                path=package/f'wide_cinema_v{version}_source'/name
                self.assertEqual(v7_sources.legacy_source_sha(path),hashlib.sha256(path.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            copied=Path(temp)/'snapshot';shutil.copytree(package/'wide_cinema_v7_source',copied)
            for name in v7_sources.FROZEN_SOURCE_SHA256:
                with self.subTest(name=name):
                    path=copied/name;before=path.read_bytes();path.write_bytes(before+b'\n# physical tamper\n')
                    with self.assertRaisesRegex(SchemaError,'frozen source snapshot changed'):
                        v7_sources.validate_frozen_sources(snapshot_directory=copied)
                    path.write_bytes(before);v7_sources.validate_frozen_sources(snapshot_directory=copied)

    def test_v8_snapshots_are_exact_and_nested_historical_hashes_remain_physical(self):
        from affinityqa import wide_cinema_v8_compat as v8_sources
        package=ROOT/'src/affinityqa'
        v8_sources.validate_frozen_sources()
        for name,expected in v8_sources.FROZEN_SOURCE_SHA256.items():
            self.assertEqual(v8_sources.legacy_source_sha(package/name),expected)
            self.assertNotEqual(hashlib.sha256((package/name).read_bytes()).hexdigest(),expected)
        for version in (3,4,5,6,7):
            for name in v8_sources.FROZEN_SOURCE_SHA256:
                path=package/f'wide_cinema_v{version}_source'/name
                self.assertEqual(v8_sources.legacy_source_sha(path),hashlib.sha256(path.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            copied=Path(temp)/'snapshot';shutil.copytree(package/'wide_cinema_v8_source',copied)
            for name in v8_sources.FROZEN_SOURCE_SHA256:
                with self.subTest(name=name):
                    path=copied/name;before=path.read_bytes();path.write_bytes(before+b'\n# physical tamper\n')
                    with self.assertRaisesRegex(SchemaError,'frozen source snapshot changed'):
                        v8_sources.validate_frozen_sources(snapshot_directory=copied)
                    path.write_bytes(before);v8_sources.validate_frozen_sources(snapshot_directory=copied)


    def test_v9_snapshots_are_exact_and_nested_historical_hashes_remain_physical(self):
        from affinityqa import wide_cinema_v9_compat as v9_sources
        package=ROOT/'src/affinityqa'
        v9_sources.validate_frozen_sources()
        for name,expected in v9_sources.FROZEN_SOURCE_SHA256.items():
            self.assertEqual(v9_sources.legacy_source_sha(package/name),expected)
            self.assertNotEqual(hashlib.sha256((package/name).read_bytes()).hexdigest(),expected)
        for version in (3,4,5,6,7,8,9):
            for name in v9_sources.FROZEN_SOURCE_SHA256:
                path=package/f'wide_cinema_v{version}_source'/name
                self.assertEqual(v9_sources.legacy_source_sha(path),hashlib.sha256(path.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            copied=Path(temp)/'snapshot';shutil.copytree(package/'wide_cinema_v9_source',copied)
            for name in v9_sources.FROZEN_SOURCE_SHA256:
                with self.subTest(name=name):
                    path=copied/name;before=path.read_bytes();path.write_bytes(before+b'\n# physical tamper\n')
                    with self.assertRaisesRegex(SchemaError,'frozen source snapshot changed'):
                        v9_sources.validate_frozen_sources(snapshot_directory=copied)
                    path.write_bytes(before);v9_sources.validate_frozen_sources(snapshot_directory=copied)


    def test_old_pending_capture_is_refused_before_lease_runtime_adapters_or_writes(self):
        for version in (3,4,5,6,7,8,9):
            with self.subTest(version=version),tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
                directory = Path(temp) / '20261018T000000Z-12345678'
                directory.mkdir()
                path = directory / 'wide-plan.json'
                path.write_text(json.dumps({'protocol_version': f'qloo-wide-cinema-discovery-v{version}'}), encoding='utf8')
                before = {p.name: p.read_bytes() for p in directory.iterdir()}
                adapters = (Mock(), Mock())
                with patch('affinityqa.wide_cinema_capture.execution_lease') as lease:
                    with self.assertRaisesRegex(SchemaError, 'Historical wide captures are read-only'):
                        capture_confirmed(directory, SEED_ID, {}, Mock(api_key=QLOO_SECRET), UNIT_SECRET,
                                          _test_adapters=adapters)
                    lease.assert_not_called()
                self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, before)
                for adapter in adapters:
                    adapter.assert_not_called()


class StrictOutputCaptureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = capture_fixtures.WideCaptureTests('test_movie100_actual_candidates_three_qloo_one_model')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def fail_http(self, status, code):
        f = self.fixture
        headers = Message()
        headers['Retry-After'] = '61'
        body = json.dumps({'error': {'code': code, 'message': 'PRIVATE_FAILED_SCHEMA_CANARY'}}).encode()
        f.opener = WideOpener(failure=HTTPError('https://api.groq.com/openai/v1/chat/completions',
                                             status, 'synthetic rejection', headers, io.BytesIO(body)))
        report, receipt = f.finish()
        self.assertEqual((report['status'], receipt['verification_status']), ('INCOMPLETE', 'VERIFIED_PARTIAL'))
        self.assertEqual((len(f.transport.calls), len(f.opener.calls)), (3, 1))
        self.assertEqual(receipt['verified_model_packets'], 0)
        self.assertEqual(receipt['model_rejection']['code'], 'COMPLETION_REJECTED')
        sent = f.opener.calls[0][1]
        self.assertEqual(sent['model'], 'openai/gpt-oss-20b')
        self.assertEqual(sent['response_format'], {'type':'text'})
        with sqlite3.connect(f.base / 'provider.sqlite3') as db:
            state, actual_status, tokens, input_tokens, output_tokens, result = db.execute(
                "SELECT state,status,tokens,input_tokens,output_tokens,result FROM operations WHERE provider='groq'").fetchone()
        self.assertEqual((state, actual_status, result), ('FAILED', status, None))
        self.assertGreater(tokens, 2048)
        self.assertEqual((tokens, output_tokens), (input_tokens + 2048, 2048))
        for path in f.directory.iterdir():
            if path.is_file():
                self.assertNotIn('PRIVATE_FAILED_SCHEMA_CANARY', path.read_text(encoding='utf8'))
        before = {path.name: path.read_bytes() for path in f.directory.iterdir() if path.is_file()}
        with f.runtime().activate('capture'), self.assertRaises(Exception):
            capture_confirmed(f.directory, SEED_ID, receipt, f.settings, UNIT_SECRET, _test_adapters=f.adapters())
        self.assertEqual((len(f.transport.calls), len(f.opener.calls)), (3, 1))
        self.assertEqual({path.name: path.read_bytes() for path in f.directory.iterdir() if path.is_file()}, before)

    def test_unsupported_schema_http400_remains_charged_without_relaxation(self):
        self.fail_http(400, 'unsupported_response_format')

    def test_strict_model_http429_remains_charged_without_automatic_retry(self):
        self.fail_http(429, 'rate_limit_exceeded')

    def test_independent_verifier_rejects_any_model_reason_and_separate_echo_errors(self):
        def mutate(body,page):
            for row in body['results']['entities']:
                if UUID(row['entity_id']).int==9:row['name']='Training Day';row['properties']['release_year']=2001
        f=self.fixture;f.finish(transport=capture_fixtures.WideTransport(mutation=mutate))
        packet=json.loads((f.directory/'wide-execution-001.json').read_bytes());manifest=json.loads((f.directory/'wide-model-manifest.json').read_bytes())
        for expected,change in (
            ('eligible catalog index',{'catalog_index':8,'title':'Training Day','release_year':2001,'text':IdentityAlignmentTests.OBSERVED_WRONG_REASON}),
            ('eligible catalog index',{'catalog_index':8,'title':'Spider-Man','release_year':2002}),
            ('eligible catalog index',{'catalog_index':8,'title':'Training Day','release_year':2002})):
            forged=copy.deepcopy(packet);forged['observation']['provider_envelope']['choice']['ordered_catalog_indices'][0]=change
            with self.subTest(change=change),self.assertRaisesRegex(SchemaError,expected):verify_packet(forged,manifest,forged['effective_request'])

    def test_v3_v4_v5_v6_v7_v8_complete_packets_and_partial_projections_remain_read_only(self):
        from affinityqa import wide_cinema_v3_verify,wide_cinema_v4_verify,wide_cinema_v5_verify,wide_cinema_v6_verify,wide_cinema_v7_verify,wide_cinema_v8_verify
        from affinityqa.wide_cinema_agent import failure_projection
        f=self.fixture;f.finish();current=json.loads((f.directory/'wide-execution-001.json').read_bytes())
        for legacy in (wide_cinema_v3_verify,wide_cinema_v4_verify,wide_cinema_v5_verify,wide_cinema_v6_verify,wide_cinema_v7_verify,wide_cinema_v8_verify):
            with self.subTest(protocol=legacy.PROTOCOL):
                packet=copy.deepcopy(current);context=packet['effective_request']['context']
                context.pop('grounded_explanations');context.pop('grounding_sha256');context['context_sha256']=fingerprint({k:v for k,v in context.items() if k!='context_sha256'})
                decision=legacy._decision(packet['effective_request']['request'],context,f.directory.name)
                manifest=legacy.expected_manifest('test-double-only');payload=legacy._input_schema(decision)[0]
                key=fingerprint({'protocol':legacy.PROTOCOL,'request':decision['request'],'context':context,'manifest':manifest})
                env=packet['observation']['provider_envelope'];block=[];reasons=[]
                for row in env['choice']['ordered_catalog_indices']:
                    target=context['candidate_catalog'][row['catalog_index']]
                    row=dict(row,title=target['name'],release_year=target['release_year'])
                    text=f"{row['title']} ({row['release_year']}): Interpretación sintética histórica sin afirmación de calidad ni verdad."
                    reasons.append({'catalog_index':row['catalog_index'],'text':text})
                    block.append(dict(row,text=text) if legacy.PROTOCOL[-2:] in ('v6','v7','v8') else dict(catalog_index=row['catalog_index'],text=text))
                env['choice']['ordered_catalog_indices']=block;checked={'ranking':packet['response']['ranked_entity_ids'],'reasons':reasons}
                packet.update(effective_request=decision,model_payload=payload,cache_key_sha256=key)
                packet['response']={'schema_version':1,'request_id':decision['request_id'],'ranked_entity_ids':checked['ranking'],'reasons':reasons,'output_sha256':fingerprint(checked),'cache_key_sha256':key}
                packet['observation'].update(provider_envelope_sha256=fingerprint(env),input_sha256=fingerprint(payload),
                    output_sha256=fingerprint(checked),provider_request_sha256=fingerprint(legacy._wire(decision,manifest)))
                self.assertEqual(verify_packet(packet,manifest,decision)['ranking'],checked['ranking'])
                prepared={'provider_request_sha256':fingerprint(legacy._wire(decision,manifest))}
                partial=failure_projection(decision,prepared,'COMPLETION','COMPLETION_REJECTED',None,None,None);partial['protocol']=legacy.PROTOCOL
                self.assertEqual(legacy._rejection(partial,decision,prepared),partial);self.assertFalse(partial['accepted'])
                changed=copy.deepcopy(manifest);changed['options']['max_completion_tokens']=1024 if legacy.PROTOCOL.endswith('v8') else 2048
                with self.assertRaises(SchemaError):verify_packet(packet,changed,decision)

    def test_v9_closed_triples_remain_readable_but_are_never_current_model_observations(self):
        from affinityqa import wide_cinema_v9_verify as legacy
        f=self.fixture;f.finish();packet=json.loads((f.directory/'wide-execution-001.json').read_bytes())
        context=packet['effective_request']['context'];decision=legacy._decision(packet['effective_request']['request'],context,f.directory.name)
        manifest=legacy.expected_manifest('test-double-only');payload=legacy._input_schema(decision)[0]
        env=packet['observation']['provider_envelope'];block=[]
        for row in env['choice']['ordered_catalog_indices']:
            target=context['candidate_catalog'][row['catalog_index']]
            block.append(dict(row,title=target['name'],release_year=target['release_year']))
        env['choice']['ordered_catalog_indices']=block
        checked={'ranking':packet['response']['ranked_entity_ids'],'choices':block}
        key=fingerprint({'protocol':legacy.PROTOCOL,'request':decision['request'],'context':context,'manifest':manifest})
        packet.update(effective_request=decision,model_payload=payload,cache_key_sha256=key)
        packet['response']={'schema_version':1,'request_id':decision['request_id'],'ranked_entity_ids':checked['ranking'],
            'selected_identities':block,'output_sha256':fingerprint(checked),'cache_key_sha256':key}
        packet['observation'].update(provider_envelope_sha256=fingerprint(env),input_sha256=fingerprint(payload),
            output_sha256=fingerprint(checked),provider_request_sha256=fingerprint(legacy._wire(decision,manifest)))
        before=copy.deepcopy(packet);self.assertEqual(verify_packet(packet,manifest,decision),checked);self.assertEqual(packet,before)
        forged=copy.deepcopy(packet);forged['observation']['provider_envelope']['choice']['ordered_catalog_indices'][0]['title']='Synthetic wrong echo'
        with self.assertRaisesRegex(SchemaError,'exact indexed title and year'):verify_packet(forged,manifest,decision)
        for mutation in (lambda p:p['response']['ranked_entity_ids'].reverse(),lambda p:p['response']['selected_identities'].reverse()):
            forged=copy.deepcopy(packet);mutation(forged)
            with self.assertRaises(SchemaError):verify_packet(forged,manifest,decision)

    def test_v10_packet_cannot_be_relabelled_as_v3_v4_v5_v6_v7_and_has_no_relocation_override(self):
        f = self.fixture
        _, receipt = f.finish()
        packet = json.loads((f.directory / 'wide-execution-001.json').read_bytes())
        manifest = json.loads((f.directory / 'wide-model-manifest.json').read_bytes())
        decision = copy.deepcopy(packet['effective_request'])
        decision['protocol'] = 'qloo-wide-cinema-discovery-v3'
        forged = copy.deepcopy(packet)
        forged['effective_request'] = decision
        with self.assertRaises(SchemaError):
            verify_packet(forged, manifest, decision)
        decision['protocol'] = 'qloo-wide-cinema-discovery-v5'
        forged['effective_request'] = decision
        with self.assertRaises(SchemaError):
            verify_packet(forged, manifest, decision)
        decision['protocol'] = 'qloo-wide-cinema-discovery-v4'
        forged['effective_request'] = decision
        with self.assertRaises(SchemaError):
            verify_packet(forged, manifest, decision)
        decision['protocol'] = 'qloo-wide-cinema-discovery-v6'
        forged['effective_request'] = decision
        with self.assertRaises(SchemaError):
            verify_packet(forged, manifest, decision)
        decision['protocol'] = 'qloo-wide-cinema-discovery-v7'
        forged['effective_request'] = decision
        with self.assertRaises(SchemaError):
            verify_packet(forged, manifest, decision)
        decision['protocol']='qloo-wide-cinema-discovery-v8'
        forged['effective_request']=decision
        with self.assertRaises(SchemaError):verify_packet(forged,manifest,decision)
        decision['protocol']='qloo-wide-cinema-discovery-v9'
        forged['effective_request']=decision
        with self.assertRaises(SchemaError):verify_packet(forged,manifest,decision)
        with self.assertRaises(SchemaError):
            verify_discoveries(f.directory, original_output_directory=str(f.directory.parent))
        self.assertEqual(receipt['verification_status'], 'VERIFIED_COMPLETE')

    def test_provider_runtime_reserves_same_exact2048_wire_cost_as_agent_and_verifier(self):
        f=self.fixture
        with patch.object(f.scheduler,'reserve',wraps=f.scheduler.reserve) as reserve:
            f.finish()
        operation=next(call.kwargs for call in reserve.call_args_list if call.kwargs.get('provider')=='groq')
        actual=f.opener.calls[0][0].data
        expected=_reservation(actual)
        self.assertEqual({key:operation[key] for key in ('tokens','input_tokens','output_tokens')},expected)
        events=[json.loads(line) for line in (f.directory/'ledger.jsonl').read_text(encoding='utf8').splitlines()]
        prepared=next(row['data'] for row in events if row['kind']=='wide_model_attempt_prepared')
        self.assertEqual(prepared['reservation'],expected)
        self.assertEqual(expected['output_tokens'],2048)

    def test_independent_verifier_rejects_bounded_but_falsely_increased_prepared_cost(self):
        f=self.fixture;f.finish();path=f.directory/'ledger.jsonl';original=path.read_bytes()
        events=[json.loads(line) for line in original.splitlines()]
        costs=next(row['data']['reservation'] for row in events if row['kind']=='wide_model_attempt_prepared')
        costs['tokens']+=1;costs['input_tokens']+=1
        self.assertLessEqual(costs['tokens'],8000)
        try:
            path.write_text(''.join(json.dumps(row)+'\n' for row in events),encoding='utf8')
            with self.assertRaisesRegex(SchemaError,'exact independently reconstructed token reservation'):
                verify_discoveries(f.directory)
        finally:path.write_bytes(original)


class Completion2048EstimatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.estimator=WideHarmonyTokenEstimator(ROOT/'assets/tokenizers/o200k_base.tiktoken')

    def test_2048_cap_accepted_2049_and_boolean_rejected_and_default_agent_matches(self):
        decision=make_decision(request_fixture(),context_fixture(),'estimate2048-synthetic')
        payload=wire(decision,model_manifest('test-double-only'))
        actual=encoded(payload);cost=self.estimator.estimate(actual)
        self.assertEqual(cost['output_tokens'],2048)
        self.assertEqual(cost,_reservation(actual))
        self.assertIsInstance(WideCinemaAgent(UNIT_SECRET,_test_opener=WideOpener()).token_estimator,WideHarmonyTokenEstimator)
        for cap in (2049,0,True):
            invalid=copy.deepcopy(payload);invalid['max_completion_tokens']=cap
            with self.subTest(cap=cap),self.assertRaises(ValueError):self.estimator.estimate(encoded(invalid))

    def test_legacy1024_costs_match_immutable_estimator_for_each_historical_transport(self):
        from affinityqa.provider_runtime import PinnedHarmonyTokenEstimator
        from affinityqa import wide_cinema_v3_verify,wide_cinema_v4_verify,wide_cinema_v5_verify,wide_cinema_v6_verify,wide_cinema_v7_verify
        previous=PinnedHarmonyTokenEstimator(ROOT/'assets/tokenizers/o200k_base.tiktoken')
        for legacy in (wide_cinema_v3_verify,wide_cinema_v4_verify,wide_cinema_v5_verify,wide_cinema_v6_verify,wide_cinema_v7_verify):
            decision=legacy._decision(request_fixture(),context_fixture(),'legacy-cost-synthetic')
            data=encoded(legacy._wire(decision,legacy.expected_manifest('test-double-only')))
            with self.subTest(protocol=legacy.PROTOCOL):
                self.assertEqual(self.estimator.estimate(data),previous.estimate(data))
                self.assertEqual(self.estimator.estimate(data)['output_tokens'],1024)
        self.assertNotEqual(self.estimator.manifest,previous.manifest)

    def test_full_wire_above8000_is_stopped_before_reserve_sent_or_open(self):
        from affinityqa.provider_runtime import ProviderRuntime
        from affinityqa.provider_scheduler import ProviderScheduler,QuotaWindow
        def mutate(body,page):
            for row in body['results']['entities']:row['name']='映'*50+' '+row['entity_id'][-5:]
        decision=make_decision(request_fixture(),context_fixture(transport=capture_fixtures.WideTransport(mutation=mutate)),
            'over8000-synthetic')
        data=encoded(wire(decision,model_manifest('test-double-only')))
        self.assertLess(len(data),65536);self.assertGreater(self.estimator.estimate(data)['tokens'],8000)
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp:
            scheduler=ProviderScheduler(Path(temp)/'provider.sqlite3',limits={'groq':(QuotaWindow('rpm',10,60),)})
            opener=WideOpener();engine=WideCinemaAgent(UNIT_SECRET,_test_opener=opener,token_estimator=self.estimator)
            runtime=ProviderRuntime(scheduler,'over8000-synthetic','synthetic-owner',token_estimator=self.estimator)
            with patch.object(scheduler,'reserve',wraps=scheduler.reserve) as reserve,patch.object(scheduler,'mark_sent',wraps=scheduler.mark_sent) as sent:
                with runtime.activate('capture'),self.assertRaises(AgentError):engine.rank(decision)
                reserve.assert_not_called();sent.assert_not_called()
            self.assertEqual((engine.calls,len(opener.calls)),(0,0))


class IdentityAlignmentTests(unittest.TestCase):
    OBSERVED_WRONG_REASON='Spider-Man 2002 combina acción y crecimiento personal, presentando un héroe que, al igual que los protagonistas de 8 Mile, enfrenta obstáculos y evoluciona.'

    def decision(self):
        def mutate(body,page):
            replacements={9:('Training Day',2001),11:('Spider-Man',2002)}
            for row in body['results']['entities']:
                number=UUID(row['entity_id']).int
                if number in replacements:row['name'],row['properties']['release_year']=replacements[number]
        return make_decision(request_fixture(),context_fixture(transport=capture_fixtures.WideTransport(mutation=mutate)),'identity-synthetic-only')

    def test_observed_training_index_cannot_carry_spider_title_year_or_reason(self):
        decision=self.decision();value=output_fixture(decision);value['ordered_catalog_indices'][0]=choice_fixture(decision,8)
        self.assertEqual(model_input(decision)['candidates'][8]['title'],'Training Day')
        for change in ({'title':'Spider-Man','release_year':2002},{'text':self.OBSERVED_WRONG_REASON}):
            bad=copy.deepcopy(value);bad['ordered_catalog_indices'][0].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(SchemaError,'OUTPUT_CHOICE_SHAPE'):validate_output(decision,bad)
        from affinityqa.wide_cinema_discovery import result_for
        result=result_for(decision,value);row=next(r for r in result['candidate_catalog'] if r['entity_id']==result['delivered'][0])
        self.assertEqual((row['name'],row['release_year']),('Training Day',2001))
        self.assertEqual((result['reasons'][0]['evidence']['title'],result['reasons'][0]['evidence']['release_year']),('Training Day',2001))

    def test_echoed_identity_and_generated_prose_are_all_forbidden_extra_fields(self):
        decision=self.decision();value=output_fixture(decision)
        self.assertEqual(set(validate_output(decision,value)['choices'][0]),{'catalog_index'})
        for key,raw in (('title','Training Day'),('release_year',2001),('release_year',True),('entity_id',str(UUID(int=9))),('text','short'),('reason_refs',[])):
            bad=copy.deepcopy(value);bad['ordered_catalog_indices'][0][key]=raw
            with self.subTest(key=key,raw=raw),self.assertRaisesRegex(SchemaError,'OUTPUT_CHOICE_SHAPE'):validate_output(decision,bad)

    def test_sparse_indices_same_name_different_year_preserve_canonical_order(self):
        def mutate(body,page):
            for row in body['results']['entities']:
                number=UUID(row['entity_id']).int
                if number in (1,2):row['name']='Lunar Echo Ω';row['properties']['release_year']=2000+number
        decision=make_decision(request_fixture(excluded_entity_ids=[str(UUID(int=3)),str(UUID(int=5))]),context_fixture(transport=capture_fixtures.WideTransport(mutation=mutate)),'novel-synthetic-only')
        self.assertEqual([r['catalog_index'] for r in model_input(decision)['candidates'][:5]],[0,1,3,5,6])
        from affinityqa.wide_cinema_discovery import result_for
        result=result_for(decision,output_fixture(decision,first=True))
        self.assertEqual(result['delivered'][:2],[str(UUID(int=1)),str(UUID(int=2))])
        self.assertEqual([r['evidence']['release_year'] for r in result['reasons'][:2]],[2001,2002])

    def test_unicode_and_long_titles_are_server_reconstructed_without_echo_or_truncation(self):
        for title in ('Café Ω','A'*250):
            def mutate(body,page):
                if page==1:body['results']['entities'][0]['name']=title
            decision=make_decision(request_fixture(),context_fixture(transport=capture_fixtures.WideTransport(mutation=mutate)),'unicode-target-synthetic-only')
            from affinityqa.wide_cinema_discovery import result_for
            output=output_fixture(decision,first=True);result=result_for(decision,output)
            self.assertEqual(len(model_input(decision)['candidates']),100)
            self.assertEqual(output['ordered_catalog_indices'][0],{'catalog_index':0})
            self.assertEqual(result['reasons'][0]['evidence']['title'],title)

    def test_v9_observed_safe_rejection_shape_is_retained_and_new_indices_are_not_old_salvage(self):
        from affinityqa import wide_cinema_v9_verify as legacy
        from affinityqa.wide_cinema_agent import failure_projection
        decision=self.decision();indices=[7,76,73,34,3]
        value={'ordered_catalog_indices':[{'catalog_index':i} for i in indices]}
        self.assertEqual(validate_output(decision,value)['ranking'],[decision['context']['candidate_catalog'][i]['entity_id'] for i in indices])
        old=legacy._decision(decision['request'],decision['context'],'legacy-v9-synthetic')
        prepared={'provider_request_sha256':fingerprint(legacy._wire(old,legacy.expected_manifest('test-double-only')))}
        wrong={'ordered_catalog_indices':[dict(row,title=old['context']['candidate_catalog'][row['catalog_index']]['name'],release_year=old['context']['candidate_catalog'][row['catalog_index']]['release_year']) for row in value['ordered_catalog_indices']]}
        wrong['ordered_catalog_indices'][0]['title']='Synthetic wrong echoed title'
        body={'choices':[{'finish_reason':'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}}
        projection=failure_projection(old,prepared,'OUTPUT','OUTPUT_IDENTITY_TITLE',body,wrong,'a'*64);projection['protocol']=legacy.PROTOCOL
        before=copy.deepcopy(projection)
        self.assertEqual(legacy._rejection(projection,old,prepared),before)
        self.assertEqual(projection['indices'],indices);self.assertFalse(projection['accepted'])
        self.assertTrue(all(projection['indices_eligible']));self.assertNotIn('Synthetic wrong',json.dumps(projection))
        with self.assertRaisesRegex(SchemaError,'OUTPUT_CHOICE_SHAPE'):validate_output(decision,wrong)
        self.assertEqual(projection,before)


if __name__ == '__main__':
    unittest.main()
