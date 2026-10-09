"""Separate Groq discovery contract; legacy twenty-movie execution stays closed.

Only the bounded credential-redacting HTTPS transport is inherited. The input,
output, prompt and observation contract belong to the new discovery protocol.
No constructor metadata/inference request, retry or schema fallback is made.
"""
import copy
import hashlib
import json
import math
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request

from .agents import AgentError, strict_json
from .cinema_discoveries import (
    DISCOVERY_PROMPT, DISCOVERY_PROTOCOL, model_input, output_schema,
    validate_model_output, validate_request, validate_response,
)
from .errors import SchemaError
from .evidence import fingerprint
from .groq_agent import (
    GroqToolContextMovieAgent, MAX_REQUEST_BYTES, MAX_PROMPT_TOKENS,
    MAX_COMPLETION_TOKENS, contains_secret, finite_integer, need,
    model_manifest as legacy_model_manifest,
    ENDPOINT, USER_AGENT, MAX_RESPONSE_BYTES,
)
from .cinema_discovery_diagnostics import CONTRACT, closed_http, http_diagnostic


class DiscoveryHTTPError(AgentError):
    def __init__(self, diagnostic):
        self.http_diagnostic = closed_http(diagnostic)
        need(self.http_diagnostic is not None, 'invalid bounded HTTP diagnostic.')
        super().__init__(f"Remote model: HTTP{self.http_diagnostic['http_status']}; stopped without retry or fallback.")


class DiscoveryRateLimitError(DiscoveryHTTPError):
    pass


class DiscoveryCredentialsError(DiscoveryHTTPError):
    pass


class DiscoveryRequestRejectedError(DiscoveryHTTPError):
    pass


class DiscoveryServiceError(DiscoveryHTTPError):
    pass


class DiscoveryNetworkError(AgentError):
    pass


def model_manifest(execution_source, *, max_calls=2, timeout=120):
    """Versioned pure manifest: provider ID is not an immutable model revision."""
    need(type(max_calls) is int and 1 <= max_calls <= 39, 'invalid discovery decision budget.')
    need(type(timeout) in (int, float) and math.isfinite(timeout) and 1 <= timeout <= 120,
         'invalid discovery timeout.')
    manifest = legacy_model_manifest(execution_source, max_calls=max_calls, timeout=timeout)
    manifest.update(
        prompt_version=DISCOVERY_PROTOCOL,
        prompt_sha256=fingerprint(DISCOVERY_PROMPT),
        tool_contract='qloo-composite-signal+known-favorites+exact-discovery-universe-v1',
        response_contract='groq-strict-discovery-rank-slots-v2-redacted-envelope',
        output_universe='Reference catalog minus explicit known favorites; exact permutation, not padded to twenty.',
        diagnostic_contract=copy.deepcopy(CONTRACT),
    )
    return manifest


