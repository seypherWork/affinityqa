"""Literal captured Qloo descriptions; no generated synopsis or remote request."""
import copy
import hashlib
import re
import unicodedata
from pathlib import Path

from .agents import strict_json
from .evidence import fingerprint
from .errors import SchemaError
from .individual_verify import checked_path,sha
from .models import parse_entities

RENDERER='qloo-short-description-v1'
DISPLAY='qloo-grounded-display-v1'
FALLBACK='Seleccionada por IA entre las películas obtenidas para esta búsqueda. No hay una descripción breve vinculada disponible.'
ARCHIVED_NOTICE='La explicación original de IA se conserva archivada. Esta ficha utiliza únicamente datos vinculados de Qloo o un aviso sin trama.'
CURRENT_NOTICE='La IA selecciona; Qloo aporta la ficha. La fidelidad a la fuente no acredita su verdad ni la afinidad cultural.'
EVIDENCE_KEYS={'schema_version','renderer','source','language','catalog_index','entity_id','title','release_year',
    'page','position','sample_sha256','response_sha256','value_pointer','languages_pointer','value_sha256','fallback_reason'}
REASON_KEYS={'catalog_index','entity_id','kind','verification','text','provider_cause_verified','evidence'}


def _need(condition,message):
    if not condition:raise SchemaError('Wide grounding: '+message)


def _literal(value):
    return (isinstance(value,str) and 40 <= len(value) <= 240 and value == ' '.join(value.split())
        and not any(unicodedata.category(c).startswith('C') for c in value)
        and re.search(r'\[REDACTED\]|\b(?:gsk_|sk-)[A-Za-z0-9_-]{16,}|\b(?:Bearer|Authorization|X-Api-Key|PRIVATE_\w*CANARY|\w*credential\w*)\b',value,re.I) is None)


def _description(properties):
    values=properties.get('short_descriptions')
    if values is None or values == []:return None,None,None,'MISSING'
    if not isinstance(values,list) or len(values)>100:return None,None,None,'MALFORMED'
    choices={'es':{},'en':{}}
    for index,item in enumerate(values):
        if not isinstance(item,dict) or not isinstance(item.get('languages'),list) or not item['languages'] or any(not isinstance(v,str) or not v for v in item['languages']) or not isinstance(item.get('value'),str):
            return None,None,None,'MALFORMED'
        for language in ('es','en'):
            if language in item['languages']:
                choices[language].setdefault(item['value'],index)
    for language in ('es','en'):
        if choices[language]:
            if len(choices[language]) != 1:return None,None,None,'AMBIGUOUS'
            value,index=next(iter(choices[language].items()))
            if not _literal(value):return None,None,None,'UNSAFE'
            return value,language,index,None
    return None,None,None,'MISSING'


def grounding_registry(catalog,samples):
    """Bind each catalog identity to its first eligible raw observation only."""
    first={}
    for page,item in enumerate(samples,1):
        sample,sample_sha=item['sample'],item['sample_sha256']
        _need(sample.get('response_sha256')==fingerprint(sample.get('response')),'response hash changed')
        parsed=parse_entities(sample['response'],insights=True)
        raw=sample['response']['results']['entities']
        for position,row in enumerate(parsed):
            year=row.metadata.get('release_year')
            if type(year) is int and 1888<=year<=2100:
                first.setdefault(row.entity_id,(page,position,row,raw[position],sample_sha,sample['response_sha256']))
    registry=[]
    for index,movie in enumerate(catalog):
        _need(movie['entity_id'] in first,'missing original identity')
        page,position,row,raw,sample_sha,response_sha=first[movie['entity_id']]
        _need(row.name==movie['name'] and type(row.metadata.get('release_year')) is int and row.metadata['release_year']==movie['release_year'],'exact original identity')
        value,language,description_index,failure=_description(raw.get('properties',{}))
        pointer=f'/response/results/entities/{position}/properties/short_descriptions/{description_index}' if value is not None else None
        evidence={'schema_version':1,'renderer':RENDERER,'source':'QLOO_OBSERVED' if value is not None else 'RETRIEVAL_CONTEXT',
            'language':language,'catalog_index':index,'entity_id':movie['entity_id'],'title':movie['name'],'release_year':movie['release_year'],
            'page':page,'position':position,'sample_sha256':sample_sha,'response_sha256':response_sha,
            'value_pointer':pointer+'/value' if pointer else None,'languages_pointer':pointer+'/languages' if pointer else None,
            'value_sha256':hashlib.sha256(value.encode()).hexdigest() if value is not None else None,'fallback_reason':failure}
        registry.append({'catalog_index':index,'entity_id':movie['entity_id'],'kind':'SOURCE_EXTRACT' if value is not None else 'RETRIEVAL_CONTEXT',
            'verification':'SOURCE_BOUND_NOT_FACT_CHECKED','text':value if value is not None else FALLBACK,'provider_cause_verified':False,'evidence':evidence})
    return registry


