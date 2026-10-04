"""Synthetic unit fixtures only: no network, model, or real-run receipt evidence."""
import copy,math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from affinityqa.causal_agent import (FAULTS,profile_hash,validate_catalog,context_from_sample,validate_context,make_request,ToolContextMovieAgent,ExecutionRecorder,CausalMovieSession,diagnose)
from affinityqa.evidence import fingerprint
from affinityqa.errors import SchemaError
from affinityqa.agents import AgentError


class FakeLedger:
    run_id='synthetic-unit-only'
    def __init__(self):self.files={};self.events=[]
    def write(self,name,data):
        if name in self.files:raise AssertionError('Unit ledger overwrite')
        self.files[name]=copy.deepcopy(data)
    def record(self,name,data):self.events.append((name,copy.deepcopy(data)))


class FakeEngine:
    """Deterministic synthetic decisions expose both profile and tool payload."""
    def __init__(self):
        self.manifest={'source':'synthetic-unit-only','model':'no-real-inference'};self.observations=[];self.last_input=None;self.calls=0;self.damage=None
        self.adapter=ToolContextMovieAgent.__new__(ToolContextMovieAgent)
    def rank(self,request):
        self.calls+=1;self.last_input=self.adapter.decision_input(request,{'type':'object'})
        ids=[r['entity_id'] for r in request['catalog']]
        ranking=[ids[row['catalog_index']] for row in self.last_input['provider_movie_context']]
        if self.damage=='short':ranking=ranking[:5]
        if self.damage=='tail-duplicate':ranking[-1]=ranking[0]
        if self.damage=='outside':ranking[-1]='ffffffff-ffff-4fff-8fff-ffffffffffff'
        observation={'call':self.calls,'input_sha256':fingerprint(self.last_input),'output_sha256':fingerprint(ranking)}
        if self.damage=='input-hash':observation['input_sha256']='0'*64
        if self.damage=='output-hash':observation['output_sha256']='0'*64
        if self.damage=='payload-profile':self.last_input['profile']['name']='Wrong observed profile'
        self.observations.append(observation)
        return {'schema_version':1,'request_id':request['request_id'],'ranked_entity_ids':ranking}


