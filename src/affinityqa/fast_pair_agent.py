"""One observed Groq completion with two correlated projections; no fallback."""
import copy
import json
from pathlib import Path
import re
import time
from .agents import strict_json
from .evidence import fingerprint
from .groq_agent import GroqToolContextMovieAgent, model_manifest as base_manifest, contains_secret, finite_integer, need
from .provider_runtime import PinnedHarmonyTokenEstimator
from .fast_pair import PROTOCOL, PROMPT, input_for, schema_for, rankings

def model_manifest(source):
    value = base_manifest(source,max_calls=1)
    value.update(prompt_version=PROTOCOL,prompt_sha256=fingerprint(PROMPT),
        tool_contract='paired-confirmed-cinema-context-v1',response_contract='groq-paired-exact-discovery-arrays-v1',
        decision_scope='one-shared-call-two-correlated-projections',maximum_token_reservation=8000,
        prompt_cache_discount_reserved=False)
    return value

def wire(request, manifest):
    return {'model':manifest['model'],'messages':[{'role':'system','content':PROMPT},
        {'role':'user','content':json.dumps(input_for(request),ensure_ascii=False,separators=(',',':'),allow_nan=False)}],
        'response_format':{'type':'json_schema','json_schema':{'name':'affinityqa_paired_discovery_v1','strict':True,'schema':schema_for(request)}},
        **manifest['options']}

class FastPairMovieAgent(GroqToolContextMovieAgent):
    kind = 'groq-remote-paired-discovery-v1'
    def __init__(self,api_key,*,forbidden_secrets=(),_test_opener=None,token_estimator=None):
        super().__init__(api_key,max_calls=1,forbidden_secrets=forbidden_secrets,_test_opener=_test_opener)
        self.manifest = model_manifest(self.source)
        self.system_prompt = PROMPT
        self._manifest_sha256 = fingerprint(self.manifest)
        self.token_estimator = token_estimator or PinnedHarmonyTokenEstimator(Path(__file__).resolve().parents[2]/'assets/tokenizers/o200k_base.tiktoken')
        self.dispatch_ledger = None
        self.last_prepared = None

    def _rank_locked(self,request):
        need(self.calls==0 and fingerprint(self.manifest)==self._manifest_sha256 and self.system_prompt==PROMPT,'frozen unused paired operator required.')
        payload = wire(request,self.manifest)
        need(not contains_secret(payload,self._secrets),'private data in paired request.')
        encoded = json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
        need(len(encoded)<=65536,'paired request byte bound.')
        reservation = self.token_estimator.estimate(encoded)
        need(set(reservation)=={'tokens','input_tokens','output_tokens'} and all(type(v) is int and v>0 for v in reservation.values())
             and reservation['tokens']==reservation['input_tokens']+reservation['output_tokens']
             and reservation['input_tokens']>=1024 and reservation['tokens']<=8000 and reservation['output_tokens']==1024,
             'paired reservation exceeds conservative 8000-token cap; no dispatch.')
        self.last_prepared = {'request_id':request['request_id'],'input_sha256':fingerprint(input_for(request)),
            'provider_request_sha256':fingerprint(payload),'wire_sha256':__import__('hashlib').sha256(encoded).hexdigest(),
            'request_bytes':len(encoded),'reservation':reservation}
        if self.dispatch_ledger is not None:
            self.dispatch_ledger.record('pair_model_attempt_prepared',self.last_prepared)
        self.calls += 1
        started = time.monotonic()
        body, response_hash = self._completion(encoded)
        need(isinstance(body,dict) and body.get('object')=='chat.completion' and body.get('model')==self.model,'paired response identity.')
        need(isinstance(body.get('id'),str) and re.fullmatch(r'[!-~]{1,160}',body['id'])
             and finite_integer(body.get('created'),1,2**63-1),'completion identity/time.')
        choices = body.get('choices')
        need(isinstance(choices,list) and len(choices)==1 and isinstance(choices[0],dict),'one completion choice.')
        choice = choices[0]
        need(type(choice.get('index')) is int and choice['index']==0 and choice.get('finish_reason')=='stop','complete paired answer required.')
        message = choice.get('message')
        need(isinstance(message,dict) and message.get('role')=='assistant' and isinstance(message.get('content'),str)
             and message.get('refusal') in (None,'') and message.get('reasoning') in (None,'')
             and message.get('tool_calls') in (None,[]) and message.get('function_call') is None,'only final JSON, no reasoning or tools.')
        output = strict_json(message['content'].encode())
        need(isinstance(output,dict) and set(output)=={'ordered_catalog_indices'},'closed paired output.')
        result = rankings(request,output['ordered_catalog_indices'])
        usage = body.get('usage')
        need(isinstance(usage,dict) and finite_integer(usage.get('prompt_tokens'),1,8192)
             and finite_integer(usage.get('completion_tokens'),1,1024) and type(usage.get('total_tokens')) is int
             and usage['total_tokens']==usage['prompt_tokens']+usage['completion_tokens'],'typed paired token usage.')
        details = usage.get('completion_tokens_details')
        reasoning = None if details is None else details.get('reasoning_tokens') if isinstance(details,dict) else False
        need(reasoning is None or finite_integer(reasoning,0,usage['completion_tokens']),'reasoning token usage.')
        fp = body.get('system_fingerprint')
        need(fp is None or isinstance(fp,str) and re.fullmatch(r'[!-~]{1,128}',fp),'provider fingerprint.')
        envelope = {'schema_version':1,'execution_source':self.source,'provider':'groq','object':body['object'],
            'model':body['model'],'id':body['id'],'created':body['created'],'system_fingerprint':fp,
            'choice':{'index':0,'finish_reason':'stop','role':'assistant','ordered_catalog_indices':output['ordered_catalog_indices']},
            'usage':{'prompt_tokens':usage['prompt_tokens'],'completion_tokens':usage['completion_tokens'],
                     'total_tokens':usage['total_tokens'],'reasoning_tokens':reasoning}}
        self.last_input = copy.deepcopy(input_for(request))
        self.observations.append({'call':1,'input_sha256':fingerprint(self.last_input),'output_sha256':fingerprint(result),
            'elapsed_ms':round((time.monotonic()-started)*1000,3),'prompt_eval_count':usage['prompt_tokens'],
            'eval_count':usage['completion_tokens'],'private_thinking_recorded':False,'done':True,'done_reason':'stop',
            'provider':'groq','model':self.model,'completion_id':body['id'],'provider_created':body['created'],
            'system_fingerprint':fp,'provider_response_sha256':response_hash,
            'provider_response_hash_scope':'Full parsed response observation; not reconstructible from the redacted envelope.',
            'provider_request_sha256':fingerprint(payload),'provider_envelope':envelope,'provider_envelope_sha256':fingerprint(envelope),
            'total_tokens':usage['total_tokens'],'reasoning_tokens':reasoning,'model_revision_attested':False,'execution_source':self.source})
        return {'schema_version':1,'request_id':request['request_id'],'ranked_entity_ids':result}
