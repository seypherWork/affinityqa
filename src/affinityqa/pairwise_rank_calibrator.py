"""Fixed top-five delta-NDCG weighted convex logistic rank calibration.

Training only: eight numeric features and exact twenty-item ordinal targets.
Pair weights use reference ranks, not changing predicted ranks. This is a
convex surrogate, not an assertion that optimizing it improves measured NDCG.
"""
import math
from .errors import SchemaError

WIDTH=8
REGULARIZATION=.001
MAX_ITERATIONS=50
GRADIENT_TOLERANCE=1e-8


def _number(value):
    return type(value) in (int,float) and math.isfinite(value)


def logistic_terms(margin):
    """Loss, sigmoid(-margin), curvature; stable for either finite extreme."""
    if not _number(margin):raise SchemaError('Finite logistic margin required.')
    if margin>=0:
        z=math.exp(-margin);prob=z/(1+z)
        return math.log1p(z),prob,z/(1+z)**2
    z=math.exp(margin);prob=1/(1+z)
    return -margin+math.log1p(z),prob,z/(1+z)**2


def training_pairs(samples):
    """85 preferred pairs per profile; normalized within profile then globally."""
    if not isinstance(samples,list) or not samples:raise SchemaError('Nonempty profile samples required.')
    expected={1-r/19:r for r in range(20)};pairs=[]
    discounts=[1/math.log2(r+2) if r<5 else 0. for r in range(20)]
    ideal=sum((20-r)*discounts[r] for r in range(5))
    for sample in samples:
        if not isinstance(sample,(tuple,list)) or len(sample)!=2:raise SchemaError('Numeric feature rows and targets required.')
        rows,target=sample
        if not isinstance(rows,list) or not isinstance(target,list) or len(rows)!=20 or len(target)!=20 or any(not isinstance(row,list) or len(row)!=WIDTH for row in rows):raise SchemaError('Twenty eight-feature rows per profile required.')
        if any(not _number(v) or not 0<=v<=1 for row in rows for v in row) or any(not _number(v) for v in target) or set(target)!=set(expected):raise SchemaError('Features must be unit-range and targets the exact twenty ordinal values.')
        ranks=[expected[v] for v in target];ordered=sorted(range(20),key=lambda i:ranks[i]);local=[]
        for better in range(5):
            for worse in range(better+1,20):
                i,j=ordered[better],ordered[worse]
                weight=(worse-better)*(discounts[better]-discounts[worse])/ideal
                local.append(([a-b for a,b in zip(rows[i],rows[j])],weight))
        total=sum(weight for _,weight in local)
        if len(local)!=85 or total<=0:raise SchemaError('Invalid top-five pair construction.')
        pairs.extend((delta,weight/total/len(samples)) for delta,weight in local)
    return pairs


def objective_derivatives(coefficients,pairs,regularization=REGULARIZATION):
    if type(regularization) not in (int,float) or regularization!=REGULARIZATION:raise SchemaError('Only the fixed .001 penalty is supported.')
    if not isinstance(coefficients,(tuple,list)) or len(coefficients)!=WIDTH or any(not _number(v) for v in coefficients):raise SchemaError('Eight finite coefficients required.')
    if not isinstance(pairs,list) or not pairs:raise SchemaError('Training pairs required.')
    value=.5*regularization*sum(v*v for v in coefficients)
    gradient=[regularization*v for v in coefficients];hessian=[[regularization if i==j else 0. for j in range(WIDTH)] for i in range(WIDTH)]
    for pair in pairs:
        if not isinstance(pair,(tuple,list)) or len(pair)!=2:raise SchemaError('Invalid pair record.')
        delta,weight=pair
        if not isinstance(delta,list) or len(delta)!=WIDTH or any(not _number(v) or not -1<=v<=1 for v in delta) or not _number(weight) or not 0<weight<=1:raise SchemaError('Invalid pair delta or weight.')
        loss,prob,curvature=logistic_terms(sum(v*x for v,x in zip(coefficients,delta)));value+=weight*loss
        for i in range(WIDTH):
            gradient[i]-=weight*prob*delta[i]
            for j in range(WIDTH):hessian[i][j]+=weight*curvature*delta[i]*delta[j]
    if not math.isfinite(value) or any(not math.isfinite(v) for v in gradient) or any(not math.isfinite(v) for row in hessian for v in row):raise SchemaError('Nonfinite objective arithmetic.')
    return value,gradient,hessian


def _cholesky_solve(matrix,rhs):
    lower=[[0.]*WIDTH for _ in range(WIDTH)]
    for i in range(WIDTH):
        for j in range(i+1):
            value=matrix[i][j]-sum(lower[i][k]*lower[j][k] for k in range(j))
            if i==j:
                if not math.isfinite(value) or value<=0:raise SchemaError('Hessian is not positive definite.')
                lower[i][j]=math.sqrt(value)
            else:lower[i][j]=value/lower[j][j]
    y=[]
    for i in range(WIDTH):y.append((rhs[i]-sum(lower[i][j]*y[j] for j in range(i)))/lower[i][i])
    result=[0.]*WIDTH
    for i in reversed(range(WIDTH)):result[i]=(y[i]-sum(lower[j][i]*result[j] for j in range(i+1,WIDTH)))/lower[i][i]
    if any(not math.isfinite(v) for v in result):raise SchemaError('Nonfinite Newton step.')
    return result


def fit(samples,regularization=REGULARIZATION):
    if type(regularization) not in (int,float) or regularization!=REGULARIZATION:raise SchemaError('Only the frozen .001 penalty is permitted.')
    pairs=training_pairs(samples);coefficients=[0.]*WIDTH
    for iteration in range(MAX_ITERATIONS+1):
        value,gradient,hessian=objective_derivatives(coefficients,pairs,regularization)
        norm=max(abs(v) for v in gradient)
        if norm<=GRADIENT_TOLERANCE:return {'coefficients':coefficients,'iterations':iteration,'converged':True,'objective':value,'gradient_inf_norm':norm,'training_pairs':len(pairs)}
        if iteration==MAX_ITERATIONS:break
        direction=_cholesky_solve(hessian,[-v for v in gradient]);slope=sum(a*b for a,b in zip(gradient,direction))
        if slope>=0:raise SchemaError('Newton direction does not descend.')
        alpha=1.;accepted=False
        for _ in range(20):
            proposal=[w+alpha*d for w,d in zip(coefficients,direction)]
            next_value,_,_=objective_derivatives(proposal,pairs,regularization)
            if next_value<=value+1e-4*alpha*slope:
                coefficients=proposal;accepted=True;break
            alpha*=.5
        if not accepted:raise SchemaError('Frozen Newton line search failed.')
    raise SchemaError('Frozen Newton iteration budget exhausted without convergence.')
