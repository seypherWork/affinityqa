"""Verify a fixed real capture through the restricted surface; no live calls."""
import argparse
import json
import re
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def inventory(root):
    return {p.relative_to(root).as_posix():(p.stat().st_size,p.stat().st_mtime_ns)
            for directory in ('runs','evidence') for p in (root/directory).rglob('*') if p.is_file()}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


CHECKS = {'supported_diagnosis', 'repair_applied', 'profile_integrity_restored',
          'decision_redispatched', 'matches_recorded_healthy', 'legitimate_cache_reuse'}
TRACE_HASHES = {'requested_profile_sha256', 'transmitted_profile_sha256',
                'tool_profile_sha256', 'output_profile_sha256'}
REPLAY_FIELDS = {'schema_version', 'status', 'replay_gate', 'run_id', 'pair_id', 'fault',
                 'repeat', 'source', 'new_model_calls', 'new_qloo_calls',
                 'recorded_decision_dispatches', 'diagnosis', 'repair', 'checks',
                 'cultural_gate', 'release_gate', 'notice', 'before', 'after', 'healthy',
                 'trace', 'repaired_trace', 'requested_artist', 'identity_before', 'identity_after'}
OPERATIONS = {'cache-omits-profile': ('CACHE_OMITS_PROFILE', 'set-profile-cache', 3),
              'stale-profile': ('STALE_PROFILE', 'restore-request-profile', 4),
              'wrong-tool-profile': ('WRONG_TOOL_PROFILE', 'bind-request-tool', 4)}


