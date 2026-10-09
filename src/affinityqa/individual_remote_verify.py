"""Pure v3 remote audit. No engine, credential lookup, requests or attestation."""
import json
import math
from pathlib import PurePosixPath, PureWindowsPath
import re

from .agents import AgentError
from .causal_agent import PROTOCOL, PROMPT, FAULTS
from .evidence import fingerprint
from .errors import SchemaError
from .individual_remote_capture import SOURCES, validate_request
from .individual_verify import SOURCE_ROOT, _verify, need, same, sha


def expected_manifest(execution_source):
    # Independent closed contract: never accept whatever the adapter produces.
    return {
        'provider': 'groq', 'model': 'openai/gpt-oss-20b',
        'endpoint': 'https://api.groq.com/openai/v1/chat/completions',
        'model_identity_mode': 'provider-model-id+per-response-system-fingerprint-v3',
        'model_weights_sha256': None, 'immutable_model_revision_attested': False,
        'prompt_version': PROTOCOL, 'prompt_sha256': fingerprint(PROMPT),
        'tool_contract': 'qloo-context-input-not-quality-label-v1',
        'response_contract': 'groq-strict-twenty-movie-v3-redacted-envelope',
        'options': {'temperature': 0, 'seed': 7, 'reasoning_effort': 'low',
                    'include_reasoning': False, 'stream': False, 'max_completion_tokens': 1024},
        'seed_determinism_guaranteed': False, 'max_inference_calls': 39,
        'inference_timeout_seconds': 120, 'maximum_request_bytes': 65536,
        'maximum_response_bytes': 262144, 'maximum_observed_prompt_tokens': 8192,
        'prompt_token_bound': 'Checked against provider usage after the attempt; not a prepaid cost cap or local tokenizer estimate.',
        'private_thinking_recorded': False, 'execution_source': execution_source,
        'automatic_retry': False, 'automatic_model_or_schema_fallback': False,
    }


def verify_plan(plan):
    request = validate_request(plan['request'])
    output = plan['output_directory']
    need(isinstance(output, str) and len(output) <= 4000 and
         (PureWindowsPath(output).is_absolute() or PurePosixPath(output).is_absolute()), 'original remote output declaration')
    expected = {'schema_version': 3, 'protocol_version': PROTOCOL, 'mode': 'individual-remote-capture',
        'request': request, 'output_directory': output, 'remote_operator': expected_manifest('remote-llm'),
        'execution_pacing': expected_pacing(plan['execution_pacing']['minimum_interval_seconds']),
        'source_sha256': {name: sha(SOURCE_ROOT/'src/affinityqa'/name) for name in SOURCES},
        'driver_sha256': sha(SOURCE_ROOT/'scripts/capture_individual_remote.py'),
        'verification_driver_sha256': sha(SOURCE_ROOT/'scripts/verify_individual_remote.py'),
        'dependencies_lock_sha256': sha(SOURCE_ROOT/'requirements-backend.lock.txt'),
        'maximum_qloo_requests': 4, 'maximum_attempts_per_request': 1, 'maximum_model_decisions': 39,
        'healthy_repeats_per_profile': 3, 'faults': list(FAULTS), 'new_model_metadata_requests': 0,
        'startup_model_metadata_requests': 0, 'runtime_model_metadata_requests': 0, 'model_load_requests': 0,
        'individual_demo_only': True, 'independent_validation_claim': False,
        'cultural_gate': 'NOT_VALIDATED', 'release_gate': 'BLOCKED',
        'partial_failure_policy': 'Preserve all evidence, stop without retry or resume.'}
    expected['plan_sha256'] = fingerprint(expected)
    need(same(plan, expected), 'remote plan or installed source binding differs')
    return request


def expected_pacing(seconds):
    # Independent literal; do not admit a producer-selected contract or quota claim.
    need(seconds is None or type(seconds) is float and math.isfinite(seconds) and 0<=seconds<=65,
         'remote interval must be a canonical finite float or unconfigured')
    return {'schema_version':1,'configured':seconds is not None,'minimum_interval_seconds':seconds,
            'clock':'monotonic','maximum_model_attempts':39,'maximum_scheduled_wait_seconds':70,
            'maximum_sleep_slice_seconds':5,'maximum_wait_wakeups':100,
            'provider_quota_attested':False,'external_capacity_reserved':False,
            'automatic_retry':False,'automatic_model_or_schema_fallback':False}


