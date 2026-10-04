"""Separate shortlist selection from ordering; identical intervention in controls."""
from .affinity_repair import normalize
from .affinity_refinement import refined_fuse
from .errors import SchemaError

WEIGHTS=tuple(i/8 for i in range(9))

def order_head(baseline,movie,weight,scale,*,other=None):
    if type(weight) not in (int,float) or weight not in WEIGHTS or scale not in ('catalog','shortlist'):
        raise SchemaError('Undeclared head-order policy.')
    selected=refined_fuse(baseline,movie,movie,.875,other_movie=other,other_artist=other)
    values={i:v**.875 for i,v in normalize(movie).items()}
    if other is not None:
        opposite={i:v**.875 for i,v in normalize(other).items()}
        values={i:(values[i]+opposite[i])/2 for i in baseline}
    positions={i:n for n,i in enumerate(baseline)};head=selected[:5]
    if scale=='catalog':local={i:1-positions[i]/19 for i in head}
    else:
        lo=min(values[i] for i in head);span=max(values[i] for i in head)-lo
        values={i:(values[i]-lo)/span if span>1e-12 else 0.0 for i in head}
        local={i:1-n/4 for n,i in enumerate(sorted(head,key=positions.get))}
    return sorted(head,key=lambda i:(-((1-weight)*local[i]+weight*values[i]),positions[i],i))+selected[5:]

def capture(cases,policy,plan_hash):
    output={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for case in cases:
        ranks={'baseline':case['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for r in range(3):
            for p in ('A','B'):
                other='B' if p=='A' else 'A';b=case['baseline'][p][r];m=case['movie'][p][r];om=case['movie'][other][r]
                ranks['qloo_graph'][p].append(order_head(b,m,**policy))
                ranks['neutral_graph'][p].append(order_head(b,m,**policy,other=om))
                ranks['swapped_graph'][p].append(order_head(b,om,**policy))
        output['cases'].append({'pair_id':case['pair_id'],'rankings':ranks})
    return output
