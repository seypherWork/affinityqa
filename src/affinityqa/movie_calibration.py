"""Position calibration with factual film genre/year features, never identities."""
import math
from .errors import SchemaError
from .kernel_calibration import kernel_features
from .ordinal_calibration import fit


def movie_features(l,m,a,width,facts,vocabulary):
    if (not isinstance(facts,dict) or set(facts)!={'genres','release_year'}
            or type(facts['release_year']) is not int or not 1888<=facts['release_year']<=2100
            or not isinstance(facts['genres'],list) or any(not isinstance(g,str) for g in facts['genres'])
            or vocabulary!=sorted(set(vocabulary)) or len(vocabulary)>50):
        raise SchemaError('Film calibration needs only verified genre/year facts and a frozen vocabulary.')
    row=kernel_features(l,m,a,width);x,y,z=l/19,m/19,a/19
    for genre in vocabulary:
        present=float(genre in facts['genres']);row.extend((present,present*y,present*z))
    year=(facts['release_year']-1950)/100
    row.extend((year,year*x,year*y,year*z))
    return row


def movie_fuse(baseline,movie_graph,artist_graph,model,catalog_facts,*,other_movie=None,other_artist=None):
    ids=set(baseline)
    if (len(baseline)!=20 or len(ids)!=20 or any(len(r)!=20 or set(r)!=ids for r in (movie_graph,artist_graph))
            or set(catalog_facts)!=ids or set(model)!={'width','coefficients','genre_vocabulary'}
            or (other_movie is None)!=(other_artist is None)
            or (other_movie is not None and any(len(r)!=20 or set(r)!=ids for r in (other_movie,other_artist)))):
        raise SchemaError('Film calibration requires complete matching rankings and metadata.')
    local={i:n for n,i in enumerate(baseline)};m={i:n for n,i in enumerate(movie_graph)};a={i:n for n,i in enumerate(artist_graph)}
    if other_movie is not None:
        om={i:n for n,i in enumerate(other_movie)};oa={i:n for n,i in enumerate(other_artist)}
        m={i:(m[i]+om[i])/2 for i in baseline};a={i:(a[i]+oa[i])/2 for i in baseline}
    coeff=model['coefficients'];vocab=model['genre_vocabulary']
    expected=129+3*len(vocab)+4
    if len(coeff)!=expected or any(type(v) not in (int,float) or not math.isfinite(v) for v in coeff):raise SchemaError('Malformed factual-film calibration model.')
    scores={i:sum(w*x for w,x in zip(coeff,movie_features(local[i],m[i],a[i],model['width'],catalog_facts[i],vocab),strict=True)) for i in baseline}
    return sorted(baseline,key=lambda i:(-scores[i],local[i],i))


def movie_capture(movie_source,artist_source,model,catalog_facts,plan_sha256):
    if ([c['pair_id'] for c in movie_source['cases']]!=[c['pair_id'] for c in artist_source['cases']]
            or movie_source['status']!='COMPLETE_GRAPH_CAPTURE' or artist_source['status']!='COMPLETE_GRAPH_CAPTURE'):
        raise SchemaError('Complete matching film-calibration sources are required.')
    result={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_sha256,'real_qloo_requests':0,'cases':[]}
    for movie,artist in zip(movie_source['cases'],artist_source['cases'],strict=True):
        if movie['rankings']['baseline']!=artist['rankings']['baseline']:raise SchemaError('Different film-calibration baselines.')
        ranks={'baseline':movie['rankings']['baseline'],**{v:{'A':[],'B':[]} for v in ('neutral_graph','qloo_graph','swapped_graph')}}
        for repeat in range(3):
            for p in ('A','B'):
                other='B' if p=='A' else 'A';base=ranks['baseline'][p][repeat]
                mg=movie['graphs'][p][repeat];ag=artist['graphs'][p][repeat];om=movie['graphs'][other][repeat];oa=artist['graphs'][other][repeat]
                ranks['qloo_graph'][p].append(movie_fuse(base,mg,ag,model,catalog_facts))
                ranks['neutral_graph'][p].append(movie_fuse(base,mg,ag,model,catalog_facts,other_movie=om,other_artist=oa))
                ranks['swapped_graph'][p].append(movie_fuse(base,om,oa,model,catalog_facts))
        result['cases'].append({'pair_id':movie['pair_id'],'rankings':ranks})
    return result
