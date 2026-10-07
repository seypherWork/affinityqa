"""Read-only audit of individual capture records, never provider attestation.

Recorded decisions are replayed in sequence without creating an engine or making
requests. Independent arithmetic checks the operator's scores. Simulation labels
are preserved. A receipt does not approve release or cultural quality.
"""
import copy
from datetime import datetime, timezone
import hashlib
import ipaddress
from itertools import combinations
import json
import math
import os
from pathlib import Path, PureWindowsPath, PurePosixPath
import re
import unicodedata
from urllib.parse import urlsplit

from .agents import strict_json, validate_response, AgentError
from .causal_agent import PROTOCOL, PROMPT, FAULTS, ToolContextMovieAgent, context_from_sample, profile_hash
from .causal_runner import capture_pair
from .causal_evaluator import evaluate_pair
from .evidence import fingerprint, utc_now
from .errors import SchemaError
from .individual_capture import SOURCES, validate_request
from .models import parse_entities, validate_response_envelope

SOURCE_ROOT = Path(__file__).resolve().parents[2]
RUN_ID = re.compile(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}')
STATES = ('qloo-tool+local-llm', 'test-double-only')


def need(condition, message):
    if not condition:
        raise SchemaError('Individual audit: ' + message)


def same(actual, expected):
    """Preserve JSON types: False is never an integer counter equal to zero."""
    return fingerprint(actual) == fingerprint(expected)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_path(path):
    path = Path(path).absolute()
    for member in (path, *path.parents):
        need(not member.is_symlink() and not (hasattr(member, 'is_junction') and member.is_junction()), 'linked path')
    return path


def inventory(directory):
    directory = checked_path(directory)
    need(directory.is_dir(), 'missing capture directory')
    result = {}
    total = 0
    for path in directory.iterdir():
        checked_path(path)
        need(path.is_file() and re.fullmatch(r'[A-Za-z0-9_.-]+', path.name), 'non-flat artifact tree')
        total += path.stat().st_size
        need(path.stat().st_size <= 16_000_000 and total <= 160_000_000 and len(result) < 64, 'artifact read bound')
        result[path.name] = sha(path)
    return result


def read(path):
    raw = checked_path(path).read_bytes()
    need(len(raw) <= 16_000_000, 'JSON read bound')
    try:
        return strict_json(raw)
    except (AgentError, ValueError, UnicodeError) as exc:
        raise SchemaError('Individual audit: invalid strict JSON') from exc


def instant(value):
    need(isinstance(value, str), 'invalid timestamp')
    parsed = datetime.fromisoformat(value)
    need(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, 'timestamp must be UTC')
    return parsed


def distance(a, b, k=5):
    """Separate symmetric ordinal arithmetic; no production metric import."""
    need(len(a) == len(b) == 20 and len(set(a)) == 20 and set(a) == set(b), 'score permutation')
    def score(actual, reference):
        relevance = {item:20-index for index,item in enumerate(reference)}
        return sum(relevance[item]/math.log2(index+2) for index,item in enumerate(actual[:k])) / sum(
            (20-index)/math.log2(index+2) for index in range(k))
    return max(0., 1-(score(a,b)+score(b,a))/2)


def musical_identity(name, body):
    """Select exact musical observations without calling the capture resolver."""
    validate_response_envelope(body, insights=False)
    seen = []
    norm = lambda text:' '.join(unicodedata.normalize('NFKC',text).casefold().split())
    for raw in body['results']:
        entity = parse_entities({'results':[raw]}, insights=False)[0]
        if any(old == raw for old,_ in seen):
            continue
        for old,other in seen:
            if other.entity_id == entity.entity_id:
                need(other.name.casefold() == entity.name.casefold() and not set(other.types).intersection(entity.types),
                     'conflicting identity observations')
        seen.append((raw,entity))
    exact = [row for _,row in seen if norm(row.name) == norm(name)]
    artists = [row for row in exact if 'urn:entity:artist' in row.types]
    need(len(artists) <= 1, 'ambiguous artist')
    if artists:
        return {'entity_id':artists[0].entity_id,'name':name,'type':'urn:entity:artist'}
    people = [row for row in exact if 'urn:entity:person' in row.types]
    need(len(people) == 1, 'missing unique musical person')
    row = people[0]
    occupations = row.metadata.get('occupations',row.metadata.get('occupation',[]))
    occupations = [occupations] if isinstance(occupations,str) else occupations
    musical = {'musician','singer','singer songwriter','songwriter','rapper','composer','pianist','guitarist',
               'harpist','record producer','music producer'}
    accepted = isinstance(occupations,list) and any(isinstance(v,str) and norm(re.sub(r'[_-]',' ',v)) in musical for v in occupations)
    external = row.metadata.get('external',{})
    service = isinstance(external,dict) and any(isinstance(external.get(k),dict) and bool(external[k].get('id'))
                                              for k in ('musicbrainz','lastfm','spotify'))
    need(accepted or service, 'person lacks musical metadata')
    return {'entity_id':row.entity_id,'name':name,'type':'urn:entity:person'}


