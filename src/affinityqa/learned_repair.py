"""Small supervised rank calibrator; runtime accepts numeric context, never references.

Training uses exposed reference labels. Pair-centred ridge regression has seven
fixed features and no artist, case or movie identity coefficients.
"""
import math
from .affinity_repair import normalize
from .individual_context import signal as validate_context
from .errors import SchemaError

FEATURES=('baseline_ordinal','movie_affinity','movie_ordinal','artist_mean','artist_ordinal','artist_dispersion','view_disagreement')

def ordinal(values):
    result={};ordered=sorted(values.values())
    for identity,value in values.items():
        positions=[n for n,v in enumerate(ordered) if v==value]
        result[identity]=sum(positions)/len(positions)/19
    return result

def context(movie,neighbors):
    validate_context(movie,neighbors,'mean',.5)
    m=normalize(movie);available=[normalize(n['values']) for n in neighbors if n['values'] is not None]
    if len(available)<2:available=[m]
    a={i:sum(v[i] for v in available)/len(available) for i in m};mr=ordinal(m);ar=ordinal(a)
    return {i:[m[i],mr[i],a[i],ar[i],math.sqrt(sum((v[i]-a[i])**2 for v in available)/len(available)),abs(m[i]-a[i])] for i in m}

def features(baseline,ctx,pooled=None):
    if len(baseline)!=20 or len(set(baseline))!=20 or set(ctx)!=set(baseline):raise SchemaError('Complete feature catalog required.')
    for data in (ctx,) if pooled is None else (ctx,pooled):
        if set(data)!=set(baseline) or any(len(v)!=6 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in v) for v in data.values()):raise SchemaError('Invalid numeric context features.')
    return {i:[1-n/19,*[ctx[i][j] if pooled is None else (ctx[i][j]+pooled[i][j])/2 for j in range(6)]] for n,i in enumerate(baseline)}

def fit(samples,regularization):
    """Fit numeric rows grouped by profile; every profile receives equal weight."""
    if type(regularization) not in (int,float) or regularization not in (.001,.01,.1) or not samples:raise SchemaError('Undeclared ridge regularization or no samples.')
    width=len(FEATURES);matrix=[[0.0]*width for _ in range(width)];rhs=[0.0]*width
    for rows,target in samples:
        if len(rows)!=20 or len(target)!=20 or any(len(x)!=width for x in rows):raise SchemaError('Malformed training profile.')
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for row in rows for v in row) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in target):raise SchemaError('Invalid training values.')
        means=[sum(row[j] for row in rows)/20 for j in range(width)];target_mean=sum(target)/20
        for row,y in zip(rows,target,strict=True):
            x=[v-m for v,m in zip(row,means,strict=True)];weight=1/(len(samples)*20)
            for j in range(width):
                rhs[j]+=weight*x[j]*(y-target_mean)
                for k in range(width):matrix[j][k]+=weight*x[j]*x[k]
    for j in range(width):matrix[j][j]+=regularization
    augmented=[[*row,value] for row,value in zip(matrix,rhs,strict=True)]
    for column in range(width):
        pivot=max(range(column,width),key=lambda r:abs(augmented[r][column]));augmented[column],augmented[pivot]=augmented[pivot],augmented[column]
        scale=augmented[column][column]
        if abs(scale)<1e-14:raise SchemaError('Ill-conditioned ridge system.')
        augmented[column]=[v/scale for v in augmented[column]]
        for r in range(width):
            if r==column:continue
            factor=augmented[r][column];augmented[r]=[a-factor*b for a,b in zip(augmented[r],augmented[column],strict=True)]
    coefficients=[augmented[j][-1] for j in range(width)]
    residual=max(abs(sum(matrix[j][k]*coefficients[k] for k in range(width))-rhs[j]) for j in range(width))
    if residual>1e-10 or any(not math.isfinite(v) for v in coefficients):raise SchemaError('Ridge solution residual is too large.')
    return coefficients

def rank(baseline,ctx,coefficients,pooled=None):
    if len(coefficients)!=len(FEATURES) or any(type(v) not in (int,float) or not math.isfinite(v) for v in coefficients):raise SchemaError('Invalid fitted coefficients.')
    x=features(baseline,ctx,pooled);position={i:n for n,i in enumerate(baseline)}
    scores={i:sum(a*b for a,b in zip(row,coefficients,strict=True)) for i,row in x.items()}
    return sorted(baseline,key=lambda i:(-scores[i],position[i]))

def capture(cases,coefficients,plan_hash):
    output={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for c in cases:
        ranks={'baseline':c['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for r in range(3):
            contexts={p:context(c['movie'][p][r],c['individual'][p]) for p in ('A','B')}
            for p in ('A','B'):
                q='B' if p=='A' else 'A';b=c['baseline'][p][r];s=contexts[p];other=contexts[q]
                ranks['qloo_graph'][p].append(rank(b,s,coefficients))
                ranks['neutral_graph'][p].append(rank(b,s,coefficients,other))
                ranks['swapped_graph'][p].append(rank(b,other,coefficients))
        output['cases'].append({'pair_id':c['pair_id'],'rankings':ranks})
    return output
