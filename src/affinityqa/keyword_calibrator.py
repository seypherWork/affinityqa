"""Eight numeric features; exact-keyword cosine and one fixed ridge penalty.

References belong only to supervised sample construction, never runtime inputs.
Keyword absence is zero membership, not proof that a theme is absent in a film.
"""
import math
from .errors import SchemaError
from .models import normalized_name, canonical_id
from .learned_repair import FEATURES as PREVIOUS_FEATURES, context, features as previous_features

FEATURES=(*PREVIOUS_FEATURES,'keyword_tfidf_cosine')
REGULARIZATION=.001
PREFIX='urn:tag:keyword:media:'


def _number(value):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1


def _tag(identity):
    return isinstance(identity,str) and identity.startswith(PREFIX) and len(identity)>len(PREFIX) and not any(c.isspace() for c in identity)


def profile_vector(rows,excluded_names=()):
    """All eligible returned rows, never select tags using evaluator scores."""
    if not isinstance(rows,list) or not 10<=len(rows)<=20:raise SchemaError('Ten to twenty raw profile keywords required.')
    if any(not isinstance(n,str) for n in excluded_names):raise SchemaError('Invalid exclusion names.')
    excluded={normalized_name(n) for n in excluded_names};result={};seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'tag_id','name','affinity'}:raise SchemaError('Unexpected profile fields; references are forbidden.')
        identity=row['tag_id'];name=row['name'];weight=row['affinity']
        if not _tag(identity) or identity in seen or not isinstance(name,str) or not name.strip() or not _number(weight):raise SchemaError('Invalid or duplicate media keyword.')
        seen.add(identity)
        if normalized_name(name) in excluded or normalized_name(identity) in excluded or normalized_name(identity[len(PREFIX):].replace('_',' ')) in excluded:continue
        result[identity]=weight
    if len(result)<10 or not any(result.values()):raise SchemaError('Insufficient eligible positive keyword evidence.')
    return result


def _vector(vector):
    if not isinstance(vector,dict) or not vector or any(not _tag(k) or not _number(v) for k,v in vector.items()) or not any(vector.values()):raise SchemaError('Invalid sparse keyword vector.')


def pooled_vector(a,b):
    _vector(a);_vector(b)
    return {t:(a.get(t,0)+b.get(t,0))/2 for t in sorted(set(a)|set(b))}


def cosine_scores(vector,catalog_keywords):
    """Binary movie documents; unseen profile tags stay in the norm (df=0)."""
    _vector(vector)
    if not isinstance(catalog_keywords,dict) or len(catalog_keywords)!=20 or any(not isinstance(i,str) or not i for i in catalog_keywords):raise SchemaError('Exactly twenty catalog identities required.')
    documents={}
    for identity,tags in catalog_keywords.items():
        if not isinstance(tags,(list,tuple,set,frozenset)) or not tags or any(not _tag(t) for t in tags):raise SchemaError('Movie keywords must be nonempty exact media IDs.')
        documents[identity]=set(tags)
    universe=set(vector).union(*(v for v in documents.values()))
    idf={t:math.log(21/(1+sum(t in tags for tags in documents.values())))+1 for t in universe}
    norm=math.sqrt(sum((weight*idf[t])**2 for t,weight in vector.items()))
    result={}
    for identity,tags in documents.items():
        denominator=norm*math.sqrt(sum(idf[t]**2 for t in tags))
        value=sum(vector.get(t,0)*idf[t]**2 for t in tags)/denominator
        if not math.isfinite(value) or value < -1e-12 or value > 1+1e-12:raise SchemaError('Invalid cosine arithmetic.')
        result[identity]=min(1.,max(0.,value))
    return result


def signals_for_pair(a,b,catalog_keywords):
    return {'A':cosine_scores(a,catalog_keywords),'B':cosine_scores(b,catalog_keywords),'pooled':cosine_scores(pooled_vector(a,b),catalog_keywords)}


def movie_keywords(rows):
    """Read only exact keyword membership from twenty raw /entities records."""
    if not isinstance(rows,list) or len(rows)!=20:raise SchemaError('Twenty raw movie records required.')
    result={}
    for row in rows:
        if not isinstance(row,dict) or 'urn:entity:movie' not in row.get('types',[]) or not isinstance(row.get('tags'),list):raise SchemaError('Typed movie metadata required.')
        identity=canonical_id(row.get('entity_id'))
        if identity in result:raise SchemaError('Duplicate movie identity.')
        tags=set()
        for tag in row['tags']:
            if not isinstance(tag,dict):raise SchemaError('Malformed movie tag.')
            if tag.get('type')=='urn:tag:keyword:media':
                if not _tag(tag.get('tag_id')):raise SchemaError('Malformed movie keyword ID.')
                tags.add(tag['tag_id'])
        if not tags:raise SchemaError('Each movie needs recorded exact keywords.')
        result[identity]=tags
    return result


def cosine_signals(movies,profiles):
    return cosine_scores(profiles,movies)


def combined_profile(a,b):
    return pooled_vector(a,b)


def features(baseline,ctx,keywords,pooled=None):
    original=previous_features(baseline,ctx,pooled)
    if not isinstance(keywords,dict) or set(keywords)!=set(baseline) or any(not _number(v) for v in keywords.values()):raise SchemaError('Complete numeric keyword catalog required; references forbidden.')
    return {i:[*row,keywords[i]] for i,row in original.items()}