def verify_plan(plan):
    request = validate_request(plan['request'])
    parsed = urlsplit(plan['ollama_url'])
    need(parsed.scheme == 'http' and ipaddress.ip_address(parsed.hostname).is_loopback and
         1024 <= parsed.port <= 65535 and not parsed.username and not parsed.password and
         not parsed.path and not parsed.query and not parsed.fragment, 'model URL differs')
    output = plan['output_directory']
    need(isinstance(output,str) and len(output) <= 4000 and
         (PureWindowsPath(output).is_absolute() or PurePosixPath(output).is_absolute()), 'original output declaration')
    expected = {'schema_version':1,'protocol_version':PROTOCOL,'mode':'individual-local-capture',
        'request':request,'output_directory':output,'ollama_url':plan['ollama_url'],
        'source_sha256':{name:sha(SOURCE_ROOT/'src/affinityqa'/name) for name in SOURCES},
        'driver_sha256':sha(SOURCE_ROOT/'scripts/capture_individual_pair.py'),
        'dependencies_lock_sha256':sha(SOURCE_ROOT/'requirements-backend.lock.txt'),
        'maximum_qloo_requests':4,'maximum_attempts_per_request':1,'maximum_model_decisions':39,
        'healthy_repeats_per_profile':3,'faults':list(FAULTS),'new_model_metadata_requests':3,
        'startup_model_metadata_requests':2,'runtime_model_metadata_requests':1,'model_load_requests':1,
        'individual_demo_only':True,'independent_validation_claim':False,'cultural_gate':'NOT_VALIDATED',
        'release_gate':'BLOCKED','partial_failure_policy':'Preserve all evidence, stop without retry or resume.'}
    expected['plan_sha256'] = fingerprint(expected)
    need(plan == expected and fingerprint(plan) == fingerprint(expected), 'plan or installed source binding differs')
    return request


class _ReplayEnd(Exception):
    pass


class _MemoryLedger:
    def __init__(self, run_id):
        self.run_id = run_id
        self.files = {}
        self.events = []
    def write(self, name, value):
        need(name not in self.files, 'replay overwrote evidence')
        self.files[name] = copy.deepcopy(value)
    def record(self, kind, data):
        self.events.append((kind,copy.deepcopy(data)))


class _PacketReplay:
    """Consume recorded packets in order, including nondeterministic responses."""
    def __init__(self, manifest, packets):
        self.manifest = manifest
        self.packets = packets
        self.calls = 0
        self.observations = []
        self.last_input = None
    def rank(self, request):
        if self.calls == len(self.packets):
            raise _ReplayEnd()
        packet = self.packets[self.calls]
        need(same(request,packet['effective_request']), 'recorded request differs from executed protocol')
        self.calls += 1
        self.observations.append(copy.deepcopy(packet['observation']))
        self.last_input = copy.deepcopy(packet['model_payload'])
        return copy.deepcopy(packet['response'])


