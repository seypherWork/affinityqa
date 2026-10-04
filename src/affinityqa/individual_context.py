"""Indirect identity-clean signals. Evaluator references never enter this module."""
import math
from statistics import median
from .affinity_repair import normalize
from .errors import SchemaError

def signal(movie,neighbors,aggregation,movie_weight):
    if aggregation not in ('mean','weighted','median') or type(movie_weight) not in (int,float) or movie_weight not in (0,.5,1):
        raise SchemaError('Undeclared individual-context policy.')
    m=normalize(movie);available=[];seen=set()
    if len(neighbors)!=3:raise SchemaError('Three selected context identities are mandatory, including unavailable ones.')
    for item in neighbors:
        identity=item['entity_id'];weight=item['affinity'];values=item['values']
        if identity in seen or type(weight) not in (int,float) or not math.isfinite(weight) or not 0<=weight<=1:raise SchemaError('Invalid context identity or selection weight.')
        seen.add(identity)
        if values is None:continue
        if set(values)!=set(m):raise SchemaError('Individual context catalog changed.')
        available.append((normalize(values),weight))
    # Missing coverage is not zero evidence. This fallback is identical in controls.
    if len(available)<2 or movie_weight==1:return m
    total=sum(w for _,w in available)
    if aggregation=='weighted' and total<=0:raise SchemaError('No positive neighbor weight.')
    a={i:(median(v[i] for v,_ in available) if aggregation=='median' else
          sum(v[i]*w for v,w in available)/total if aggregation=='weighted' else
          sum(v[i] for v,_ in available)/len(available)) for i in m}
    return {i:movie_weight*m[i]+(1-movie_weight)*a[i] for i in m}

def rank(baseline,values,graph_weight,*,pooled=None):
    if (len(baseline)!=20 or len(set(baseline))!=20 or set(values)!=set(baseline)
        or type(graph_weight) not in (int,float) or graph_weight not in (.25,.5,.75,1)):
        raise SchemaError('Invalid complete ranking or undeclared weight.')
    for view in (values,) if pooled is None else (values,pooled):
        if set(view)!=set(baseline) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in view.values()):raise SchemaError('Invalid complete context signal.')
    s=values if pooled is None else {i:(values[i]+pooled[i])/2 for i in baseline}
    position={i:n for n,i in enumerate(baseline)}
    utility={i:(1-graph_weight)*(1-position[i]/19)+graph_weight*s[i] for i in baseline}
    return sorted(baseline,key=lambda i:(-utility[i],position[i],i))

def capture(cases,policy,plan_hash):
    result={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for c in cases:
        ranks={'baseline':c['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for r in range(3):
            signals={p:signal(c['movie'][p][r],c['individual'][p],policy['aggregation'],policy['movie_weight']) for p in ('A','B')}
            for p in ('A','B'):
                q='B' if p=='A' else 'A';b=c['baseline'][p][r];s=signals[p];other=signals[q];w=policy['graph_weight']
                ranks['qloo_graph'][p].append(rank(b,s,w))
                ranks['neutral_graph'][p].append(rank(b,s,w,pooled=other))
                ranks['swapped_graph'][p].append(rank(b,other,w))
        result['cases'].append({'pair_id':c['pair_id'],'rankings':ranks})
    return result
