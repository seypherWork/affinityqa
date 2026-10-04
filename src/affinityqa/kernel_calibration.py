"""Smooth global calibration on numeric positions; no identity lookup table."""
from itertools import product
import math
from .errors import SchemaError
from .ordinal_calibration import fit

CENTERS=tuple(product((0,.25,.5,.75,1),repeat=3))


def kernel_features(l,m,a,width):
    if width not in (.2,.35,.5) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=19 for v in (l,m,a)):
        raise SchemaError('Invalid fixed kernel positions or width.')
    x,y,z=l/19,m/19,a/19
    return [1,x,y,z]+[math.exp(-((x-u)**2+(y-v)**2+(z-w)**2)/(2*width*width)) for u,v,w in CENTERS]


def kernel_fuse(baseline,movie_graph,artist_graph,model,*,other_movie=None,other_artist=None):
    ids=set(baseline)
    if (len(baseline)!=20 or len(ids)!=20 or any(len(r)!=20 or set(r)!=ids for r in (movie_graph,artist_graph))
            or set(model)!={'width','coefficients'} or model['width'] not in (.2,.35,.5)
            or (other_movie is None)!=(other_artist is None)
            or (other_movie is not None and any(len(r)!=20 or set(r)!=ids for r in (other_movie,other_artist)))):
        raise SchemaError('Invalid kernel model or complete ranking inputs.')
    local={i:n for n,i in enumerate(baseline)};m={i:n for n,i in enumerate(movie_graph)};a={i:n for n,i in enumerate(artist_graph)}
    if other_movie is not None:
        om={i:n for n,i in enumerate(other_movie)};oa={i:n for n,i in enumerate(other_artist)}
        m={i:(m[i]+om[i])/2 for i in baseline};a={i:(a[i]+oa[i])/2 for i in baseline}
    coeff=model['coefficients']
    if len(coeff)!=129 or any(type(v) not in (int,float) or not math.isfinite(v) for v in coeff):raise SchemaError('Malformed global kernel coefficients.')
    scores={i:sum(w*x for w,x in zip(coeff,kernel_features(local[i],m[i],a[i],model['width']),strict=True)) for i in baseline}
    return sorted(baseline,key=lambda i:(-scores[i],local[i],i))


def kernel_capture(movie_source,artist_source,model,plan_sha256):
    if ([c['pair_id'] for c in movie_source['cases']]!=[c['pair_id'] for c in artist_source['cases']]
            or movie_source['status']!='COMPLETE_GRAPH_CAPTURE' or artist_source['status']!='COMPLETE_GRAPH_CAPTURE'):
        raise SchemaError('Complete matching kernel graph sources are required.')
    result={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_sha256,'real_qloo_requests':0,'cases':[]}
    for movie,artist in zip(movie_source['cases'],artist_source['cases'],strict=True):
        if movie['rankings']['baseline']!=artist['rankings']['baseline']:raise SchemaError('Different kernel baselines.')
        ranks={'baseline':movie['rankings']['baseline'],**{v:{'A':[],'B':[]} for v in ('neutral_graph','qloo_graph','swapped_graph')}}
        for repeat in range(3):
            for p in ('A','B'):
                other='B' if p=='A' else 'A';base=ranks['baseline'][p][repeat]
                mg=movie['graphs'][p][repeat];ag=artist['graphs'][p][repeat];om=movie['graphs'][other][repeat];oa=artist['graphs'][other][repeat]
                ranks['qloo_graph'][p].append(kernel_fuse(base,mg,ag,model))
                ranks['neutral_graph'][p].append(kernel_fuse(base,mg,ag,model,other_movie=om,other_artist=oa))
                ranks['swapped_graph'][p].append(kernel_fuse(base,om,oa,model))
        result['cases'].append({'pair_id':movie['pair_id'],'rankings':ranks})
    return result
