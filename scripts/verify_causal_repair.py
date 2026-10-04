"""Read-only replay of causal evidence; exclusive verification receipt only.

Checks recorded transport observations, not a cryptographic attestation of the
external model service. Makes no provider/model requests and loads no secrets.
"""
import argparse
import json
import math
import re
import unicodedata
from collections import Counter
from itertools import combinations
from pathlib import Path

from run_causal_repair import ROOT, read, sha, SOURCES, DIGEST, FRESH
from affinityqa.agents import validate_response
from affinityqa.causal_agent import context_from_sample, profile_hash, ToolContextMovieAgent
from affinityqa.causal_evaluator import evaluate_pair
from affinityqa.evidence import fingerprint, utc_now
from affinityqa.errors import SchemaError
from affinityqa.models import parse_entities, resolve_seed, validate_response_envelope
from affinityqa.store import RUN_ID


def need(condition, message):
    if not condition:
        raise SchemaError('Causal audit: ' + message)


def events(path):
    result = [json.loads(s) for s in path.read_text(encoding='utf8').splitlines() if s.strip()]
    need([e['sequence'] for e in result] == list(range(1, len(result) + 1)), 'ledger sequence gap')
    need(all(a['timestamp_utc'] <= b['timestamp_utc'] for a, b in zip(result, result[1:])), 'ledger time reversal')
    return result


def distance(a, b, k=5):
    """Independent symmetric linear-ordinal arithmetic (no production metrics)."""
    need(len(a) == len(b) == 20 and len(set(a)) == 20 and set(a) == set(b), 'score permutation')
    def score(actual, reference):
        rel = {x: 20-i for i, x in enumerate(reference)}
        return sum(rel[x]/math.log2(i+2) for i, x in enumerate(actual[:k])) / sum((20-i)/math.log2(i+2) for i in range(k))
    return max(0., 1-(score(a, b)+score(b, a))/2)


def enclosed(base, relative):
    p = (base / relative).resolve()
    need(p.is_relative_to(base.resolve()), 'path escapes evidence directory')
    return p


def musical_identity(name, rows):
    """Independent replay of the metadata-only identity amendment."""
    normalize=lambda s:' '.join(unicodedata.normalize('NFKC',s).casefold().split())
    matches=[r for r in rows if normalize(r.name)==normalize(name)]
    artists=[r for r in matches if 'urn:entity:artist' in r.types]
    need(len(artists)<=1,'ambiguous artist in amended identity selection')
    if artists:return artists[0]
    people=[r for r in matches if 'urn:entity:person' in r.types]
    need(len(people)==1,'missing unique musical person')
    row=people[0]; occupations=row.metadata.get('occupations',row.metadata.get('occupation',[]))
    if isinstance(occupations,str):occupations=[occupations]
    if not isinstance(occupations,list):occupations=[]
    accepted={'musician','singer','singer songwriter','songwriter','rapper','composer','pianist','guitarist','harpist','record producer','music producer'}
    musical=any(isinstance(v,str) and ' '.join(re.sub(r'[_-]',' ',v.casefold()).split()) in accepted for v in occupations)
    external=row.metadata.get('external',{})
    service=isinstance(external,dict) and any(isinstance(external.get(k),dict) and bool(external[k].get('id')) for k in ('musicbrainz','lastfm','spotify'))
    need(musical or service,'person lacks explicit musical evidence')
    return row


def search_rows(body):
    validate_response_envelope(body,insights=False)
    seen=[]; entities=[]; audit=[]
    norm=lambda s:' '.join(unicodedata.normalize('NFKC',s).casefold().split())
    for index,raw in enumerate(body['results']):
        entity=parse_entities({'results':[raw]},insights=False)[0]; duplicate=False
        for old_index,old_raw,old in seen:
            if old.entity_id!=entity.entity_id:continue
            if old_raw==raw:
                audit.append({'row':index,'same_as_row':old_index,'entity_id':entity.entity_id,'action':'exact_duplicate_collapsed'});duplicate=True;break
            need(norm(old.name)==norm(entity.name),'same UUID conflicting search names')
            need(not set(old.types).intersection(entity.types),'same-type conflicting search metadata')
            audit.append({'row':index,'same_as_row':old_index,'entity_id':entity.entity_id,'action':'disjoint_type_observations_preserved'})
        if not duplicate:seen.append((index,raw,entity));entities.append(entity)
    return entities,audit


