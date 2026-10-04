"""Select twenty typed external movie identities without catalog alias overlap."""
import math
from .identity_context import names
from .errors import SchemaError

def select_movies(rows,catalog):
    if len(catalog)!=20 or len({e.entity_id for e in catalog})!=20:raise SchemaError('Complete movie catalog identities required.')
    denied_ids={e.entity_id for e in catalog};denied_names=set().union(*(names(e) for e in catalog));groups=[];audit=[]
    for e in rows:
        if 'urn:entity:movie' not in e.types or type(e.affinity) not in (int,float) or not math.isfinite(e.affinity) or not 0<=e.affinity<=1:raise SchemaError('Invalid external movie category or affinity.')
        tokens=names(e)
        matching=[g for g in groups if g['names']&tokens or any(v.entity_id==e.entity_id for v in g['entities'])]
        group={'names':set(tokens),'entities':[e]}
        for g in matching:group['names']|=g['names'];group['entities']+=g['entities'];groups.remove(g)
        groups.append(group)
    eligible=[]
    for g in groups:
        if g['names']&denied_names or any(e.entity_id in denied_ids for e in g['entities']):
            audit.extend({'entity_id':e.entity_id,'name':e.name,'reason':'catalog_identity_overlap'} for e in g['entities']);continue
        valid=[]
        for e in g['entities']:
            if type(e.metadata.get('release_year'))!=int:
                audit.append({'entity_id':e.entity_id,'name':e.name,'reason':'missing_release_year'})
            else:valid.append(e)
        if not valid:continue
        valid.sort(key=lambda e:(-e.affinity,e.entity_id));eligible.append(valid[0])
        audit.extend({'entity_id':e.entity_id,'name':e.name,'reason':'duplicate_movie_identity','kept_entity_id':valid[0].entity_id} for e in valid[1:])
    selected=sorted(eligible,key=lambda e:(-e.affinity,e.entity_id))[:20]
    if len(selected)!=20:raise SchemaError('Fewer than twenty distinct disjoint movie identities after review.')
    return selected,audit
