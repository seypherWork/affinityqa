"""Global numeric rank calibration; no entity identity or test references."""
import math
from .errors import SchemaError


def features(l,m,a,degree):
    if degree not in (1,2) or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=19 for x in (l,m,a)):
        raise SchemaError('Invalid ordinal features.')
    x,y,z=l/19,m/19,a/19
    row=[1,x,y,z,float(l==0),float(m==0),float(a==0),float(m<5 and a<5),float(l<5 and m<5),float(l<5 and a<5)]
    if degree==2:row += [x*x,y*y,z*z,x*y,x*z,y*z]
    return row


def fit(rows,regularization):
    if regularization not in (.01,.1,1,10) or not rows:raise SchemaError('Undeclared calibration regularization.')
    n=len(rows[0][0]);matrix=[[0.0]*(n+1) for _ in range(n)]
    for x,y,w in rows:
        if len(x)!=n or not all(math.isfinite(v) for v in (*x,y,w)) or w<=0:raise SchemaError('Invalid calibration training row.')
        for i in range(n):
            matrix[i][n]+=w*x[i]*y
            for j in range(n):matrix[i][j]+=w*x[i]*x[j]
    for i in range(1,n):matrix[i][i]+=regularization
    for c in range(n):
        pivot=max(range(c,n),key=lambda r:abs(matrix[r][c]));matrix[c],matrix[pivot]=matrix[pivot],matrix[c]
        if abs(matrix[c][c])<1e-12:raise SchemaError('Singular calibration system; no invented model.')
        denom=matrix[c][c];matrix[c]=[v/denom for v in matrix[c]]
        for r in range(n):
            if r==c:continue
            scale=matrix[r][c];matrix[r]=[v-scale*q for v,q in zip(matrix[r],matrix[c],strict=True)]
    result=[r[-1] for r in matrix]
    if not all(math.isfinite(v) for v in result):raise SchemaError('Nonfinite learned model.')
    return result


def calibrated_fuse(baseline,movie_graph,artist_graph,model,*,other_movie=None,other_artist=None):
    ids=set(baseline)
    if (len(baseline)!=20 or len(ids)!=20 or any(len(r)!=20 or set(r)!=ids for r in (movie_graph,artist_graph))
            or set(model)!={'degree','coefficients'} or model['degree'] not in (1,2)
            or (other_movie is None)!=(other_artist is None)
            or (other_movie is not None and any(len(r)!=20 or set(r)!=ids for r in (other_movie,other_artist)))):
        raise SchemaError('Invalid calibration model or complete ranking inputs.')
    local={i:n for n,i in enumerate(baseline)};m={i:n for n,i in enumerate(movie_graph)};a={i:n for n,i in enumerate(artist_graph)}
    if other_movie is not None:
        om={i:n for n,i in enumerate(other_movie)};oa={i:n for n,i in enumerate(other_artist)}
        m={i:(m[i]+om[i])/2 for i in baseline};a={i:(a[i]+oa[i])/2 for i in baseline}
    coeff=model['coefficients']
    if (len(coeff)!=len(features(0,0,0,model['degree']))
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in coeff)):
        raise SchemaError('Malformed global calibration coefficients.')
    scores={i:sum(w*x for w,x in zip(coeff,features(local[i],m[i],a[i],model['degree']),strict=True)) for i in baseline}
    return sorted(baseline,key=lambda i:(-scores[i],local[i],i))


def calibrated_capture(movie_source,artist_source,model,plan_sha256):
    if ([c['pair_id'] for c in movie_source['cases']]!=[c['pair_id'] for c in artist_source['cases']]
            or movie_source['status']!='COMPLETE_GRAPH_CAPTURE' or artist_source['status']!='COMPLETE_GRAPH_CAPTURE'):
        raise SchemaError('Complete matching graph sources are required.')
    result={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_sha256,'real_qloo_requests':0,'cases':[]}
    for movie,artist in zip(movie_source['cases'],artist_source['cases'],strict=True):
        if movie['rankings']['baseline']!=artist['rankings']['baseline']:raise SchemaError('Different baselines in calibrated sources.')
        ranks={'baseline':movie['rankings']['baseline'],**{v:{'A':[],'B':[]} for v in ('neutral_graph','qloo_graph','swapped_graph')}}
        for repeat in range(3):
            for p in ('A','B'):
                other='B' if p=='A' else 'A';base=ranks['baseline'][p][repeat]
                mg=movie['graphs'][p][repeat];ag=artist['graphs'][p][repeat];om=movie['graphs'][other][repeat];oa=artist['graphs'][other][repeat]
                ranks['qloo_graph'][p].append(calibrated_fuse(base,mg,ag,model))
                ranks['neutral_graph'][p].append(calibrated_fuse(base,mg,ag,model,other_movie=om,other_artist=oa))
                ranks['swapped_graph'][p].append(calibrated_fuse(base,om,oa,model))
        result['cases'].append({'pair_id':movie['pair_id'],'rankings':ranks})
    return result
