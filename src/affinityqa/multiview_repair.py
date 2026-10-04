"""A global two-view patch; pure ranking code cannot consume evaluator data."""
from fractions import Fraction
from .errors import SchemaError


def multiview_fuse(baseline,movie_graph,artist_graph,graph_weight,movie_weight,*,other_movie=None,other_artist=None):
    ids=set(baseline)
    if (len(baseline)!=20 or len(ids)!=20 or any(len(r)!=20 or set(r)!=ids for r in (movie_graph,artist_graph))
            or graph_weight not in (.4,.5,.6) or movie_weight not in (0,.2,.4,.5,.6,.8,1)
            or (other_movie is None)!=(other_artist is None)
            or (other_movie is not None and any(len(r)!=20 or set(r)!=ids for r in (other_movie,other_artist)))):
        raise SchemaError('Invalid complete multiview inputs or untrained policy scalars.')
    gw=Fraction(str(graph_weight));mw=Fraction(str(movie_weight))
    local={i:n for n,i in enumerate(baseline)}
    movies={i:Fraction(n) for n,i in enumerate(movie_graph)}
    artists={i:Fraction(n) for n,i in enumerate(artist_graph)}
    if other_movie is not None:
        om={i:n for n,i in enumerate(other_movie)};oa={i:n for n,i in enumerate(other_artist)}
        movies={i:(movies[i]+om[i])/2 for i in baseline}
        artists={i:(artists[i]+oa[i])/2 for i in baseline}
    scores={i:(1-gw)*local[i]+gw*(mw*movies[i]+(1-mw)*artists[i]) for i in baseline}
    return sorted(baseline,key=lambda i:(scores[i],local[i],i))


def build_capture(movie_source,artist_source,graph_weight,movie_weight,plan_sha256):
    if ([c['pair_id'] for c in movie_source['cases']]!=[c['pair_id'] for c in artist_source['cases']]
            or movie_source['status']!='COMPLETE_GRAPH_CAPTURE' or artist_source['status']!='COMPLETE_GRAPH_CAPTURE'):
        raise SchemaError('Both complete graph views must describe the same cases.')
    result={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_sha256,'real_qloo_requests':0,'cases':[]}
    for movie,artist in zip(movie_source['cases'],artist_source['cases'],strict=True):
        if movie['rankings']['baseline']!=artist['rankings']['baseline']:
            raise SchemaError('Graph views cannot use different local baselines.')
        ranks={'baseline':movie['rankings']['baseline'],**{v:{'A':[],'B':[]} for v in ('neutral_graph','qloo_graph','swapped_graph')}}
        for repeat in range(3):
            for p in ('A','B'):
                other='B' if p=='A' else 'A';base=ranks['baseline'][p][repeat]
                mg=movie['graphs'][p][repeat];ag=artist['graphs'][p][repeat]
                om=movie['graphs'][other][repeat];oa=artist['graphs'][other][repeat]
                ranks['qloo_graph'][p].append(multiview_fuse(base,mg,ag,graph_weight,movie_weight))
                ranks['neutral_graph'][p].append(multiview_fuse(base,mg,ag,graph_weight,movie_weight,other_movie=om,other_artist=oa))
                ranks['swapped_graph'][p].append(multiview_fuse(base,om,oa,graph_weight,movie_weight))
        result['cases'].append({'pair_id':movie['pair_id'],'rankings':ranks})
    return result
