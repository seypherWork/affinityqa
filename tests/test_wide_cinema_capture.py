"""Synthetic offline pages, real durable runtime and bounded model transport."""
import copy
from email.message import Message
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.errors import SchemaError, TransportError
from affinityqa.agents import AgentError
from affinityqa.evidence import fingerprint
from affinityqa.qloo import Settings,Response
from affinityqa.provider_runtime import ProviderRuntime
from affinityqa.wide_cinema_tokens import WideHarmonyTokenEstimator
from affinityqa.provider_scheduler import ProviderScheduler,QuotaWindow,ProviderUncertain,ProviderRecordedFailure
from affinityqa.wide_cinema_discovery import MODEL,context_from_samples,qloo_request,make_decision
from affinityqa.wide_cinema_agent import WideCinemaAgent,failure_projection,validate_failure_projection
from affinityqa.wide_cinema_capture import prepare_plan,search_identities,capture_confirmed,WideCinemaClient
from affinityqa.wide_cinema_verify import verify_identity_search,verify_discoveries

UNIT_SECRET = 'unit-wide-model-private-credential'
QLOO_SECRET = 'unit-wide-qloo-private-credential'
SEED_ID = str(UUID(int=10000));ARTIST_ID = str(UUID(int=20000));FAVORITE_ID = str(UUID(int=10001))


def request_fixture(mode='movie',favorite=False,**changes):
    value = {'schema_version':9,'mode':mode,'seed_query':'Synthetic seed 2000' if mode == 'movie' else 'Synthetic musician',
        'favorite_movie_query':'Synthetic favorite 2001' if favorite else None,'intent_text':'','excluded_entity_ids':[],'model':dict(MODEL)}
    value.update(changes);return value


def movie_row(i):
    entity_id = str(UUID(int=i))
    return {'entity_id':entity_id,'name':f'Synthetic film {i}','types':['urn:entity:movie'],
        'properties':{'release_year':1950+i,'short_descriptions':[{'languages':['es'],'value':f'Ficha sintética de la película {i}: una descripción de ejemplo vinculada exclusivamente a este registro de prueba.'}],'image':{'url':f'https://images.qloo.com/i/{entity_id.upper()}-420x-auto.jpg'}},
        'query':{'affinity':round(1-i/200,4)}}


class WideTransport:
    def __init__(self,*,pages=None,page_status=None,mutation=None,search_mutation=None,failure=None):
        self.pages = pages or {1:list(range(1,51)),2:list(range(51,101))}
        self.page_status = page_status or {};self.mutation,self.search_mutation,self.failure = mutation,search_mutation,failure;self.calls = []
    def send(self,path,params):
        self.calls.append((path,copy.deepcopy(params)))
        if self.failure is not None:raise self.failure
        if path == '/search':
            if params['types'] != 'urn:entity:movie':row = {'entity_id':ARTIST_ID,'name':'Synthetic musician','types':['urn:entity:artist'],'properties':{}}
            else:
                favorite = params['query'] == 'Synthetic favorite 2001'
                row = {'entity_id':FAVORITE_ID if favorite else SEED_ID,'name':'Synthetic favorite' if favorite else 'Synthetic seed',
                    'types':['urn:entity:movie'],'properties':{'release_year':2001 if favorite else 2000}}
            body = {'results':[row]}
            if self.search_mutation:self.search_mutation(body,params)
            return Response(200,body,{},1)
        if path != '/v2/insights':raise AssertionError('Unreviewed endpoint')
        page = params['page'];body = {'success':True,'results':{'entities':[movie_row(i) for i in self.pages[page]]}}
        if self.mutation:self.mutation(body,page)
        status = self.page_status.get(page,200)
        return Response(status,body if status == 200 else {'synthetic_error':True},{},1.25)


class ModelResponse(io.BytesIO):
    def __init__(self,body):
        super().__init__(json.dumps(body).encode());self.status = 200;self.headers = Message();self.headers['Content-Type'] = 'application/json'