class DiscoveryMovieAgent(GroqToolContextMovieAgent):
    kind = 'groq-remote-strict-discovery-rank-slots-v2'

    def __init__(self, api_key, *, max_calls=2, timeout=120,
                 forbidden_secrets=(), _test_opener=None):
        super().__init__(api_key, timeout=timeout, max_calls=max_calls,
                         forbidden_secrets=forbidden_secrets, _test_opener=_test_opener)
        self.system_prompt = DISCOVERY_PROMPT
        self.manifest = model_manifest(self.source, max_calls=max_calls, timeout=timeout)
        self._manifest_sha256 = fingerprint(self.manifest)
        self.dispatch_ledger = None
        self.last_prepared = None

    def bind_dispatch_ledger(self, ledger):
        need(self.calls == 0 and self.dispatch_ledger is None and
             isinstance(ledger.run_id,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',ledger.run_id)
             and callable(ledger.record), 'bind one unused operator to its evidence ledger.')
        self.dispatch_ledger = ledger

    def decision_input(self, request, schema):
        try:
            return model_input(request, schema)
        except SchemaError as exc:
            raise AgentError(str(exc)) from None

    def _completion(self, encoded):
        # Keep legacy transport untouched. Reuse its same configured no-proxy,
        # redirect-denying HTTPS opener, endpoint, headers and response bounds.
        request = Request(ENDPOINT,data=encoded,method='POST',headers={
            'Authorization':'Bearer '+self._api_key,'Accept':'application/json',
            'Content-Type':'application/json','User-Agent':USER_AGENT})
        try:
            with self.opener.open(request,timeout=self.timeout) as response:
                need(response.status == 200 and response.headers.get_content_type() == 'application/json',
                     'a complete HTTP200 JSON response is required.')
                raw = response.read(MAX_RESPONSE_BYTES+1)
        except HTTPError as error:
            code = error.code
            category = (DiscoveryRateLimitError if code == 429 else
                        DiscoveryCredentialsError if code in (401,403) else
                        DiscoveryRequestRejectedError if 400 <= code < 500 else DiscoveryServiceError)
            diagnostic = http_diagnostic(error)
            if contains_secret(diagnostic,self._secrets):
                diagnostic.update(provider_error_type=None,provider_error_code=None)
            raise category(diagnostic) from None
        except (URLError,TimeoutError,OSError):
            raise DiscoveryNetworkError('Remote model: network/TLS/timeout failure; stopped without retry.') from None
        need(len(raw) <= MAX_RESPONSE_BYTES,'response exceeded the recording bound.')
        body = strict_json(raw)
        need(not contains_secret(body,self._secrets),'credential-shaped content was rejected without recording it.')
        return body,fingerprint(body)

    def _rank_locked(self, request):
        self.last_prepared = None
        need(fingerprint(self.manifest) == self._manifest_sha256,
             'frozen discovery model contract changed; no request.')
        need(type(self.max_calls) is int and self.max_calls == self.manifest['max_inference_calls']
             and self.model == self.manifest['model']
             and type(self.timeout) in (int, float) and self.timeout == self.manifest['inference_timeout_seconds'],
             'effective discovery transport differs from the frozen contract; no request.')
        need(finite_integer(self.calls, 0, self.max_calls) and self.calls < self.max_calls,
             'discovery decision budget exhausted or invalid.')
        need(fingerprint(self.system_prompt) == self.manifest['prompt_sha256'],
             'frozen discovery prompt changed; no request.')
        try:
            request = validate_request(request)
            schema = output_schema(request)
        except SchemaError as exc:
            raise AgentError(str(exc)) from None
        decision_input = self.decision_input(request, schema)
        need(not contains_secret(decision_input, self._secrets),
             'a private credential must not enter a discovery payload.')
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': self.system_prompt},
                {'role': 'user', 'content': json.dumps(decision_input, ensure_ascii=False, allow_nan=False)},
            ],
            'response_format': {'type': 'json_schema', 'json_schema': {
                'name': 'affinityqa_discovery_rank_slots_v2', 'strict': True, 'schema': schema,
            }},
            **self.manifest['options'],
        }
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        need(len(encoded) <= MAX_REQUEST_BYTES, 'discovery request exceeded the transport bound.')
        prepared = {'schema_version':1,'protocol':'discovery-prepared-request-v1',
            'execution_source':self.source,'run_id':self.dispatch_ledger.run_id if self.dispatch_ledger else None,
            'slot':self.calls+1,'request_id':request['request_id'],
            'input_sha256':fingerprint(decision_input),'provider_request_sha256':fingerprint(payload),
            'wire_sha256':hashlib.sha256(encoded).hexdigest(),'request_bytes':len(encoded),
            'external_dispatch_attested':False}
        if self.dispatch_ledger is not None:
            self.dispatch_ledger.record('discovery_request_prepared',prepared)
        self.last_prepared = copy.deepcopy(prepared)
        self.calls += 1
        started = time.monotonic()
        body, response_sha256 = self._completion(encoded)
        ranking, indices, usage, envelope = self._decode(request, body)
        response = {'schema_version': 1, 'request_id': request['request_id'], 'ranked_entity_ids': ranking}
        try:
            validate_response(request, response)
        except SchemaError as exc:
            raise AgentError(str(exc)) from None
        self.last_input = copy.deepcopy(decision_input)
        self.observations.append({
            'call': self.calls, 'input_sha256': fingerprint(decision_input),
            'output_sha256': fingerprint(ranking),
            'elapsed_ms': round((time.monotonic() - started) * 1000, 3),
            'prompt_eval_count': usage['prompt_tokens'], 'eval_count': usage['completion_tokens'],
            'private_thinking_recorded': False, 'done': True, 'done_reason': 'stop',
            'provider': 'groq', 'model': self.model, 'completion_id': envelope['id'],
            'provider_created': envelope['created'], 'system_fingerprint': envelope['system_fingerprint'],
            'provider_response_sha256': response_sha256,
            'provider_response_hash_scope': 'Full parsed response observation; not reconstructible from the redacted envelope.',
            'provider_request_sha256': fingerprint(payload),
            'provider_envelope': envelope, 'provider_envelope_sha256': fingerprint(envelope),
            'total_tokens': usage['total_tokens'], 'reasoning_tokens': envelope['usage']['reasoning_tokens'],
            'model_revision_attested': False, 'execution_source': self.source,
            'discovery_protocol': DISCOVERY_PROTOCOL, 'reference_catalog_count': 20,
            'raw_discovery_count': len(indices),
        })
        return response

    def _decode(self, request, body):
        need(body.get('object') == 'chat.completion' and body.get('model') == self.model,
             'response model or envelope differs from the discovery contract.')
        completion_id = body.get('id')
        need(isinstance(completion_id, str) and re.fullmatch(r'[!-~]{1,160}', completion_id),
             'bounded provider completion identity required.')
        need(all(observation['completion_id'] != completion_id for observation in self.observations),
             'repeated provider completion identity; attempt consumed without a second successful observation.')
        need(finite_integer(body.get('created'), 1, 2**63 - 1), 'provider timestamp required.')
        choices = body.get('choices')
        need(isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict),
             'exactly one complete discovery choice required.')
        choice = choices[0]
        need(type(choice.get('index')) is int and choice['index'] == 0 and choice.get('finish_reason') == 'stop',
             'truncated/refused/unfinished discovery decisions are rejected.')
        message = choice.get('message')
        need(isinstance(message, dict) and message.get('role') == 'assistant'
             and isinstance(message.get('content'), str)
             and message.get('refusal') in (None, '') and message.get('reasoning') in (None, '')
             and message.get('tool_calls') in (None, []) and message.get('function_call') is None,
             'only a final structured answer is admitted; no private reasoning or tools.')
        output = strict_json(message['content'].encode('utf-8'))
        try:
            ranking = validate_model_output(request, output)
        except SchemaError as exc:
            raise AgentError(str(exc)) from None
        slots = output['ordered_catalog_indices']
        indices = [slots[f'rank_{position:02d}'] for position in range(1, len(slots) + 1)]
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
        envelope = {
            'schema_version': 3, 'discovery_protocol': DISCOVERY_PROTOCOL,
            'execution_source': self.source, 'provider': 'groq',
            'object': body['object'], 'model': body['model'], 'id': completion_id,
            'created': body['created'], 'system_fingerprint': system_fingerprint,
            'choice': {'index': 0, 'finish_reason': 'stop', 'role': 'assistant',
                       'ordered_catalog_indices': copy.deepcopy(slots)},
            'usage': {'prompt_tokens': usage['prompt_tokens'], 'completion_tokens': usage['completion_tokens'],
                      'total_tokens': usage['total_tokens'], 'reasoning_tokens': reasoning_tokens},
        }
        return ranking, indices, usage, envelope