def verify_pacing(plan,events,report,observed,frozen):
    policy=plan['execution_pacing']
    need(same(policy,expected_pacing(policy['minimum_interval_seconds'])),'pacing policy differs')
    need(report['source']=='test-double-only' or policy['configured'] is True,'real capture without configured cadence')
    slots=[event for event in events if event['kind']=='remote_model_attempt_admitted']
    # Admission and adapter counters can each lose one record, but the runtime
    # stops on the first failure: together they must still lose at most one packet.
    need(integer(report.get('admitted_model_slots'),0,39) and report['admitted_model_slots']==len(slots)
         and report['model_attempts']<=len(slots)<=report['model_attempts']+1
         and len(slots)-len(observed)<=1,'consumed remote slot accounting')
    need(not slots or len(frozen)==1 and frozen[0]['sequence']<slots[0]['sequence'],'slot admitted before sealed tool inputs')
    interval=policy['minimum_interval_seconds'] or 0.0
    previous=None
    for i,event in enumerate(slots,1):
        data=event['data']
        need(set(data)=={'schema_version','execution_source','slot','adapter_calls_before_dispatch',
                        'relative_start_seconds','scheduled_wait_seconds','minimum_interval_seconds','external_completion_attested'},
             'remote slot fields differ')
        need(type(data['schema_version']) is int and data['schema_version']==1 and integer(data['slot'],i,i)
             and integer(data['adapter_calls_before_dispatch'],i-1,i-1)
             and data['execution_source']==engine_source(report['source'])
             and type(data['minimum_interval_seconds']) is float and data['minimum_interval_seconds']==interval
             and data['external_completion_attested'] is False,'remote slot identity or contract differs')
        start,wait=data['relative_start_seconds'],data['scheduled_wait_seconds']
        need(type(start) in (int,float) and math.isfinite(start) and 0<=start<=1e12
             and type(wait) in (int,float) and math.isfinite(wait) and 0<=wait<=70,'remote pacing observation bound')
        need(start==0 if previous is None else start-previous>=interval-1e-8,'recorded cadence differs')
        need(i>len(observed) or event['sequence']<observed[i-1]['sequence'],'remote slot not committed before its packet')
        need(i==1 or i-2>=len(observed) or observed[i-2]['sequence']<event['sequence'],'remote slot admitted before previous decision completed')
        previous=start
    need(len(observed)<=len(slots) and (report['status']!='COMPLETE' or len(slots)==39),'complete pacing coverage differs')


def engine_source(source):
    need(source in ('qloo-tool+groq-remote-llm', 'test-double-only'), 'remote provenance')
    return 'test-double-only' if source == 'test-double-only' else 'remote-llm'


def verify_manifest(manifest, source):
    need(same(manifest, expected_manifest(engine_source(source))), 'remote manifest/model/options differ')


def integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


def verify_backend_gates(report, deployments, passing, *, complete):
    # Independently derive the result from validated packets, not producer helpers
    # or report-selected fingerprints. No changing thresholds or skipping repeats.
    known = sorted(set(value for value in deployments if value is not None))
    missing = deployments.count(None)
    if len(deployments) != 39:
        status = 'NOT_EVALUATED'
    elif missing:
        status = 'VARIED_AND_ABSENT' if len(known) > 1 else 'ABSENT'
    else:
        status = 'VARIED' if len(known) > 1 else 'STABLE_KNOWN'
    expected = {'schema_version': 1, 'status': status, 'expected_decisions': 39,
                'observed_decisions': len(deployments), 'system_fingerprints': known,
                'missing_fingerprint_decisions': missing,
                'scope': 'Observed provider backend fingerprints across all 39 decisions; immutable weights are not attested.'}
    integration = ('PASS' if passing == 3 else 'FAIL') if complete else 'NOT_EVALUATED'
    attribution = ('FAIL' if integration == 'FAIL' else
                   'PASS' if status == 'STABLE_KNOWN' else 'INCONCLUSIVE') if complete else 'NOT_EVALUATED'
    need(same(report.get('backend_comparability'), expected), 'reported backend comparability differs from packets')
    need(report.get('integration_gate') == integration and report['causal_gate'] == attribution,
         'reported integration or causal gate differs')
    need(report.get('integration_gate_scope') == 'All nine unchanged checks for all three declared faults; a failure is an observed checklist failure, not attribution of its cause.'
         and report.get('causal_gate_scope') == 'Integration checks pass and all 39 observed backend fingerprints are known and identical; fingerprints do not attest immutable weights.'
         and report.get('behavioral_gate_scope') == 'All three declared faults; at least one observed recovery repeat for each. Observed behavior alone does not causally attribute a recovery to repair.',
         'remote gate scope differs')