def verify(run_id):
    need(RUN_ID.fullmatch(run_id) is not None, 'invalid run ID')
    directory = ROOT/'runs'/run_id
    plan = read(directory/'causal-plan.json'); report = read(directory/'causal-report.json')
    complete = report['status'] == 'COMPLETE'
    observations_amended = plan.get('schema_version') == 3
    amended = plan.get('schema_version') in (2,3)
    need(report['status'] in ('COMPLETE', 'INCOMPLETE'), 'unknown status')
    need(plan['plan_sha256'] == fingerprint({k:v for k,v in plan.items() if k != 'plan_sha256'}) == report['plan_sha256'], 'plan hash')
    original_driver_sha = sha(Path(__file__).with_name('run_causal_repair.py'))
    driver_name = 'resume_causal_identity.py' if observations_amended else 'continue_causal_validation.py' if amended else 'run_causal_repair.py'
    need(plan['driver_sha256'] == sha(Path(__file__).with_name(driver_name)), 'driver changed')
    if amended:need(plan.get('original_driver_sha256')==original_driver_sha and plan['mode']=='validation','amendment driver binding')
    need(set(plan['source_sha256']) == set(SOURCES), 'source manifest coverage')
    for name, digest in plan['source_sha256'].items():
        need(sha(ROOT/'src/affinityqa'/name) == digest, 'source changed: ' + name)
    for name, digest in plan['source_artifact_sha256'].items():
        need(sha(enclosed(ROOT, name)) == digest, 'source artifact changed')
    need(plan['catalog_sha256'] == fingerprint(plan['catalog']), 'catalog hash')
    need(plan['manifest']['model_digest'] == DIGEST and plan['manifest']['options']['num_ctx'] == 8192, 'model identity/context')
    need(report['cultural_gate'] == 'NOT_VALIDATED' and report['release_gate'] == 'BLOCKED' and report['release_approved'] is False, 'invalid cultural/release claim')
    development = plan['mode'] == 'development'; count = 1 if development else 6
    expected_pairs = [{'pair_id':'causal-development-01','artists':{'A':'Brian Eno','B':'Bad Bunny'},'split':'development'}] if development else [
        {'pair_id':f'causal-validation-{i:02d}','artists':{'A':a,'B':b},'split':'validation'} for i,(a,b) in enumerate(FRESH,1)]
    need(plan['pairs'] == expected_pairs and report['denominator'] == 3*count, 'sealed pair denominator')
    need(plan['maximum_model_calls'] == 39*count and plan['maximum_qloo_requests'] == (19 if observations_amended else 23 if amended else 2 if development else 24)
         and plan['maximum_attempts_per_request'] == 1, 'budget changed')
    root_events = events(directory/'ledger.jsonl')
    reused = []
    if amended:
        amendment=plan['amendment']; prior_id=amendment['interrupted_run']
        need(prior_id==('20261004T122943Z-c400e1fb' if observations_amended else '20261004T122430Z-3986e92d') and amendment['before_model_outputs'] is True,'unapproved continuation')
        prior_path=ROOT/'evidence'/('CAUSAL-REPAIR-'+prior_id+'.json'); prior=read(prior_path)
        need(sha(prior_path)==amendment['interrupted_receipt_sha256'] and prior['status']=='INCOMPLETE'
             and prior['model_calls']==0 and prior.get('model_attempts')==0 and prior['qloo_requests']==(4 if observations_amended else 1) and prior['pairs']==[],'continuation not pre-inference')
        for name,h in prior['artifact_sha256'].items():need(sha(enclosed(ROOT/'runs'/prior_id,name))==h,'interrupted artifact changed')
        oldplan=read(ROOT/'runs'/prior_id/'causal-plan.json')
        need(oldplan['pairs']==plan['pairs'] and oldplan['catalog']==plan['catalog'] and oldplan['source_sha256']==plan['source_sha256']
             and oldplan['parent_run']==plan['parent_run'],'amendment changed protected scope')
        if observations_amended:
            need(amendment['kind']=='search-observations-v1' and amendment['prior_amendment']==oldplan['amendment']
                 and amendment['prior_driver_sha256']==oldplan['driver_sha256']==sha(Path(__file__).with_name('continue_causal_validation.py')),'search amendment chain')
            bindings=amendment['reused_samples']
            need([b['query'] for b in bindings]==['Alice Coltrane','Lil Nas X','Kraftwerk','Halsey','Slowdive'],'wrong reused searches')
        else:
            need(oldplan['driver_sha256']==original_driver_sha,'original driver changed')
            bindings=[{'query':'Alice Coltrane',**amendment['reused_sample']}]
        for binding in bindings:
            reused_path=enclosed(ROOT,binding['path']);sample=read(reused_path)
            expected_run='20261004T122430Z-3986e92d' if binding['query']=='Alice Coltrane' else prior_id
            need(reused_path.parent==ROOT/'runs'/expected_run and sha(reused_path)==binding['sha256'],'reused search binding')
            need(sample['status']==200 and sample['attempt']==1 and sample['live_network_request'] is True
                 and sample['request']=={'method':'GET','host':'https://hackathon.api.qloo.com','path':'/search','params':{'query':binding['query'],'take':5}}
                 and sample['response_sha256']==fingerprint(sample['response']),'reused search not valid')
            reused.append(sample)
        need(plan['total_maximum_qloo_requests']==24 and report['reused_qloo_requests']==len(reused)
             and report['total_qloo_requests']==report['qloo_requests']+len(reused)<=24,'amended total budget')
    samples = {}; sample_requests = []
    tool_events = [e for e in root_events if e['kind'] == 'tool_call']
    for e in tool_events:
        path = enclosed(directory, e['data']['sample']); s = read(path); request = s['request']
        need(s['attempt'] == 1 and s['live_network_request'] is True, 'not one real network attempt')
        need(s['response_sha256'] == fingerprint(s['response']), 'provider response changed')
        need(e['data'] == {'sample':path.name, **{k:v for k,v in s.items() if k != 'response'}}, 'provider ledger mismatch')
        need(set(request) == {'method','host','path','params'} and request['method'] == 'GET' and request['host'] == 'https://hackathon.api.qloo.com', 'unapproved request envelope')
        if request['path'] == '/search':
            need(set(request['params']) == {'query','take'} and request['params']['take'] == 5
                 and request['params']['query'] in {n for p in expected_pairs for n in p['artists'].values()}, 'unapproved search')
        else:
            need(request['path'] == '/v2/insights' and set(request['params']) == {'filter.type','bias.trends','take','signal.interests.entities','filter.results.entities'}, 'unapproved provider path/params')
        if complete: need(s['status'] == 200, 'complete run contains failed provider response')
        samples[sha(path)] = s; sample_requests.append(fingerprint(request))
    need(len(set(sample_requests)) == len(sample_requests), 'duplicate/retried provider request')
    need(all(fingerprint(s['request']) not in sample_requests for s in reused),'reused lookup was retried')
    need(len(samples) == report['qloo_requests'] <= plan['maximum_qloo_requests'], 'provider call count')
    need({p.name for p in directory.glob('http-*.json')} == {e['data']['sample'] for e in tool_events}, 'orphan provider sample')
    tool_path = directory/'causal-tool-inputs.json'; captured = read(tool_path) if tool_path.exists() else {}
    search_samples = list(samples.values()) + reused
    identities = None
    if amended:
        ipath=directory/'causal-identities.json'
        if ipath.exists():
            identities=read(ipath);identity_events=[e for e in root_events if e['kind']=='all_identities_frozen']
            need(set(identities)=={p['pair_id'] for p in expected_pairs} and len(identity_events)==1,'identity coverage')
            search_count=7 if observations_amended else 11
            ie=identity_events[0];need(ie['data']=={'sha256':fingerprint(identities),'model_calls':0,'qloo_calls':search_count},'identity seal metadata')
            searches=[e for e in tool_events if e['data']['request']['path']=='/search'];insights=[e for e in tool_events if e['data']['request']['path']=='/v2/insights']
            need(len(searches)==search_count and all(e['sequence']<ie['sequence'] for e in searches)
                 and all(e['sequence']>ie['sequence'] for e in insights),'identity preflight ordering')
            resolved_ids=[]; expected_search_audit={}
            for pair in expected_pairs:
                profiles=identities[pair['pair_id']];need(set(profiles)=={'A','B'},'missing pinned profile')
                for label,name in pair['artists'].items():
                    ss=[s for s in search_samples if s['request']['path']=='/search' and s['request']['params']['query']==name]
                    need(len(ss)==1 and ss[0]['status']==200,'missing identity source')
                    if observations_amended:
                        rows,audit=search_rows(ss[0]['response']);expected_search_audit[name]=audit
                    else:rows=parse_entities(ss[0]['response'],insights=False)
                    entity=musical_identity(name,rows)
                    expected_profile={'entity_id':entity.entity_id,'name':' '.join(unicodedata.normalize('NFKC',name).split()),'type':'urn:entity:artist' if 'urn:entity:artist' in entity.types else 'urn:entity:person'}
                    need(profiles[label]==expected_profile,'pinned identity selection differs');resolved_ids.append(entity.entity_id)
            need(len(set(resolved_ids))==12,'pinned original identities coincide')
            if observations_amended:need(read(directory/'causal-search-audit.json')==expected_search_audit,'search observation audit changed')
        else:
            need(not complete and all(s['request']['path']=='/search' for s in samples.values()),'Insights before identity seal')
    if complete: need(len(captured) == count and len(samples) == plan['maximum_qloo_requests'], 'incomplete tool inputs')
    for pair in expected_pairs:
        if pair['pair_id'] not in captured: continue
        entry = captured[pair['pair_id']]
        if amended:need(identities is not None and entry['profiles']==identities[pair['pair_id']],'tool input ignored pinned identity')
        need(set(entry['profiles']) == {'A','B'} and set(entry['contexts']) == {profile_hash(p) for p in entry['profiles'].values()}, 'profile context coverage')
        for label, profile in entry['profiles'].items():
            need(profile['name'] == pair['artists'][label], 'profile name changed')
            context = entry['contexts'][profile_hash(profile)]; s = samples.get(context['sample_sha256'])
            need(s is not None and context_from_sample(profile, plan['catalog'], s, context['sample_sha256']) == context, 'context raw-source mismatch')
            if not development:
                searches = [s for s in search_samples if s['request']['path']=='/search' and s['request']['params']['query']==profile['name']]
                need(len(searches) == 1, 'missing unique identity resolution')
                rows=search_rows(searches[0]['response'])[0] if observations_amended else parse_entities(searches[0]['response'], insights=False)
                entity = musical_identity(profile['name'],rows) if amended else resolve_seed({'name':profile['name'],'accepted_names':[profile['name']],'accepted_types':['urn:entity:artist','urn:entity:person']}, rows, synthetic=False)
                need(entity.entity_id == profile['entity_id'] and profile['type'] in entity.types, 'resolved identity changed')
    policy_path = directory/'frozen-causal-policy.json'; policy = read(policy_path) if policy_path.exists() else None
    if complete: need(policy is not None, 'missing frozen policy')
    if policy:
        need(policy['policy_sha256'] == fingerprint({k:v for k,v in policy.items() if k!='policy_sha256'}), 'policy hash')
        need(policy['source_sha256'] == plan['source_sha256'] and policy['model_manifest'] == plan['manifest']
             and policy['catalog_sha256'] == plan['catalog_sha256'] and policy['reserved_pairs_seen'] == 0, 'policy binding')
    if not development:
        parent_id = plan['parent_run']; need(RUN_ID.fullmatch(parent_id) is not None, 'parent ID')
        parent_path = ROOT/'evidence'/('CAUSAL-REPAIR-'+parent_id+'.json'); parent = read(parent_path)
        need(sha(parent_path) == plan['parent_receipt_sha256'] and parent['status']=='COMPLETE' and parent['causal_gate']=='PASS' and parent['behavioral_gate']=='OBSERVED_RECOVERY', 'parent not qualified')
        need(parent['driver_sha256']==(original_driver_sha if amended else plan['driver_sha256']), 'parent driver changed')
        for name,h in parent['artifact_sha256'].items(): need(sha(enclosed(ROOT/'runs'/parent_id,name))==h,'parent evidence changed')
        parent_policy = read(ROOT/'runs'/parent_id/'frozen-causal-policy.json')
        if policy: need(policy == parent_policy, 'validation changed frozen policy')
        elif not complete: policy = parent_policy
    verified_calls = 0; summaries = []; independent_reports = 0
    for pair in expected_pairs:
        key = pair['pair_id']; binding_path = directory/('causal-execution-binding-'+key+'.json')
        if not binding_path.exists():
            need(not complete, 'missing execution binding'); continue
        binding = read(binding_path); sub = enclosed(directory,binding['directory'])
        need(binding['pair_id']==key and sub.parent==directory/'pair-executions', 'wrong execution binding')
        manifest = read(sub/'model-manifest.json'); need(manifest==plan['manifest'],'pair model changed')
        readiness_path=sub/'model-readiness.json'
        if readiness_path.exists():
            ready=read(readiness_path);need(ready['status']=='READY' and ready['model_digest']==DIGEST and ready['context_length']==8192 and ready['inference_calls']==0,'model readiness')
        else: need(not complete, 'missing model readiness')
        se = events(sub/'ledger.jsonl') if (sub/'ledger.jsonl').exists() else []
        observed = [e for e in se if e['kind']=='observed_model_execution']
        packet_paths = sorted(sub.glob('causal-execution-*.json')); need(len(packet_paths)==len(observed)<=39,'observed execution count')
        packets = {}; schema={'type':'object','properties':{'ordered_catalog_indices':{'type':'array','items':{'type':'integer','enum':list(range(20))},'minItems':20,'maxItems':20}},'required':['ordered_catalog_indices'],'additionalProperties':False}
        model = ToolContextMovieAgent.__new__(ToolContextMovieAgent)
        for n, path in enumerate(packet_paths,1):
            pkt=read(path); obs=pkt['observation']; req=pkt['effective_request']; payload=pkt['model_payload']
            need(path.name==f'causal-execution-{n:03d}.json' and obs['call']==n and pkt['execution_id']==sub.name+'/'+str(n),'execution sequence')
            need(obs['done'] is True and obs['done_reason']=='stop' and obs['private_thinking_recorded'] is False
                 and type(obs['prompt_eval_count']) is int and obs['prompt_eval_count']+1024<=8192,'incomplete/truncated inference')
            need(req['catalog']==plan['catalog'] and payload==model.decision_input(req,schema),'actual model payload mismatch')
            need(req['tool_context'] in captured[key]['contexts'].values(),'unsealed tool context consumed')
            ranks=validate_response(req,pkt['response']);need(len(ranks)==20 and len(set(ranks))==20,'incomplete actual response')
            need(obs['input_sha256']==fingerprint(payload) and obs['output_sha256']==fingerprint(ranks),'model observation hash')
            need(observed[n-1]['data']=={'execution_id':pkt['execution_id'],'request_sha256':fingerprint(req),'payload_sha256':fingerprint(payload),'output_sha256':fingerprint(ranks)},'model ledger mismatch')
            packets[pkt['execution_id']]=pkt
        verified_calls += len(packets)
        if observed:
            frozen = [e for e in root_events if e['kind']=='all_tool_inputs_frozen'];need(len(frozen)==1 and frozen[0]['data']['sha256']==fingerprint(captured) and frozen[0]['timestamp_utc']<=observed[0]['timestamp_utc'],'inputs not sealed before inference')
        boundaries = [e['data'] for e in se if e['kind']=='observed_session_boundary']
        for t in boundaries:
            need(t['execution_id'] in packets,'trace missing actual packet'); pkt=packets[t['execution_id']]; req=pkt['effective_request']; payload=pkt['model_payload']
            expected={'transmitted_profile_sha256':profile_hash(payload['profile']),'tool_profile_sha256':profile_hash(req['tool_context']['profile']),
                'output_profile_sha256':profile_hash(payload['profile']),'call':pkt['observation']['call'],'payload_sha256':fingerprint(payload),
                'context_response_sha256':req['tool_context']['response_sha256'],'execution_request_sha256':fingerprint(req),'output_sha256':fingerprint(pkt['response']['ranked_entity_ids'])}
            need(all(t[k]==v for k,v in expected.items()),'trace misstates actual boundary')
        record_path=directory/('causal-pair-'+key+'.json')
        if not record_path.exists(): need(not complete,'missing completed pair');continue
        rec=read(record_path); need(rec==read(sub/record_path.name),'pair record differs between ledgers')
        need(rec['profiles']==captured[key]['profiles'] and rec['catalog']==plan['catalog'] and all(rec[k]==pair[k] for k in ('pair_id','artists','split')),'pair input binding')
        tool_ranks=[[r['entity_id'] for r in captured[key]['contexts'][profile_hash(rec['profiles'][p])]['ranked_entities']] for p in ('A','B')]
        need(abs(distance(*tool_ranks)-rec['tool_signal_distance'])<=1e-12,'tool contrast arithmetic')
        decisions=[]
        for p in ('A','B'): decisions += [(d,p) for d in rec['healthy'][p]]
        decisions += [(c,None) for c in rec['healthy_controls']]
        for control in rec['healthy_controls']:
            need(control.get('patch') == {'operation':'none','attempt':0,'applied':False}, 'healthy control changed state')
        for c in rec['cases']:
            for r in c['repeats']:
                for state in ('before','after'): decisions += [(d,p) for p,d in r[state].items()]
                decisions += [(d,None) for d in r['after_controls']]
                for control in r['after_controls']:
                    need(control.get('patch') == {'operation':'none','attempt':0,'applied':False}, 'reuse control changed state')
        boundary_set={fingerprint(t) for t in boundaries}
        for d,p in decisions:
            t=d['trace'];need(fingerprint(t) in boundary_set and d['ranking']==packets[t['execution_id']]['response']['ranked_entity_ids'],'decision differs from recorded boundary/output')
            if p is not None: need(t['requested_profile_sha256']==profile_hash(rec['profiles'][p]),'requested profile mislabeled')
        need(len(packets)==39 and len(boundaries)==54 and {d['trace']['execution_id'] for d,p in decisions}==set(packets),'incomplete pair execution coverage')
        need(policy is not None and rec['policy_sha256']==policy['policy_sha256'],'pair policy missing')
        barrier=policy['noise_barrier']; summary=evaluate_pair(rec,barrier)
        need(summary==read(sub/('causal-summary-'+key+'.json')),'stored summary differs from replay')
        noise=max(distance(a['ranking'],b['ranking']) for rows in rec['healthy'].values() for a,b in combinations(rows,2))
        need(abs(noise-rec['observed_healthy_noise'])<=1e-12,'healthy noise arithmetic')
        if development:
            need(abs(noise-barrier)<=1e-12 and policy['calibration_sha256']==fingerprint({'healthy':rec['healthy'],'controls':rec['healthy_controls']}),'calibration mismatch')
            pf=[e for e in root_events if e['kind']=='policy_frozen'];need(len(pf)==1 and pf[0]['data']['model_calls']==6 and observed[5]['timestamp_utc']<=policy['created_utc']<=pf[0]['timestamp_utc']<=observed[6]['timestamp_utc'],'policy not frozen between healthy and incident')
        for c,s in zip(rec['cases'],summary['cases'],strict=True):
            changed=recovered=0; worst=before=full=0.
            for r in c['repeats']:
                victim=r['order'][1]; b=min(distance(r['before'][victim]['ranking'],h['ranking']) for h in rec['healthy'][victim])
                a=max(distance(r['after'][p]['ranking'],h['ranking']) for p in ('A','B') for h in rec['healthy'][p])
                full=max(full,*(distance(r['after'][p]['ranking'],h['ranking'],20) for p in ('A','B') for h in rec['healthy'][p]))
                before=max(before,b);worst=max(worst,a);changed+=b>barrier+1e-12;recovered+=b>barrier+1e-12 and a<=barrier+1e-12
            need(s['behavior_changed_repeats']==changed and s['behavioral_recovery_observed_repeats']==recovered and all(abs(s[k]-v)<=1e-12 for k,v in [('recovery_max_distance',worst),('before_max_distance',before),('full_ranking_recovery_max_distance',full)]),'independent distance arithmetic')
            independent_reports+=1
        summaries.append(summary)
    need(report['pairs']==summaries and verified_calls==report['model_calls'],'report completed pair/call accounting')
    if complete:
        need(len(summaries)==count and verified_calls==39*count,'complete denominator')
        passing=sum(c['passing'] for p in summaries for c in p['cases']);observed=sum(c['behavioral_recovery_observed_repeats'] for p in summaries for c in p['cases']);cache=sum(c['behavioral_recovery_observed_repeats'] for p in summaries for c in p['cases'] if c['fault']=='cache-omits-profile')
        need(report['passing']==passing and report['causal_gate']==('PASS' if passing==3*count else 'FAIL')
             and report['behavioral_gate']==('OBSERVED_RECOVERY' if observed and cache else 'INCONCLUSIVE')
             and report['behavioral_recoveries_observed']==observed and report['cache_behavioral_recoveries']==cache,'report gates')
    else:
        need(report['causal_gate']=='NOT_EVALUATED' and report['behavioral_gate']=='NOT_EVALUATED'
             and verified_calls<=report.get('model_attempts',verified_calls)<=plan['maximum_model_calls'],'partial run approval/accounting')
    receipt={**report,'verified_utc':utc_now(),'driver_sha256':plan['driver_sha256'],'verifier_sha256':sha(Path(__file__)),
        'source_sha256':plan['source_sha256'],'source_artifact_sha256':plan['source_artifact_sha256'],
        'verified_actual_model_calls':verified_calls,'independent_score_reports':independent_reports,
        'artifact_sha256':{p.relative_to(directory).as_posix():sha(p) for p in sorted(directory.rglob('*')) if p.is_file()},
        'verification_boundary':'Recorded model packets, source, provider samples and independent score arithmetic. Not external-service cryptographic attestation, human preference validation or population reliability.',
        'release_approved':False}
    return receipt


def main():
    parser=argparse.ArgumentParser();parser.add_argument('run_id');args=parser.parse_args()
    receipt=verify(args.run_id);path=ROOT/'evidence'/('CAUSAL-REPAIR-'+args.run_id+'.json')
    with path.open('x',encoding='utf8') as f:json.dump(receipt,f,indent=2,ensure_ascii=False,allow_nan=False)
    print(json.dumps({k:receipt[k] for k in ('run_id','status','causal_gate','behavioral_gate','verified_actual_model_calls','qloo_requests','independent_score_reports')},indent=2))


if __name__=='__main__':main()