class WideOpener:
    def __init__(self,mutation=None,failure=None):self.calls=[];self.mutation,self.failure=mutation,failure
    def open(self,request,timeout):
        wire = json.loads(request.data);self.calls.append((request,wire,timeout))
        if self.failure is not None:raise self.failure
        data = json.loads(wire['messages'][1]['content']);rows = data['candidates']
        selected = rows[:5] if data['intent_text'] else list(reversed(rows))[:5]
        reasons = [{'catalog_index':r['catalog_index']} for r in selected]
        body = {'id':'synthetic-wide-completion','object':'chat.completion','created':1791280000,'model':MODEL['name'],'system_fingerprint':'synthetic-wide',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps({'ordered_catalog_indices':reasons})}}],
            'usage':{'prompt_tokens':1000,'completion_tokens':300,'total_tokens':1300,'completion_tokens_details':{'reasoning_tokens':10}}}
        if self.mutation:self.mutation(body)
        return ModelResponse(body)


def seed_fixture(mode='movie'):
    return {'entity_id':SEED_ID,'name':'Synthetic seed','type':'urn:entity:movie','release_year':2000} if mode == 'movie' else {'entity_id':ARTIST_ID,'name':'Synthetic musician','type':'urn:entity:artist'}


def context_fixture(mode='movie',favorite=False,transport=None):
    seed=seed_fixture(mode);fav={'entity_id':FAVORITE_ID,'name':'Synthetic favorite','type':'urn:entity:movie','release_year':2001} if favorite else None
    transport=transport or WideTransport();samples=[]
    for page in (1,2):
        http=qloo_request(mode,seed,fav,page);r=transport.send(http['path'],http['params'])
        sample={'source':'test-double-only','request':http,'status':r.status,'response':r.body,'response_sha256':fingerprint(r.body),'response_headers':{},
            'elapsed_ms':r.elapsed_ms,'attempt':1,'live_network_request':False}
        samples.append({'sample':sample,'sample_sha256':fingerprint(sample)})
    return context_from_samples(mode,seed,fav,samples)


class WideCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT.parent);self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.settings=Settings(QLOO_SECRET);self.estimator=WideHarmonyTokenEstimator(ROOT/'assets/tokenizers/o200k_base.tiktoken')
        self.scheduler=ProviderScheduler(self.base/'provider.sqlite3',limits={'qloo':(QuotaWindow('rpm',1000,60),),
            'groq':(QuotaWindow('rpm',1000,60),QuotaWindow('tpm',1000000,60,'tokens'))})
        self.transport=WideTransport();self.opener=WideOpener()
        for name in ('socket.socket','socket.create_connection','socket.getaddrinfo'):
            guard=patch(name,side_effect=AssertionError('Real network/DNS forbidden'));guard.start();self.addCleanup(guard.stop)
    def runtime(self):
        return ProviderRuntime(self.scheduler,'synthetic-'+self.output.name,'synthetic-owner',namespace={'request':self.request},token_estimator=self.estimator)
    def adapters(self):
        return (lambda:WideCinemaAgent(UNIT_SECRET,_test_opener=self.opener,forbidden_secrets=(QLOO_SECRET,),token_estimator=self.estimator),lambda:self.transport)
    def search(self,request=None,transport=None):
        self.request=request or request_fixture();self.transport=transport or self.transport
        self.output=self.base/('capture-'+str(len(list(self.base.glob('capture-*')))));self.plan=prepare_plan(self.request,self.output)
        with self.runtime().activate('identity-search'):
            report,self.directory=search_identities(self.request,self.output,self.plan['plan_sha256'],self.settings,_test_adapters=self.adapters())
        return report,verify_identity_search(self.directory)
    def finish(self,request=None,transport=None):
        _,receipt=self.search(request,transport)
        with self.runtime().activate('capture'):
            report,_=capture_confirmed(self.directory,SEED_ID if self.request['mode']=='movie' else ARTIST_ID,receipt,self.settings,UNIT_SECRET,
                selected_favorite_movie_entity_id=FAVORITE_ID if self.request['favorite_movie_query'] else None,_test_adapters=self.adapters())
        return report,verify_discoveries(self.directory)
    def test_movie100_actual_candidates_three_qloo_one_model(self):
        report,receipt=self.finish();result=receipt['wide_cinema_results']
        self.assertEqual((report['status'],receipt['verification_status']),('COMPLETE','VERIFIED_COMPLETE'))
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,1));self.assertEqual(result['candidate_count'],100)
        self.assertEqual(len(result['delivered']),5);self.assertEqual(len(result['presentation_assets']),100)
        self.assertNotEqual(result['delivered'],result['baseline_delivered']);self.assertEqual(receipt['provenance'],'SIMULATION_ONLY')
        self.assertEqual([p['page'] for path,p in self.transport.calls if path=='/v2/insights'],[1,2])
        self.assertTrue(all('filter.results.entities' not in p for path,p in self.transport.calls))
    def test_music_without_and_with_one_favorite_has_exact_budget(self):
        for favorite in (False,True):
            with self.subTest(favorite=favorite):
                self.transport=WideTransport();self.opener=WideOpener()
                report,receipt=self.finish(request_fixture('music',favorite))
                self.assertEqual(receipt['verification_status'],'VERIFIED_COMPLETE');self.assertEqual(report['qloo_attempts'],4 if favorite else 3)
                result=receipt['wide_cinema_results'];self.assertEqual(result['seed_identity']['entity_id'],ARTIST_ID)
                self.assertEqual(result['known_favorite_movie'] is not None,favorite)
                self.assertNotIn(FAVORITE_ID,result['delivered']);self.assertEqual(len(self.opener.calls),1)
    def test_overlap_deduplicates_consistent_uuid_and_retains_raw_counts(self):
        _,receipt=self.finish(transport=WideTransport(pages={1:list(range(1,51)),2:list(range(41,91))}))
        result=receipt['wide_cinema_results'];self.assertEqual((result['provider_rows_count'],result['candidate_count'],result['deduplicated_rows_count']),(100,90,10))
    def test_missing_year_rows_are_preserved_rejected_and_not_invented(self):
        def mutate(body,page):body['results']['entities'][0]['properties'].pop('release_year')
        _,receipt=self.finish(transport=WideTransport(mutation=mutate));result=receipt['wide_cinema_results']
        self.assertEqual((result['provider_rows_count'],result['candidate_count'],result['rejected_rows_count']),(100,98,2))
        self.assertNotIn(str(UUID(int=1)),result['delivered'])
    def test_below_five_eligible_stops_before_model(self):
        report,receipt=self.finish(request_fixture(excluded_entity_ids=[str(UUID(int=1))]),transport=WideTransport(pages={1:[1,2,3,4,5],2:[]}))
        self.assertEqual((report['model_attempts'],receipt['verification_status'],len(self.opener.calls)),(0,'VERIFIED_PARTIAL',0))
    def test_first_bad_page_stops_before_second_page(self):
        def mutate(body,page):body['results']['entities'][0]['entity_id']='invalid'
        _,receipt=self.search(transport=WideTransport(mutation=mutate))
        with self.runtime().activate('capture'):
            capture_confirmed(self.directory,SEED_ID,receipt,self.settings,UNIT_SECRET,_test_adapters=self.adapters())
        receipt=verify_discoveries(self.directory)
        self.assertEqual(receipt['verification_status'],'VERIFIED_PARTIAL');self.assertEqual(len(self.transport.calls),2);self.assertEqual(len(self.opener.calls),0)
    def test_http_error_never_retries_or_uses_first_page_as_complete(self):
        _,receipt=self.search(transport=WideTransport(page_status={2:429}))
        with self.runtime().activate('capture'),self.assertRaises(ProviderRecordedFailure):
            capture_confirmed(self.directory,SEED_ID,receipt,self.settings,UNIT_SECRET,_test_adapters=self.adapters())
        receipt=verify_discoveries(self.directory);self.assertEqual((receipt['verification_status'],receipt['qloo_attempts'],receipt['model_attempts']),('VERIFIED_PARTIAL',3,0))
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,0))
    def test_actual100row_wire_includes_contract_under_cap_without_uuid_or_urls(self):
        self.finish();wire=self.opener.calls[0][1];payload=json.loads(wire['messages'][1]['content']);serialized=json.dumps(payload)
        self.assertEqual(len(payload['candidates']),100);self.assertNotIn('https://',serialized);self.assertNotIn(SEED_ID,serialized)
        self.assertIn('output_contract',payload);self.assertNotIn('entity_id',serialized)
        reservation=self.estimator.estimate(json.dumps(wire,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())
        self.assertLessEqual(reservation['tokens'],8000)
    def test_v10_http400_is_one_fixed_text_send_without_fallback_or_resume(self):
        error=HTTPError('https://api.groq.com/openai/v1/chat/completions',400,'synthetic rejection',Message(),
            io.BytesIO(b'{"error":{"message":"PRIVATE_FAILED_GENERATION_CANARY","code":"json_validate_failed"}}'))
        self.opener=WideOpener(failure=error);report,receipt=self.finish()
        self.assertEqual((report['status'],receipt['verification_status'],receipt['verified_model_packets']),('INCOMPLETE','VERIFIED_PARTIAL',0))
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,1))
        transport=self.opener.calls[0][1]['response_format']
        self.assertEqual(transport,{'type':'text'})
        self.assertEqual(receipt['model_rejection']['code'],'COMPLETION_REJECTED')
        self.assertFalse((self.directory/'wide-execution-001.json').exists())
        for name in ('wide-model-rejection.json','ledger.jsonl'):
            self.assertNotIn('PRIVATE_FAILED_GENERATION_CANARY',(self.directory/name).read_text(encoding='utf8'))
        with self.runtime().activate('capture'),self.assertRaises(Exception):
            capture_confirmed(self.directory,SEED_ID,receipt,self.settings,UNIT_SECRET,_test_adapters=self.adapters())
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),(3,1))
    def test_v10_independent_verifier_binds_contract_and_keeps_all_choice_guards(self):
        from affinityqa.wide_cinema_verify import verify_packet
        from affinityqa.wide_cinema_discovery import output_schema
        self.finish();packet=json.loads((self.directory/'wide-execution-001.json').read_bytes())
        manifest=json.loads((self.directory/'wide-model-manifest.json').read_bytes());decision=packet['effective_request']
        self.assertEqual(verify_packet(packet,manifest,decision)['ranking'],packet['response']['ranked_entity_ids'])
        self.assertTrue(all(set(row)=={'catalog_index'}
            for row in packet['observation']['provider_envelope']['choice']['ordered_catalog_indices']))
        self.assertNotIn('reasons',packet['response']);self.assertTrue(all(set(row)=={'catalog_index'} for row in packet['response']['selected_catalog_indices']))
        oldwire=copy.deepcopy(self.opener.calls[0][1]);oldwire['response_format']={'type':'json_schema'}
        forged=copy.deepcopy(packet);forged['observation']['provider_request_sha256']=fingerprint(oldwire)
        with self.assertRaises(SchemaError):verify_packet(forged,manifest,decision)
        for changed in ({'type':'text','extra':True},{'type':'json_schema'},{'type':'json_object'},None):
            forged_manifest=copy.deepcopy(manifest);forged_manifest['provider_response_format']=changed
            with self.subTest(mode=changed),self.assertRaises(SchemaError):verify_packet(packet,forged_manifest,decision)
        changes=[lambda b:b.pop(),lambda b:b.append(copy.deepcopy(b[0])),lambda b:b[0].update(catalog_index=True),
            lambda b:b[0].update(catalog_index=-1),lambda b:b[1].update(catalog_index=b[0]['catalog_index']),
            lambda b:b[0].update(title='Wrong target'),lambda b:b[0].update(release_year=2000),
            lambda b:b[0].update(release_year='2000'),
            lambda b:b[0].update(text='Spider-Man (2002): This explanation names a different movie target.'),
            lambda b:b[0].update(text='  Synthetic archived prose'),
            lambda b:b[0].update(text='Ｓｙｎｔｈｅｔｉｃ prose must not be accepted'),
            lambda b:b[0].update(text='short'),lambda b:b[0].update(text='x'*241),
            lambda b:b[0].update(text=' '*1000+'Raw reason remains outside its unchanged bound.'),
            lambda b:b[0].update(text='An unsafe control must remain rejected by the verifier.\x00'),
            lambda b:b[0].update(cultural_gate='VALIDATED'),lambda b:b[0].update(text='  A normalized but untrimmed explanation must be rejected on disk.  ')]
        for change in changes:
            forged=copy.deepcopy(packet);change(forged['observation']['provider_envelope']['choice']['ordered_catalog_indices'])
            with self.subTest(change=change),self.assertRaises(SchemaError):verify_packet(forged,manifest,decision)
    def test_receipt_modified_selection_or_asset_url_rejected(self):
        self.finish();path=self.directory/'wide-result.json';original=path.read_bytes();value=json.loads(original)
        value['presentation_assets'][0]['url']='https://example.invalid/foreign.jpg';path.write_text(json.dumps(value),encoding='utf8')
        with self.assertRaises(SchemaError):verify_discoveries(self.directory)
        path.write_bytes(original);value=json.loads(original);value['delivered'][0]=SEED_ID;path.write_text(json.dumps(value),encoding='utf8')
        with self.assertRaises(SchemaError):verify_discoveries(self.directory)
    def test_scope_requires_active_runtime_before_creating_capture(self):
        request=request_fixture();output=self.base/'no-runtime';plan=prepare_plan(request,output)
        with self.assertRaises(SchemaError):search_identities(request,output,plan['plan_sha256'],self.settings,_test_adapters=self.adapters())
        self.assertFalse(output.exists());self.assertEqual(self.transport.calls,[])
    def test_client_itself_rejects_unbounded_or_mismatched_reviewed_requests(self):
        pages=[qloo_request('movie',seed_fixture(),None,page) for page in (1,2)]
        search=[{'method':'GET','host':'https://hackathon.api.qloo.com','path':'/search',
                 'params':{'query':'Synthetic seed 2000','types':'urn:entity:movie','take':5}}]
        WideCinemaClient(self.transport,None,pages,testing=True,maximum=3,initial=1)
        WideCinemaClient(self.transport,None,search,testing=True,maximum=3)
        invalid=[]
        for key,value in (('take',100),('take',True),('page',True),('page',3),
                          ('filter.type','urn:entity:artist'),('filter.results.entities',SEED_ID),
                          ('signal.interests.entities','invalid'),('filter.exclude.entities',FAVORITE_ID)):
            changed=copy.deepcopy(pages);changed[0]['params'][key]=value;invalid.append((changed,3,1))
        changed=copy.deepcopy(pages);changed[0]['host']='https://example.invalid';invalid.append((changed,3,1))
        changed=copy.deepcopy(pages);changed[0]['path']='/unreviewed';invalid.append((changed,3,1))
        invalid.extend(((list(reversed(pages)),3,1),(pages,4,1),(pages,3,0),(pages[:1],3,1)))
        for key,value in (('take',True),('take',50),('types','urn:entity:album'),('extra','not-reviewed')):
            changed=copy.deepcopy(search);changed[0]['params'][key]=value;invalid.append((changed,3,0))
        invalid.extend(((search,4,0),(search,3,1),(search*2,4,0)))
        for requests,maximum,initial in invalid:
            with self.subTest(requests=requests,maximum=maximum,initial=initial),self.assertRaises(SchemaError):
                WideCinemaClient(self.transport,None,requests,testing=True,maximum=maximum,initial=initial)
        self.assertEqual(self.transport.calls,[])
    def test_rejected_model_records_only_safe_guard_projection_and_stays_failed(self):
        def mutate(body):
            value=json.loads(body['choices'][0]['message']['content']);value['ordered_catalog_indices'][0]['text']='sensitive rejected explanation'
            body['choices'][0]['message']['content']=json.dumps(value)
        self.opener=WideOpener(mutation=mutate);report,receipt=self.finish()
        self.assertEqual((report['status'],receipt['verification_status']),('INCOMPLETE','VERIFIED_PARTIAL'))
        path=self.directory/'wide-model-rejection.json';self.assertTrue(path.is_file())
        diagnostic=json.loads(path.read_bytes());self.assertEqual((diagnostic['stage'],diagnostic['code']),('OUTPUT','OUTPUT_CHOICE_SHAPE'))
        self.assertEqual(diagnostic['reported_usage']['completion_tokens'],300)
        self.assertNotIn('sensitive rejected explanation',path.read_text(encoding='utf8'))
        self.assertFalse((self.directory/'wide-execution-001.json').exists())
        import sqlite3
        db=sqlite3.connect(self.base/'provider.sqlite3')
        try:self.assertEqual(db.execute("SELECT state,result FROM operations WHERE provider='groq'").fetchone(),('FAILED',None))
        finally:db.close()
        before=(len(self.transport.calls),len(self.opener.calls))
        with self.runtime().activate('capture'),self.assertRaises(Exception):
            capture_confirmed(self.directory,SEED_ID,receipt,self.settings,UNIT_SECRET,_test_adapters=self.adapters())
        self.assertEqual((len(self.transport.calls),len(self.opener.calls)),before)
    def test_each_output_and_envelope_guard_has_closed_numeric_diagnostic(self):
        def output_change(change):
            def mutate(body):
                value=json.loads(body['choices'][0]['message']['content']);change(value)
                body['choices'][0]['message']['content']=json.dumps(value)
            return mutate
        cases=[
            ('OUTPUT_TOP_LEVEL',output_change(lambda v:v.update(extra='never persist this field'))),
            ('OUTPUT_COUNT',output_change(lambda v:v['ordered_catalog_indices'].pop())),
            ('OUTPUT_CHOICE_SHAPE',output_change(lambda v:v['ordered_catalog_indices'][0].update(extra='never persist this value'))),
            ('OUTPUT_INDEX_TYPE',output_change(lambda v:v['ordered_catalog_indices'][0].update(catalog_index=True))),
            ('OUTPUT_INDEX_ELIGIBILITY',output_change(lambda v:v['ordered_catalog_indices'][0].update(catalog_index=10001))),
            ('OUTPUT_INDEX_DUPLICATE',output_change(lambda v:v['ordered_catalog_indices'][1].update(catalog_index=v['ordered_catalog_indices'][0]['catalog_index']))),
            ('OUTPUT_CHOICE_SHAPE',output_change(lambda v:v['ordered_catalog_indices'][0].update(title='PRIVATE_WRONG_TITLE_CANARY'))),
            ('OUTPUT_CHOICE_SHAPE',output_change(lambda v:v['ordered_catalog_indices'][0].update(release_year=1888))),
            ('OUTPUT_CHOICE_SHAPE',output_change(lambda v:v['ordered_catalog_indices'][0].update(text='PRIVATE_WRONG_TARGET_CANARY names a different film in this reason.'))),
            ('OUTPUT_CHOICE_SHAPE',output_change(lambda v:v['ordered_catalog_indices'][0].update(text=42))),
            ('OUTPUT_CHOICE_SHAPE',output_change(lambda v:v['ordered_catalog_indices'][0].update(text=' '*1000+'A synthetic interpretation that must never be persisted.'))),
            ('OUTPUT_CHOICE_SHAPE',output_change(lambda v:v['ordered_catalog_indices'][0].update(text='A synthetic interpretation with an unsafe zero byte\x00 in the explanation.'))),
            ('OUTPUT_CHOICE_SHAPE',output_change(lambda v:v['ordered_catalog_indices'][0].update(text='too short'))),
            ('ENVELOPE_IDENTITY',lambda b:b.update(model='another-model')),
            ('COMPLETION_IDENTITY',lambda b:b.update(id=None)),
            ('CHOICE_SHAPE',lambda b:b.update(choices=[])),
            ('FINISH_REASON',lambda b:b['choices'][0].update(finish_reason='length')),
            ('FINAL_MESSAGE',lambda b:b['choices'][0]['message'].update(reasoning='PRIVATE_REASONING_CANARY_DO_NOT_RECORD')),
            ('OUTPUT_JSON',lambda b:b['choices'][0]['message'].update(content='rejected free-form prose must not be stored')),
            ('USAGE_SHAPE',lambda b:b['usage'].update(prompt_tokens=True)),
            ('USAGE_REASONING',lambda b:b['usage']['completion_tokens_details'].update(reasoning_tokens=True)),
            ('PROVIDER_FINGERPRINT',lambda b:b.update(system_fingerprint='invalid fingerprint whitespace')),
            ('COMPLETION_REJECTED',lambda b:b.update(id=UNIT_SECRET)),
        ]
        for code,mutation in cases:
            with self.subTest(code=code):
                self.transport=WideTransport();self.opener=WideOpener(mutation=mutation)
                report,receipt=self.finish();diagnostic=receipt['model_rejection']
                self.assertEqual((report['status'],receipt['verification_status'],diagnostic['code']),('INCOMPLETE','VERIFIED_PARTIAL',code))
                self.assertFalse(diagnostic['accepted']);self.assertEqual(receipt['verified_model_packets'],0)
                artifact=(self.directory/'wide-model-rejection.json').read_text(encoding='utf8')
                for marker in ('PRIVATE_REASONING_CANARY','never persist','rejected free-form prose',UNIT_SECRET,QLOO_SECRET):
                    self.assertNotIn(marker,artifact)
    def test_reported_usage_above_reservation_is_retained_only_as_rejection(self):
        def mutate(body):body['usage'].update(prompt_tokens=8192,total_tokens=8492)
        self.opener=WideOpener(mutation=mutate);report,receipt=self.finish()
        self.assertEqual(receipt['model_rejection']['code'],'USAGE_RESERVATION')
        self.assertEqual(receipt['model_rejection']['reported_usage']['prompt_tokens'],8192)
        self.assertEqual((receipt['verified_model_packets'],report['status']),(0,'INCOMPLETE'))
    def test_finish_length_with_actual2048_completion_is_diagnostic_never_accepted(self):
        def mutate(body):
            body['choices'][0].update(finish_reason='length');body['usage'].update(completion_tokens=2048,total_tokens=3048)
        self.opener=WideOpener(mutation=mutate);report,receipt=self.finish();diagnostic=receipt['model_rejection']
        self.assertEqual((diagnostic['finish_reason'],diagnostic['reported_usage']['completion_tokens']),('LENGTH',2048))
        self.assertEqual((diagnostic['code'],receipt['verified_model_packets'],report['status']),('FINISH_REASON',0,'INCOMPLETE'))
    def test_arbitrary_schema_error_suffix_is_not_a_persisted_diagnostic_code(self):
        with patch('affinityqa.wide_cinema_agent.validate_output',side_effect=SchemaError('Wide cinema output: '+UNIT_SECRET)):
            _,receipt=self.finish()
        self.assertEqual(receipt['verification_status'],'VERIFIED_PARTIAL')
        self.assertEqual(receipt['model_rejection']['code'],'OUTPUT_VALIDATION')
        for path in (self.directory/'wide-model-rejection.json',self.directory/'ledger.jsonl'):
            self.assertNotIn(UNIT_SECRET,path.read_text(encoding='utf8'))
        self.assertEqual(receipt['verified_model_packets'],0)
    def test_projection_and_capture_reject_arbitrary_stages_before_persisting(self):
        with self.assertRaises(Exception):
            failure_projection({},None,UNIT_SECRET,'COMPLETION_REJECTED',None,None,None)
        # Even a substituted projection cannot carry arbitrary text into the ledger.
        def mutate(body):
            value=json.loads(body['choices'][0]['message']['content']);value['ordered_catalog_indices'][0]['text']='short'
            body['choices'][0]['message']['content']=json.dumps(value)
        self.opener=WideOpener(mutation=mutate)
        with patch('affinityqa.wide_cinema_agent.failure_projection',return_value={'stage':'UNREVIEWED_PRIVATE_STAGE_CANARY'}):
            _,receipt=self.finish()
        self.assertEqual(receipt['verification_status'],'VERIFIED_PARTIAL');self.assertEqual(receipt['verified_model_packets'],0)
        self.assertFalse((self.directory/'wide-model-rejection.json').exists())
        self.assertNotIn('UNREVIEWED_PRIVATE_STAGE_CANARY',(self.directory/'ledger.jsonl').read_text(encoding='utf8'))
    def test_decoded_nonobject_response_hash_is_valid_safe_rejection_with_zero_sends(self):
        from affinityqa.wide_cinema_verify import _rejection
        decision=make_decision(request_fixture(),context_fixture(),'synthetic-nonobject')
        for body in ([],None):
            with self.subTest(body=body):
                opener=WideOpener();engine=WideCinemaAgent(UNIT_SECRET,_test_opener=opener,token_estimator=self.estimator)
                with patch.object(engine,'_completion',return_value=(body,fingerprint(body))),self.assertRaises(AgentError):
                    engine.rank(decision)
                diagnostic=engine.last_rejection
                self.assertTrue(diagnostic['body_parsed']);self.assertEqual(diagnostic['provider_response_sha256'],fingerprint(body))
                self.assertEqual((diagnostic['stage'],diagnostic['code'],diagnostic['finish_reason']),('ENVELOPE','ENVELOPE_IDENTITY','MISSING'))
                validate_failure_projection(diagnostic,decision,engine.last_prepared)
                _rejection(diagnostic,decision,engine.last_prepared)
                self.assertEqual(opener.calls,[])
    def test_rejection_diagnostic_cannot_forge_extra_fields_acceptance_or_constraints(self):
        def mutate(body):
            value=json.loads(body['choices'][0]['message']['content']);value['ordered_catalog_indices'][0]['text']='short'
            body['choices'][0]['message']['content']=json.dumps(value)
        self.opener=WideOpener(mutation=mutate);self.finish()
        path=self.directory/'wide-model-rejection.json';ledger=self.directory/'ledger.jsonl'
        original=path.read_bytes();original_ledger=ledger.read_bytes()
        for change in (lambda d:d.update(rejected_text='must not be admitted'),lambda d:d.update(accepted=True),
                lambda d:d.update(code='UNKNOWN_UNREVIEWED'),lambda d:d['reason_lengths'].__setitem__(0,'private text'),
                lambda d:d['indices_eligible'].__setitem__(0,False),lambda d:d.update(stage='USAGE')):
            value=json.loads(original);change(value);path.write_text(json.dumps(value),encoding='utf8')
            events=[json.loads(line) for line in original_ledger.splitlines()]
            event=next(e for e in events if e['kind']=='wide_model_rejected')
            event['data'].update(sha256=__import__('hashlib').sha256(path.read_bytes()).hexdigest(),stage=value['stage'],code=value['code'])
            ledger.write_text(''.join(json.dumps(e)+'\n' for e in events),encoding='utf8')
            with self.subTest(change=change),self.assertRaises(SchemaError):verify_discoveries(self.directory)
            path.write_bytes(original);ledger.write_bytes(original_ledger)
        fake=self.directory/'wide-execution-001.json';fake.write_text('{}',encoding='utf8')
        with self.assertRaises(SchemaError):verify_discoveries(self.directory)
    def test_exact_indices_survive_actual_accepted_operation_reconstruction(self):
        _,receipt=self.finish()
        self.assertEqual(receipt['verification_status'],'VERIFIED_COMPLETE');self.assertIsNone(receipt['model_rejection'])
        packet=json.loads((self.directory/'wide-execution-001.json').read_bytes());block=packet['observation']['provider_envelope']['choice']['ordered_catalog_indices']
        self.assertEqual(len(block),5);self.assertTrue(all(set(row)=={'catalog_index'} for row in block))
        self.assertFalse((self.directory/'wide-model-rejection.json').exists())
        opener=WideOpener(failure=AssertionError('Accepted reconstruction must not send'))
        engine=WideCinemaAgent(UNIT_SECRET,_test_opener=opener,token_estimator=self.estimator);runtime=self.runtime()
        with runtime.activate('capture'):response=engine.rank(packet['effective_request'])
        self.assertEqual(response,packet['response']);self.assertEqual(engine.observations[-1],packet['observation'])
        self.assertEqual((len(opener.calls),runtime.counters['exact_reconstructions']),(0,1))



    def test_private_model_marker_in_saved_plan_stops_before_confirmation_or_adapters(self):
        from unittest.mock import Mock
        _, receipt = self.search(request_fixture(intent_text=UNIT_SECRET))
        before_files = {p.name: p.read_bytes() for p in self.directory.iterdir() if p.is_file()}
        before_calls = (len(self.transport.calls), len(self.opener.calls))
        adapters = tuple(Mock(wraps=factory) for factory in self.adapters())
        with self.runtime().activate('capture'):
            with self.assertRaisesRegex(SchemaError, r'Provider secrets must remain private\.'):
                capture_confirmed(self.directory, SEED_ID, receipt, self.settings, UNIT_SECRET,
                                  _test_adapters=adapters)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), before_calls)
        self.assertEqual(before_calls, (1, 0))
        for factory in adapters:
            factory.assert_not_called()
        self.assertFalse((self.directory / 'wide-confirmation.json').exists())
        self.assertEqual({p.name: p.read_bytes() for p in self.directory.iterdir() if p.is_file()}, before_files)

if __name__=='__main__':unittest.main()