def _verify(directory, *, remote=False):
    # The public v1 wrapper never dispatches from untrusted file fields. Remote
    # v2 has its own explicit wrapper and closed provider-specific checks.
    if remote:
        from .individual_remote_capture import SOURCE as REMOTE_SOURCE
        from .individual_remote_verify import verify_plan as remote_plan, verify_manifest, verify_packet
        states = (REMOTE_SOURCE, 'test-double-only')
    else:
        states = STATES
    directory = checked_path(directory)
    need(RUN_ID.fullmatch(directory.name) is not None, 'invalid run ID')
    before = inventory(directory)
    plan = read(directory/'individual-plan.json')
    request = remote_plan(plan) if remote else verify_plan(plan)
    report = read(directory/'individual-report.json')
    complete = report['status'] == 'COMPLETE'
    source = report['source']
    need(source in states and report['status'] in ('COMPLETE','INCOMPLETE'), 'unknown status/source')
    need(type(report['schema_version']) is int and report['schema_version'] == (2 if remote else 1) and report['run_id'] == directory.name
         and report['mode'] == plan['mode'] and report['plan_sha256'] == plan['plan_sha256'], 'report binding')
    need(report['cultural_gate'] == 'NOT_VALIDATED' and report['release_gate'] == 'BLOCKED' and
         report['release_approved'] is False and report['independent_verification'] == 'PENDING'
         and report['partial_evidence_preserved'] is True, 'unapproved quality/release claim')
    for key,maximum in (('model_attempts',39),('qloo_attempts',4),('model_load_attempts',0 if remote else 1)):
        need(type(report[key]) is int and 0 <= report[key] <= maximum, 'attempt budget')
    need((report['error_class'] is None) if complete else isinstance(report['error_class'],str) and bool(report['error_class']),
         'complete/error state differs')
    ledger_path = directory/'ledger.jsonl'
    need(ledger_path.stat().st_size <= 2_000_000, 'ledger read bound')
    events = [strict_json(line) for line in ledger_path.read_bytes().splitlines() if line.strip()]
    need(events and all(type(e['sequence']) is int and e['sequence'] == i for i,e in enumerate(events,1)), 'ledger sequence')
    need(all(e['source'] == source and set(e) == {'sequence','timestamp_utc','source','kind','data'} for e in events), 'ledger source/schema')
    times = [instant(e['timestamp_utc']) for e in events]
    need(times == sorted(times), 'ledger time reversal')
    first = events[0]
    need(first['kind'] == 'individual_plan_frozen' and same(first['data'],{'plan_sha256':plan['plan_sha256'],'model_calls':0,'qloo_calls':0}), 'plan not first')
    allowed_kinds = {'individual_plan_frozen','tool_call','transport_failure','all_tool_inputs_frozen',
        'observed_model_execution','observed_session_boundary','policy_frozen','pair_healthy_capture_complete','stopped_without_retry'}
    if remote:
        allowed_kinds.add('remote_model_attempt_admitted')
    need(all(e['kind'] in allowed_kinds for e in events), 'unknown ledger event')
    stopped = [e for e in events if e['kind']=='stopped_without_retry']
    need(not stopped if complete else len(stopped)==1 and stopped[0] == events[-1]
         and stopped[0]['data'] == {'error_class':report['error_class']}, 'stop/retry state')
    attempts = [e for e in events if e['kind'] in ('tool_call','transport_failure')]
    need(len(attempts) == report['qloo_attempts'] and len(attempts) <= 4, 'provider attempt accounting')
    profiles = read(directory/'individual-identities.json') if 'individual-identities.json' in before else None
    sequence = [{'query':name,'take':5} for name in request['artists'].values()]
    if profiles is not None:
        need(set(profiles)=={'A','B'} and len({p['entity_id'] for p in profiles.values()})==2, 'profile coverage')
        sequence += [{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,
            'signal.interests.entities':profiles[p]['entity_id'],
            'filter.results.entities':','.join(sorted(r['entity_id'] for r in request['catalog']))} for p in request['artists']]
    samples = {}
    sample_names = []
    for i,event in enumerate(attempts):
        data = event['data']
        query = data['request']
        need(i < len(sequence) and query == {'method':'GET','host':'https://hackathon.api.qloo.com',
            'path':'/search' if i<2 else '/v2/insights','params':sequence[i]} and type(data['attempt']) is int and data['attempt']==1,
            'provider request prefix/retry')
        if event['kind']=='transport_failure':
            need(not complete and event==attempts[-1] and set(data)=={'request','attempt'}, 'failed request retried')
            continue
        name = data['sample']
        need(name == f'http-{event["sequence"]:04d}.json', 'sample filename/sequence')
        sample = read(directory/name)
        need(sample['source']==source and sample['request']==query and sample['attempt']==1 and
             sample['live_network_request'] is True and sample['response_sha256']==fingerprint(sample['response']), 'provider sample binding')
        need(same(data,{'sample':name,**{k:v for k,v in sample.items() if k!='response'}}), 'provider ledger differs')
        need(type(sample['status']) is int and 100<=sample['status']<=599 and (not complete or sample['status']==200), 'provider status')
        sample_names.append(name)
        samples[before[name]] = sample
    need({n for n in before if n.startswith('http-')} == set(sample_names), 'orphan provider sample')
    if profiles is not None:
        for i,(label,name) in enumerate(request['artists'].items()):
            need(len(sample_names)>i, 'missing profile search')
            sample = read(directory/sample_names[i])
            need(sample['status']==200 and same(profiles[label],musical_identity(name,sample['response'])), 'resolved identity differs')
    contexts = read(directory/'individual-tool-inputs.json') if 'individual-tool-inputs.json' in before else None
    frozen = [e for e in events if e['kind']=='all_tool_inputs_frozen']
    if contexts is not None:
        need(profiles is not None and set(contexts)=={profile_hash(p) for p in profiles.values()} and len(frozen)==1, 'context coverage')
        for profile in profiles.values():
            context = contexts[profile_hash(profile)]
            need(context['sample_sha256'] in samples and same(context_from_sample(profile,request['catalog'],
                 samples[context['sample_sha256']],context['sample_sha256']),context), 'context differs from source')
        need(same(frozen[0]['data'],{'sha256':fingerprint(contexts),'model_calls':0,'qloo_calls':4})
             and attempts[-1]['sequence']<frozen[0]['sequence'], 'tool input seal')
    else:
        need(not complete and not frozen, 'missing sealed inputs')
    manifest = read(directory/'model-manifest.json') if 'model-manifest.json' in before else None
    if manifest is not None:
        if remote:
            verify_manifest(manifest,source)
        else:
            need(manifest['model']==request['model']['name'] and manifest['model_digest']==request['model']['digest']
             and type(manifest['max_inference_calls']) is int and manifest['max_inference_calls']==39, 'model manifest')
        if not remote and source == STATES[0]:
            need(manifest.get('provider')=='ollama-local' and 'source' not in manifest and
                 manifest['prompt_version']==PROTOCOL and manifest['prompt_sha256']==fingerprint(PROMPT)
                 and same(manifest['options'],{'temperature':0,'seed':7,'num_ctx':8192,'num_predict':1024})
                 and manifest['private_thinking_recorded'] is False and manifest['inference_timeout_seconds']==180
                 and manifest['tool_contract']=='qloo-context-input-not-quality-label-v1', 'production model contract')
    need(not complete or (manifest is not None and contexts is not None and len(samples)==4), 'incomplete provider coverage')
    if remote:
        need('model-readiness.json' not in before and report['model_load_attempts']==0, 'remote capture must not load a local model')
    elif 'model-readiness.json' in before:
        ready = read(directory/'model-readiness.json')
        need(report['model_load_attempts']==1 and contexts is not None, 'model loaded before tool preflight')
        if source == STATES[0]:
            need(ready['status']=='READY' and ready['model']==manifest['model'] and ready['model_digest']==manifest['model_digest']
                 and ready['context_length']==8192 and type(ready['inference_calls']) is int and ready['inference_calls']==0
                 and type(ready['new_qloo_requests']) is int and ready['new_qloo_requests']==0, 'model readiness')
        else:
            need(ready.get('source')=='test-double-only', 'mixed simulation readiness')
    else:
        need(not complete and report['model_attempts']==0, 'decisions without readiness')
    packet_names = sorted(n for n in before if n.startswith('causal-execution-'))
    observed = [e for e in events if e['kind']=='observed_model_execution']
    need(len(packet_names)==len(observed)<=report['model_attempts']<=39, 'model packet/attempt count')
    need(report['model_attempts']-len(packet_names)<=1, 'more than one unrecorded model attempt after first-failure stop')
    if complete:
        need(len(packet_names)==report['model_attempts']==39 and report['qloo_attempts']==4
             and report['model_load_attempts']==(0 if remote else 1), 'complete budgets')
    if remote and report['model_attempts'] > 0:
        need(manifest is not None and contexts is not None and len(samples)==4 and len(frozen)==1,
             'remote attempt before complete sealed tool preflight')
    if remote:
        from .individual_remote_verify import verify_pacing
        verify_pacing(plan,events,report,observed,frozen)
    if packet_names:
        need(contexts is not None and manifest is not None and len(frozen)==1 and frozen[0]['sequence']<observed[0]['sequence'], 'inference before input seal')
    schema = {'type':'object','properties':{'ordered_catalog_indices':{'type':'array','items':{'type':'integer','enum':list(range(20))},
        'minItems':20,'maxItems':20}},'required':['ordered_catalog_indices'],'additionalProperties':False}
    builder = ToolContextMovieAgent.__new__(ToolContextMovieAgent)
    packets = []
    deployment_fingerprint = None
    completion_ids = set()
    for i,name in enumerate(packet_names,1):
        packet = read(directory/name)
        observation = packet['observation']
        req = packet['effective_request']
        ranks = validate_response(req,packet['response'])
        need(name==f'causal-execution-{i:03d}.json' and packet['execution_id']==directory.name+'/'+str(i)
             and type(observation['call']) is int and observation['call']==i, 'packet sequence')
        need(observation['done'] is True and observation['done_reason']=='stop' and observation['private_thinking_recorded'] is False
             and type(observation['prompt_eval_count']) is int
             and 0<=observation['prompt_eval_count']<=(8192 if remote else 7168), 'incomplete/truncated decision')
        need(req['catalog']==request['catalog'] and req['tool_context'] in contexts.values()
             and req['profile'] in profiles.values() and packet['model_payload']==builder.decision_input(req,schema), 'model input binding')
        need(observation['input_sha256']==fingerprint(packet['model_payload']) and observation['output_sha256']==fingerprint(ranks), 'observed model hashes')
        if remote:
            observed_fingerprint = verify_packet(packet,manifest,source)
            need(not packets or observed_fingerprint==deployment_fingerprint, 'remote deployment fingerprint changed')
            deployment_fingerprint = observed_fingerprint
            need(observation['completion_id'] not in completion_ids, 'remote completion identity was reused')
            completion_ids.add(observation['completion_id'])
        need(same(observed[i-1]['data'],{'execution_id':packet['execution_id'],'request_sha256':fingerprint(req),
             'payload_sha256':fingerprint(packet['model_payload']),'output_sha256':fingerprint(ranks)}), 'model ledger binding')
        packets.append(packet)
    policy = read(directory/'frozen-causal-policy.json') if 'frozen-causal-policy.json' in before else None
    policy_events = [e for e in events if e['kind']=='policy_frozen']
    pair_id = 'individual-'+directory.name
    replay_ledger = _MemoryLedger(directory.name)
    if packets:
        engine = _PacketReplay(manifest,packets)
        pair = {'pair_id':pair_id,'artists':request['artists'],'split':'individual-demonstration'}
        try:
            # A partial run before calibration stops on its next missing packet;
            # after calibration, the recorded policy is used without changing it.
            capture_pair(engine,replay_ledger,pair,request['catalog'],profiles,contexts,policy=policy,
                freeze=lambda *args: (_ for _ in ()).throw(_ReplayEnd()))
        except _ReplayEnd:
            need(not complete, 'replay incomplete')
    relevant = {'observed_model_execution','observed_session_boundary','pair_healthy_capture_complete'}
    actual_replay_events = [(e['kind'],e['data']) for e in events if e['kind'] in relevant]
    expected_replay_events = [(kind,data) for kind,data in replay_ledger.events if kind in relevant]
    need(same(actual_replay_events,expected_replay_events[:len(actual_replay_events)]) and
         (not complete or same(actual_replay_events,expected_replay_events)), 'boundary order/multiplicity or protocol replay differs')
    if policy is not None:
        need(len(policy_events)==1 and len(observed)>=6 and
             observed[5]['sequence']<policy_events[0]['sequence'] and
             (len(observed)==6 or policy_events[0]['sequence']<observed[6]['sequence']), 'policy freeze ordering')
        boundaries = [e for e in events if e['kind']=='observed_session_boundary'][:9]
        need(len(boundaries)==9 and boundaries[-1]['sequence']<policy_events[0]['sequence'], 'healthy controls before freeze')
        healthy = {'A':[],'B':[]}
        controls = []
        for event in boundaries:
            trace = event['data']
            number = trace['call']
            decision = {'ranking':packets[number-1]['response']['ranked_entity_ids'],'trace':trace}
            label = next(p for p in profiles if profile_hash(profiles[p])==trace['requested_profile_sha256'])
            if not trace['cache_hit']:
                healthy[label].append(decision)
            controls.append({**decision,'diagnosis':{'diagnosis':'NONE','operation':'none'},
                'expected_cache_hit':trace['cache_hit'],'patch':{'operation':'none','attempt':0,'applied':False}})
        need(all(len(rows)==3 for rows in healthy.values()), 'calibration coverage')
        noise = max(distance(a['ranking'],b['ranking']) for rows in healthy.values() for a,b in combinations(rows,2))
        need(type(policy['noise_barrier']) in (int,float) and abs(policy['noise_barrier']-noise)<=1e-12
             and policy['calibration_sha256']==fingerprint({'healthy':healthy,'controls':controls}), 'independent calibration differs')
        need(policy['policy_sha256']==fingerprint({k:v for k,v in policy.items() if k!='policy_sha256'})
             and policy['schema_version']==1 and policy['protocol_version']==PROTOCOL and policy['model_manifest']==manifest
             and policy['source_sha256']==plan['source_sha256'] and policy['catalog_sha256']==fingerprint(request['catalog'])
             and policy['development_pair_id']==pair_id and type(policy['reserved_pairs_seen']) is int and policy['reserved_pairs_seen']==0
             and type(policy['practical_tolerance']) is int and policy['practical_tolerance']==0
             and policy['cultural_gate']=='NOT_VALIDATED' and policy['release_gate']=='BLOCKED', 'policy binding')
        expected_policy = {'schema_version':1,'protocol_version':PROTOCOL,'created_utc':policy['created_utc'],
            'noise_barrier':policy['noise_barrier'],'practical_tolerance':0,
            'noise_method':'maximum observed within-profile symmetric ordinal NDCG@5 distance over three fresh development decisions per profile',
            'calibration_sha256':fingerprint({'healthy':healthy,'controls':controls}),'model_manifest':manifest,
            'catalog_sha256':fingerprint(request['catalog']),'source_sha256':plan['source_sha256'],
            'development_pair_id':pair_id,'reserved_pairs_seen':0,
            'causal_checks':['complete_repeats','correct_diagnosis','repair_applied','profile_integrity_restored','real_rerun',
                'healthy_stable','no_behavioral_regression','no_false_alarm','legitimate_cache_reuse'],
            'quality_boundary':'Direct Qloo context is consumed. Agreement with that snapshot cannot independently certify cultural quality.',
            'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}
        expected_policy['policy_sha256'] = fingerprint(expected_policy)
        need(same(policy,expected_policy), 'policy schema/meaning differs')
        need(same(policy_events[0]['data'],{'policy_sha256':policy['policy_sha256'],'model_calls':6,'reserved_pairs_seen':0})
             and instant(observed[5]['timestamp_utc'])<=instant(policy['created_utc'])<=instant(policy_events[0]['timestamp_utc']), 'policy metadata/time')
    else:
        need(not complete and not policy_events and len(packets)<=6, 'missing policy')
    pair_name,summary_name = f'causal-pair-{pair_id}.json',f'causal-summary-{pair_id}.json'
    scores = 0
    if complete:
        need(policy is not None and pair_name in before and summary_name in before, 'missing completed pair')
        record,summary = read(directory/pair_name),read(directory/summary_name)
        need(same(record,replay_ledger.files[pair_name]) and same(summary,evaluate_pair(record,policy['noise_barrier']))
             and same(summary,replay_ledger.files[summary_name]), 'stored pair or evaluator differs')
        tool_ranks = [[r['entity_id'] for r in contexts[profile_hash(profiles[p])]['ranked_entities']] for p in ('A','B')]
        need(abs(distance(*tool_ranks)-record['tool_signal_distance'])<=1e-12 and
             abs(record['observed_healthy_noise']-policy['noise_barrier'])<=1e-12, 'independent tool/noise distance')
        for case,result in zip(record['cases'],summary['cases'],strict=True):
            changed = recovered = 0
            worst = before_distance = full = 0.
            for repeat in case['repeats']:
                victim = repeat['order'][1]
                b = min(distance(repeat['before'][victim]['ranking'],h['ranking']) for h in record['healthy'][victim])
                a = max(distance(repeat['after'][p]['ranking'],h['ranking']) for p in ('A','B') for h in record['healthy'][p])
                full = max(full,*(distance(repeat['after'][p]['ranking'],h['ranking'],20) for p in ('A','B') for h in record['healthy'][p]))
                before_distance = max(before_distance,b)
                worst = max(worst,a)
                changed += b>policy['noise_barrier']+1e-12
                recovered += b>policy['noise_barrier']+1e-12 and a<=policy['noise_barrier']+1e-12
            need(result['behavior_changed_repeats']==changed and result['behavioral_recovery_observed_repeats']==recovered
                 and all(abs(result[k]-v)<=1e-12 for k,v in (('recovery_max_distance',worst),('before_max_distance',before_distance),
                                                         ('full_ranking_recovery_max_distance',full))), 'independent score differs')
            scores += 1
        recovered = {case['fault']:case['behavioral_recovery_observed_repeats'] for case in summary['cases']}
        passing = sum(case['passing'] for case in summary['cases'])
        need(type(report['passing']) is int and report['passing']==passing and type(report['denominator']) is int and report['denominator']==3
             and same(report['summary'],summary) and report['policy_sha256']==policy['policy_sha256']
             and same(report['observed_recoveries_by_fault'],recovered) and report['causal_gate']==('PASS' if passing==3 else 'FAIL')
             and report['behavioral_gate']==('OBSERVED_RECOVERY' if all(recovered.values()) else 'INCONCLUSIVE'), 'reported result differs')
    else:
        need(report['causal_gate']==report['behavioral_gate']=='NOT_EVALUATED', 'partial approval')
        if pair_name in before:
            need(pair_name in replay_ledger.files and same(read(directory/pair_name),replay_ledger.files[pair_name]), 'partial completed pair differs')
        if summary_name in before:
            need(summary_name in replay_ledger.files and same(read(directory/summary_name),replay_ledger.files[summary_name]), 'partial summary differs')
    allowed_files = {'individual-plan.json','individual-report.json','ledger.jsonl','individual-identities.json',
        'individual-tool-inputs.json','model-manifest.json','model-readiness.json','frozen-causal-policy.json',pair_name,summary_name}
    need(set(before)<=allowed_files | set(sample_names) | set(packet_names), 'unknown artifact')
    need(inventory(directory)==before, 'capture changed during verification')
    return {**report,'verified_utc':utc_now(),'verification_status':'VERIFIED_COMPLETE' if complete else 'VERIFIED_PARTIAL',
        'recorded_source':source,'provenance':'SIMULATION_ONLY' if source=='test-double-only' else 'RECORDED_PROVIDER_OBSERVATIONS',
        'external_service_attested':False,'independent_validation_claim':False,'verified_model_packets':len(packets),
        'verified_provider_samples':len(samples),'independent_score_reports':scores,'artifact_sha256':before,
        'capture_source_sha256':plan['source_sha256'],'capture_driver_sha256':plan['driver_sha256'],
        'dependencies_lock_sha256':plan['dependencies_lock_sha256'],
        'verifier_source_sha256':({'individual_verify.py':sha(Path(__file__)),
            'individual_remote_verify.py':sha(SOURCE_ROOT/'src/affinityqa/individual_remote_verify.py'),
            'verify_individual_remote.py':sha(SOURCE_ROOT/'scripts/verify_individual_remote.py')} if remote else
            {'individual_verify.py':sha(Path(__file__)),
             'verify_individual_capture.py':sha(SOURCE_ROOT/'scripts/verify_individual_capture.py')}),
        'verification_boundary':'Recorded-file coherence, sequential protocol replay and independent score arithmetic; '
            'no new requests, external-service cryptographic attestation, cultural quality or population reliability. '
            + ('Remote envelopes and effective request hashes are checked; full response hashes are un-reconstructible observations. '
               'Provider model ID and stable optional fingerprint do not attest immutable weights. '
               'Monotonic pacing slots are local observations, not provider capacity reservations or independent timing attestation.' if remote else
               'Metadata request counts are planned budgets, not individually recorded transport observations.')}


def verify_individual(directory):
    try:
        return _verify(directory)
    except SchemaError:
        raise
    except (AgentError,KeyError,TypeError,ValueError,IndexError,StopIteration,OSError) as exc:
        raise SchemaError('Individual audit: missing, malformed or inconsistent evidence') from exc


def write_receipt(receipt, destination, directory):
    destination, directory = checked_path(destination),checked_path(directory)
    need(not destination.resolve().is_relative_to(directory.resolve()) and destination.parent.is_dir(), 'receipt must be outside artifacts')
    need(inventory(directory)==receipt['artifact_sha256'], 'capture changed before receipt')
    encoded = (json.dumps(receipt,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf-8')
    fd = os.open(destination,os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os,'O_BINARY',0),0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(encoded)
    need(destination.read_bytes()==encoded, 'receipt write incomplete; retain and inspect')
