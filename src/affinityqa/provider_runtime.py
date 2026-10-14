"""Opt-in transport coordination for versioned repeatable jobs.

Original protocol packets describe their original observations byte for byte.
Separate receipts state whether this execution dispatched, reconstructed, or used
a private validated Qloo cache. No accepted model decision is shared across jobs.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import copy
from datetime import datetime, timezone
import hashlib
import base64
from http.client import IncompleteRead
from importlib.metadata import version
import json
from pathlib import Path
import threading

from .evidence import fingerprint, redact
from .models import validate_response_envelope
from .provider_scheduler import (ProviderDeferred, ProviderRequestTooLarge,
                                 ProviderRecordedFailure, ProviderUncertain, ProviderAdmissionPaused,
                                 safe_quota_metadata)
from .qloo_cache import SCOPE_FIELDS

_CURRENT = ContextVar('affinityqa_provider_runtime', default=None)
_HOOK_LOCK = threading.RLock()
_HOOK_COUNT = 0
_ORIGINAL_GET = None
_ORIGINAL_RANK = None

HARMONY_RANKS_SHA256 = '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'
# OpenAI tiktoken_ext/openai_public.py, MIT, tiktoken 0.14.0.
HARMONY_PATTERN = '|'.join((
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r'\p{N}{1,3}', r' ?[^\s\p{L}\p{N}]+[\r\n/]*', r'\s*[\r\n]+', r'\s+(?!\S)', r'\s+',
))


class PinnedHarmonyTokenEstimator:
    """Offline exact text tokenizer plus declared conservative provider margin.

    This does not attest Groq's private prompt renderer. The explicit 1024-token
    guard exceeds reviewed two-message Harmony framing and covers schema/template
    additions; authorized live acceptance must compare observed usage. No network
    load, token-prefix discount or model fallback occurs here.
    """
    def __init__(self, ranks_path):
        if version('tiktoken') != '0.14.0':
            raise ValueError('Reviewed offline tiktoken==0.14.0 is required.')
        import tiktoken
        path = Path(ranks_path)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != HARMONY_RANKS_SHA256:
            raise ValueError('Pinned OpenAI Harmony vocabulary integrity differs.')
        ranks = {}
        for line in raw.splitlines():
            token, rank = line.split()
            ranks[base64.b64decode(token, validate=True)] = int(rank)
        if len(ranks) != 199998 or set(ranks.values()) != set(range(199998)):
            raise ValueError('Incomplete pinned OpenAI token vocabulary.')
        special = {'<|endoftext|>': 199999, '<|endofprompt|>': 200018,
                   '<|startoftext|>': 199998, '<|return|>': 200002, '<|constrain|>': 200003,
                   '<|channel|>': 200005, '<|start|>': 200006, '<|end|>': 200007,
                   '<|message|>': 200008, '<|call|>': 200012}
        special.update({f'<|reserved_{i}|>': i for i in (200000, 200001, 200004, 200009, 200010, 200011)})
        special.update({f'<|reserved_{i}|>': i for i in range(200013, 201088)})
        self.encoding = tiktoken.Encoding(name='o200k_harmony', pat_str=HARMONY_PATTERN,
                                         mergeable_ranks=ranks, special_tokens=special)
        self.manifest = {'schema_version': 1, 'method': 'pinned-o200k-harmony+full-wire+split-content+1024-guard-v1',
                         'tokenizer': 'tiktoken', 'version': '0.14.0', 'encoding': 'o200k_harmony',
                         'vocabulary_sha256': HARMONY_RANKS_SHA256, 'provider_template_guard_tokens': 1024,
                         'maximum_messages': 2, 'exact_provider_prompt_attested': False,
                         'sources': ['https://github.com/openai/gpt-oss/blob/main/gpt_oss/tokenizer.py',
                                     'https://github.com/openai/tiktoken/blob/0.14.0/tiktoken_ext/openai_public.py',
                                     'https://developers.openai.com/cookbook/articles/openai-harmony']}

    def estimate(self, encoded):
        payload = json.loads(encoded)
        if payload.get('model') != 'openai/gpt-oss-20b':
            raise ValueError('The pinned Harmony estimator admits only the reviewed GPT-OSS20B model.')
        messages = payload.get('messages')
        if (not isinstance(messages, list) or len(messages) != 2
                or [m.get('role') for m in messages] != ['system', 'user']
                or any(set(m) != {'role', 'content'} or not isinstance(m['content'], str) for m in messages)):
            raise ValueError('Only the reviewed two-message model payload is admitted.')
        output = payload.get('max_completion_tokens')
        if type(output) is not int or not 1 <= output <= 1024:
            raise ValueError('Explicit bounded completion reservation required.')
        def count(text):
            # Special-token-looking user text is ordinary data, never an assumed
            # one-token control sequence or a prompt-cache hit.
            return len(self.encoding.encode_ordinary(text))
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        wire_count = max(count(encoded.decode('utf-8')), count(canonical))
        message_count = sum(count(m['content']) + count(m['role']) for m in messages)
        schema_count = count(json.dumps(payload['response_format'], ensure_ascii=False, allow_nan=False))
        input_tokens = max(wire_count, message_count + schema_count) + 1024
        return dict(tokens=input_tokens + output, input_tokens=input_tokens, output_tokens=output)


def _coordinated_qloo_get(client, path, params, *, cache=True):
    runtime = current_runtime()
    if runtime is None:
        return _ORIGINAL_GET(client, path, params, cache=cache)
    from .qloo import validate_params
    validate_params(path, params, synthetic=client.synthetic)
    return runtime.qloo_get(client, path, params, cache=cache)


def _coordinated_model_rank(agent, request):
    runtime = current_runtime()
    if runtime is None:
        return _ORIGINAL_RANK(agent, request)
    with agent._lock:
        return runtime.model_rank(agent, request, agent._rank_locked)


def _install_hooks():
    global _HOOK_COUNT, _ORIGINAL_GET, _ORIGINAL_RANK
    from .qloo import QlooClient
    from .groq_agent import GroqToolContextMovieAgent
    with _HOOK_LOCK:
        if _HOOK_COUNT == 0:
            _ORIGINAL_GET, _ORIGINAL_RANK = QlooClient.get, GroqToolContextMovieAgent.rank
            QlooClient.get, GroqToolContextMovieAgent.rank = _coordinated_qloo_get, _coordinated_model_rank
        _HOOK_COUNT += 1


def _restore_hooks():
    global _HOOK_COUNT
    from .qloo import QlooClient
    from .groq_agent import GroqToolContextMovieAgent
    with _HOOK_LOCK:
        _HOOK_COUNT -= 1
        if _HOOK_COUNT == 0:
            QlooClient.get, GroqToolContextMovieAgent.rank = _ORIGINAL_GET, _ORIGINAL_RANK


def current_runtime():
    return _CURRENT.get()


def conservative_model_tokens(encoded):
    """Byte-token upper planning bound plus visible template/schema margin.

