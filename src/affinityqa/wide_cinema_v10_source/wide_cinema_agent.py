"""One bounded wide-cinema selection; no change to the legacy runtime codec."""
import copy
import json
from pathlib import Path
import re
import time
import unicodedata

from .agents import strict_json
from .evidence import fingerprint
from .errors import AffinityQAError
from .groq_agent import GroqToolContextMovieAgent, model_manifest as base_manifest, contains_secret, finite_integer, need
from .wide_cinema_tokens import WideHarmonyTokenEstimator
from .wide_cinema_discovery import PROTOCOL, PROMPT, model_input, output_schema, validate_output, cache_key

DIAGNOSTIC_CODES={
    'COMPLETION':frozenset({'COMPLETION_REJECTED'}),
    'ENVELOPE':frozenset({'ENVELOPE_IDENTITY','COMPLETION_IDENTITY','CHOICE_SHAPE','FINISH_REASON','FINAL_MESSAGE'}),
    'OUTPUT':frozenset({'OUTPUT_JSON','OUTPUT_VALIDATION','OUTPUT_TOP_LEVEL','OUTPUT_COUNT','OUTPUT_CHOICE_SHAPE',
        'OUTPUT_INDEX_TYPE','OUTPUT_INDEX_ELIGIBILITY','OUTPUT_INDEX_DUPLICATE','OUTPUT_TEXT_TYPE',
        'OUTPUT_TEXT_RAW_LENGTH','OUTPUT_TEXT_CONTROL','OUTPUT_TEXT_LENGTH','OUTPUT_IDENTITY_TITLE',
        'OUTPUT_IDENTITY_YEAR','OUTPUT_TEXT_TARGET'}),
    'USAGE':frozenset({'USAGE_SHAPE','USAGE_RESERVATION','USAGE_REASONING','PROVIDER_FINGERPRINT'})}
DIAGNOSTIC_KEYS=frozenset({'schema_version','protocol','request_id','provider_request_sha256','stage','code','accepted',
    'scope','rejected_text_recorded','body_parsed','provider_response_sha256','finish_reason','reported_usage',
    'completion_choice_count','output_choices_count','indices','indices_unique','indices_eligible','reason_lengths',
    'reason_normalized_lengths','reason_canonical','reason_controls'})


def validate_failure_projection(value, request, prepared):
    """Reject arbitrary keys, strings and nonfinite values before any persistence."""
    need(isinstance(value,dict) and set(value) == DIAGNOSTIC_KEYS,'Closed rejection projection required.')
    stage,code=value['stage'],value['code']
    need(isinstance(stage,str) and stage in DIAGNOSTIC_CODES and isinstance(code,str)
         and code in DIAGNOSTIC_CODES[stage],'Closed rejection stage and code required.')
    sha=lambda v:isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v) is not None
    need(isinstance(request,dict) and isinstance(prepared,dict) and type(value['schema_version']) is int
         and value['schema_version'] == 1 and value['protocol'] == PROTOCOL and sha(value['request_id'])
         and value['request_id'] == request['request_id'] and sha(value['provider_request_sha256'])
         and value['provider_request_sha256'] == prepared['provider_request_sha256']
         and value['accepted'] is False and value['scope'] == 'SAFE_FAILURE_PROJECTION_NO_RAW_RESPONSE'
         and value['rejected_text_recorded'] is False,'Bound non-acceptance projection required.')
    need(type(value['body_parsed']) is bool and value['finish_reason'] in ('NOT_OBSERVED','STOP','LENGTH','CONTENT_FILTER',
        'TOOL_CALLS','FUNCTION_CALL','MISSING','OTHER'),'Closed response projection required.')
    response_hash=value['provider_response_sha256']
    need((sha(response_hash) and value['finish_reason'] != 'NOT_OBSERVED') if value['body_parsed'] else
         response_hash is None and value['finish_reason'] == 'NOT_OBSERVED','Decoded-body hash presence differs.')
    usage=value['reported_usage']
    if usage is not None:
        need(value['body_parsed'] and isinstance(usage,dict) and set(usage) == {'prompt_tokens','completion_tokens','total_tokens','reasoning_tokens'}
             and all(type(usage[k]) is int and 0 <= usage[k] <= 2**31 for k in ('prompt_tokens','completion_tokens','total_tokens'))
             and usage['total_tokens'] == usage['prompt_tokens']+usage['completion_tokens']
             and (usage['reasoning_tokens'] is None or type(usage['reasoning_tokens']) is int
                  and 0 <= usage['reasoning_tokens'] <= usage['completion_tokens']),'Typed numeric usage projection required.')
    for name in ('completion_choice_count','output_choices_count'):
        need(value[name] is None or type(value[name]) is int and 0 <= value[name] <= 262144,'Bounded numeric counts required.')
    indices=value['indices'];count=value['output_choices_count']
    need(isinstance(indices,list) and len(indices) == (min(count,5) if count is not None else 0)
         and all(v is None or type(v) is int and abs(v) <= 2**31 for v in indices),'Bounded numeric indices required.')
    for name in ('indices_eligible','reason_lengths','reason_normalized_lengths','reason_canonical','reason_controls'):
        need(isinstance(value[name],list) and len(value[name]) == len(indices),'Aligned projection arrays required.')
    for name in ('reason_lengths','reason_normalized_lengths'):
        need(all(v is None or type(v) is int and 0 <= v <= 2**31 for v in value[name]),'Finite reason lengths required.')
    for name in ('reason_canonical','reason_controls'):
        need(all(v is None or type(v) is bool for v in value[name]),'Boolean reason flags required.')
    unique=len(set(indices)) == len(indices) if indices and None not in indices else None
    need(value['indices_unique'] is unique and all(type(v) is bool for v in value['indices_eligible'])
         and value['indices_eligible'] == [v in request['eligible_catalog_indices'] if v is not None else False for v in indices],
         'Recomputed index constraints required.')
    if not value['body_parsed']:
        need(usage is None and value['completion_choice_count'] is None and count is None and not indices,'No derived facts without decoded response.')
    return copy.deepcopy(value)


