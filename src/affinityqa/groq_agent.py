"""Explicit remote adapter; no local weights, implicit calls or retry/fallback.

This candidate is separate from the frozen local operator and captures. Provider
identity is an API model ID plus each response's optional system fingerprint, never a
pretended SHA of weights. The existing local capture/verifier does not admit it.
"""
import copy
import json
import math
import re
import ssl
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from .agents import AgentError, _RejectRedirects, strict_json
from .causal_agent import PROMPT, PROTOCOL, ToolContextMovieAgent, validate_catalog
from .evidence import fingerprint

ENDPOINT = 'https://api.groq.com/openai/v1/chat/completions'
USER_AGENT = 'AffinityQA/0.2.0 (+https://github.com/seypherWork/affinityqa)'
MODEL = 'openai/gpt-oss-20b'
MAX_PROMPT_TOKENS = 8192
MAX_COMPLETION_TOKENS = 1024
MAX_REQUEST_BYTES = 65536
MAX_RESPONSE_BYTES = 262144


def need(condition, message):
    if not condition:
        raise AgentError('Remote model: ' + message)


def finite_integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def contains_secret(value, secrets):
    """Inspect actual strings, independently of sensitive field-name redaction."""
    pending = [value]
    visited = 0
    while pending:
        member = pending.pop()
        visited += 1
        need(visited <= 100000, 'credential inspection exceeded the JSON bound.')
        if isinstance(member, str) and any(secret in member for secret in secrets):
            return True
        if isinstance(member, dict):
            pending.extend(member.keys())
            pending.extend(member.values())
        elif isinstance(member, list):
            pending.extend(member)
    return False


def model_manifest(execution_source, *, max_calls=39, timeout=120, cinema=False):
    """Pure closed contract, usable in a plan without credentials or requests."""
    need(execution_source in ('remote-llm', 'test-double-only'), 'invalid execution provenance.')
    need(type(cinema) is bool, 'invalid cinema contract selector.')
    prompt, version, contract = PROMPT, PROTOCOL, 'qloo-context-input-not-quality-label-v1'
    if cinema:
        from .cinema_preferences import CINEMA_PROMPT, CINEMA_PROTOCOL
        prompt, version, contract = CINEMA_PROMPT, CINEMA_PROTOCOL, 'qloo-context+explicit-cinema-preferences-v1'
    return {
        'provider': 'groq', 'model': MODEL, 'endpoint': ENDPOINT,
        'model_identity_mode': 'provider-model-id+per-response-system-fingerprint-v3',
        'model_weights_sha256': None, 'immutable_model_revision_attested': False,
        'prompt_version': version, 'prompt_sha256': fingerprint(prompt),
        'tool_contract': contract,
        'response_contract': 'groq-strict-twenty-movie-v3-redacted-envelope',
        'options': {'temperature': 0, 'seed': 7, 'reasoning_effort': 'low',
                    'include_reasoning': False, 'stream': False,
                    'max_completion_tokens': MAX_COMPLETION_TOKENS},
        'seed_determinism_guaranteed': False,
        'max_inference_calls': max_calls, 'inference_timeout_seconds': timeout,
        'maximum_request_bytes': MAX_REQUEST_BYTES, 'maximum_response_bytes': MAX_RESPONSE_BYTES,
        'maximum_observed_prompt_tokens': MAX_PROMPT_TOKENS,
        'prompt_token_bound': 'Checked against provider usage after the attempt; not a prepaid cost cap or local tokenizer estimate.',
        'private_thinking_recorded': False, 'execution_source': execution_source,
        'automatic_retry': False, 'automatic_model_or_schema_fallback': False,
    }


