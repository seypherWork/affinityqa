"""Versioned wide2048 estimator; immutable legacy estimator/codec remain intact."""
import copy
import json
from .provider_runtime import PinnedHarmonyTokenEstimator


class WideHarmonyTokenEstimator(PinnedHarmonyTokenEstimator):
    """Same pinned vocabulary, full-wire counting and1024 framing guard; cap2048."""

    def __init__(self, ranks_path):
        super().__init__(ranks_path)
        self.manifest = copy.deepcopy(self.manifest)
        self.manifest.update(schema_version=2,
            method='pinned-o200k-harmony+full-wire+split-content+1024-guard-wide2048-v2',
            maximum_completion_tokens=2048)

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
        if type(output) is not int or not 1 <= output <= 2048:
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
