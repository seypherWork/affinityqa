"""Isolated, bounded media-tag API contract; no direct artist/movie reference."""
import math
import re
import time
from .errors import BudgetError,SchemaError,TransportError
from .evidence import fingerprint,redact
from .models import canonical_id,validate_response_envelope
from .qloo import BASE_URL

NAMESPACE='urn:tag:keyword:media'
TAG=re.compile(r'urn:tag:keyword:media:[a-zA-Z0-9_.-]+\Z')


def validate_tag_request(params):
    if not isinstance(params,dict):raise SchemaError('Tag request must be an object.')
    if params.get('filter.type')=='urn:tag':
        required={'filter.type','filter.tag.types','filter.parents.types','take'}
        if not required<=set(params) or set(params)-required-{'signal.interests.entities'}:
            raise SchemaError('Unreviewed taste-analysis parameters.')
        if params['filter.tag.types']!=NAMESPACE or params['filter.parents.types']!='urn:entity:movie':
            raise SchemaError('Only movie media-keyword tags are permitted.')
        if 'signal.interests.entities' in params:canonical_id(params['signal.interests.entities'])
    elif params.get('filter.type')=='urn:entity:movie':
        if set(params)!={'filter.type','take','bias.trends','signal.interests.tags','filter.results.entities'} or params['bias.trends']!='off':
            raise SchemaError('Projection accepts only movie catalog and tag interests.')
        tags=params['signal.interests.tags']
        if not isinstance(tags,str) or not 1<=len(tags.split(','))<=20 or any(not TAG.fullmatch(t) for t in tags.split(',')) or len(set(tags.split(',')))!=len(tags.split(',')):
            raise SchemaError('One to twenty unique approved tags required.')
        ids=params['filter.results.entities']
        if not isinstance(ids,str) or len(ids.split(','))!=20 or len(set(ids.split(',')))!=20:raise SchemaError('Exactly twenty unique catalog IDs required.')
        for i in ids.split(','):canonical_id(i)
        if params['take']!=20:raise SchemaError('The full movie catalog must be returned.')
    else:raise SchemaError('Unsupported tag request type.')
    if type(params['take']) is not int or not 1<=params['take']<=20:raise SchemaError('Bounded integer take required.')


def parse_media_tags(body):
    validate_response_envelope(body,insights=True)
    rows=body['results'].get('tags')
    if not isinstance(rows,list) or not 1<=len(rows)<=20:raise SchemaError('A bounded nonempty tag result is required.')
    result=[];seen=set()
    for row in rows:
        if not isinstance(row,dict):raise SchemaError('Malformed media tag.')
        identity=row.get('tag_id');name=row.get('name');types=row.get('types',[])
        if not isinstance(identity,str) or not TAG.fullmatch(identity) or identity in seen or row.get('subtype')!=NAMESPACE:
            raise SchemaError('Unexpected or duplicate tag identity.')
        if not isinstance(name,str) or not name.strip() or len(name)>300 or not isinstance(types,list) or 'urn:entity:movie' not in types:
            raise SchemaError('Tag metadata does not establish movie context.')
        query=row.get('query',{})
        if not isinstance(query,dict):raise SchemaError('Invalid tag query metadata.')
        affinity=query.get('affinity',row.get('affinity'))
        if affinity is not None and (isinstance(affinity,bool) or not isinstance(affinity,(int,float)) or not math.isfinite(affinity) or not 0<=affinity<=1):raise SchemaError('Invalid tag affinity.')
        seen.add(identity);result.append({'tag_id':identity,'name':name,'affinity':affinity})
    return result


class TasteTagClient:
    """One attempt per query, no redirects, cache, arbitrary host or retry."""
    def __init__(self,transport,ledger,*,max_requests):
        if type(max_requests) is not int or not 1<=max_requests<=100:raise BudgetError('Bounded tag request budget required.')
        self.transport=transport;self.ledger=ledger;self.max_requests=max_requests;self.requests=0;self.last=None

    def get(self,params):
        validate_tag_request(params)
        if self.requests>=self.max_requests:raise BudgetError('Tag request budget exhausted.')
        if self.last is not None:time.sleep(max(0,1-(time.monotonic()-self.last)))
        self.last=time.monotonic();self.requests+=1;self.ledger.live_requests+=1
        request={'method':'GET','host':BASE_URL,'path':'/v2/insights','params':dict(sorted(params.items()))}
        try:response=self.transport.send('/v2/insights',params)
        except TransportError:
            self.ledger.record('transport_failure',{'request':request,'attempt':1});raise
        self.ledger.sample(request,response.status,response.body,response.headers,response.elapsed_ms,live=True,attempt=1)
        if response.status!=200:raise TransportError(f'Qloo tag request returned HTTP {response.status}; stopped without retry.')
        validate_response_envelope(response.body,insights=True)
        return redact(response.body,self.ledger.secrets)
