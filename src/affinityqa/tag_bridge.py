"""Media-keyword bridge: numeric ranking inputs, no evaluator answers."""
from .affinity_repair import normalize
from .errors import SchemaError
from .models import normalized_name

BASELINE_WEIGHTS=(0,.25,.5)


def select_tags(tags,excluded_names):
    excluded={normalized_name(n) for n in excluded_names}
    eligible=[t for t in tags if normalized_name(t['name']) not in excluded and normalized_name(t['tag_id'].split(':')[-1].replace('_',' ')) not in excluded]
    if len(eligible)<10:raise SchemaError('Fewer than ten eligible media keywords.')
    chosen=eligible[:10]
    if any(t['affinity'] is None for t in chosen):raise SchemaError('Selected profile tags need recorded affinity, not missing-value imputation.')
    return sorted(t['tag_id'] for t in chosen)


def fuse_tags(baseline,projection,baseline_weight):
    if (len(baseline)!=20 or len(set(baseline))!=20 or set(projection)!=set(baseline)
        or type(baseline_weight) not in (int,float) or baseline_weight not in BASELINE_WEIGHTS):
        raise SchemaError('Complete numeric tag projection and declared weight required.')
    graph={i:v**.875 for i,v in normalize(projection).items()};position={i:n for n,i in enumerate(baseline)}
    utility={i:baseline_weight*(1-position[i]/19)+(1-baseline_weight)*graph[i] for i in baseline}
    return sorted(baseline,key=lambda i:(-utility[i],position[i],i))


def capture_rankings(cases,projections,baseline_weight,plan_hash):
    if set(projections)!={c['pair_id'] for c in cases}:raise SchemaError('Every declared pair must have a complete projection.')
    result={'status':'COMPLETE_GRAPH_CAPTURE','plan_sha256':plan_hash,'real_qloo_requests':0,'cases':[]}
    for c in cases:
        if set(projections[c['pair_id']])!={'A','B','pooled'}:raise SchemaError('Own, swapped and pooled tag controls are required.')
        ranks={'baseline':c['baseline'],**{v:{'A':[],'B':[]} for v in ('qloo_graph','neutral_graph','swapped_graph')}}
        for repeat in range(3):
            for p in ('A','B'):
                other='B' if p=='A' else 'A';b=c['baseline'][p][repeat]
                for arm,context in (('qloo_graph',p),('neutral_graph','pooled'),('swapped_graph',other)):
                    ranks[arm][p].append(fuse_tags(b,projections[c['pair_id']][context],baseline_weight))
        result['cases'].append({'pair_id':c['pair_id'],'rankings':ranks})
    return result
