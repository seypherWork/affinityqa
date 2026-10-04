"""Numeric two-view fusion, without entity identity features or reference inputs."""
from .affinity_repair import normalize
from .errors import SchemaError

def fuse(baseline,movie,artist,graph_weight,movie_weight,power,*,other_movie=None,other_artist=None):
    if (len(baseline)!=20 or len(set(baseline))!=20 or set(movie)!=set(baseline) or set(artist)!=set(baseline)
        or type(graph_weight) not in (int,float) or graph_weight not in (.25,.5,.75)
        or type(movie_weight) not in (int,float) or movie_weight not in (.25,.5,.75,1)
        or type(power) not in (int,float) or power not in (.75,.875,1)
        or (other_movie is None)!=(other_artist is None)):
        raise SchemaError('Invalid complete two-view inputs or undeclared policy.')
    transform=lambda v:{i:x**power for i,x in normalize(v).items()}
    m=transform(movie);a=transform(artist)
    if other_movie is not None:
        if set(other_movie)!=set(baseline) or set(other_artist)!=set(baseline):raise SchemaError('Pooled view catalogs differ.')
        om=transform(other_movie);oa=transform(other_artist)
        m={i:(m[i]+om[i])/2 for i in baseline};a={i:(a[i]+oa[i])/2 for i in baseline}
    position={i:n for n,i in enumerate(baseline)}
    utility={i:(1-graph_weight)*(1-position[i]/19)+graph_weight*(movie_weight*m[i]+(1-movie_weight)*a[i]) for i in baseline}
    return sorted(baseline,key=lambda i:(-utility[i],position[i],i))

def capture(cases,policy,plan_hash):
    result={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for case in cases:
        ranks={'baseline':case['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for r in range(3):
            for p in ('A','B'):
                q='B' if p=='A' else 'A';b=case['baseline'][p][r];m=case['movie'][p][r];a=case['artist'][p][r];om=case['movie'][q][r];oa=case['artist'][q][r]
                ranks['qloo_graph'][p].append(fuse(b,m,a,**policy))
                ranks['neutral_graph'][p].append(fuse(b,m,a,**policy,other_movie=om,other_artist=oa))
                ranks['swapped_graph'][p].append(fuse(b,om,oa,**policy))
        result['cases'].append({'pair_id':case['pair_id'],'rankings':ranks})
    return result
