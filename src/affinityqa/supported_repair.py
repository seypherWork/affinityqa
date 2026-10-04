"""Preserve a first choice only when a cultural projection supports it."""
from fractions import Fraction
from .multiview_repair import multiview_fuse
from .errors import SchemaError


def supported_fuse(baseline,movie_graph,artist_graph,graph_weight,movie_weight,*,other_movie=None,other_artist=None):
    fused=multiview_fuse(baseline,movie_graph,artist_graph,graph_weight,movie_weight,
                         other_movie=other_movie,other_artist=other_artist)
    first=baseline[0]
    mr=Fraction(movie_graph.index(first)+1);ar=Fraction(artist_graph.index(first)+1)
    if other_movie is not None:
        mr=(mr+other_movie.index(first)+1)/2;ar=(ar+other_artist.index(first)+1)/2
    # Same product top-five support rule for every profile and control.
    if min(mr,ar)<=5:return [first]+[i for i in fused if i!=first]
    return fused


def supported_capture(movie_source,artist_source,graph_weight,movie_weight,plan_sha256):
    if ([c['pair_id'] for c in movie_source['cases']]!=[c['pair_id'] for c in artist_source['cases']]
            or movie_source['status']!='COMPLETE_GRAPH_CAPTURE' or artist_source['status']!='COMPLETE_GRAPH_CAPTURE'):
        raise SchemaError('Both complete graph views must describe the same cases.')
    result={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_sha256,'real_qloo_requests':0,'cases':[]}
    for movie,artist in zip(movie_source['cases'],artist_source['cases'],strict=True):
        if movie['rankings']['baseline']!=artist['rankings']['baseline']:raise SchemaError('Different model baselines.')
        ranks={'baseline':movie['rankings']['baseline'],**{v:{'A':[],'B':[]} for v in ('neutral_graph','qloo_graph','swapped_graph')}}
        for repeat in range(3):
            for p in ('A','B'):
                other='B' if p=='A' else 'A';base=ranks['baseline'][p][repeat]
                mg=movie['graphs'][p][repeat];ag=artist['graphs'][p][repeat]
                om=movie['graphs'][other][repeat];oa=artist['graphs'][other][repeat]
                ranks['qloo_graph'][p].append(supported_fuse(base,mg,ag,graph_weight,movie_weight))
                ranks['neutral_graph'][p].append(supported_fuse(base,mg,ag,graph_weight,movie_weight,other_movie=om,other_artist=oa))
                ranks['swapped_graph'][p].append(supported_fuse(base,om,oa,graph_weight,movie_weight))
        result['cases'].append({'pair_id':movie['pair_id'],'rankings':ranks})
    return result