class GroqToolContextMovieAgent:
    kind = 'groq-remote-strict-json'
    # Reuse exactly the existing profile/catalog/tool payload, without running
    # the local agent constructor, metadata queries, loading or inference.
    decision_input = ToolContextMovieAgent.decision_input

    def __init__(self, api_key, *, model=MODEL, timeout=120, max_calls=39,
                 forbidden_secrets=(), _test_opener=None, cinema=False):
        need(isinstance(api_key, str) and re.fullmatch(r'[!-~]{20,512}', api_key),
             'configure a private server credential; never include it in inputs.')
        need(model == MODEL, 'only the reviewed model ID is admitted.')
        need(type(max_calls) is int and 1 <= max_calls <= 39, 'invalid decision budget.')
        need(type(timeout) in (int, float) and math.isfinite(timeout) and 1 <= timeout <= 120,
             'invalid request timeout.')
        need(isinstance(forbidden_secrets, tuple) and all(isinstance(value, str) and value for value in forbidden_secrets),
             'invalid private-input exclusion configuration.')
        self._api_key = api_key
        self._secrets = (api_key,) + forbidden_secrets
        self.model, self.timeout, self.max_calls = model, timeout, max_calls
        self.calls = 0
        self.observations = []
        self.last_input = None
        self._lock = threading.Lock()
        self.source = 'test-double-only' if _test_opener is not None else 'remote-llm'
        self.opener = _test_opener if _test_opener is not None else build_opener(
            ProxyHandler({}), _RejectRedirects(), HTTPSHandler(context=ssl.create_default_context()))
        self.manifest = model_manifest(self.source, max_calls=max_calls, timeout=timeout, cinema=cinema)
        if cinema:
            from .cinema_preferences import CINEMA_PROMPT
            self.system_prompt = CINEMA_PROMPT
        else:
            self.system_prompt = PROMPT
        self._manifest_sha256 = fingerprint(self.manifest)

    def _completion(self, encoded):
        request = Request(ENDPOINT, data=encoded, method='POST', headers={
            'Authorization': 'Bearer ' + self._api_key,
            'Accept': 'application/json', 'Content-Type': 'application/json',
            'User-Agent': USER_AGENT,
        })
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                need(response.status == 200 and response.headers.get_content_type() == 'application/json',
                     'a complete HTTP200 JSON response is required.')
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            # Do not echo URLs, headers or provider error bodies; they can contain secrets.
            raise AgentError(f'Remote model: HTTP{error.code}; stopped without retry or fallback.') from None
        except (URLError, TimeoutError, OSError):
            raise AgentError('Remote model: network/TLS/timeout failure; stopped without retry.') from None
        need(len(raw) <= MAX_RESPONSE_BYTES, 'response exceeded the recording bound.')
        body = strict_json(raw)
        need(not contains_secret(body, self._secrets), 'credential-shaped content was rejected without recording it.')
        return body, fingerprint(body)

    def rank(self, request):
        with self._lock:
            return self._rank_locked(request)

    def _rank_locked(self, request):
        need(self.calls < self.max_calls, 'decision budget exhausted.')
        need(fingerprint(self.manifest) == self._manifest_sha256, 'frozen model contract changed; no request.')
        need(fingerprint(self.system_prompt) == self.manifest['prompt_sha256'], 'frozen system prompt changed; no request.')
        schema = {'type': 'object', 'properties': {
            'ordered_catalog_indices': {'type': 'array',
                'items': {'type': 'integer', 'enum': list(range(20))},
                'minItems': 20, 'maxItems': 20}},
            'required': ['ordered_catalog_indices'], 'additionalProperties': False}
        decision_input = self.decision_input(request, schema)
        need(not contains_secret(decision_input, self._secrets), 'a private credential must not enter a model payload.')
        payload = {'model': self.model, 'messages': [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': json.dumps(decision_input, ensure_ascii=False, allow_nan=False)}],
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'affinityqa_twenty_movie_ranking', 'strict': True, 'schema': schema}},
            **self.manifest['options']}
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        need(len(encoded) <= MAX_REQUEST_BYTES, 'request exceeded the transport bound.')
        self.calls += 1
        started = time.monotonic()
        body, response_sha256 = self._completion(encoded)
        need(body.get('object') == 'chat.completion' and body.get('model') == self.model,
             'response model or envelope differs from the admitted contract.')
        completion_id = body.get('id')
        need(isinstance(completion_id, str) and re.fullmatch(r'[!-~]{1,160}', completion_id),
             'bounded provider completion identity required.')
        need(finite_integer(body.get('created'), 1, 2**63-1), 'provider timestamp required.')
        choices = body.get('choices')
        need(isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict),
             'exactly one complete choice required.')
        choice = choices[0]
        need(type(choice.get('index')) is int and choice['index'] == 0 and choice.get('finish_reason') == 'stop',
             'truncated/refused/unfinished decisions are rejected.')
        message = choice.get('message')
        need(isinstance(message, dict) and message.get('role') == 'assistant'
             and isinstance(message.get('content'), str)
             and message.get('refusal') in (None, '')
             and message.get('reasoning') in (None, '')
             and message.get('tool_calls') in (None, [])
             and message.get('function_call') is None,
             'only a final structured answer is admitted; no private reasoning or tools.')
        output = strict_json(message['content'].encode('utf-8'))
        indices = output.get('ordered_catalog_indices')
        need(set(output) == {'ordered_catalog_indices'} and isinstance(indices, list)
             and len(indices) == 20 and all(type(value) is int for value in indices)
             and set(indices) == set(range(20)), 'missing, duplicated, Boolean or invented catalog positions.')
        usage = body.get('usage')
        need(isinstance(usage, dict)
             and finite_integer(usage.get('prompt_tokens'), 1, MAX_PROMPT_TOKENS)
             and finite_integer(usage.get('completion_tokens'), 1, MAX_COMPLETION_TOKENS)
             and type(usage.get('total_tokens')) is int
             and usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens'],
             'complete typed token accounting within declared bounds required.')
        details = usage.get('completion_tokens_details')
        reasoning_tokens = None if details is None else details.get('reasoning_tokens') if isinstance(details, dict) else False
        need(reasoning_tokens is None or finite_integer(reasoning_tokens, 0, usage['completion_tokens']),
             'invalid reasoning-token accounting.')
        system_fingerprint = body.get('system_fingerprint')
        need(system_fingerprint is None or (isinstance(system_fingerprint, str)
             and re.fullmatch(r'[!-~]{1,128}', system_fingerprint)), 'invalid deployment fingerprint.')
        catalog_ids = validate_catalog(request['catalog'])
        ranking = [catalog_ids[index] for index in indices]
        self.last_input = copy.deepcopy(decision_input)
        # Explicit projection: do not persist arbitrary response fields, refusal,
        # reasoning, headers or credential-shaped content. Its hash is auditable.
        envelope = {
            'schema_version': 1, 'execution_source': self.source, 'provider': 'groq',
            'object': body['object'], 'model': body['model'], 'id': completion_id,
            'created': body['created'], 'system_fingerprint': system_fingerprint,
            'choice': {'index': 0, 'finish_reason': 'stop', 'role': 'assistant',
                       'ordered_catalog_indices': indices},
            'usage': {'prompt_tokens': usage['prompt_tokens'], 'completion_tokens': usage['completion_tokens'],
                      'total_tokens': usage['total_tokens'], 'reasoning_tokens': reasoning_tokens},
        }
        self.observations.append({
            'call': self.calls, 'input_sha256': fingerprint(decision_input), 'output_sha256': fingerprint(ranking),
            'elapsed_ms': round((time.monotonic() - started)*1000, 3),
            'prompt_eval_count': usage['prompt_tokens'], 'eval_count': usage['completion_tokens'],
            'private_thinking_recorded': False, 'done': True, 'done_reason': 'stop',
            'provider': 'groq', 'model': self.model, 'completion_id': completion_id,
            'provider_created': body['created'], 'system_fingerprint': system_fingerprint,
            'provider_response_sha256': response_sha256,
            'provider_response_hash_scope': 'Full parsed response observation; not reconstructible from the redacted envelope.',
            'provider_request_sha256': fingerprint(payload),
            'provider_envelope': envelope, 'provider_envelope_sha256': fingerprint(envelope),
            'total_tokens': usage['total_tokens'], 'reasoning_tokens': reasoning_tokens,
            'model_revision_attested': False, 'execution_source': self.source,
        })
        return {'schema_version': 1, 'request_id': request['request_id'], 'ranked_entity_ids': ranking}