def validate_registry(catalog,registry):
    _need(isinstance(registry,list) and len(registry)==len(catalog),'complete registry')
    for index,(movie,reason) in enumerate(zip(catalog,registry)):
        _need(isinstance(reason,dict) and set(reason)==REASON_KEYS and type(reason['catalog_index']) is int and reason['catalog_index']==index
            and reason['entity_id']==movie['entity_id'] and reason['verification']=='SOURCE_BOUND_NOT_FACT_CHECKED' and reason['provider_cause_verified'] is False,'closed bound explanation')
        evidence=reason['evidence']
        _need(isinstance(evidence,dict) and set(evidence)==EVIDENCE_KEYS and type(evidence['schema_version']) is int and evidence['schema_version']==1
            and evidence['renderer']==RENDERER and evidence['catalog_index']==index and type(evidence['catalog_index']) is int
            and evidence['entity_id']==movie['entity_id'] and evidence['title']==movie['name'] and type(evidence['release_year']) is int and evidence['release_year']==movie['release_year']
            and type(evidence['page']) is int and evidence['page'] in (1,2) and type(evidence['position']) is int and 0<=evidence['position']<50
            and all(isinstance(evidence[k],str) and re.fullmatch('[a-f0-9]{64}',evidence[k]) for k in ('sample_sha256','response_sha256')),'closed source identity')
        if reason['kind']=='SOURCE_EXTRACT':
            base=f"/response/results/entities/{evidence['position']}/properties/short_descriptions/"
            _need(evidence['source']=='QLOO_OBSERVED' and evidence['language'] in ('es','en') and evidence['fallback_reason'] is None
                and _literal(reason['text']) and evidence['value_sha256']==hashlib.sha256(reason['text'].encode()).hexdigest()
                and isinstance(evidence['value_pointer'],str) and re.fullmatch(re.escape(base)+r'(0|[1-9][0-9]?)/value',evidence['value_pointer'])
                and evidence['languages_pointer']==evidence['value_pointer'][:-5]+'languages','literal source fields')
        else:
            _need(reason['kind']=='RETRIEVAL_CONTEXT' and reason['text']==FALLBACK and evidence['source']=='RETRIEVAL_CONTEXT'
                and evidence['fallback_reason'] in ('MISSING','MALFORMED','AMBIGUOUS','UNSAFE') and evidence['language'] is None
                and evidence['value_pointer'] is None and evidence['languages_pointer'] is None and evidence['value_sha256'] is None,'closed no-plot fallback')
    return copy.deepcopy(registry)


def display_for_receipt(directory,receipt,receipt_sha256):
    """Caller must first validate the owned original receipt and full inventory."""
    directory=checked_path(Path(directory));result=receipt['wide_cinema_results'];inventory=receipt['artifact_sha256']
    _need(isinstance(result,dict) and isinstance(receipt_sha256,str) and re.fullmatch('[a-f0-9]{64}',receipt_sha256),'original complete receipt')
    def read_owned(name):
        _need(isinstance(name,str) and '/' not in name and '\\' not in name and name in inventory,'closed captured basename')
        path=checked_path(directory/name)
        _need(path.parent==directory and sha(path)==inventory[name],'original captured file hash')
        return strict_json(path.read_bytes())
    context=read_owned('wide-context.json')
    _need(context['context_sha256']==fingerprint({k:v for k,v in context.items() if k!='context_sha256'})
        and context['candidate_catalog']==result['candidate_catalog'] and len(context['pages'])==2,'original context binding')
    samples=[]
    for page,ref in enumerate(context['pages'],1):
        names=[name for name,digest in inventory.items() if re.fullmatch(r'http-[0-9]{4}\.json',name) and digest==ref['sample_sha256']]
        _need(ref['page']==page and len(names)==1,'one original sample per page')
        sample=read_owned(names[0])
        _need(sample['status']==200 and sample['request']['path']=='/v2/insights' and sample['request']['params']['page']==page
            and sample['response_sha256']==ref['response_sha256'] and fingerprint(sample['response'])==ref['response_sha256'],'bound page response')
        samples.append({'sample':sample,'sample_sha256':ref['sample_sha256']})
    registry=grounding_registry(result['candidate_catalog'],samples)
    validate_registry(result['candidate_catalog'],registry)
    indices={movie['entity_id']:i for i,movie in enumerate(result['candidate_catalog'])}
    reasons=[registry[indices[value]] for value in result['delivered']]
    legacy=receipt['protocol_version']!='qloo-wide-cinema-discovery-v9'
    value={'schema_version':1,'renderer_version':DISPLAY,'receipt_sha256':receipt_sha256,'protocol_version':receipt['protocol_version'],
        'delivered':copy.deepcopy(result['delivered']),'reasons':reasons,'legacy_original_archived':legacy,
        'notice':ARCHIVED_NOTICE if legacy else CURRENT_NOTICE,'integrity':'SOURCE_BOUND'}
    value['binding_sha256']=fingerprint(value)
    return value
