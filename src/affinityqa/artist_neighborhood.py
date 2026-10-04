"""Preserve the musical neighborhood before transferring to movies.

The adapter never requests the artist-to-movie evaluator answer.
"""
import time
from .errors import AffinityQAError, SchemaError
from .evidence import fingerprint, utc_now
from .graph_bridge import fuse_graph
from .models import parse_entities, resolve_seed, normalized_name, context_issues


def prepare_inputs(repair, suite):
    result={}
    for key,value in repair.items():
        pair=next(p for p in suite['pairs'] if p['id']==key and p['split']=='development')
        result[key]={'catalog':value['catalog'],'baseline':value['baseline'],
                     'artists':{p:pair[p][0]['name'] for p in ('A','B')}}
    return result


def validate_inputs(inputs, pair_ids):
    if list(inputs)!=pair_ids or len(pair_ids)!=2:
        raise SchemaError('Neighborhood capture needs both declared development cases.')
    catalog=None
    for value in inputs.values():
        if set(value)!={'catalog','baseline','artists'} or set(value['artists'])!={'A','B'}:
            raise SchemaError('Neighborhood inputs cannot contain evaluator fields.')
        ids=[e['entity_id'] for e in value['catalog']]
        if len(ids)!=20 or len(set(ids))!=20 or (catalog is not None and ids!=catalog):
            raise SchemaError('Neighborhood catalog must stay fixed and complete.')
        catalog=ids
        if (set(value['baseline'])!={'A','B'} or any(len(rows)!=3 for rows in value['baseline'].values())
                or any(len(row)!=20 or set(row)!=set(ids) for rows in value['baseline'].values() for row in rows)):
            raise SchemaError('Neighborhood baseline needs complete repeated decisions.')
        if (any(not isinstance(name,str) or not name.strip() for name in value['artists'].values())
                or normalized_name(value['artists']['A'])==normalized_name(value['artists']['B'])):
            raise SchemaError('Neighborhood mutation must change one named artist.')
    return catalog


