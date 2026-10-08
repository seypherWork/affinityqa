"""Denied-network fixtures: not Groq service acceptance or cultural evidence."""
import copy
from email.message import Message
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
import test_causal_agent as fixtures
from affinityqa.agents import AgentError
from affinityqa.causal_agent import make_request
from affinityqa.causal_runner import capture_pair, freeze_policy
from affinityqa.evidence import fingerprint
from affinityqa.groq_agent import GroqToolContextMovieAgent, ENDPOINT, MODEL, MAX_RESPONSE_BYTES

UNIT_SECRET = 'unit-provider-private-credential-only'
UNIT_QLOO_SECRET = 'unit-other-provider-private-credential-only'


class ResponseFixture(io.BytesIO):
    def __init__(self, raw, status=200, content_type='application/json'):
        super().__init__(raw)
        self.status = status
        self.headers = Message()
        self.headers['Content-Type'] = content_type


class OpenerFixture:
    def __init__(self, mutation=None, raw=None, failure=None, status=200, content_type='application/json'):
        self.mutation, self.raw, self.failure = mutation, raw, failure
        self.status, self.content_type = status, content_type
        self.calls = []

    def open(self, request, timeout):
        payload = json.loads(request.data)
        self.calls.append((request, payload, timeout))
        if self.failure is not None:
            raise self.failure
        data = json.loads(payload['messages'][1]['content'])
        indices = [row['catalog_index'] for row in data['provider_movie_context']]
        body = {'id': 'unit-completion-' + str(len(self.calls)), 'object': 'chat.completion',
                'created': 1791280000, 'model': MODEL, 'system_fingerprint': 'unit-deployment-a',
                'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant',
                    'content': json.dumps({'ordered_catalog_indices': indices})}}],
                'usage': {'prompt_tokens': 1000, 'completion_tokens': 300, 'total_tokens': 1300,
                          'completion_tokens_details': {'reasoning_tokens': 100}}}
        if self.mutation:
            self.mutation(body)
        raw = self.raw if self.raw is not None else json.dumps(body).encode()
        return ResponseFixture(raw, self.status, self.content_type)


