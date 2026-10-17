"""One bounded Groq send; nested interpretations survive the existing runtime codec."""
import copy
import json
from pathlib import Path
import re
import time

from .agents import strict_json
from .evidence import fingerprint
from .groq_agent import GroqToolContextMovieAgent, model_manifest as base_manifest, contains_secret, finite_integer, need
from .provider_runtime import PinnedHarmonyTokenEstimator
from .open_movie_discovery import PROTOCOL, PROMPT, model_input, output_schema, validate_output, cache_key


def model_manifest(source):
    value = base_manifest(source, max_calls=1)
    value.update(prompt_version=PROTOCOL, prompt_sha256=fingerprint(PROMPT), tool_contract='open-real-movie-pool-v1',
        response_contract='open-movie-ranking-and-closed-interpretations-v1', maximum_token_reservation=8000,
        decision_scope='one-movie-one-observed-decision', prompt_cache_discount_reserved=False)
    return value


def wire(request, manifest):
    return {'model': manifest['model'], 'messages': [{'role': 'system', 'content': PROMPT},
        {'role': 'user', 'content': json.dumps(model_input(request), ensure_ascii=False, separators=(',', ':'), allow_nan=False)}],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'affinityqa_open_movies_v1', 'strict': True,
                            'schema': output_schema(request)}}, **manifest['options']}


class OpenMovieAgent(GroqToolContextMovieAgent):
    kind = 'groq-open-movie-discovery-v1'

    def __init__(self, api_key, *, forbidden_secrets=(), _test_opener=None, token_estimator=None):
        super().__init__(api_key, max_calls=1, forbidden_secrets=forbidden_secrets, _test_opener=_test_opener)
        self.manifest = model_manifest(self.source); self.system_prompt = PROMPT
        self._manifest_sha256 = fingerprint(self.manifest)
        self.token_estimator = token_estimator or PinnedHarmonyTokenEstimator(Path(__file__).resolve().parents[2] / 'assets/tokenizers/o200k_base.tiktoken')
        self.dispatch_ledger = None; self.last_prepared = None

    def _rank_locked(self, request):
        need(self.calls == 0 and fingerprint(self.manifest) == self._manifest_sha256 and self.system_prompt == PROMPT, 'Frozen unused open operator required.')
        payload = wire(request, self.manifest); need(not contains_secret(payload, self._secrets), 'Private content in open request.')
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        need(len(encoded) <= 65536, 'Open request byte bound exceeded.')
        reservation = self.token_estimator.estimate(encoded)
        need(set(reservation) == {'tokens', 'input_tokens', 'output_tokens'}
             and all(type(v) is int and v > 0 for v in reservation.values())
             and reservation['tokens'] == reservation['input_tokens'] + reservation['output_tokens']
             and reservation['input_tokens'] >= 1024 and reservation['tokens'] <= 8000
             and reservation['output_tokens'] == 1024, 'Open request exceeds the reserved free-plan token bound; no send.')
        self.last_prepared = {'request_id': request['request_id'], 'input_sha256': fingerprint(model_input(request)),
            'provider_request_sha256': fingerprint(payload), 'wire_sha256': __import__('hashlib').sha256(encoded).hexdigest(),
            'request_bytes': len(encoded), 'reservation': reservation}
        if self.dispatch_ledger is not None:self.dispatch_ledger.record('open_model_attempt_prepared', self.last_prepared)
        self.calls += 1; started = time.monotonic(); body, response_hash = self._completion(encoded)
        need(isinstance(body, dict) and body.get('object') == 'chat.completion' and body.get('model') == self.model, 'Open model identity differs.')
        need(isinstance(body.get('id'), str) and re.fullmatch(r'[!-~]{1,160}', body['id'])
             and finite_integer(body.get('created'), 1, 2**63 - 1), 'Completion identity/time required.')
        choices = body.get('choices'); need(isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict), 'One complete choice required.')
        choice = choices[0]; need(type(choice.get('index')) is int and choice['index'] == 0 and choice.get('finish_reason') == 'stop', 'Truncated/refused output rejected.')
        message = choice.get('message'); need(isinstance(message, dict) and message.get('role') == 'assistant'
            and isinstance(message.get('content'), str) and message.get('refusal') in (None, '')
            and message.get('reasoning') in (None, '') and message.get('tool_calls') in (None, [])
            and message.get('function_call') is None, 'Only final structured output, no private reasoning or tools.')
        output = strict_json(message['content'].encode()); checked = validate_output(request, output)
        usage = body.get('usage'); need(isinstance(usage, dict) and finite_integer(usage.get('prompt_tokens'), 1, 8192)
            and finite_integer(usage.get('completion_tokens'), 1, 1024) and type(usage.get('total_tokens')) is int
            and usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens'], 'Typed token accounting required.')
        need(usage['prompt_tokens'] <= reservation['input_tokens'] and usage['total_tokens'] <= reservation['tokens'],
             'Observed usage exceeds the admitted reservation.')
        details = usage.get('completion_tokens_details')
        reasoning = None if details is None else details.get('reasoning_tokens') if isinstance(details, dict) else False
        need(reasoning is None or finite_integer(reasoning, 0, usage['completion_tokens']), 'Invalid reasoning-token count.')
        system_fp = body.get('system_fingerprint'); need(system_fp is None or isinstance(system_fp, str)
            and re.fullmatch(r'[!-~]{1,128}', system_fp), 'Invalid provider fingerprint.')
        envelope = {'schema_version': 1, 'execution_source': self.source, 'provider': 'groq', 'object': body['object'],
            'model': body['model'], 'id': body['id'], 'created': body['created'], 'system_fingerprint': system_fp,
            'choice': {'index': 0, 'finish_reason': 'stop', 'role': 'assistant',
                       'ordered_catalog_indices': copy.deepcopy(output['ordered_catalog_indices'])},
            'usage': {'prompt_tokens': usage['prompt_tokens'], 'completion_tokens': usage['completion_tokens'],
                      'total_tokens': usage['total_tokens'], 'reasoning_tokens': reasoning}}
        self.last_input = copy.deepcopy(model_input(request))
        self.observations.append({'call': 1, 'input_sha256': fingerprint(self.last_input), 'output_sha256': fingerprint(checked),
            'elapsed_ms': round((time.monotonic() - started) * 1000, 3), 'prompt_eval_count': usage['prompt_tokens'],
            'eval_count': usage['completion_tokens'], 'private_thinking_recorded': False, 'done': True, 'done_reason': 'stop',
            'provider': 'groq', 'model': self.model, 'completion_id': body['id'], 'provider_created': body['created'],
            'system_fingerprint': system_fp, 'provider_response_sha256': response_hash,
            'provider_response_hash_scope': 'Full parsed response observation; not reconstructible from the redacted envelope.',
            'provider_request_sha256': fingerprint(payload), 'provider_envelope': envelope,
            'provider_envelope_sha256': fingerprint(envelope), 'total_tokens': usage['total_tokens'],
            'reasoning_tokens': reasoning, 'model_revision_attested': False, 'execution_source': self.source})
        return {'schema_version': 1, 'request_id': request['request_id'], 'ranked_entity_ids': checked['ranking'],
                'reasons': checked['reasons'], 'output_sha256': fingerprint(checked), 'cache_key_sha256': cache_key(request, self.manifest)}
