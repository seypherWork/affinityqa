"""A disjoint-example repair: movie descriptions -> local vectors -> rank fusion.

No artist/reference rankings, affinities or example order enter embeddings.
This is one fixed mechanism, distinct from the closed contextual-prompt study.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from itertools import product
from statistics import median
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .agents import AgentError, _RejectRedirects, strict_json
from .errors import SchemaError
from .evidence import fingerprint, utc_now
from .film_protocol import calibrate_reference
from .metrics import ndcg_at_k, max_repeat_jitter
from .models import canonical_id, normalized_name
from .ollama_agent import local_ollama_url


class LocalEmbedder:
    def __init__(self, url, model='mxbai-embed-large:latest', *, max_calls=3):
        self.url=local_ollama_url(url)
        if model!='mxbai-embed-large:latest' or type(max_calls)!=int or not 1<=max_calls<=6:
            raise AgentError('Unsupported installed embedding model or call budget.')
        self.model=model;self.calls=0;self.max_calls=max_calls;self.observations=[]
        self.opener=build_opener(ProxyHandler({}),_RejectRedirects())
        tags=self.request('/api/tags')
        installed=next((m for m in tags.get('models',[]) if m.get('name')==model),None)
        if not installed or installed.get('remote_host') or installed.get('remote_model') or not installed.get('digest'):
            raise AgentError('An already installed local embedding model is required; no download.')
        self.manifest={'provider':'ollama-local','model':model,'digest':installed['digest'],
                       'truncate':False,'max_calls':max_calls,'private_thinking_recorded':False}

    def request(self,path,data=None):
        payload=None if data is None else json.dumps(data,allow_nan=False).encode('utf-8')
        req=Request(self.url+path,data=payload,headers={'Content-Type':'application/json'})
        try:
            with self.opener.open(req,timeout=45) as response:
                raw=response.read(2_000_001)
                if response.status!=200 or response.headers.get_content_type()!='application/json' or len(raw)>2_000_000:
                    raise AgentError('Invalid or oversized local embedding response.')
            return strict_json(raw)
        except (HTTPError,URLError,OSError,TimeoutError):
            raise AgentError('Local embeddings failed; no automatic retry or model download.') from None

    def embed(self,texts):
        if self.calls>=self.max_calls or not 1<=len(texts)<=50 or any(not isinstance(t,str) or not 1<=len(t)<=1400 for t in texts):
            raise AgentError('Embedding batch or request budget is invalid.')
        self.calls+=1;start=time.monotonic()
        result=self.request('/api/embed',{'model':self.model,'input':texts,'truncate':False})
        rows=result.get('embeddings')
        if result.get('model')!=self.model or not isinstance(rows,list) or len(rows)!=len(texts):
            raise AgentError('Embedding model or batch coverage changed.')
        lengths=set()
        for row in rows:
            if not isinstance(row,list) or not 32<=len(row)<=4096 or any(type(v) not in (int,float) or not math.isfinite(v) for v in row):
                raise AgentError('Nonfinite or malformed embedding.')
            lengths.add(len(row))
            if sum(v*v for v in row)<=1e-12:raise AgentError('Zero embedding vector.')
        if len(lengths)!=1:raise AgentError('Embedding dimensions changed within the batch.')
        rows=[unit(row) for row in rows]
        self.observations.append({'call':self.calls,'input_sha256':fingerprint(texts),'output_sha256':fingerprint(rows),
                                 'batch_size':len(rows),'elapsed_ms':round((time.monotonic()-start)*1000,3),
                                 'prompt_eval_count':result.get('prompt_eval_count')})
        return rows


def unit(row):
    length=math.sqrt(sum(v*v for v in row))
    return [v/length for v in row]


def movie_text(entity):
    props=entity.get('properties',{})
    description=props.get('description')
    if not isinstance(description,str) or len(description.strip())<20:
        raise SchemaError('A semantic movie card requires a recorded description; no invented summary.')
    genres=sorted({t['name'] for t in entity.get('tags',[]) if isinstance(t,dict)
                   and t.get('type')=='urn:tag:genre:media' and isinstance(t.get('name'),str)})
    # Fixed truncation at text boundary is part of this declared input contract.
    return f"Movie: {entity['name']} ({props['release_year']}). Genres: {', '.join(genres)}. Synopsis: {description[:850]}"


def load_development(root, study):
    receipt=json.loads((root/'evidence/CONTEXT-DEVELOPMENT-20261003.json').read_text(encoding='utf-8'))
    def checked(run,name):
        path=root/'runs'/run/name
        if path.is_symlink() or path.stat().st_size>5_100_000:
            raise SchemaError('Unsafe semantic source artifact.')
        content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=receipt['run_artifact_sha256'].get(run,{}).get(name):
            raise SchemaError('Semantic source evidence changed.')
        return json.loads(content)
    run=study['source_context_run']
    bundle=checked(run,'context-bundle.json')
    baseline=checked(study['source_baseline_run'],'context-ablation.json')
    metadata={}
    for name in receipt['run_artifact_sha256'][run]:
        if not name.startswith('http-'):continue
        sample=checked(run,name)
        if sample.get('status')!=200 or sample.get('request',{}).get('path') not in ('/entities','/v2/insights'):continue
        results=sample['response'].get('results')
        rows=results.get('entities',[]) if isinstance(results,dict) else results
        if isinstance(rows,list):
            for e in rows:
                if isinstance(e,dict) and 'entity_id' in e:metadata.setdefault(canonical_id(e['entity_id']),e)
    contexts={}
    ids=[e['entity_id'] for e in bundle['catalog']]
    names={normalized_name(e['name']) for e in bundle['catalog']}
    for pair in bundle['pairs']:
        contexts[pair['pair_id']]={}
        for label in ('A','B'):
            rows=pair['contexts'][label]
            if (len(rows)!=5 or len({r['entity_id'] for r in rows})!=5
                    or any(r['entity_id'] in ids or normalized_name(r['name']) in names for r in rows)):
                raise SchemaError('Semantic examples must exclude the entire evaluation catalog.')
            contexts[pair['pair_id']][label]=sorted(r['entity_id'] for r in rows)
    all_ids=sorted(set(ids)|{i for p in contexts.values() for rows in p.values() for i in rows})
    if not set(all_ids)<=set(metadata):
        raise SchemaError('Recorded metadata does not cover all semantic movie cards.')
    texts=[movie_text(metadata[i]) for i in all_ids]
    return bundle,baseline,contexts,all_ids,texts


def fuse(baseline, catalog_vectors, context_vectors, *, weight=.5):
    ids=list(baseline)
    if (len(ids)!=20 or len(set(ids))!=20 or set(catalog_vectors)!=set(ids)
            or not context_vectors or not 0<=weight<=1):raise SchemaError('Invalid complete semantic fusion input.')
    similarities={i:sum(sum(a*b for a,b in zip(catalog_vectors[i],v,strict=True)) for v in context_vectors)/len(context_vectors) for i in ids}
    semantic=sorted(ids,key=lambda i:(-similarities[i],i))
    positions={i:rank for rank,i in enumerate(semantic)}
    original={i:rank for rank,i in enumerate(ids)}
    return sorted(ids,key=lambda i:(weight*original[i]+(1-weight)*positions[i],original[i],i))


def profile_delta(candidate,baseline,references):
    values=[ndcg_at_k(c,r,5)-ndcg_at_k(b,r,5) for c,b,r in product(candidate,baseline,references)]
    return {'min':min(values),'median':median(values),'max':max(values)}


def evaluate_development(root, study, engine, ledger):
    bundle,baseline,contexts,all_ids,texts=load_development(root,study)
    if (study.get('study_id')!='disjoint-semantic-bridge-v1' or study['baseline_weight']!=.5
            or study['max_development_candidates']!=1 or study['development_pair_ids']!=['mutation-01','mutation-03']):
        raise SchemaError('Unsupported fixed semantic-bridge study.')
    plan={'study':study,'study_sha256':fingerprint(study),'input_text_sha256':fingerprint(texts),
          'embedding_manifest':engine.manifest,'created_utc':utc_now(),'reserved_inputs_executed':0,
          'catalog_sha256':fingerprint(bundle['catalog']),'source_baseline_sha256':fingerprint(baseline)}
    plan['plan_sha256']=fingerprint(plan)
    ledger.write('semantic-plan.json',plan);ledger.write('movie-cards.json',dict(zip(all_ids,texts)))
    ledger.record('semantic_plan_frozen',{'plan_sha256':plan['plan_sha256'],'embedding_calls':0})
    report={'status':'INCOMPLETE','candidate_gate':'NOT_VALIDATED','ci_gate':'NOT_VALIDATED','cases':[],
            'new_qloo_requests':0,'reserved_inputs_executed':0,'plan_sha256':plan['plan_sha256']}
    catalog_ids=[e['entity_id'] for e in bundle['catalog']]
    batches=[]
    for repeat in range(3):
        vectors=engine.embed(texts);batches.append(dict(zip(all_ids,vectors)))
        ledger.record('local_embedding_batch',engine.observations[-1])
    for pair_id in study['development_pair_ids']:
        ref=next(p for p in bundle['pairs'] if p['pair_id']==pair_id)
        original=next(p for p in baseline['cases'] if p['pair_id']==pair_id)['rankings']['original']
        ranks={'baseline':original,**{v:{'A':[],'B':[]} for v in ('neutral_context','qloo_context','swapped_context')}}
        for repeat,vectors in enumerate(batches):
            cv={i:vectors[i] for i in catalog_ids}
            for label in ('A','B'):
                for variant in ('neutral_context','qloo_context','swapped_context'):
                    key=label if variant=='qloo_context' else ('B' if label=='A' else 'A')
                    ctx=catalog_ids if variant=='neutral_context' else contexts[pair_id][key]
                    ranked=fuse(original[label][repeat],cv,[vectors[i] for i in ctx],weight=study['baseline_weight'])
                    ranks[variant][label].append(ranked)
        comparisons={v:{label:profile_delta(ranks['qloo_context'][label],ranks[v][label],ref['rankings'][label])
                        for label in ('A','B')} for v in ('baseline','neutral_context','swapped_context')}
        means={v:min((a+b)/2 for a,b in product(
            [ndcg_at_k(c,r,5)-ndcg_at_k(b,r,5) for c,b,r in product(ranks['qloo_context']['A'],ranks[v]['A'],ref['rankings']['A'])],
            [ndcg_at_k(c,r,5)-ndcg_at_k(b,r,5) for c,b,r in product(ranks['qloo_context']['B'],ranks[v]['B'],ref['rankings']['B'])])) for v in comparisons}
        stable=max(max_repeat_jitter(ranks['qloo_context'][p],5) for p in ('A','B'))<=1e-12
        informative=calibrate_reference(ref['rankings'],catalog_ids,5,0)['informative']
        checks={'reference_informative':informative,
                'no_profile_loss':all(comparisons[v][p]['min']>=-study['max_profile_drop']-1e-12 for v in ('baseline','neutral_context') for p in ('A','B')),
                'benefit_beyond_baseline':means['baseline']>=study['minimum_mean_gain'],
                'benefit_beyond_neutral':means['neutral_context']>=study['minimum_mean_gain'],
                'beats_swapped_context':means['swapped_context']>=study['minimum_mean_gain_over_swapped'],
                'stable':stable}
        row={'pair_id':pair_id,'rankings':ranks,'comparisons':comparisons,'minimum_pair_mean_delta':means,'checks':checks}
        report['cases'].append(row)
    report.update(status='COMPLETE_SEMANTIC_DEVELOPMENT',embedding_calls=engine.calls,
                  candidate_gate='PROMISING_DEVELOPMENT_CANDIDATE' if all(all(p['checks'].values()) for p in report['cases']) else 'REJECTED_DEVELOPMENT_CANDIDATE')
    ledger.write('embedding-observations.json',engine.observations)
    ledger.write('semantic-development.json',report)
    return report
