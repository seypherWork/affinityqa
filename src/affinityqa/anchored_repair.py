"""Protect one recomputed agent choice; never inspect evaluation answers."""
from .multiview_repair import multiview_fuse,build_capture


def anchored_fuse(baseline,movie_graph,artist_graph,graph_weight,movie_weight,**kwargs):
    fused=multiview_fuse(baseline,movie_graph,artist_graph,graph_weight,movie_weight,**kwargs)
    return [baseline[0]]+[i for i in fused if i!=baseline[0]]


def anchored_capture(movie_source,artist_source,graph_weight,movie_weight,plan_sha256):
    result=build_capture(movie_source,artist_source,graph_weight,movie_weight,plan_sha256)
    for case in result['cases']:
        for variant in ('qloo_graph','neutral_graph','swapped_graph'):
            for p in ('A','B'):
                for repeat in range(3):
                    first=case['rankings']['baseline'][p][repeat][0]
                    row=case['rankings'][variant][p][repeat]
                    case['rankings'][variant][p][repeat]=[first]+[i for i in row if i!=first]
    return result