def validate_replay(value, *, run_id, pair_id, fault, repeat, artists, required_version=None):
    """Reject mislabeled, incomplete or expanded responses before counting a replay."""
    require(type(value) is dict and type(value.get('schema_version')) is int
            and value['schema_version'] in (1, 2, 3), 'Unexpected replay schema.')
    version = value['schema_version']
    require(required_version is None or type(required_version) is int and required_version in (1, 2, 3),
            'Unexpected advertised replay schema.')
    require(required_version is None or version == required_version,
            'Replay schema differs from the advertised version.')
    expected_fields = REPLAY_FIELDS | ({'diagnostic_evidence'} if version >= 2 else set()) | ({'context_contrast'} if version == 3 else set())
    require(set(value) == expected_fields,
            'Unexpected replay projection.')
    if version >= 2:
        proof = value['diagnostic_evidence']
        proof_checks = {'raw_qloo_request_bound', 'raw_qloo_response_bound', 'context_projection_bound',
                        'model_payload_bound', 'observed_trace_bound', 'supported_transition_verified',
                        'requested_context_restored', 'legitimate_cache_bound'}
        require(type(proof) is dict and set(proof) == {'schema_version', 'source', 'status', 'diagnosis', 'operation', 'checks'}
                and type(proof['schema_version']) is int and proof['schema_version'] == 1
                and proof['source'] == 'saved-qloo-semantic-check' and proof['status'] == 'VERIFIED'
                and proof['diagnosis'] == value['diagnosis'] and proof['operation'] == value['repair']
                and type(proof['checks']) is dict and set(proof['checks']) == proof_checks
                and all(v is True for v in proof['checks'].values()), 'Independent Qloo evidence failed.')
    require((value['run_id'], value['pair_id'], value['fault']) == (run_id, pair_id, fault)
            and type(value['repeat']) is int and value['repeat'] == repeat,
            'Replay identity differs from the requested incident.')
    require(value['source'] == 'recorded-local-llm-replay', 'Unexpected replay source.')
    require(value['status'] == value['replay_gate'] == 'PASS', 'Recovery status failed.')
    require(type(value['checks']) is dict and set(value['checks']) == CHECKS
            and all(type(v) is bool and v for v in value['checks'].values()), 'Recovery checks failed.')
    require(all(type(value[k]) is int and value[k] == 0 for k in ('new_model_calls', 'new_qloo_calls')),
            'Unexpected provider execution.')
    require(fault in OPERATIONS, 'Unsupported replay fault.')
    diagnosis, operation, dispatches = OPERATIONS[fault]
    require((value['diagnosis'], value['repair']) == (diagnosis, operation), 'Unexpected supported repair.')
    require(type(value['recorded_decision_dispatches']) is int
            and value['recorded_decision_dispatches'] == dispatches, 'Recorded dispatch count differs.')
    require(value['cultural_gate'] == 'NOT_VALIDATED' and value['release_gate'] == 'BLOCKED',
            'Acceptance scopes changed.')
    require(type(value['notice']) is str and bool(value['notice'].strip()), 'Replay notice is missing.')
    expected_artist = artists['A' if repeat == 2 else 'B']
    require(value['requested_artist'] == expected_artist, 'Requested artist differs from the incident order.')
    for view in ('before', 'after', 'healthy'):
        rows = value[view]
        require(type(rows) is list and len(rows) == 5, 'Expected exactly five displayed films.')
        for position, row in enumerate(rows, 1):
            require(type(row) is dict and set(row) == {'position', 'title', 'year'}, 'Unexpected film projection.')
            require(type(row['position']) is int and row['position'] == position
                    and type(row['title']) is str and bool(row['title'].strip())
                    and type(row['year']) is int, 'Invalid film display schema.')
    require(value['after'] == value['healthy'], 'Recovery differs from healthy.')
    if version == 3:
        from affinityqa.context_contrast import validate_context_contrast
        from affinityqa.errors import SchemaError
        try:
            validate_context_contrast(value['context_contrast'],fault,
                before=value['before'],after=value['after'])
        except SchemaError as error:
            raise RuntimeError('Invalid recorded context contrast.') from error
    for field in ('trace', 'repaired_trace'):
        trace = value[field]
        require(type(trace) is dict and set(trace) == TRACE_HASHES | {'cache_hit'}, 'Unexpected trace projection.')
        require(type(trace['cache_hit']) is bool and all(type(trace[k]) is str
                and re.fullmatch(r'[a-f0-9]{64}', trace[k]) for k in TRACE_HASHES), 'Invalid trace schema.')
    names_by_hash = {}
    for identity_field, trace_field in (('identity_before', 'trace'), ('identity_after', 'repaired_trace')):
        names = value[identity_field]
        require(type(names) is dict and set(names) == TRACE_HASHES, 'Unexpected identity projection.')
        require(all(type(name) is str and name in artists.values() for name in names.values()),
                'Unexpected artist identity.')
        require(names['requested_profile_sha256'] == expected_artist, 'Requested profile label differs.')
        for key, name in names.items():
            digest = value[trace_field][key]
            require(digest not in names_by_hash or names_by_hash[digest] == name, 'Conflicting profile labels.')
            names_by_hash[digest] = name
    require(all(name == expected_artist for name in value['identity_after'].values()),
            'Repaired identity labels differ.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root',type=Path,default=ROOT)
    parser.add_argument('--run-id',required=True);parser.add_argument('--receipt-sha256',required=True)
    args=parser.parse_args();root=args.evidence_root.resolve()
    from fastapi.testclient import TestClient
    from affinityqa.public_demo import create_public_app
    before=inventory(root)
    app=create_public_app(root,origin='https://review.example',run_id=args.run_id,
                          receipt_sha256=args.receipt_sha256,web_root=ROOT/'web/out')
    results=[];routes=[]
    with TestClient(app,base_url='https://review.example',raise_server_exceptions=False) as client:
        with patch('socket.create_connection',side_effect=RuntimeError('No external network in recorded review')):
            summary=client.get('/api/demo/summary');require(summary.status_code==200,'Summary HTTP failed.')
            data=summary.json();require(data['status']=='COMPLETE' and data['run_id']==args.run_id,'Capture identity differs.')
            require('rankings' not in data and 'pairs' in data,'Unexpected summary projection.')
            for pair in data['pairs']:
                for fault in pair['faults']:
                    for repeat in (1,2,3):
                        response=client.post('/api/demo/replay',headers={'Origin':'https://review.example'},
                            json={'pair_id':pair['pair_id'],'fault':fault,'repeat':repeat})
                        require(response.status_code==200,f'Replay HTTP failed: {pair["pair_id"]} {fault} {repeat}')
                        value=response.json()
                        validate_replay(value, run_id=args.run_id, pair_id=pair['pair_id'], fault=fault,
                                        repeat=repeat, artists=pair['artists'], required_version=data.get('replay_schema_version', 1))
                        results.append({'pair_id':pair['pair_id'],'fault':fault,'repeat':repeat,'status':value['status']})
            for route in ('/api/review','/api/causal-repair/export','/api/live/jobs','/api/runs','/api/repair-contract','/docs','/openapi.json','/.env'):
                status=client.get(route).status_code;require(status==404,f'Private route exposed: {route}');routes.append({'route':route,'status':status})
            body={'pair_id':data['pairs'][0]['pair_id'],'fault':data['pairs'][0]['faults'][0],'repeat':1}
            for headers in ({},{'Origin':'https://attacker.example'}):
                require(client.post('/api/demo/replay',headers=headers,json=body).status_code==403,'Foreign or missing origin accepted.')
    require(inventory(root)==before,'Recorded surface wrote into its evidence tree.')
    require(len(results)==data['denominator']*3,'Recorded repeat coverage differs from the case denominator.')
    print(json.dumps({'status':'PASS','scope':'Restricted recorded surface with in-process HTTPS request semantics; not external TLS hosting',
        'run_id':args.run_id,'receipt_sha256':args.receipt_sha256,'replays_verified':len(results),'results':results,
        'blocked_routes':routes,'evidence_tree_unchanged':True,'new_model_calls':0,'new_qloo_calls':0,
        'cultural_gate':'NOT_VALIDATED','publication_authorized':False},indent=2))


if __name__=='__main__':main()