No cache-prefix discount or chars/4 guess. Each UTF-8 byte of the complete wire
JSON is reserved, plus 1024 framing tokens and the declared maximum completion.
This deliberately rejects unusually large requests before any send. Actual
usage is checked against the reservation; exceeding it suspends further work.
"""
    payload = json.loads(encoded)
    output = payload.get('max_completion_tokens')
    if type(output) is not int or not 1 <= output <= 1024:
        raise ValueError('Explicit bounded completion reservation required.')
    input_tokens = len(encoded) + 1024
    return dict(tokens=input_tokens + output, input_tokens=input_tokens, output_tokens=output)


class _ObservedOpener:
    def __init__(self, original, scheduler, operation):
        self.original, self.scheduler, self.operation = original, scheduler, operation
        self.status, self.headers, self.sent = None, {}, False
        self.io_failed = False
        self.reported_usage = {}

    def open(self, request, timeout):
        from urllib.error import HTTPError
        self.scheduler.mark_sent(self.operation['id'])
        self.sent = True
        try:
            response = self.original.open(request, timeout=timeout)
            self.status = getattr(response, 'status', getattr(response, 'code', None))
            self.headers = dict(getattr(response, 'headers', {}).items())
            return _ObservedResponse(response, self)
        except HTTPError as error:
            self.status, self.headers = error.code, dict((error.headers or {}).items())
            raise


class _ObservedResponse:
    """HTTP headers do not prove that a response body was fully received."""
    def __init__(self, response, observation):
        self.response, self.observation = response, observation

    def __getattr__(self, name):
        return getattr(self.response, name)

    def __enter__(self):
        try:
            self.response = self.response.__enter__()
            return self
        except (OSError, IncompleteRead):
            self.observation.io_failed = True
            raise

    def __exit__(self, *args):
        try:
            return self.response.__exit__(*args)
        except (OSError, IncompleteRead):
            self.observation.io_failed = True
            raise

    def read(self, *args, **kwargs):
        try:
            raw = self.response.read(*args, **kwargs)
            # A rejected model envelope can still report quota consumption.
            # Retain only a closed, consistent numeric usage projection.
            if isinstance(raw, bytes) and len(raw) <= 1_048_576:
                from .agents import strict_json
                try:
                    body = strict_json(raw)
                    usage = body.get('usage') if isinstance(body, dict) else None
                    names = ('prompt_tokens', 'completion_tokens', 'total_tokens')
                    if (isinstance(usage, dict) and all(type(usage.get(n)) is int and 0 <= usage[n] <= 2**31 for n in names)
                            and usage['prompt_tokens'] + usage['completion_tokens'] == usage['total_tokens']):
                        self.observation.reported_usage = {
                            'tokens': usage['total_tokens'], 'input_tokens': usage['prompt_tokens'],
                            'output_tokens': usage['completion_tokens']}
                except (ValueError, TypeError):
                    pass
            return raw
        except (OSError, IncompleteRead):
            self.observation.io_failed = True
            raise


class ProviderRuntime:
    def __init__(self, scheduler, job_id, owner_id, *, qloo_cache=None, namespace=None, cache_scope=None, token_estimator=None):
        self.scheduler, self.job_id, self.owner_id = scheduler, job_id, owner_id
        self.qloo_cache, self.namespace, self.cache_scope = qloo_cache, namespace, copy.deepcopy(cache_scope)
        self._base_namespace = copy.deepcopy(namespace)
        self.token_estimator = token_estimator
        self._ordinals = {}
        self.receipts = []
        self.counters = {'fresh_network_attempts': 0, 'qloo_cache_hits': 0, 'exact_reconstructions': 0}

    @contextmanager
    def activate(self, namespace=None):
        previous_namespace, previous_ordinals = self.namespace, self._ordinals
        if namespace is not None:
            self.namespace = namespace
        self._ordinals = {}
        _install_hooks()
        token = _CURRENT.set(self)
        try:
            yield self
        finally:
            _CURRENT.reset(token)
            _restore_hooks()
            self.namespace, self._ordinals = previous_namespace, previous_ordinals

    def _identity(self, provider, request_sha256):
        ordinal = self._ordinals.get(provider, 0) + 1
        self._ordinals[provider] = ordinal
        phase = fingerprint({'base': self._base_namespace, 'phase': self.namespace if self.namespace is not None else 'capture'})[:24]
        return dict(job_id=self.job_id, owner_id=self.owner_id, stage=f'{phase}/{provider}/{ordinal}',
                    provider=provider, request_sha256=request_sha256)

    def _existing(self, identity):
        row = self.scheduler.lookup(**identity)
        if row and row['state'] in ('SENT', 'UNKNOWN'):
            raise ProviderUncertain(identity['provider'], identity['stage'])
        if row and row['state'] in ('FAILED', 'CANCELLED'):
            # reserve supplies the original detailed oversized diagnostic.
            if row['reason'] == 'oversized':
                self.scheduler.reserve(**identity)
            raise ProviderRecordedFailure(identity['provider'], identity['stage'], row['status'])
        return row

    def _receipt(self, identity, mode, *, sample=None, original_received_at=None, wire_sha256=None,
                 original_observation=None, ledger=None):
        receipt = {'schema_version': 1, 'contract': 'repeatable-provider-provenance-v1',
                   **identity, 'operation_mode': mode, 'current_network_request': mode in ('fresh', 'failed', 'unknown'),
                   'original_received_at': original_received_at,
                   'recorded_at': datetime.fromtimestamp(self.scheduler.clock(), timezone.utc).isoformat(),
                   'wire_sha256': wire_sha256,
                   'original_sample_sha256': fingerprint(sample) if sample is not None else None,
                   'original_response_sha256': sample['response_sha256'] if sample else
                       (original_observation or {}).get('provider_response_sha256'),
                   'original_execution_source': sample['source'] if sample else
                       (original_observation or {}).get('execution_source'),
                   'token_estimation': copy.deepcopy(self.token_estimator.manifest) if self.token_estimator else
                       {'method': 'utf8-wire-bytes+1024-framing+declared-output-v1', 'exact_provider_prompt_attested': False}}
        self.receipts.append(receipt)
        self.scheduler.record_receipt(receipt)
        if ledger is not None:
            destination = ledger.directory.parent / (ledger.directory.name + '-provider-receipts.jsonl')
            with destination.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(receipt, ensure_ascii=False, allow_nan=False) + '\n')
        return receipt

    def stats(self):
        return {'schema_version': 1, 'providers': self.scheduler.stats(job_id=self.job_id, owner_id=self.owner_id),
                'current_process': dict(self.counters), 'receipts': copy.deepcopy(self.receipts)}

    def qloo_get(self, client, path, params, *, cache=True):
        from .qloo import BASE_URL
        from .errors import BudgetError, TransportError
        request = {'method': 'GET', 'host': BASE_URL, 'path': path, 'params': dict(sorted(params.items()))}
        identity = self._identity('qloo', fingerprint(request))
        existing = self._existing(identity)
        accepted = existing['result'] if existing and existing['state'] in ('ACCEPTED', 'CACHED') else None
        scope = None
        if (self.qloo_cache is not None and isinstance(self.cache_scope, dict)
                and SCOPE_FIELDS <= set(self.cache_scope)):
            scope = {**self.cache_scope, 'phase': self.namespace, 'execution_source': client.ledger.source,
                     'synthetic': client.synthetic}
        mode = 'accepted-reconstruction' if accepted else None
        if not accepted and scope is not None:
            accepted = self.qloo_cache.get(request, scope)
            if accepted:
                mode = 'private-cache'
                self.scheduler.cache_accept(**identity, result=accepted)
        if accepted:
            sample = accepted['sample']
            if sample['request'] != request or fingerprint(sample) != accepted['original_sample_sha256']:
                raise RuntimeError('Qloo reconstruction differs from its original accepted observation.')
            validate_response_envelope(sample['response'], insights=path == '/v2/insights')
            if mode == 'accepted-reconstruction':
                self.counters['exact_reconstructions'] += 1
            else:
                self.counters['qloo_cache_hits'] += 1
            # Logical accepted observations count toward each immutable protocol's
            # bound; actual current network count is separately explicit.
            client.requests += 1
            self._record_qloo_sample(client, sample)
            self._receipt(identity, mode, sample=sample, original_received_at=accepted['original_received_at'], ledger=client.ledger)
            return copy.deepcopy(sample['response'])
        if client.requests >= client.max_requests:
            raise BudgetError('Request budget exhausted; no further requests were made.')
        operation = self.scheduler.reserve(**identity)
        self.scheduler.mark_sent(operation['id'])
        client.requests += 1
        self.counters['fresh_network_attempts'] += 1
        if not client.synthetic:
            client.ledger.live_requests += 1
        try:
            response = client.transport.send(path, params)
        except BaseException:
            self.scheduler.finish(operation['id'], unknown=True)
            client.ledger.record('transport_failure', {'request': request, 'attempt': 1, 'outcome': 'UNKNOWN', 'automatic_retry': False})
            self._receipt(identity, 'unknown', ledger=client.ledger)
            raise ProviderUncertain('qloo', identity['stage']) from None
        headers = safe_quota_metadata(response.headers, now=self.scheduler.clock())
        # Keep only safe numeric/duration data, without arbitrary request IDs or
        # provider strings that might echo credentials.
        # Error payloads are arbitrary provider/debug material. Persist only a
        # closed status projection, not their strings or nested data.
        body = redact(response.body, client.ledger.secrets)
        invalid_envelope = None
        if response.status == 200:
            from .errors import SchemaError
            try:
                validate_response_envelope(body, insights=path == '/v2/insights')
            except SchemaError as error:
                invalid_envelope = error
        if response.status != 200 or invalid_envelope is not None:
            body = {'provider_error': {'http_status': response.status, 'body_retained': False,
                                      'invalid_success_envelope': invalid_envelope is not None}}
        sample = {'source': client.ledger.source, 'request': request, 'status': response.status,
                  'response': body,
                  'response_sha256': fingerprint(body),
                  'response_headers': headers, 'elapsed_ms': round(response.elapsed_ms, 3),
                  'attempt': 1, 'live_network_request': not client.synthetic}
        self._record_qloo_sample(client, sample)
        if response.status != 200 or invalid_envelope is not None:
            self.scheduler.finish(operation['id'], status=response.status, headers=response.headers)
            self._receipt(identity, 'failed', sample=sample, ledger=client.ledger)
            if invalid_envelope is not None:
                raise invalid_envelope
            raise ProviderRecordedFailure('qloo', identity['stage'], response.status)
        received_at = datetime.fromtimestamp(self.scheduler.clock(), timezone.utc).isoformat()
        accepted = {'schema_version': 1, 'sample': sample, 'original_sample_sha256': fingerprint(sample),
                    'original_received_at': received_at}
        self.scheduler.finish(operation['id'], result=accepted, status=200, headers=response.headers)
        self._receipt(identity, 'fresh', sample=sample, original_received_at=received_at, ledger=client.ledger)
        if scope is not None:
            self.qloo_cache.put(request, scope, sample, received_at=received_at, secrets=client.ledger.secrets)
        return copy.deepcopy(sample['response'])

    @staticmethod
    def _record_qloo_sample(client, sample):
        # This is a copy of the ORIGINAL accepted HTTP observation. Its historical
        # live flag never describes the current operation: the sidecar does.
        client.ledger.sample(sample['request'], sample['status'], sample['response'], sample['response_headers'],
                             sample['elapsed_ms'], live=sample['live_network_request'], attempt=sample['attempt'])

    def model_rank(self, agent, request, rank):
        """Intercept concrete encoded completion for all inherited Groq adapters.

        The original strict validator still runs on accepted reconstruction. Only
        after it accepts do we restore the original projected observation.
        """
        original_completion, original_opener = agent._completion, agent.opener
        initial_calls = agent.calls
        active = {}

        def completion(encoded):
            payload = json.loads(encoded)
            identity = self._identity('groq', fingerprint({'endpoint': agent.manifest['endpoint'], 'payload': payload}))
            wire_sha = hashlib.sha256(encoded).hexdigest()
            active.update(identity=identity, wire_sha=wire_sha)
            existing = self._existing(identity)
            if existing and existing['state'] == 'ACCEPTED':
                accepted = existing['result']
                if accepted['wire_sha256'] != wire_sha:
                    raise RuntimeError('Exact accepted provider wire bytes differ; no request sent.')
                active.update(accepted=accepted)
                return copy.deepcopy(accepted['decode_body']), accepted['observation']['provider_response_sha256']
            costs = self.token_estimator.estimate(encoded) if self.token_estimator else conservative_model_tokens(encoded)
            operation = self.scheduler.reserve(**identity, **costs)
            observed = _ObservedOpener(original_opener, self.scheduler, operation)
            active.update(operation=operation, observed=observed, costs=costs)
            agent.opener = observed
            return original_completion(encoded)

        agent._completion = completion
        try:
            result = rank(request)
            if not active:
                raise RuntimeError('Remote adapter returned without an observed completion boundary.')
            observation = copy.deepcopy(agent.observations[-1])
            accepted = active.get('accepted')
            if accepted:
                if (observation['input_sha256'] != accepted['observation']['input_sha256']
                        or observation['output_sha256'] != accepted['observation']['output_sha256']
                        or observation['provider_envelope_sha256'] != accepted['observation']['provider_envelope_sha256']):
                    raise RuntimeError('Accepted model reconstruction failed its independent boundary bindings.')
                agent.observations[-1] = copy.deepcopy(accepted['observation'])
                agent.last_input = copy.deepcopy(accepted['last_input'])
                self.counters['exact_reconstructions'] += 1
                mode = 'accepted-reconstruction'
            else:
                costs = active['costs']
                envelope = observation['provider_envelope']
                usage = copy.deepcopy(envelope['usage'])
                reasoning = usage.pop('reasoning_tokens')
                if reasoning is not None:
                    usage['completion_tokens_details'] = {'reasoning_tokens': reasoning}
                decode_body = {key: envelope[key] for key in ('object', 'model', 'id', 'created', 'system_fingerprint')}
                decode_body.update(choices=[{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant',
                    'content': json.dumps({'ordered_catalog_indices': envelope['choice']['ordered_catalog_indices']})}}], usage=usage)
                accepted = {'schema_version': 1, 'wire_sha256': active['wire_sha'], 'decode_body': decode_body,
                            'observation': observation, 'last_input': copy.deepcopy(agent.last_input),
                            'original_received_at': datetime.fromtimestamp(self.scheduler.clock(), timezone.utc).isoformat()}
                finished = self.scheduler.finish(active['operation']['id'], result=accepted, status=200,
                                      headers=active['observed'].headers, tokens=observation['total_tokens'],
                                      input_tokens=observation['prompt_eval_count'],
                                      output_tokens=envelope['usage']['completion_tokens'])
                mode = 'fresh'
            self._receipt(active['identity'], mode, original_received_at=accepted['original_received_at'],
                          wire_sha256=active['wire_sha'], original_observation=accepted['observation'],
                          ledger=getattr(agent, 'dispatch_ledger', None))
            if not active.get('accepted') and finished['reservation_exceeded']:
                raise ProviderAdmissionPaused('groq', 'token-reservation-exceeded')
            return result
        except BaseException as exc:
            observed = active.get('observed')
            if observed and observed.sent:
                uncertain = observed.status is None or observed.io_failed
                row = self.scheduler.lookup(**active['identity'])
                if row['state'] == 'SENT':
                    self.scheduler.finish(active['operation']['id'], status=observed.status,
                                          headers=observed.headers, unknown=uncertain,
                                          **observed.reported_usage)
                    self._receipt(active['identity'], 'unknown' if uncertain else 'failed',
                                  wire_sha256=active['wire_sha'], ledger=getattr(agent, 'dispatch_ledger', None))
                if uncertain:
                    raise ProviderUncertain('groq', active['identity']['stage']) from None
            elif isinstance(exc, (ProviderDeferred, ProviderRequestTooLarge, ProviderUncertain,
                                  ProviderRecordedFailure, ProviderAdmissionPaused)):
                # The legacy adapter increments at completion entry; a deferred
                # pre-dispatch operation is not a consumed network attempt.
                agent.calls = initial_calls
            raise
        finally:
            if active.get('observed') and active['observed'].sent:
                self.counters['fresh_network_attempts'] += 1
            agent._completion, agent.opener = original_completion, original_opener
