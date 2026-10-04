"""Bounded global refinement between the two best value-fusion candidates."""
from .affinity_repair import normalize,fuse
from .errors import SchemaError


def refined_fuse(baseline,movie,artist,power,*,other_movie=None,other_artist=None):
    if power not in (.625,.75,.875):raise SchemaError('Undeclared affinity refinement.')
    def transform(values):return {i:v**power for i,v in normalize(values,1).items()}
    # The same signal normalization and intervention are used in every ablation.
    return fuse(baseline,transform(movie),transform(artist),.5,1,1,
                other_movie=transform(other_movie) if other_movie is not None else None,
                other_artist=transform(other_artist) if other_artist is not None else None)


def capture(cases,power,plan_hash):
    output={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for case in cases:
        ranks={'baseline':case['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for r in range(3):
            for p in ('A','B'):
                other='B' if p=='A' else 'A';b=case['baseline'][p][r]
                m=case['movie'][p][r];a=case['artist'][p][r];om=case['movie'][other][r];oa=case['artist'][other][r]
                ranks['qloo_graph'][p].append(refined_fuse(b,m,a,power))
                ranks['neutral_graph'][p].append(refined_fuse(b,m,a,power,other_movie=om,other_artist=oa))
                ranks['swapped_graph'][p].append(refined_fuse(b,om,oa,power))
        output['cases'].append({'pair_id':case['pair_id'],'rankings':ranks})
    return output
