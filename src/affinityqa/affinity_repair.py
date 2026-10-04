"""Value-sensitive global fusion. No reference, artist identity or case rule."""
import math
from .errors import SchemaError


def normalize(values, power=1):
    if (not isinstance(values, dict) or len(values)!=20 or power not in (.5,1,2)
            or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in values.values())):
        raise SchemaError('Twenty finite affinity values in [0,1] are required.')
    lo=min(values.values());span=max(values.values())-lo
    return {i:((v-lo)/span)**power if span>1e-12 else 0.0 for i,v in values.items()}


def fuse(baseline,movie,artist,graph_weight,movie_weight,power,*,other_movie=None,other_artist=None):
    if (len(baseline)!=20 or len(set(baseline))!=20 or set(movie)!=set(baseline) or set(artist)!=set(baseline)
            or graph_weight not in (.25,.5,.75) or movie_weight not in (0,.5,1)
            or (other_movie is None)!=(other_artist is None)):
        raise SchemaError('Invalid complete affinity fusion inputs or undeclared policy.')
    m=normalize(movie,power);a=normalize(artist,power)
    if other_movie is not None:
        if set(other_movie)!=set(baseline) or set(other_artist)!=set(baseline):raise SchemaError('Pooled catalogs differ.')
        om=normalize(other_movie,power);oa=normalize(other_artist,power)
        m={i:(m[i]+om[i])/2 for i in baseline};a={i:(a[i]+oa[i])/2 for i in baseline}
    position={i:n for n,i in enumerate(baseline)}
    value={i:(1-graph_weight)*(1-position[i]/19)+graph_weight*(movie_weight*m[i]+(1-movie_weight)*a[i]) for i in baseline}
    return sorted(baseline,key=lambda i:(-value[i],position[i],i))


def build_capture(cases,policy,plan_hash):
    output={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for case in cases:
        ranks={'baseline':case['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for repeat in range(3):
            for p in ('A','B'):
                other='B' if p=='A' else 'A';b=case['baseline'][p][repeat]
                m=case['movie'][p][repeat];a=case['artist'][p][repeat]
                om=case['movie'][other][repeat];oa=case['artist'][other][repeat]
                ranks['qloo_graph'][p].append(fuse(b,m,a,**policy))
                ranks['neutral_graph'][p].append(fuse(b,m,a,**policy,other_movie=om,other_artist=oa))
                ranks['swapped_graph'][p].append(fuse(b,om,oa,**policy))
        output['cases'].append({'pair_id':case['pair_id'],'rankings':ranks})
    return output
