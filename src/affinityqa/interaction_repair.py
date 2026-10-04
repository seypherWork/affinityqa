"""Quadratic numeric calibration. No identity features or evaluator runtime inputs."""
import math
from .errors import SchemaError
from .learned_repair import FEATURES as BASE_FEATURES, context, features as base_features

TERMS=tuple((i,j) for i in range(7) for j in range(i,7))
FEATURES=(*BASE_FEATURES,*(f'{BASE_FEATURES[i]}*{BASE_FEATURES[j]}' for i,j in TERMS))


def expand(row):
    if len(row)!=7 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in row):
        raise SchemaError('Seven finite bounded base features required.')
    return [*row,*(row[i]*row[j] for i,j in TERMS)]


def fit(samples,regularization):
    if type(regularization) not in (int,float) or regularization not in (.001,.01,.1) or not samples:
        raise SchemaError('Undeclared interaction regularization or empty samples.')
    width=len(FEATURES);matrix=[[0.0]*width for _ in range(width)];rhs=[0.0]*width
    for rows,target in samples:
        if len(rows)!=20 or len(target)!=20:raise SchemaError('Twenty rows required per training profile.')
        expanded=[expand(row) for row in rows]
        if any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1 for v in target):raise SchemaError('Invalid training target.')
        center=[sum(x[j] for x in expanded)/20 for j in range(width)];ym=sum(target)/20
        for row,y in zip(expanded,target,strict=True):
            x=[v-m for v,m in zip(row,center,strict=True)];weight=1/(20*len(samples))
            for j in range(width):
                rhs[j]+=weight*x[j]*(y-ym)
                for k in range(width):matrix[j][k]+=weight*x[j]*x[k]
    for j in range(width):matrix[j][j]+=regularization
    augmented=[[*row,value] for row,value in zip(matrix,rhs,strict=True)]
    for column in range(width):
        pivot=max(range(column,width),key=lambda r:abs(augmented[r][column]));augmented[column],augmented[pivot]=augmented[pivot],augmented[column]
        scale=augmented[column][column]
        if abs(scale)<1e-14:raise SchemaError('Ill-conditioned interaction solve.')
        augmented[column]=[v/scale for v in augmented[column]]
        for r in range(width):
            if r==column:continue
            factor=augmented[r][column];augmented[r]=[a-factor*b for a,b in zip(augmented[r],augmented[column],strict=True)]
    beta=[augmented[j][-1] for j in range(width)]
    if any(not math.isfinite(v) for v in beta) or max(abs(sum(matrix[j][k]*beta[k] for k in range(width))-rhs[j]) for j in range(width))>1e-10:
        raise SchemaError('Interaction solution failed residual check.')
    return beta


def rank(baseline,ctx,coefficients,pooled=None):
    if len(coefficients)!=len(FEATURES) or any(type(v) not in (int,float) or not math.isfinite(v) for v in coefficients):raise SchemaError('Invalid interaction coefficients.')
    # Pool the raw numeric context before expansion. Same operator in every arm.
    rows=base_features(baseline,ctx,pooled);position={i:n for n,i in enumerate(baseline)}
    scores={i:sum(a*b for a,b in zip(expand(row),coefficients,strict=True)) for i,row in rows.items()}
    return sorted(baseline,key=lambda i:(-scores[i],position[i]))


def capture(cases,coefficients,plan_hash):
    result={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for c in cases:
        ranks={'baseline':c['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for r in range(3):
            contexts={p:context(c['movie'][p][r],c['individual'][p]) for p in ('A','B')}
            for p in ('A','B'):
                b=c['baseline'][p][r];a=contexts[p];other=contexts['B' if p=='A' else 'A']
                ranks['qloo_graph'][p].append(rank(b,a,coefficients))
                ranks['neutral_graph'][p].append(rank(b,a,coefficients,other))
                ranks['swapped_graph'][p].append(rank(b,other,coefficients))
        result['cases'].append({'pair_id':c['pair_id'],'rankings':ranks})
    return result
