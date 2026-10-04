"""Two-view shortlist plus separately weighted ordering; no case-specific features."""
from .multiview_value import fuse
from .affinity_repair import normalize
from .errors import SchemaError

def rank(baseline,movie,artist,policy,*,other_movie=None,other_artist=None):
    parameters={k:policy[k] for k in ('graph_weight','movie_weight','power')}
    weight=policy['order_weight']
    if type(weight) not in (int,float) or weight not in (.125,.25,.375,.5,.625,.75):raise SchemaError('Undeclared two-stage ordering weight.')
    selected=fuse(baseline,movie,artist,**parameters,other_movie=other_movie,other_artist=other_artist)
    def signal(m,a):
        nm=normalize(m);na=normalize(a);w=policy['movie_weight'];power=policy['power']
        return {i:w*nm[i]**power+(1-w)*na[i]**power for i in baseline}
    values=signal(movie,artist)
    if other_movie is not None:
        opposite=signal(other_movie,other_artist);values={i:(values[i]+opposite[i])/2 for i in baseline}
    positions={i:n for n,i in enumerate(baseline)}
    return sorted(selected[:5],key=lambda i:(-((1-weight)*(1-positions[i]/19)+weight*values[i]),positions[i],i))+selected[5:]

def capture(cases,policy,plan_hash):
    output={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for case in cases:
        ranks={'baseline':case['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for r in range(3):
            for p in ('A','B'):
                q='B' if p=='A' else 'A';b=case['baseline'][p][r];m=case['movie'][p][r];a=case['artist'][p][r];om=case['movie'][q][r];oa=case['artist'][q][r]
                ranks['qloo_graph'][p].append(rank(b,m,a,policy))
                ranks['neutral_graph'][p].append(rank(b,m,a,policy,other_movie=om,other_artist=oa))
                ranks['swapped_graph'][p].append(rank(b,om,oa,policy))
        output['cases'].append({'pair_id':case['pair_id'],'rankings':ranks})
    return output
