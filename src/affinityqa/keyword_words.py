"""Fixed lexical composition of media-keyword IDs, without semantic expansion.

Lowercase suffix tokens use [a-z0-9]+ only. No stemming, synonyms, stopwords,
profile identities or evaluator labels. Missing metadata remains observable.
"""
import math
import re
from .errors import SchemaError

PREFIX='urn:tag:keyword:media:'


def tokens(identity):
    if not isinstance(identity,str) or not identity.startswith(PREFIX):raise SchemaError('Exact media-keyword namespace required.')
    suffix=identity[len(PREFIX):]
    if not suffix or ':' in suffix or any(c.isspace() for c in suffix):raise SchemaError('Canonical media-keyword suffix required.')
    result=set(re.findall(r'[a-z0-9]+',suffix.lower()))
    if not result:raise SchemaError('Keyword has no permitted lexical tokens.')
    return result


def profile_words(vector):
    if not isinstance(vector,dict) or not vector:raise SchemaError('Nonempty keyword affinity vector required.')
    result={}
    for identity,affinity in vector.items():
        if type(affinity) not in (int,float) or not math.isfinite(affinity) or not 0<=affinity<=1:raise SchemaError('Finite unit-range affinity required.')
        for term in sorted(tokens(identity)):result[term]=max(result.get(term,0.),affinity)
    if not any(result.values()):raise SchemaError('A profile needs positive lexical evidence.')
    return result


def movie_words(movies):
    if not isinstance(movies,dict) or len(movies)!=20 or any(not isinstance(i,str) or not i for i in movies):raise SchemaError('Exactly twenty movie identities required.')
    result={}
    for identity,keywords in movies.items():
        if not isinstance(keywords,(set,frozenset,list,tuple)) or not keywords:raise SchemaError('Nonempty movie keyword collection required.')
        result[identity]=set().union(*(tokens(k) for k in keywords))
    return result


def _cosine(documents,vector):
    universe=set(vector).union(*documents.values())
    idf={term:math.log(21/(1+sum(term in words for words in documents.values())))+1 for term in sorted(universe)}
    norm=math.sqrt(sum((vector[term]*idf[term])**2 for term in sorted(vector)))
    values={}
    for identity,words in documents.items():
        score=sum(vector.get(term,0)*idf[term]**2 for term in sorted(words))/(norm*math.sqrt(sum(idf[term]**2 for term in sorted(words))))
        if not math.isfinite(score) or not -1e-12<=score<=1+1e-12:raise SchemaError('Invalid lexical cosine.')
        values[identity]=min(1.,max(0.,score))
    return values


def word_signals(movie_keyword_map,a_tag_vector_or_none,b_tag_vector_or_none):
    documents=movie_words(movie_keyword_map)
    a=None if a_tag_vector_or_none is None else profile_words(a_tag_vector_or_none)
    b=None if b_tag_vector_or_none is None else profile_words(b_tag_vector_or_none)
    observed={'A':a is not None,'B':b is not None,'pooled':a is not None and b is not None}
    zero={i:0. for i in documents}
    signals={'A':dict(zero) if a is None else _cosine(documents,a),'B':dict(zero) if b is None else _cosine(documents,b)}
    if observed['pooled']:
        pooled={t:(a.get(t,0)+b.get(t,0))/2 for t in sorted(set(a)|set(b))}
        signals['pooled']=_cosine(documents,pooled)
    else:signals['pooled']=dict(zero)
    return signals,observed
