"""Deterministic source-disagreement penalty, not a statistical confidence bound."""
import math
from .affinity_repair import normalize
from .individual_context import signal as validate_signal,rank
from .errors import SchemaError

def signal(movie,neighbors,penalty):
    if type(penalty) not in (int,float) or penalty not in (0,.25,.5,1):raise SchemaError('Undeclared disagreement penalty.')
    mean=validate_signal(movie,neighbors,'mean',.5)
    available=[normalize(e['values']) for e in neighbors if e['values'] is not None]
    if len(available)<2:return mean
    m=normalize(movie)
    return {i:max(0.0,mean[i]-penalty*math.sqrt(.5*(m[i]-mean[i])**2+.5*sum((a[i]-mean[i])**2 for a in available)/len(available))) for i in mean}

def capture(cases,policy,plan_hash):
    if set(policy)!={'graph_weight','penalty'}:raise SchemaError('Unexpected disagreement policy fields.')
    output={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for c in cases:
        ranks={'baseline':c['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for r in range(3):
            signals={p:signal(c['movie'][p][r],c['individual'][p],policy['penalty']) for p in ('A','B')}
            for p in ('A','B'):
                q='B' if p=='A' else 'A';b=c['baseline'][p][r];s=signals[p];other=signals[q];w=policy['graph_weight']
                ranks['qloo_graph'][p].append(rank(b,s,w))
                ranks['neutral_graph'][p].append(rank(b,s,w,pooled=other))
                ranks['swapped_graph'][p].append(rank(b,other,w))
        output['cases'].append({'pair_id':c['pair_id'],'rankings':ranks})
    return output