def capture_neighborhood(client, inputs, study, *, sleeper=time.sleep, progress=None):
    if (client.max_requests!=21 or client.max_attempts!=1 or client.requests
            or study.get('baseline_weight')!=.5 or study.get('anchor_count')!=5
            or study.get('repeats')!=3 or study.get('max_development_candidates')!=1):
        raise SchemaError('Neighborhood study requires the fixed twenty-one-request/no-retry policy.')
    ids=validate_inputs(inputs,study['development_pair_ids'])
    ledger=client.ledger
    plan={'study':study,'study_sha256':fingerprint(study),'repair_inputs_sha256':fingerprint(inputs),
          'created_utc':utc_now(),'request_cap':21,'max_attempts':1,'minimum_interval_seconds':1,
          'provider_quota':'UNKNOWN','reserved_inputs_executed':0,'evaluator_inputs_received':False}
    plan['plan_sha256']=fingerprint(plan);ledger.write('neighborhood-plan.json',plan)
    ledger.write('neighborhood-inputs.json',inputs)
    ledger.record('neighborhood_plan_frozen',{'plan_sha256':plan['plan_sha256'],'requests':0})
    result={'status':'INCOMPLETE','error':None,'cases':[],'ci_gate':'NOT_VALIDATED',
            'plan_sha256':plan['plan_sha256'],'reserved_inputs_executed':0,'evaluator_inputs_received':False}
    last=None
    def get(path,params):
        nonlocal last
        if last is not None:sleeper(max(0,1-(time.monotonic()-last)))
        last=time.monotonic()
        return client.get(path,params,cache=False)
    try:
        entities=parse_entities(get('/entities',{'entity_ids':','.join(ids)}),insights=False,synthetic=client.synthetic)
        expected={e['entity_id']:e for e in next(iter(inputs.values()))['catalog']}
        if (len(entities)!=20 or {e.entity_id for e in entities}!=set(ids)
                or context_issues(entities,{'filter_type':'urn:entity:movie','filters':{}},set())
                or any(e.name!=expected[e.entity_id]['name'] or e.metadata.get('release_year')!=expected[e.entity_id]['release_year'] for e in entities)):
            raise SchemaError('Neighborhood catalog identity changed.')
        for key,value in inputs.items():
            seeds={};anchors={}
            for p in ('A','B'):
                name=value['artists'][p]
                seed={'name':name,'query':name,'search_type':'urn:entity:artist',
                      'accepted_names':[name],'accepted_types':['urn:entity:artist']}
                rows=parse_entities(get('/search',{'query':name,'types':'urn:entity:artist','take':5}),
                                    insights=False,synthetic=client.synthetic)
                seeds[p]=resolve_seed(seed,rows,synthetic=client.synthetic).entity_id
            if seeds['A']==seeds['B']:raise SchemaError('Artist lookup collapsed the declared mutation.')
            for p in ('A','B'):
                rows=parse_entities(get('/v2/insights',{'filter.type':'urn:entity:artist','bias.trends':'off','take':5,
                    'signal.interests.entities':seeds[p],'filter.exclude.entities':','.join(sorted(seeds.values()))}),
                    insights=True,synthetic=client.synthetic)
                if (len(rows)!=5 or context_issues(rows,{'filter_type':'urn:entity:artist','filters':{}},set(seeds.values()))
                        or any(e.affinity is None for e in rows)):
                    raise SchemaError('Related-artist anchors violate type, coverage or exclusions.')
                # Drop ranks/affinities: transfer an unordered set of related artists.
                anchors[p]=sorted(e.entity_id for e in rows)
                ledger.write(f'artist-anchors-{key}-{p}.json',sorted(
                    [{'entity_id':e.entity_id,'name':e.name} for e in rows],key=lambda e:e['entity_id']))
            graphs={'A':[],'B':[]}
            for repeat in range(3):
                for p in (('A','B') if repeat%2==0 else ('B','A')):
                    if set(anchors[p]) & set(seeds.values()):raise SchemaError('Original artist entered a movie query.')
                    if progress:progress(key,p,repeat+1,client.requests+1)
                    rows=parse_entities(get('/v2/insights',{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,
                        'signal.interests.entities':','.join(anchors[p]),'filter.results.entities':','.join(ids)}),
                        insights=True,synthetic=client.synthetic)
                    if (len(rows)!=20 or {e.entity_id for e in rows}!=set(ids)
                            or context_issues(rows,{'filter_type':'urn:entity:movie','filters':{}},set(seeds.values())|set(anchors[p]))
                            or any(e.affinity is None for e in rows)):
                        raise SchemaError('Neighborhood movie graph coverage or type failed.')
                    graphs[p].append([e.entity_id for e in rows])
                    ledger.record('neighborhood_decision',{'pair_id':key,'profile':p,'repeat':repeat+1,
                        'ranked_entity_ids':graphs[p][-1],'original_artist_in_movie_query':False})
            ranks={'baseline':value['baseline'],**{v:{'A':[],'B':[]} for v in ('neutral_graph','qloo_graph','swapped_graph')}}
            for repeat in range(3):
                for p in ('A','B'):
                    other='B' if p=='A' else 'A';base=ranks['baseline'][p][repeat]
                    own=graphs[p][repeat];opposite=graphs[other][repeat]
                    ranks['qloo_graph'][p].append(fuse_graph(base,own))
                    ranks['neutral_graph'][p].append(fuse_graph(base,own,opposite))
                    ranks['swapped_graph'][p].append(fuse_graph(base,opposite))
            row={'pair_id':key,'anchors':anchors,'graphs':graphs,'rankings':ranks}
            ledger.write('neighborhood-'+key+'.json',row);result['cases'].append(row)
        # Use the common evaluator contract only after independent decisions exist.
        result['status']='COMPLETE_GRAPH_CAPTURE'
    except AffinityQAError as exc:
        result['error']=str(exc);ledger.record('stopped',{'reason':str(exc)})
    result.update(real_qloo_requests=ledger.live_requests,transport_attempts=client.requests)
    ledger.write('neighborhood-capture.json',result)
    return result