class CausalAgentTests(unittest.TestCase):
    def setUp(self):
        self.catalog=[{'entity_id':f'aaaaaaaa-0000-4000-8000-{i:012d}','name':f'Unit movie {i}','release_year':2000+i} for i in range(20)]
        self.profiles=[{'entity_id':f'bbbbbbbb-0000-4000-8000-{i:012d}','name':f'Unit artist {i}','type':'urn:entity:artist'} for i in range(2)]
        self.contexts={profile_hash(p):context_from_sample(p,self.catalog,self.raw(p,i),fingerprint({'synthetic_fixture':i})) for i,p in enumerate(self.profiles)}
        self.requests=[make_request('Rank unit movies',self.catalog,p,self.contexts[profile_hash(p)],f'unit-{i}') for i,p in enumerate(self.profiles)]

    def raw(self,profile,reverse=0):
        rows=[{'entity_id':r['entity_id'],'name':r['name'],'types':['urn:entity:movie'],'properties':{'release_year':r['release_year']},'query':{'affinity':1-i/20}} for i,r in enumerate(self.catalog)]
        if reverse:rows.reverse()
        body={'success':True,'results':{'entities':rows}}
        return {'fixture_provenance':'synthetic-unit-only-not-live-evidence','request':{'method':'GET','host':'https://hackathon.api.qloo.com','path':'/v2/insights','params':{'filter.type':'urn:entity:movie','bias.trends':'off','take':20,'signal.interests.entities':profile['entity_id'],'filter.results.entities':','.join(sorted(r['entity_id'] for r in self.catalog))}},'status':200,'attempt':1,'live_network_request':True,'response':body,'response_sha256':fingerprint(body)}

    def session(self,fault=None):
        engine=FakeEngine();ledger=FakeLedger();return CausalMovieSession(ExecutionRecorder(engine,ledger),self.contexts,fault=fault),engine,ledger

    def test_three_faults_diagnosed_from_trace_and_repaired_with_new_execution(self):
        expected={'cache-omits-profile':('CACHE_OMITS_PROFILE','scope','profile'),'stale-profile':('STALE_PROFILE','route_current',True),'wrong-tool-profile':('WRONG_TOOL_PROFILE','bind_current',True)}
        for fault in FAULTS:
            with self.subTest(fault=fault):
                session,engine,ledger=self.session(fault);session.rank(self.requests[0]);broken=session.rank(self.requests[1]);before=engine.calls
                trace=broken['trace'];self.assertNotIn('fault',trace);self.assertNotIn('diagnosis',trace)
                diagnosis=diagnose(trace);self.assertEqual(diagnosis['diagnosis'],expected[fault][0]);result=session.apply(diagnosis)
                self.assertTrue(result['applied']);self.assertEqual(getattr(session,expected[fault][1]),expected[fault][2])
                repaired=session.rank(self.requests[1]);self.assertEqual(engine.calls,before+1);self.assertEqual(diagnose(repaired['trace'])['diagnosis'],'NONE')
                self.assertEqual(repaired['ranking'],list(reversed([r['entity_id'] for r in self.catalog])))
                cached=session.rank(self.requests[1]);self.assertTrue(cached['trace']['cache_hit']);self.assertEqual(engine.calls,before+1);self.assertEqual(diagnose(cached['trace'])['diagnosis'],'NONE')
                self.assertEqual(len(ledger.files),engine.calls)
                with self.assertRaises(SchemaError):session.apply(diagnosis)

    def test_healthy_and_legitimate_cache_none_patch_is_noop(self):
        session,engine,_=self.session()
        for request in self.requests:
            first=session.rank(request);again=session.rank(request)
            self.assertEqual(diagnose(first['trace']),{'diagnosis':'NONE','operation':'none'});self.assertEqual(diagnose(again['trace'])['diagnosis'],'NONE')
        before=(session.patches,engine.calls,copy.deepcopy(session.cache))
        self.assertEqual(session.apply({'diagnosis':'NONE','operation':'none'}),{'operation':'none','attempt':0,'applied':False})
        self.assertEqual((session.patches,engine.calls,session.cache),before)

    def test_malformed_and_ambiguous_traces_unsupported(self):
        session,_,_=self.session();trace=session.rank(self.requests[0])['trace']
        for invalid in (None,{}, {**trace,'cache_hit':1},{**trace,'tool_profile_sha256':'short'},{**trace,'transmitted_profile_sha256':'a'*64,'tool_profile_sha256':'b'*64,'output_profile_sha256':'c'*64}):
            self.assertEqual(diagnose(invalid),{'diagnosis':'UNSUPPORTED','operation':'none'})
        with self.assertRaises(SchemaError):session.apply({'diagnosis':'UNSUPPORTED','operation':'none'})

    def test_empty_patch_and_nonhex_trace_regressions(self):
        session,_,_=self.session();trace=session.rank(self.requests[0])['trace']
        for invalid in ({},None,{'diagnosis':'NONE'},{'diagnosis':'NONE','operation':'none','extra':True}):
            with self.assertRaises(SchemaError):session.apply(invalid)
        bad={**trace,**{k:'z'*64 for k in ('requested_profile_sha256','transmitted_profile_sha256','tool_profile_sha256','output_profile_sha256')}}
        self.assertEqual(diagnose(bad),{'diagnosis':'UNSUPPORTED','operation':'none'})

    def test_invalid_incoming_request_rejected_before_cache_hit(self):
        for cached in (False,True):
            session,engine,_=self.session()
            if cached:session.rank(self.requests[0])
            before=engine.calls;variants=[]
            bad=copy.deepcopy(self.requests[0]);bad['task']='Modified without rehash';variants.append(bad)
            bad={**self.requests[0],'expected_result':[]};bad['request_id']=fingerprint({k:v for k,v in bad.items() if k!='request_id'});variants.append(bad)
            bad=copy.deepcopy(self.requests[0]);bad['tool_context']=copy.deepcopy(self.contexts[profile_hash(self.profiles[1])]);bad['request_id']=fingerprint({k:v for k,v in bad.items() if k!='request_id'});variants.append(bad)
            bad=copy.deepcopy(self.requests[0]);ctx=bad['tool_context'];ctx['ranked_entities'].reverse();ctx['context_sha256']=fingerprint({k:v for k,v in ctx.items() if k!='context_sha256'});bad['request_id']=fingerprint({k:v for k,v in bad.items() if k!='request_id'});variants.append(bad)
            for request in variants:
                with self.assertRaises(SchemaError):session.rank(request)
                self.assertEqual(engine.calls,before)

    def test_raw_tool_query_source_hash_and_full_coverage_bound(self):
        base=self.raw(self.profiles[0]);variants=[]
        for field,value in [('status',500),('attempt',2),('live_network_request',False),('response_sha256','0'*64)]:
            sample=copy.deepcopy(base);sample[field]=value;variants.append(sample)
        for field,value in [('host','https://example.invalid'),('path','/search')]:
            sample=copy.deepcopy(base);sample['request'][field]=value;variants.append(sample)
        sample=copy.deepcopy(base);sample['request']['params']['signal.interests.entities']=self.profiles[1]['entity_id'];variants.append(sample)
        for mutation in ('missing','duplicate','affinity','type','year'):
            sample=copy.deepcopy(base);rows=sample['response']['results']['entities']
            if mutation=='missing':rows.pop()
            elif mutation=='duplicate':rows[-1]=copy.deepcopy(rows[0])
            elif mutation=='affinity':rows[0]['query']['affinity']=1.1
            elif mutation=='type':rows[0]['types']=['urn:entity:artist']
            elif mutation=='year':rows[0]['properties']['release_year']=1900
            sample['response_sha256']=fingerprint(sample['response']);variants.append(sample)
        for sample in variants:
            with self.assertRaises(SchemaError):context_from_sample(self.profiles[0],self.catalog,sample,'unit-sample-hash')

    def test_context_rehash_does_not_hide_bad_affinity_or_membership(self):
        original=self.contexts[profile_hash(self.profiles[0])]
        for value in (True,math.inf,math.nan,-.1,1.1,None):
            context=copy.deepcopy(original);context['ranked_entities'][0]['affinity']=value
            if value in (math.inf,) or isinstance(value,float) and math.isnan(value):
                # Nonfinite values cannot even be canonically hashed.
                with self.assertRaises((SchemaError,ValueError)):validate_context(context,self.catalog)
            else:
                context['context_sha256']=fingerprint({k:v for k,v in context.items() if k!='context_sha256'})
                with self.assertRaises(SchemaError):validate_context(context,self.catalog)
        context=copy.deepcopy(original);context['ranked_entities'][-1]=context['ranked_entities'][0];context['context_sha256']=fingerprint({k:v for k,v in context.items() if k!='context_sha256'})
        with self.assertRaises(SchemaError):validate_context(context,self.catalog)

    def test_catalog_duplicate_and_extra_fields_rejected(self):
        duplicate=copy.deepcopy(self.catalog);duplicate[-1]=duplicate[0]
        for bad in (duplicate,self.catalog[:-1],[{**r,'expected_rank':i} for i,r in enumerate(self.catalog)]):
            with self.assertRaises(SchemaError):validate_catalog(bad)

    def test_recorder_rejects_partial_tail_and_observation_tampering(self):
        for damage in ('short','tail-duplicate','outside','input-hash','output-hash','payload-profile'):
            engine=FakeEngine();engine.damage=damage;ledger=FakeLedger();recorder=ExecutionRecorder(engine,ledger)
            with self.assertRaises((AgentError,SchemaError)):recorder.execute(self.requests[0])
            self.assertEqual(ledger.files,{})

    def test_decision_input_contains_actual_context_without_evaluation_labels(self):
        agent=ToolContextMovieAgent.__new__(ToolContextMovieAgent);payload=agent.decision_input(self.requests[0],{'type':'object'})
        self.assertEqual(set(payload),{'task','catalog','profile','provider_movie_context','tool_notice','output_schema'})
        self.assertEqual(payload['profile'],self.profiles[0]);self.assertEqual(len(payload['provider_movie_context']),20)
        self.assertEqual(set(payload['provider_movie_context'][0]),{'catalog_index','affinity'});self.assertEqual(payload,agent.last_input)
        for forbidden in ('threshold','diagnosis','expected_healthy','chain_of_thought'):
            bad={**self.requests[0],forbidden:1};bad['request_id']=fingerprint({k:v for k,v in bad.items() if k!='request_id'})
            with self.assertRaises(AgentError):agent.decision_input(bad,{})
        bad=copy.deepcopy(self.requests[0]);bad['task']='Changed request'
        with self.assertRaises(AgentError):agent.decision_input(bad,{})


if __name__=='__main__':unittest.main()
