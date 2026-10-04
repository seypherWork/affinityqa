"""Bounded supervised selection exports one scalar, never reference answers."""
from fractions import Fraction
from .errors import SchemaError


def weighted_fuse(baseline, graph, graph_weight, other=None):
    if (len(baseline)!=20 or len(set(baseline))!=20 or len(graph)!=20 or set(graph)!=set(baseline)
            or (other is not None and (len(other)!=20 or set(other)!=set(baseline)))
            or type(graph_weight) not in (int,float) or graph_weight not in [i/10 for i in range(1,11)]):
        raise SchemaError('Invalid complete weighted-fusion inputs or undeclared scalar.')
    weight=Fraction(str(graph_weight));local={i:n for n,i in enumerate(baseline)}
    positions={i:n for n,i in enumerate(graph)}
    counterpart={i:n for n,i in enumerate(other)} if other is not None else positions
    scores={i:(1-weight)*local[i]+weight*Fraction(positions[i]+counterpart[i],2) for i in baseline}
    return sorted(baseline,key=lambda i:(scores[i],local[i],i))


def training_capture(source, graph_weight, plan_sha256):
    result={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_sha256,'real_qloo_requests':0,'cases':[]}
    for case in source['cases']:
        ranks={'baseline':case['rankings']['baseline'],**{v:{'A':[],'B':[]} for v in ('neutral_graph','qloo_graph','swapped_graph')}}
        for repeat in range(3):
            for p in ('A','B'):
                other='B' if p=='A' else 'A';base=ranks['baseline'][p][repeat]
                graph=case['graphs'][p][repeat];opposite=case['graphs'][other][repeat]
                ranks['qloo_graph'][p].append(weighted_fuse(base,graph,graph_weight))
                ranks['neutral_graph'][p].append(weighted_fuse(base,graph,graph_weight,opposite))
                ranks['swapped_graph'][p].append(weighted_fuse(base,opposite,graph_weight))
        result['cases'].append({'pair_id':case['pair_id'],'rankings':ranks})
    return result
