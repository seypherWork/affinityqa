"""Reviewable identity exclusion and deduplication for indirect artist context."""
import math
from .errors import SchemaError
from .models import normalized_name

def names(entity):
    result={normalized_name(entity.name)}
    aliases=entity.metadata.get('aliases') or []
    if not isinstance(aliases,list) or any(not isinstance(v,str) for v in aliases):raise SchemaError('Unreviewed artist alias schema.')
    result.update(normalized_name(v) for v in aliases if v.strip())
    akas=entity.metadata.get('akas') or []
    if not isinstance(akas,list) or any(not isinstance(v,dict) or not isinstance(v.get('value'),str) for v in akas):raise SchemaError('Unreviewed alternate-name schema.')
    result.update(normalized_name(v['value']) for v in akas if isinstance(v,dict) and isinstance(v.get('value'),str) and v['value'].strip())
    return result

def select_context(entities,excluded_ids,excluded_names,count=3):
    if count!=3 or len(entities)<3:raise SchemaError('Three distinct related artists are required.')
    denied={normalized_name(n) for n in excluded_names};blocked=[];eligible=[]
    for e in entities:
        identities=names(e)
        if type(e.affinity) not in (int,float) or not math.isfinite(e.affinity) or not 0<=e.affinity<=1:raise SchemaError('Invalid context selection affinity.')
        eligible.append((e,identities))
    # Connected components make deduplication independent of response order.
    groups=[]
    for e,tokens in eligible:
        matches=[g for g in groups if g['names']&tokens or any(v.entity_id==e.entity_id for v in g['entities'])]
        group={'names':set(tokens),'entities':[e]}
        for g in matches:group['names']|=g['names'];group['entities']+=g['entities'];groups.remove(g)
        groups.append(group)
    candidates=[]
    for group in groups:
        if group['names']&denied or any(e.entity_id in excluded_ids for e in group['entities']):
            blocked.extend({'entity_id':e.entity_id,'name':e.name,'reason':'original_profile_identity','matched_names':sorted(group['names']&denied)} for e in group['entities'])
            continue
        ordered=sorted(group['entities'],key=lambda e:(-e.affinity,e.entity_id));candidates.append(ordered[0])
        blocked.extend({'entity_id':e.entity_id,'name':e.name,'reason':'duplicate_alias_identity','kept_entity_id':ordered[0].entity_id} for e in ordered[1:])
    chosen=sorted(candidates,key=lambda e:(-e.affinity,e.entity_id))[:count]
    if len(chosen)!=count:raise SchemaError('Fewer than three independent non-profile artists remain after identity review.')
    return chosen,blocked
