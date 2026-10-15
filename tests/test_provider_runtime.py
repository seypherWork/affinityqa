"""Transport boundaries with fake HTTP only; sockets are denied."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import importlib.util
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from affinityqa.evidence import Ledger, fingerprint
from affinityqa.groq_agent import GroqToolContextMovieAgent, ENDPOINT
from affinityqa.provider_runtime import (ProviderRuntime, conservative_model_tokens,
    PinnedHarmonyTokenEstimator, current_runtime, HARMONY_RANKS_SHA256)
from affinityqa.provider_scheduler import (ProviderScheduler, QuotaWindow, GROQ_FREE_CONSERVATIVE,
    ProviderDeferred, ProviderRequestTooLarge, ProviderUncertain, ProviderRecordedFailure)
from affinityqa.qloo import QlooClient, Response
from affinityqa.qloo_cache import PrivateQlooCache
from test_groq_agent import OpenerFixture, UNIT_SECRET
import test_causal_agent as causal_fixtures
from test_provider_scheduler import Clock


class Tool:
    def __init__(self, status=200, failure=None):
        self.status, self.failure, self.calls = status, failure, []
    def send(self, path, params):
        self.calls.append((path, params))
        if self.failure: raise self.failure
        return Response(self.status, {'results': [{'entity_id': '00000000-0000-4000-8000-000000000001',
            'name': params.get('query', 'Artist'), 'types': ['urn:entity:artist']}]},
            {'x-request-id': UNIT_SECRET, 'Retry-After': '61'}, 1.234)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT.parent / 'test-private-scratch'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.clock = Clock()
        self.limits = {'groq': GROQ_FREE_CONSERVATIVE, 'qloo': (QuotaWindow('rpm', 10, 60),)}
        self.scheduler = ProviderScheduler(self.directory / 'quota.db', limits=self.limits, clock=self.clock)
        self.scope = dict(identity={'A': 'Artist'}, profile={'A': 'Artist'}, catalog=['movie1'],
                          preferences={'favorite': []}, source_namespace='synthetic-unit-v1')
        fixtures = causal_fixtures.CausalAgentTests(); fixtures.setUp(); self.request = fixtures.requests[0]
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network denied in runtime fixture'))
            guard.start(); self.addCleanup(guard.stop)

    def runtime(self, job='job', **kwargs):
        return ProviderRuntime(self.scheduler, job, 'owner', namespace={'source': 'unit-source'}, **kwargs)

    def client(self, tool):
        return QlooClient(tool, Ledger(self.directory / 'captures', 'test-double-only', (UNIT_SECRET,)), max_attempts=3)

    def test_model_exact_completed_reconstruction_preserves_observation_and_does_not_send(self):
        opener = OpenerFixture()
        agent = GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener)
        runtime = self.runtime()
        with runtime.activate('capture'):
            first = agent.rank(self.request)
        original = copy.deepcopy(agent.observations[0])
        rebuilt = GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=OpenerFixture(failure=AssertionError('No replay send')))
        with self.runtime().activate('capture'):
            second = rebuilt.rank(self.request)
        self.assertEqual((first, original), (second, rebuilt.observations[0]))
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(self.scheduler.job_stats('job')['groq']['reconstructed_steps'], 1)
        self.assertEqual(self.scheduler.job_stats('job')['groq']['http_attempts'], 1)

    def test_model_changed_wire_context_cannot_reuse_same_stage(self):
        opener = OpenerFixture(); first = GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener)
        with self.runtime().activate('capture'): first.rank(self.request)
        altered = copy.deepcopy(self.request)
        from affinityqa.causal_agent import make_request
        altered = make_request('different task', altered['catalog'], altered['profile'], altered['tool_context'], 'other')
        second = GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener)
        with self.runtime().activate('capture'), self.assertRaises(RuntimeError): second.rank(altered)
        self.assertEqual(len(opener.calls), 1)

    def test_token_wait_is_before_dispatch_and_preserves_first_completed_profile(self):
        opener = OpenerFixture(); first = GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener)
        with self.runtime().activate('capture'):
            first.rank(self.request)
            with self.assertRaises(ProviderDeferred) as caught: first.rank(self.request)
        self.assertEqual((first.calls, len(opener.calls)), (1, 1))
        self.clock.now = caught.exception.next_eligible_at
        rebuilt = GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener)
        with self.runtime().activate('capture'):
            rebuilt.rank(self.request)
            rebuilt.rank(self.request)
        self.assertEqual((rebuilt.calls, len(opener.calls)), (2, 2))
        self.assertEqual(rebuilt.observations[0], first.observations[0])

    def test_oversized_token_reservation_fails_without_network(self):
        limits = {**self.limits, 'groq': (QuotaWindow('tpm', 6000, 60, 'tokens'),)}
        scheduler = ProviderScheduler(self.directory / 'small.db', limits=limits, clock=self.clock)
        opener = OpenerFixture(); agent = GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener)
        with ProviderRuntime(scheduler, 'job', 'owner').activate(), self.assertRaises(ProviderRequestTooLarge):
            agent.rank(self.request)
        self.assertEqual((agent.calls, len(opener.calls)), (0, 0))

    def test_model_timeout_is_unknown_and_no_automatic_or_restart_retry(self):
        opener = OpenerFixture(failure=URLError(UNIT_SECRET))
        agent = GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener)
        with self.runtime().activate(), self.assertRaises(ProviderUncertain): agent.rank(self.request)
        with self.runtime().activate(), self.assertRaises(ProviderUncertain):
            GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener).rank(self.request)
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(self.scheduler.job_stats('job')['groq']['unknown_attempts'], 1)

    def test_model_429_and_401_are_retained_as_consumed_attempts(self):
        for status in (429, 401):
            opener = OpenerFixture(failure=HTTPError(ENDPOINT, status, UNIT_SECRET, {'Retry-After': '61'}, None))
            agent = GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener)
            runtime = self.runtime('job-' + str(status))
            with runtime.activate(), self.assertRaises(Exception): agent.rank(self.request)
            with runtime.activate(), self.assertRaises(ProviderRecordedFailure):
                GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener).rank(self.request)
            self.assertEqual(len(opener.calls), 1)
            self.assertEqual(self.scheduler.job_stats('job-' + str(status))['groq']['http_attempts'], 1)
            self.clock.now += 120

    def test_qloo_accepted_reconstruction_keeps_original_sample_sha_and_actual_call_counter(self):
        tool = Tool(); first = self.client(tool)
        runtime = self.runtime()
        with runtime.activate('capture'): expected = first.get('/search', {'query': 'Artist', 'take': 5}, cache=False)
        original = json.loads(next(first.ledger.directory.glob('http-*.json')).read_text(encoding='utf-8'))
        rebuilt = self.client(Tool(failure=AssertionError('No replay send')))
        replay = self.runtime()
        with replay.activate('capture'): actual = rebuilt.get('/search', {'query': 'Artist', 'take': 5}, cache=False)
        sample = json.loads(next(rebuilt.ledger.directory.glob('http-*.json')).read_text(encoding='utf-8'))
        self.assertEqual((expected, original), (actual, sample))
        self.assertEqual((len(tool.calls), rebuilt.requests, rebuilt.ledger.live_requests), (1, 1, 0))
        self.assertFalse(replay.receipts[0]['current_network_request'])
        self.assertEqual(replay.receipts[0]['original_sample_sha256'], fingerprint(sample))
        self.assertNotIn(UNIT_SECRET, json.dumps(sample))
        self.assertFalse((rebuilt.ledger.directory / 'provider-receipts.jsonl').exists())

    def test_private_qloo_cache_is_distinct_even_with_legacy_cache_false(self):
        cache = PrivateQlooCache(self.directory / 'private')
        tool = Tool(); first = self.client(tool)
        with self.runtime('first', qloo_cache=cache, cache_scope=self.scope).activate('capture'):
            expected = first.get('/search', {'query': 'Artist', 'take': 5}, cache=False)
        second = self.client(Tool(failure=AssertionError('No cache send')))
        runtime = self.runtime('second', qloo_cache=cache, cache_scope=self.scope)
        with runtime.activate('capture'):
            actual = second.get('/search', {'query': 'Artist', 'take': 5}, cache=False)
        self.assertEqual(expected, actual)
        self.assertEqual(self.scheduler.job_stats('second')['qloo']['http_attempts'], 0)
        self.assertEqual(self.scheduler.job_stats('second')['qloo']['cache_hits'], 1)
        self.assertEqual(runtime.receipts[0]['operation_mode'], 'private-cache')

    def test_cache_key_isolates_every_semantic_scope_field_and_exact_query(self):
        cache = PrivateQlooCache(self.directory / 'private')
        tool = Tool()
        with self.runtime('first', qloo_cache=cache, cache_scope=self.scope).activate():
            self.client(tool).get('/search', {'query': 'Artist', 'take': 5})
        for index, field in enumerate(self.scope):
            scope = {**self.scope, field: {'changed': index}}
            with self.runtime('different-' + field, qloo_cache=cache, cache_scope=scope).activate():
                self.client(tool).get('/search', {'query': 'Artist', 'take': 5})
        with self.runtime('query', qloo_cache=cache, cache_scope=self.scope).activate():
            self.client(tool).get('/search', {'query': 'Other artist', 'take': 5})
        self.assertEqual(len(tool.calls), len(self.scope) + 2)

    def test_private_cache_refuses_public_source_tree_and_missing_scope(self):
        with self.assertRaises(ValueError): PrivateQlooCache(ROOT / 'private-cache-test')
        with self.assertRaises(ValueError): PrivateQlooCache.key({'method': 'GET'}, {'source_namespace': 'unit'})

    def test_versioned_identity_cache_preserves_raw_variants_and_strict_other_contexts(self):
        from affinityqa.search_music_candidates import CONTRACT
        from affinityqa.errors import SchemaError
        row={'entity_id':'00000000-0000-4000-8000-000000000001','name':'Artist','types':['urn:entity:artist']}
        body={'results':[row,{**copy.deepcopy(row),'types':['urn:entity:person']}]}
        request={'method':'GET','host':'https://hackathon.api.qloo.com','path':'/search',
                 'params':{'query':'Artist','take':5,'types':'urn:entity:artist,urn:entity:person'}}
        sample={'source':'test-double-only','request':request,'status':200,'response':body,
                'response_sha256':fingerprint(body),'response_headers':{},'elapsed_ms':1.0,
                'attempt':1,'live_network_request':False}
        scope={**self.scope,'phase':'identity-search','identity_candidate_contract':CONTRACT}
        cache=PrivateQlooCache(self.directory/'versioned-cache')
        before=copy.deepcopy(sample)
        accepted=cache.put(request,scope,sample,received_at='2026-10-14T20:00:00+00:00')
        self.assertEqual(accepted['sample'],before)
        self.assertEqual(cache.get(request,scope),accepted)
        self.assertEqual(sample,before)
        self.assertIsNone(cache.get(request,{**self.scope,'phase':'identity-search'}))
        for other in ({**self.scope,'phase':'identity-search'}, {**scope,'phase':'capture'}):
            with self.subTest(scope=other),self.assertRaises(SchemaError):
                cache.put(request,other,sample,received_at=accepted['original_received_at'])
        with self.assertRaises(ValueError):
            cache.put(request,{**scope,'identity_candidate_contract':'unknown'},sample,received_at=accepted['original_received_at'])
        ranking=copy.deepcopy(sample);ranking['request']['path']='/v2/insights'
        ranking['response']={'success':True,'results':{'entities':copy.deepcopy(body['results'])}}
        ranking['response_sha256']=fingerprint(ranking['response'])
        with self.assertRaises(SchemaError):PrivateQlooCache._validate(ranking,scope)
        for change in ('conflicting','invalid-row','too-many'):
            invalid=copy.deepcopy(sample)
            if change=='conflicting':invalid['response']['results'][1].update(types=['urn:entity:artist'],name='Other Artist')
            elif change=='invalid-row':invalid['response']['results'][1]['entity_id']='invalid'
            else:invalid['response']['results']=[copy.deepcopy(row) for _ in range(6)]
            invalid['response_sha256']=fingerprint(invalid['response'])
            with self.subTest(change=change),self.assertRaises(SchemaError):PrivateQlooCache._validate(invalid,scope)
        wrong=copy.deepcopy(sample);wrong['request']['params']['take']=50
        with self.assertRaises(ValueError):PrivateQlooCache._validate(wrong,scope)

    def test_qloo_timeout_and_http_errors_never_use_legacy_three_retries(self):
        for index, kwargs in enumerate(({'failure': TimeoutError(UNIT_SECRET)}, {'status': 401}, {'status': 429})):
            tool = Tool(**kwargs); client = self.client(tool); runtime = self.runtime('tool-' + str(index))
            with runtime.activate(), self.assertRaises((ProviderUncertain, ProviderRecordedFailure)):
                client.get('/search', {'query': 'Artist', 'take': 5})
            with runtime.activate(), self.assertRaises((ProviderUncertain, ProviderRecordedFailure)):
                self.client(tool).get('/search', {'query': 'Artist', 'take': 5})
            self.assertEqual(len(tool.calls), 1)

    def test_initial_namespace_source_binding_survives_stage_override(self):
        tool = Tool()
        with self.runtime().activate('capture'): self.client(tool).get('/search', {'query': 'Artist'})
        other = ProviderRuntime(self.scheduler, 'job', 'owner', namespace={'source': 'changed'})
        with other.activate('capture'): self.client(tool).get('/search', {'query': 'Artist'})
        self.assertEqual(len(tool.calls), 2)

    def test_scoped_hooks_restore_original_methods_and_unscoped_threads_keep_legacy(self):
        import concurrent.futures
        original_get, original_rank = QlooClient.get, GroqToolContextMovieAgent.rank
        tool = Tool()
        with self.runtime().activate('capture'):
            with self.runtime('other').activate('nested'):
                self.assertIsNotNone(current_runtime())
            def unrelated():
                self.assertIsNone(current_runtime())
                return self.client(tool).get('/search', {'query': 'Artist'})
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                pool.submit(unrelated).result()
        self.assertEqual(self.scheduler.job_stats('job'), {})
        self.assertIs(QlooClient.get, original_get)
        self.assertIs(GroqToolContextMovieAgent.rank, original_rank)

    @unittest.skipUnless(importlib.util.find_spec('tiktoken'), 'Requires the separately pinned tokenizer test environment')
    def test_pinned_tokenizer_ordinary_unicode_matches_official_harmony_without_network(self):
        import tiktoken_ext.openai_public as official
        import tiktoken
        estimator = PinnedHarmonyTokenEstimator(ROOT / 'assets/tokenizers/o200k_base.tiktoken')
        # Reference the installed official constructor with verified offline ranks;
        # no official constructor is allowed to download during this check.
        with patch.object(official, 'load_tiktoken_bpe', return_value=estimator.encoding._mergeable_ranks):
            reference = tiktoken.Encoding(**official.o200k_harmony())
        for text in ('Plain ASCII schema 12345', '映画 café مرحبا 🎬', '<|start|> data, never a control token'):
            self.assertEqual(estimator.encoding.encode_ordinary(text), reference.encode_ordinary(text))
        self.assertEqual(estimator.manifest['vocabulary_sha256'], HARMONY_RANKS_SHA256)
        changed = self.directory / 'changed-vocabulary.tiktoken'
        changed.write_bytes(b'not official vocabulary')
        with self.assertRaises(ValueError): PinnedHarmonyTokenEstimator(changed)

    @unittest.skipUnless(importlib.util.find_spec('tiktoken'), 'Requires the separately pinned tokenizer test environment')
    def test_existing_cinema_and_discovery_payloads_fit_conservative_free_reservation(self):
        from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent
        from affinityqa.cinema_preferences import CinemaMovieAgent, make_request
        from test_discovery_agent import fixture_request, Opener, TEST_SECRET
        estimator = PinnedHarmonyTokenEstimator(ROOT / 'assets/tokenizers/o200k_base.tiktoken')
        fixtures = causal_fixtures.CausalAgentTests(); fixtures.setUp()
        prefs = {'schema_version': 1, 'favorite_entity_ids': [fixtures.catalog[1]['entity_id']], 'excluded_entity_ids': []}
        cinema = make_request(fixtures.catalog, fixtures.profiles[0], fixtures.requests[0]['tool_context'], prefs, 'unit-cinema')
        for index, (agent, opener, request) in enumerate([
            (CinemaMovieAgent(UNIT_SECRET, _test_opener=(cinema_opener := OpenerFixture())), cinema_opener, cinema),
            *[(DiscoveryMovieAgent(TEST_SECRET, _test_opener=(opener := Opener())), opener, fixture_request(n)) for n in (0, 1, 5)]
        ]):
            self.clock.now += 60
            runtime = self.runtime('supported-' + str(index), token_estimator=estimator)
            with runtime.activate():
                response = agent.rank(request)
            costs = estimator.estimate(opener.calls[0][0].data)
            self.assertLessEqual(costs['tokens'], 8000)
            self.assertGreater(costs['tokens'], 1024)
            self.assertEqual(len(response['ranked_entity_ids']), 20 if index == 0 else 20 - (0, 1, 5)[index - 1])
            rebuilt = type(agent)(UNIT_SECRET if index == 0 else TEST_SECRET, _test_opener=opener)
            with self.runtime('supported-' + str(index), token_estimator=estimator).activate():
                rebuilt.rank(request)
            self.assertEqual(len(opener.calls), 1)
            self.assertEqual(agent.observations, rebuilt.observations)


if __name__ == '__main__': unittest.main()