class GroqAgentTests(unittest.TestCase):
    def setUp(self):
        data = fixtures.CausalAgentTests()
        data.setUp()
        self.data = data
        self.request = data.requests[0]
        for target in ('socket.socket', 'socket.create_connection', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network/DNS denied in offline fixture'))
            guard.start()
            self.addCleanup(guard.stop)

    def agent(self, opener=None, **kwargs):
        opener = opener or OpenerFixture()
        return GroqToolContextMovieAgent(UNIT_SECRET, _test_opener=opener, **kwargs), opener

    def test_constructor_has_no_calls_or_local_model_identity(self):
        agent, opener = self.agent()
        self.assertEqual(opener.calls, [])
        self.assertEqual(agent.calls, 0)
        self.assertEqual(agent.source, 'test-double-only')
        self.assertIsNone(agent.manifest['model_weights_sha256'])
        self.assertFalse(agent.manifest['immutable_model_revision_attested'])
        self.assertNotIn('model_digest', agent.manifest)

    def test_invalid_private_configuration_rejected_before_transport(self):
        for kwargs in ({'model': 'other-model'}, {'max_calls': True}, {'max_calls': 0},
                       {'max_calls': 40}, {'timeout': True}, {'timeout': float('nan')},
                       {'forbidden_secrets': [UNIT_QLOO_SECRET]}):
            with self.subTest(kwargs=kwargs), self.assertRaises(AgentError):
                self.agent(**kwargs)
        for key in ('', 'has whitespace credential', 'unit-key\r\nHeader:value'):
            with self.assertRaises(AgentError):
                GroqToolContextMovieAgent(key, _test_opener=OpenerFixture())

    def test_strict_request_and_actual_boundary_observation(self):
        agent, opener = self.agent()
        result = agent.rank(self.request)
        request, payload, timeout = opener.calls[0]
        self.assertEqual(request.full_url, ENDPOINT)
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + UNIT_SECRET)
        self.assertEqual(request.get_header('User-agent'),
                         'AffinityQA/0.2.0 (+https://github.com/seypherWork/affinityqa)')
        self.assertFalse(payload['stream'])
        self.assertFalse(payload['include_reasoning'])
        self.assertEqual(payload['reasoning_effort'], 'low')
        contract = payload['response_format']['json_schema']
        self.assertTrue(contract['strict'])
        self.assertFalse(contract['schema']['additionalProperties'])
        self.assertEqual(contract['schema']['properties']['ordered_catalog_indices']['maxItems'], 20)
        data = json.loads(payload['messages'][1]['content'])
        self.assertEqual(data['profile'], self.request['profile'])
        self.assertEqual(len(data['provider_movie_context']), 20)
        self.assertEqual(result['ranked_entity_ids'], [row['entity_id'] for row in self.data.catalog])
        observation = agent.observations[0]
        self.assertEqual(observation['input_sha256'], fingerprint(data))
        self.assertEqual(observation['output_sha256'], fingerprint(result['ranked_entity_ids']))
        self.assertEqual(observation['execution_source'], 'test-double-only')
        self.assertFalse(observation['model_revision_attested'])
        self.assertFalse(observation['private_thinking_recorded'])
        self.assertNotIn(UNIT_SECRET, json.dumps(observation))

    def test_invalid_request_no_inference_attempt(self):
        agent, opener = self.agent()
        request = copy.deepcopy(self.request)
        request['request_id'] = '0'*64
        with self.assertRaises(AgentError):
            agent.rank(request)
        self.assertEqual((agent.calls, len(opener.calls)), (0, 0))

    def test_model_contract_mutation_stops_before_transport(self):
        agent, opener = self.agent()
        agent.manifest['options']['max_completion_tokens'] = 5000
        with self.assertRaises(AgentError):
            agent.rank(self.request)
        self.assertEqual((agent.calls, len(opener.calls)), (0, 0))

    def test_own_and_other_provider_secret_cannot_enter_prompt(self):
        for secret in (UNIT_SECRET, UNIT_QLOO_SECRET):
            agent, opener = self.agent(forbidden_secrets=(UNIT_QLOO_SECRET,))
            request = make_request('Do not send ' + secret, self.data.catalog,
                self.data.profiles[0], self.request['tool_context'], 'private-exclusion')
            with self.assertRaises(AgentError):
                agent.rank(request)
            self.assertEqual((agent.calls, len(opener.calls)), (0, 0))

    def test_missing_duplicate_boolean_invented_positions_rejected(self):
        variants = [list(range(19)), [0]*20, list(range(19))+[True],
                    list(range(19))+[20], list(range(19))+['19']]
        for indices in variants:
            def mutation(body):
                body['choices'][0]['message']['content'] = json.dumps({'ordered_catalog_indices': indices})
            agent, opener = self.agent(OpenerFixture(mutation))
            with self.subTest(indices=indices), self.assertRaises(AgentError):
                agent.rank(self.request)
            self.assertEqual((agent.calls, len(opener.calls), len(agent.observations)), (1, 1, 0))

    def test_extra_or_duplicate_fields_and_prose_rejected(self):
        answers = [json.dumps({'ordered_catalog_indices': list(range(20)), 'extra': 1}),
                   '{"ordered_catalog_indices":[],"ordered_catalog_indices":[]}',
                   'Here is the ranking: ' + json.dumps({'ordered_catalog_indices': list(range(20))})]
        for answer in answers:
            agent, opener = self.agent(OpenerFixture(lambda body: body['choices'][0]['message'].update(content=answer)))
            with self.subTest(answer=answer), self.assertRaises(AgentError):
                agent.rank(self.request)
            self.assertEqual(len(opener.calls), 1)

    def test_truncation_refusal_and_reasoning_not_admitted(self):
        changes = [lambda body: body['choices'][0].update(finish_reason='length'),
                   lambda body: body['choices'][0]['message'].update(refusal='refused'),
                   lambda body: body['choices'][0]['message'].update(reasoning='private hidden text'),
                   lambda body: body['choices'][0]['message'].update(tool_calls=[{'id': 'tool'}])]
        for mutation in changes:
            agent, _ = self.agent(OpenerFixture(mutation))
            with self.assertRaises(AgentError):
                agent.rank(self.request)
            self.assertEqual(agent.observations, [])

    def test_absent_null_or_empty_reasoning_is_not_private_text(self):
        for reasoning in ('absent', None, ''):
            mutation = None if reasoning == 'absent' else lambda body: body['choices'][0]['message'].update(reasoning=reasoning)
            agent, _ = self.agent(OpenerFixture(mutation))
            with self.subTest(reasoning=reasoning):
                answer = agent.rank(self.request)
                self.assertEqual(len(answer['ranked_entity_ids']), 20)
                self.assertFalse(agent.observations[0]['private_thinking_recorded'])

    def test_response_identity_and_choice_count_checked(self):
        changes = [lambda body: body.update(model='unexpected-model'),
                   lambda body: body.update(object='chunk'),
                   lambda body: body.update(id=''),
                   lambda body: body.update(created=True),
                   lambda body: body['choices'].append(copy.deepcopy(body['choices'][0])),
                   lambda body: body['choices'][0].update(index=False),
                   lambda body: body['choices'][0]['message'].update(role='user')]
        for mutation in changes:
            agent, _ = self.agent(OpenerFixture(mutation))
            with self.assertRaises(AgentError):
                agent.rank(self.request)
            self.assertEqual(agent.observations, [])

    def test_usage_missing_boolean_inconsistent_and_over_budget_rejected(self):
        changes = [lambda body: body.pop('usage'),
                   lambda body: body['usage'].update(prompt_tokens=True),
                   lambda body: body['usage'].update(completion_tokens=1025, total_tokens=2025),
                   lambda body: body['usage'].update(prompt_tokens=8193, total_tokens=8493),
                   lambda body: body['usage'].update(total_tokens=1),
                   lambda body: body['usage'].update(completion_tokens_details={'reasoning_tokens': True})]
        for mutation in changes:
            agent, _ = self.agent(OpenerFixture(mutation))
            with self.assertRaises(AgentError):
                agent.rank(self.request)
            self.assertEqual(agent.calls, 1)
            self.assertEqual(agent.observations, [])

    def test_deployment_change_stops_without_filling_result(self):
        opener = OpenerFixture()
        agent, _ = self.agent(opener)
        agent.rank(self.request)
        opener.mutation = lambda body: body.update(system_fingerprint='unit-deployment-b')
        with self.assertRaises(AgentError):
            agent.rank(self.request)
        self.assertEqual((agent.calls, len(agent.observations)), (2, 1))

    def test_absent_fingerprint_stays_explicitly_unattested(self):
        agent, _ = self.agent(OpenerFixture(lambda body: body.pop('system_fingerprint')))
        agent.rank(self.request)
        agent.rank(self.request)
        self.assertTrue(all(row['system_fingerprint'] is None and not row['model_revision_attested'] for row in agent.observations))

    def test_response_credential_echo_never_recorded(self):
        agent, _ = self.agent(OpenerFixture(lambda body: body.update(error=UNIT_SECRET)))
        with self.assertRaises(AgentError) as error:
            agent.rank(self.request)
        self.assertNotIn(UNIT_SECRET, str(error.exception))
        self.assertEqual(agent.observations, [])

    def test_http_failure_consumes_attempt_and_never_retries(self):
        for code in (301, 400, 401, 429, 500):
            opener = OpenerFixture(failure=HTTPError(ENDPOINT, code, UNIT_SECRET, {}, None))
            agent, _ = self.agent(opener, max_calls=1)
            with self.subTest(code=code), self.assertRaises(AgentError) as error:
                agent.rank(self.request)
            self.assertNotIn(UNIT_SECRET, str(error.exception))
            with self.assertRaises(AgentError):
                agent.rank(self.request)
            self.assertEqual((agent.calls, len(opener.calls)), (1, 1))

    def test_network_error_redacted_and_no_retry(self):
        agent, opener = self.agent(OpenerFixture(failure=URLError(UNIT_SECRET)))
        with self.assertRaises(AgentError) as error:
            agent.rank(self.request)
        self.assertNotIn(UNIT_SECRET, str(error.exception))
        self.assertEqual(len(opener.calls), 1)

    def test_non_json_oversized_and_duplicate_envelope_rejected(self):
        variants = [OpenerFixture(content_type='text/html'),
                    OpenerFixture(raw=b'x'*(MAX_RESPONSE_BYTES+1)),
                    OpenerFixture(raw=b'{"model":"one","model":"two"}'),
                    OpenerFixture(raw=b'\xff')]
        for opener in variants:
            agent, _ = self.agent(opener)
            with self.assertRaises(AgentError):
                agent.rank(self.request)
            self.assertEqual(agent.observations, [])

    def test_unchanged_operator_runs_39_decisions_three_faults_and_real_reruns(self):
        agent, opener = self.agent()
        ledger = fixtures.FakeLedger()
        profiles = dict(zip(('A', 'B'), self.data.profiles))
        pair = {'pair_id': 'unit-remote-only', 'artists': {key: value['name'] for key, value in profiles.items()}, 'split': 'synthetic'}
        def freeze(noise, healthy, controls):
            self.assertEqual(agent.calls, 6)
            return freeze_policy(noise, healthy, controls,
                plan={'catalog_sha256': fingerprint(self.data.catalog), 'source_sha256': {'fixture': 'synthetic'}, 'pairs': [pair]},
                manifest=agent.manifest, ledger=ledger)
        record, summary, policy = capture_pair(agent, ledger, pair, self.data.catalog, profiles, self.data.contexts, freeze=freeze)
        self.assertEqual((agent.calls, len(opener.calls)), (39, 39))
        self.assertEqual(len(agent.observations), 39)
        self.assertEqual(len(summary['cases']), 3)
        self.assertTrue(all(case['passing'] and case['behavioral_recovery_observed_repeats'] == 3 for case in summary['cases']))
        self.assertEqual(policy['cultural_gate'], 'NOT_VALIDATED')
        self.assertEqual(policy['release_gate'], 'BLOCKED')
        self.assertTrue(all(row['execution_source'] == 'test-double-only' for row in agent.observations))
        self.assertNotIn(UNIT_SECRET, json.dumps(ledger.files))


if __name__ == '__main__':
    unittest.main()