def fit(samples,regularization=REGULARIZATION):
    if type(regularization) not in (int,float) or regularization!=REGULARIZATION or not isinstance(samples,list) or not samples:raise SchemaError('Only the frozen .001 penalty and nonempty samples are permitted.')
    width=8;matrix=[[0.]*width for _ in range(width)];rhs=[0.]*width
    for sample in samples:
        if not isinstance(sample,(tuple,list)) or len(sample)!=2:raise SchemaError('Numeric rows and numeric targets required.')
        rows,target=sample
        if not isinstance(rows,list) or not isinstance(target,list) or len(rows)!=20 or len(target)!=20 or any(not isinstance(row,list) or len(row)!=width for row in rows):raise SchemaError('Exactly twenty eight-feature rows per profile required.')
        if any(not _number(v) for row in rows for v in row) or any(not _number(v) for v in target):raise SchemaError('Invalid numeric training values.')
        means=[sum(row[j] for row in rows)/20 for j in range(width)];mean_y=sum(target)/20
        for row,y in zip(rows,target):
            x=[v-m for v,m in zip(row,means)];weight=1/(len(samples)*20)
            for j in range(width):
                rhs[j]+=weight*x[j]*(y-mean_y)
                for k in range(width):matrix[j][k]+=weight*x[j]*x[k]
    for j in range(width):matrix[j][j]+=regularization
    system=[[*row,y] for row,y in zip(matrix,rhs)]
    for j in range(width):
        pivot=max(range(j,width),key=lambda r:abs(system[r][j]));system[j],system[pivot]=system[pivot],system[j]
        divisor=system[j][j]
        if abs(divisor)<1e-14:raise SchemaError('Ill-conditioned ridge system.')
        system[j]=[v/divisor for v in system[j]]
        for r in range(width):
            if r!=j:
                factor=system[r][j];system[r]=[a-factor*b for a,b in zip(system[r],system[j])]
    coefficients=[system[j][-1] for j in range(width)]
    if any(not math.isfinite(v) for v in coefficients) or max(abs(sum(matrix[j][k]*coefficients[k] for k in range(width))-rhs[j]) for j in range(width))>1e-10:raise SchemaError('Invalid ridge residual.')
    return coefficients


def rank(baseline,ctx,keywords,coefficients,pooled=None):
    if not isinstance(coefficients,(list,tuple)) or len(coefficients)!=8 or any(type(v) not in (int,float) or not math.isfinite(v) for v in coefficients):raise SchemaError('Eight finite numeric coefficients required.')
    rows=features(baseline,ctx,keywords,pooled);positions={i:n for n,i in enumerate(baseline)}
    return sorted(baseline,key=lambda i:(-sum(a*b for a,b in zip(rows[i],coefficients)),positions[i]))


def capture(cases,signals,coefficients,plan_hash):
    keys=[c['pair_id'] for c in cases]
    if len(set(keys))!=len(keys) or not isinstance(signals,dict) or set(signals)!=set(keys):raise SchemaError('Exact pair coverage required.')
    output={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for c in cases:
        if set(c)!={'pair_id','baseline','movie','individual'}:raise SchemaError('Unexpected case fields; references are forbidden.')
        s=signals[c['pair_id']]
        if not isinstance(s,dict) or set(s)!={'A','B','pooled'}:raise SchemaError('Exactly own and pooled keyword signals required.')
        if any(set(c[field])!={'A','B'} for field in ('baseline','movie','individual')) or any(len(c[field][p])!=3 for field in ('baseline','movie') for p in ('A','B')):raise SchemaError('Three repeats for both profiles required.')
        ranks={'baseline':c['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for r in range(3):
            ctx={p:context(c['movie'][p][r],c['individual'][p]) for p in ('A','B')}
            for p in ('A','B'):
                q='B' if p=='A' else 'A';b=c['baseline'][p][r]
                ranks['qloo_graph'][p].append(rank(b,ctx[p],s[p],coefficients))
                ranks['neutral_graph'][p].append(rank(b,ctx[p],s['pooled'],coefficients,ctx[q]))
                ranks['swapped_graph'][p].append(rank(b,ctx[q],s[q],coefficients))
        output['cases'].append({'pair_id':c['pair_id'],'rankings':ranks})
    return output


def samples(cases,signals,references,exclude=None):
    """Evaluator-only supervised builder; skip excluded labels before accessing."""
    result=[];used=[]
    for c in cases:
        key=c['pair_id']
        if key==exclude:continue
        ref=references[key];used.append(key)
        for p in ('A','B'):
            b=c['baseline'][p][0];ranks=ref[p]
            if len(ranks)!=3 or any(len(r)!=20 or set(r)!=set(b) for r in ranks):raise SchemaError('Complete supervised reference permutations required.')
            if any(c['baseline'][p][r]!=b or c['movie'][p][r]!=c['movie'][p][0] or ranks[r]!=ranks[0] for r in range(3)):raise SchemaError('Repeated snapshots must be identical to contribute once.')
            x=features(b,context(c['movie'][p][0],c['individual'][p]),signals[key][p])
            result.append(([x[i] for i in b],[1-ranks[0].index(i)/19 for i in b]))
    return result,used