def verify_packet(packet, manifest, source, *, system_prompt=PROMPT):
    observation = packet['observation']
    need(set(observation) == {'call', 'input_sha256', 'output_sha256', 'elapsed_ms',
        'prompt_eval_count', 'eval_count', 'private_thinking_recorded', 'done', 'done_reason',
        'provider', 'model', 'completion_id', 'provider_created', 'system_fingerprint',
        'provider_response_sha256', 'provider_response_hash_scope', 'provider_request_sha256',
        'provider_envelope', 'provider_envelope_sha256', 'total_tokens', 'reasoning_tokens',
        'model_revision_attested', 'execution_source'}, 'remote observation schema differs')
    envelope = observation['provider_envelope']
    need(isinstance(envelope, dict) and set(envelope) == {'schema_version', 'execution_source', 'provider',
        'object', 'model', 'id', 'created', 'system_fingerprint', 'choice', 'usage'}, 'remote envelope schema')
    need(type(envelope['schema_version']) is int and envelope['schema_version'] == 1
         and envelope['provider'] == observation['provider'] == 'groq'
         and envelope['execution_source'] == observation['execution_source'] == engine_source(source)
         and envelope['model'] == observation['model'] == manifest['model']
         and envelope['object'] == 'chat.completion', 'remote envelope identity/provenance')
    need(isinstance(envelope['id'], str) and re.fullmatch(r'[!-~]{1,160}', envelope['id'])
         and envelope['id'] == observation['completion_id']
         and integer(envelope['created'], 1, 2**63-1)
         and type(observation['provider_created']) is int
         and envelope['created'] == observation['provider_created'], 'remote completion identity/time')
    deployment = envelope['system_fingerprint']
    need(deployment is None or isinstance(deployment, str) and re.fullmatch(r'[!-~]{1,128}', deployment), 'remote fingerprint format')
    need(observation['system_fingerprint'] == deployment, 'remote fingerprint observation differs')
    choice = envelope['choice']
    need(isinstance(choice, dict) and set(choice) == {'index', 'finish_reason', 'role', 'ordered_catalog_indices'}
         and type(choice['index']) is int and choice['index'] == 0 and choice['finish_reason'] == 'stop'
         and choice['role'] == 'assistant', 'remote answer contract')
    indices = choice['ordered_catalog_indices']
    need(isinstance(indices, list) and len(indices) == 20 and all(type(v) is int for v in indices)
         and set(indices) == set(range(20)), 'remote answer permutation')
    ranking = [packet['effective_request']['catalog'][i]['entity_id'] for i in indices]
    need(same(ranking, packet['response']['ranked_entity_ids']), 'remote answer/ranking differs')
    usage = envelope['usage']
    need(isinstance(usage, dict) and set(usage) == {'prompt_tokens', 'completion_tokens', 'total_tokens', 'reasoning_tokens'}
         and integer(usage['prompt_tokens'], 1, 8192) and integer(usage['completion_tokens'], 1, 1024)
         and type(usage['total_tokens']) is int and usage['total_tokens'] == usage['prompt_tokens']+usage['completion_tokens'],
         'remote usage budget/accounting')
    need(usage['reasoning_tokens'] is None or integer(usage['reasoning_tokens'], 0, usage['completion_tokens']), 'remote reasoning token accounting')
    for key, usage_key in (('prompt_eval_count', 'prompt_tokens'), ('eval_count', 'completion_tokens'),
                           ('total_tokens', 'total_tokens'), ('reasoning_tokens', 'reasoning_tokens')):
        need(same(observation[key], usage[usage_key]), 'remote usage observation differs')
    need(observation['model_revision_attested'] is False and observation['private_thinking_recorded'] is False
         and observation['done'] is True and observation['done_reason'] == 'stop', 'remote attestation/termination claim')
    need(type(observation['elapsed_ms']) in (int, float) and math.isfinite(observation['elapsed_ms'])
         and observation['elapsed_ms'] >= 0, 'remote elapsed observation')
    need(isinstance(observation['provider_response_sha256'], str)
         and re.fullmatch(r'[0-9a-f]{64}', observation['provider_response_sha256'])
         and observation['provider_response_hash_scope'] == 'Full parsed response observation; not reconstructible from the redacted envelope.',
         'remote full response observation scope')
    need(observation['provider_envelope_sha256'] == fingerprint(envelope), 'remote envelope hash')
    payload = {'model': manifest['model'], 'messages': [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': json.dumps(packet['model_payload'], ensure_ascii=False, allow_nan=False)}],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'affinityqa_twenty_movie_ranking',
            'strict': True, 'schema': packet['model_payload']['output_schema']}}, **manifest['options']}
    need(len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')) <= 65536
         and observation['provider_request_sha256'] == fingerprint(payload), 'remote effective request differs')
    return deployment


def verify_individual_remote(directory):
    try:
        return _verify(directory, remote=True)
    except SchemaError:
        raise
    except (AgentError, KeyError, TypeError, ValueError, IndexError, StopIteration, OSError) as exc:
        raise SchemaError('Remote individual audit: missing, malformed or inconsistent evidence') from exc