def model_manifest(source):
    value = base_manifest(source, max_calls=1)
    value.update(prompt_version=PROTOCOL, prompt_sha256=fingerprint(PROMPT), tool_contract='wide-real-film-pool-v1',
        response_contract='wide-five-ordered-catalog-indices-v10',
        provider_response_format={'type':'text'},
        maximum_token_reservation=8000,
        decision_scope='one-wide-profile-one-five-choice-decision', prompt_cache_discount_reserved=False)
    value['options'] = {**value['options'],'max_completion_tokens':2048}
    return value


def wire(request, manifest):
    expected = {'type':'text'}
    need(fingerprint(manifest.get('provider_response_format')) == fingerprint(expected), 'Frozen text transport required.')
    response_format = copy.deepcopy(expected)
    return {'model': manifest['model'], 'messages': [{'role': 'system', 'content': PROMPT},
        {'role': 'user', 'content': json.dumps(model_input(request), ensure_ascii=False, separators=(',', ':'), allow_nan=False)}],
        'response_format': response_format, **manifest['options']}


def failure_projection(request, prepared, stage, code, body, output, response_hash):
    """Closed failure metadata only. No rejected text, unknown fields or reasoning."""
    need(isinstance(stage,str) and stage in DIAGNOSTIC_CODES and isinstance(code,str)
         and code in DIAGNOSTIC_CODES[stage],'Closed rejection stage and code required.')
    decoded=response_hash is not None
    choices=body.get('choices') if isinstance(body,dict) else None
    choice=choices[0] if isinstance(choices,list) and choices and isinstance(choices[0],dict) else {}
    finish=choice.get('finish_reason')
    finish={'stop':'STOP','length':'LENGTH','content_filter':'CONTENT_FILTER','tool_calls':'TOOL_CALLS',
            'function_call':'FUNCTION_CALL'}.get(finish,'MISSING' if finish is None else 'OTHER') if isinstance(finish,(str,type(None))) else 'OTHER'
    usage=body.get('usage') if isinstance(body,dict) else None;reported=None
    if isinstance(usage,dict) and all(type(usage.get(k)) is int and 0 <= usage[k] <= 2**31
            for k in ('prompt_tokens','completion_tokens','total_tokens')) and usage['total_tokens'] == usage['prompt_tokens']+usage['completion_tokens']:
        details=usage.get('completion_tokens_details');reasoning=details.get('reasoning_tokens') if isinstance(details,dict) else None
        reported={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens')}
        reported['reasoning_tokens']=reasoning if type(reasoning) is int and 0 <= reasoning <= usage['completion_tokens'] else None
    block=output.get('ordered_catalog_indices') if isinstance(output,dict) else None
    values=block[:5] if isinstance(block,list) else [];indices=[];lengths=[];normal_lengths=[];canonical=[];controls=[]
    for value in values:
        index=value.get('catalog_index') if isinstance(value,dict) else None
        indices.append(index if type(index) is int and abs(index) <= 2**31 else None)
        raw=value.get('text') if isinstance(value,dict) else None
        normalized=' '.join(unicodedata.normalize('NFKC',raw).split()) if isinstance(raw,str) else None
        lengths.append(len(raw) if isinstance(raw,str) else None);normal_lengths.append(len(normalized) if normalized is not None else None)
        canonical.append(raw == normalized if isinstance(raw,str) else None)
        controls.append(any(unicodedata.category(c).startswith('C') and c not in '\t\r\n' for c in raw) if isinstance(raw,str) else None)
    value={'schema_version':1,'protocol':PROTOCOL,'request_id':request['request_id'],
        'provider_request_sha256':prepared['provider_request_sha256'],'stage':stage,'code':code,
        'accepted':False,'scope':'SAFE_FAILURE_PROJECTION_NO_RAW_RESPONSE','rejected_text_recorded':False,
        'body_parsed':decoded,'provider_response_sha256':response_hash,
        'finish_reason':finish if decoded else 'NOT_OBSERVED','reported_usage':reported,
        'completion_choice_count':len(choices) if isinstance(choices,list) else None,
        'output_choices_count':len(block) if isinstance(block,list) else None,'indices':indices,
        'indices_unique':len(set(indices)) == len(indices) if indices and None not in indices else None,
        'indices_eligible':[v in request['eligible_catalog_indices'] if v is not None else False for v in indices],
        'reason_lengths':lengths,'reason_normalized_lengths':normal_lengths,'reason_canonical':canonical,'reason_controls':controls}
    return validate_failure_projection(value,request,prepared)


class WideCinemaAgent(GroqToolContextMovieAgent):
    kind = 'groq-wide-cinema-discovery-v10'

    def __init__(self, api_key, *, forbidden_secrets=(), _test_opener=None, token_estimator=None):
        super().__init__(api_key, max_calls=1, forbidden_secrets=forbidden_secrets, _test_opener=_test_opener)
        self.manifest = model_manifest(self.source); self.system_prompt = PROMPT
        self._manifest_sha256 = fingerprint(self.manifest)
        self.token_estimator = token_estimator or WideHarmonyTokenEstimator(Path(__file__).resolve().parents[2] / 'assets/tokenizers/o200k_base.tiktoken')
        self.dispatch_ledger = None; self.last_prepared = None; self.last_rejection = None

    def _rank_locked(self, request):
        self.last_rejection=None;self._failure_stage='PREFLIGHT';self._failure_code='PREFLIGHT_REJECTED'
        self._observed_body=self._observed_output=self._response_hash=None
        try:return self._rank_observed(request)
        except AffinityQAError as error:
            if self.last_prepared is not None:
                stage=self._failure_stage if isinstance(self._failure_stage,str) and self._failure_stage in DIAGNOSTIC_CODES else 'COMPLETION'
                fallback={'COMPLETION':'COMPLETION_REJECTED','ENVELOPE':'ENVELOPE_IDENTITY','OUTPUT':'OUTPUT_VALIDATION','USAGE':'USAGE_SHAPE'}[stage]
                code=self._failure_code if isinstance(self._failure_code,str) and self._failure_code in DIAGNOSTIC_CODES[stage] else fallback
                if stage == 'OUTPUT':
                    messages={'Wide cinema output: '+c:c for c in DIAGNOSTIC_CODES['OUTPUT'] if c not in ('OUTPUT_JSON','OUTPUT_VALIDATION')}
                    code=messages.get(str(error),'OUTPUT_JSON' if code == 'OUTPUT_JSON' else 'OUTPUT_VALIDATION')
                self.last_rejection=failure_projection(request,self.last_prepared,stage,code,
                    self._observed_body,self._observed_output,self._response_hash)
            raise
        finally:self._observed_body=self._observed_output=None

    def _guard(self, condition, code, message):
        self._failure_code=code;need(condition,message)

    def _rank_observed(self, request):
        need(self.calls == 0 and fingerprint(self.manifest) == self._manifest_sha256 and self.system_prompt == PROMPT, 'Frozen unused open operator required.')
        payload = wire(request, self.manifest); need(not contains_secret(payload, self._secrets), 'Private content in open request.')
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        need(len(encoded) <= 65536, 'Open request byte bound exceeded.')
        reservation = self.token_estimator.estimate(encoded)
        need(set(reservation) == {'tokens', 'input_tokens', 'output_tokens'}
             and all(type(v) is int and v > 0 for v in reservation.values())
             and reservation['tokens'] == reservation['input_tokens'] + reservation['output_tokens']
             and reservation['input_tokens'] >= 1024 and reservation['tokens'] <= 8000
             and reservation['output_tokens'] == 2048, 'Open request exceeds the reserved free-plan token bound; no send.')
        self.last_prepared = {'request_id': request['request_id'], 'input_sha256': fingerprint(model_input(request)),
            'provider_request_sha256': fingerprint(payload), 'wire_sha256': __import__('hashlib').sha256(encoded).hexdigest(),
            'request_bytes': len(encoded), 'reservation': reservation}
        if self.dispatch_ledger is not None:self.dispatch_ledger.record('wide_model_attempt_prepared', self.last_prepared)
        self.calls += 1; started = time.monotonic();self._failure_stage='COMPLETION';self._failure_code='COMPLETION_REJECTED'
        body, response_hash = self._completion(encoded);self._observed_body=body;self._response_hash=response_hash;self._failure_stage='ENVELOPE'
        self._guard(isinstance(body, dict) and body.get('object') == 'chat.completion' and body.get('model') == self.model, 'ENVELOPE_IDENTITY','Open model identity differs.')
        self._guard(isinstance(body.get('id'), str) and re.fullmatch(r'[!-~]{1,160}', body['id'])
             and finite_integer(body.get('created'), 1, 2**63 - 1), 'COMPLETION_IDENTITY','Completion identity/time required.')
        choices = body.get('choices');self._guard(isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], dict), 'CHOICE_SHAPE','One complete choice required.')
        choice = choices[0];self._guard(type(choice.get('index')) is int and choice['index'] == 0 and choice.get('finish_reason') == 'stop', 'FINISH_REASON','Truncated/refused output rejected.')
        message = choice.get('message');self._guard(isinstance(message, dict) and message.get('role') == 'assistant'
            and isinstance(message.get('content'), str) and message.get('refusal') in (None, '')
            and message.get('reasoning') in (None, '') and message.get('tool_calls') in (None, [])
            and message.get('function_call') is None, 'FINAL_MESSAGE','Only final structured output, no private reasoning or tools.')
        self._failure_stage='OUTPUT';self._failure_code='OUTPUT_JSON'
        output = strict_json(message['content'].encode());self._observed_output=output;self._failure_code='OUTPUT_VALIDATION'
        checked = validate_output(request, output);self._failure_stage='USAGE'
        usage = body.get('usage');self._guard(isinstance(usage, dict) and finite_integer(usage.get('prompt_tokens'), 1, 8192)
            and finite_integer(usage.get('completion_tokens'), 1, 2048) and type(usage.get('total_tokens')) is int
            and usage['total_tokens'] == usage['prompt_tokens'] + usage['completion_tokens'], 'USAGE_SHAPE','Typed token accounting required.')
        self._guard(usage['prompt_tokens'] <= reservation['input_tokens'] and usage['total_tokens'] <= reservation['tokens'],
             'USAGE_RESERVATION','Observed usage exceeds the admitted reservation.')
        details = usage.get('completion_tokens_details')
        reasoning = None if details is None else details.get('reasoning_tokens') if isinstance(details, dict) else False
        self._guard(reasoning is None or finite_integer(reasoning, 0, usage['completion_tokens']), 'USAGE_REASONING','Invalid reasoning-token count.')
        system_fp = body.get('system_fingerprint');self._guard(system_fp is None or isinstance(system_fp, str)
            and re.fullmatch(r'[!-~]{1,128}', system_fp), 'PROVIDER_FINGERPRINT','Invalid provider fingerprint.')
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
                'selected_catalog_indices': checked['choices'], 'output_sha256': fingerprint(checked), 'cache_key_sha256': cache_key(request, self.manifest)}
