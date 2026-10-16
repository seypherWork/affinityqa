"""Offline joint-call fixtures: every provider and DNS boundary is synthetic."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.fast_pair_agent import FastPairMovieAgent
from affinityqa.fast_pair_capture import prepare_plan,search_identities,capture_confirmed
from affinityqa.fast_pair_verify import verify_discovery_search,verify_confirmed_discoveries,verify_packet
from affinityqa.fast_pair import input_for,cache_key,pair_request
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
from affinityqa.individual_verify import inventory
from affinityqa.provider_runtime import PinnedHarmonyTokenEstimator, ProviderRuntime
from affinityqa.provider_scheduler import QuotaWindow
from affinityqa.repeatable_capture import request_for
from affinityqa.movie_case_bodies import PlanBody
from test_discovery_agent import Response,TEST_SECRET
from test_groq_agent import UNIT_QLOO_SECRET
import test_movie_case_api as movie_fixtures
from test_movie_case_api import PREFIX, FILM_A, FILM_B


class PairOpenerFixture:
    def __init__(self,*,mutation=None,failure=None):
        self.calls = []; self.mutation,self.failure = mutation,failure
    def open(self,request,timeout):
        payload = json.loads(request.data); self.calls.append((request,payload,timeout))
        if self.failure is not None: raise self.failure
        data = json.loads(payload['messages'][1]['content'])
        rows = {k:[r['catalog_index'] for r in data['profiles'][k]['provider_movie_context']] for k in ('A','B')}
        body = {'id':'synthetic-paired-'+str(len(self.calls)),'object':'chat.completion','created':1792179154,
            'model':'openai/gpt-oss-20b','system_fingerprint':'synthetic-pair-revision',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps({'ordered_catalog_indices':rows})}}],
            'usage':{'prompt_tokens':3000,'completion_tokens':400,'total_tokens':3400,
                     'completion_tokens_details':{'reasoning_tokens':100}}}
        if self.mutation: self.mutation(body)
        return Response(json.dumps(body).encode())


class FastPairTests(unittest.TestCase):
    def setUp(self):
        self.f = movie_fixtures.MovieCaseApiTests('test_external_films_condition_both_recorded_inputs_and_download_restores')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.f.agent_class = FastPairMovieAgent; self.f.opener = PairOpenerFixture()
        self.estimator = PinnedHarmonyTokenEstimator(ROOT/'assets/tokenizers/o200k_base.tiktoken')
        self.f.manager.manager.token_estimator = self.estimator
        self.f.scheduler.limits['groq'] = (QuotaWindow('rpm',30,60),QuotaWindow('rpd',1000,86400),
            QuotaWindow('tpm',8000,60,'tokens'),QuotaWindow('tpd',200000,86400,'tokens'))
        for name in ('socket.create_connection','socket.getaddrinfo','affinityqa.qloo.LiveTransport.send','urllib.request.OpenerDirector.open'):
            guard = patch(name,side_effect=AssertionError('Real network forbidden in paired tests'))
            guard.start(); self.addCleanup(guard.stop)

    def plan(self,movies=True):
        value = {'artists':self.f.request['artists'],'preferences':self.f.request['preferences'],
            'confirm_identities':True,'discover_new_movies':True,'fast_pair_review':True,
            'movie_queries':self.f.request['movie_queries'] if movies else {'A':[],'B':[]}}
        response = self.f.client.post(PREFIX+'/plans',json=value,headers=self.f.headers)
        self.assertEqual(response.status_code,201,response.text); return response.json()

    def finish(self,movies=True):
        job = self.plan(movies); pending = self.f.search(job)
        choice = self.f.choice(pending)
        if not movies: choice['selected_movie_entity_ids'] = {'A':[],'B':[]}
        response = self.f.client.post(PREFIX+f"/jobs/{job['job_id']}/confirm-identities",json=choice,headers=self.f.headers)
        self.assertEqual(response.status_code,202,response.text); self.f.manager.manager.run_once()
        result = self.f.client.get(PREFIX+f"/jobs/{job['job_id']}").json()
        self.assertEqual(result['status'],'COMPLETE',result)
        row = self.f.manager.manager._job(job['job_id'])
        return result,Path(row['directory'])

    def test_complete_one_operation_packet_two_projections_under_real_conservative_cap(self):
        cap = self.f.client.get(PREFIX+'/capabilities').json(); self.assertTrue(cap['fast_pair_review_supported'])
        result,directory = self.finish(); self.assertEqual(result['maximum_model_decisions'],1)
        self.assertEqual(result['case_protocol'],'cinema-paired-discovery-v1')
        self.assertEqual((len(self.f.transport.calls),len(self.f.opener.calls)),(6,1))
        self.assertEqual(result['saved_model_packets'],1)
        receipt = verify_confirmed_discoveries(directory)
        self.assertEqual((receipt['shared_model_calls'],receipt['correlated_projections']), (1,2))
        self.assertFalse(receipt['independent_model_decisions'])
        stats = result['provider_stats']['groq']; self.assertEqual((stats['http_attempts'],stats['unknown_attempts']),(1,0))
        packet = json.loads((directory/'pair-execution-001.json').read_bytes())
        for label,seed in [('A',FILM_A),('B',FILM_B)]:
            data = packet['model_payload']['profiles'][label]
            self.assertEqual(data['external_favorite_movies'][0]['entity_id'],seed)
            rows = receipt['cinema_results'][label]['delivered']; self.assertEqual(len(set(rows)),5); self.assertNotIn(seed,rows)
            public = result['result']['cinema_results'][label]
            self.assertEqual(public,receipt['cinema_results'][label])
            self.assertIsInstance(public['excluded_removed'],list)
            self.assertIs(type(public['selection_changed']),bool)
            self.assertEqual(public['known_favorite_count'],1)
            for field in ('preferences_sha256','intent_sha256','raw_ranking_sha256','delivery_sha256'):
                self.assertRegex(public[field],r'^[a-f0-9]{64}$')
            self.assertEqual(public['preferences_sha256'],fingerprint(public['preferences']))
            self.assertEqual(public['intent_sha256'],packet['effective_request']['profiles'][label]['intent_sha256'])
            self.assertEqual(public['raw_ranking_sha256'],fingerprint(public['raw_ranking']))
            self.assertEqual(public['delivery_sha256'],fingerprint(public['delivered']))
        prepared = [json.loads(x) for x in (directory/'ledger.jsonl').read_bytes().splitlines() if json.loads(x)['kind']=='pair_model_attempt_prepared'][0]
        self.assertLessEqual(prepared['data']['reservation']['tokens'],8000)
        self.assertEqual(prepared['data']['reservation']['output_tokens'],1024)
        before = inventory(directory); verify_confirmed_discoveries(directory); self.assertEqual(inventory(directory),before)
        self.f.access(self.f.client); self.assertEqual(self.f.client.get(PREFIX+f"/jobs/{result['job_id']}").json()['status'],'COMPLETE')
        self.assertEqual((len(self.f.transport.calls),len(self.f.opener.calls)),(6,1))

    def test_zero_queries_is_closed_empty_confirmation_and_four_qloo_one_groq(self):
        result,directory = self.finish(False)
        self.assertEqual((len(self.f.transport.calls),len(self.f.opener.calls)),(4,1))
        self.assertEqual(result['chosen_movie_inputs'],{'A':[],'B':[]})
        self.assertEqual(verify_confirmed_discoveries(directory)['movie_queries'],{'A':[],'B':[]})

    def test_internal_favorites_and_exclusions_never_delivered_or_repeated_as_seeds(self):
        ids = [v['entity_id'] for v in self.f.request['catalog']]
        self.f.request['preferences']['A']['favorite_entity_ids'] = [ids[0]]
        self.f.request['preferences']['B']['favorite_entity_ids'] = [ids[1],ids[2]]
        for k in ('A','B'): self.f.request['preferences'][k]['excluded_entity_ids'] = [ids[-1]]
        _,directory = self.finish(False); r = verify_confirmed_discoveries(directory)
        for k in ('A','B'):
            v = r['cinema_results'][k]; prefs = self.f.request['preferences'][k]
            self.assertEqual(len(v['raw_ranking']),20-len(prefs['favorite_entity_ids']))
            self.assertFalse(set(v['delivered']) & set(prefs['favorite_entity_ids']+prefs['excluded_entity_ids']))

    def test_missing_profile_duplicate_or_cross_profile_index_rejects_one_call_without_fallback(self):
        for mode in ('missing','duplicate','cross'):
            with self.subTest(mode=mode):
                self.f.fixture.now += timedelta(seconds=61)
                f = self.f; f.opener.calls.clear(); f.transport.calls.clear()
                def mutate(body):
                    out = json.loads(body['choices'][0]['message']['content'])['ordered_catalog_indices']
                    if mode=='missing': out.pop('B')
                    elif mode=='duplicate': out['A'][-1] = out['A'][0]
                    else: out['A'][0] = 99
                    body['choices'][0]['message']['content'] = json.dumps({'ordered_catalog_indices':out})
                f.opener.mutation = mutate
                job=self.plan();pending=f.search(job);choice=f.choice(pending)
                response=f.client.post(PREFIX+f"/jobs/{job['job_id']}/confirm-identities",json=choice,headers=f.headers)
                self.assertEqual(response.status_code,202);f.manager.manager.run_once()
                result=f.client.get(PREFIX+f"/jobs/{job['job_id']}").json()
                self.assertEqual(result['status'],'PARTIAL',result);self.assertEqual(len(f.opener.calls),1)
                self.assertEqual(result['saved_model_packets'],0)

    def test_packet_swap_missing_context_catalog_preferences_and_cache_bindings_fail(self):
        _,directory = self.finish(); packet=json.loads((directory/'pair-execution-001.json').read_bytes())
        manifest=json.loads((directory/'model-manifest.json').read_bytes()); contexts=json.loads((directory/'individual-tool-inputs.json').read_bytes())
        mutations=[lambda p:p['model_payload']['profiles'].update(A=p['model_payload']['profiles']['B']),
            lambda p:p['effective_request']['profiles'].pop('B'),
            lambda p:p['model_payload']['catalog'][0].update(release_year=1980),
            lambda p:p['model_payload']['profiles']['A']['cinema_preferences'].update(excluded_catalog_indices=[0]),
            lambda p:p.update(joint_cache_key_sha256='0'*64)]
        for mutation in mutations:
            value=copy.deepcopy(packet);mutation(value)
            with self.assertRaises((SchemaError,KeyError)):verify_packet(value,manifest,contexts)
        changed=copy.deepcopy(contexts);changed['B']=copy.deepcopy(contexts['A'])
        with self.assertRaises(SchemaError):verify_packet(packet,manifest,changed)
        original=packet['joint_cache_key_sha256']; altered=copy.deepcopy(packet['effective_request'])
        altered['profiles']['B']['request_nonce']='different-transport-nonce';altered['profiles']['B'].pop('request_id')
        altered['profiles']['B']['request_id']=fingerprint(altered['profiles']['B']);altered.pop('request_id');altered['request_id']=fingerprint(altered)
        self.assertEqual(cache_key(altered,manifest),original)

    def test_plan_self_rehash_cannot_change_source_or_budget(self):
        job=self.plan();pending=self.f.search(job);row=self.f.manager.manager._job(job['job_id']);p=Path(row['directory'])/'pair-plan.json'
        data=json.loads(p.read_bytes());data['source_sha256']['groq_agent.py']='0'*64;data.pop('plan_sha256');data['plan_sha256']=fingerprint(data);p.write_text(json.dumps(data))
        with self.assertRaises(SchemaError):verify_discovery_search(p.parent)

    def test_accepted_joint_operation_reconstructs_once_without_second_send_or_wait(self):
        _,directory=self.finish(False);p=json.loads((directory/'pair-execution-001.json').read_bytes())
        self.f.fixture.now += timedelta(seconds=61)
        opener=PairOpenerFixture()
        runtime=ProviderRuntime(self.f.scheduler,'synthetic-paired-recovery','1'*64,namespace={'protocol':'paired-test'},token_estimator=self.estimator)
        answers=[]
        for _ in range(2):
            agent=FastPairMovieAgent(TEST_SECRET,_test_opener=opener,token_estimator=self.estimator)
            with runtime.activate(namespace='capture'):
                answers.append(agent.rank(p['effective_request']))
            self.assertEqual(len(agent.observations),1)
        self.assertEqual(answers[0],answers[1]);self.assertEqual(len(opener.calls),1)
        self.assertEqual([r['operation_mode'] for r in runtime.receipts],['fresh','accepted-reconstruction'])
        self.assertEqual(runtime.counters['exact_reconstructions'],1)

    def test_oversized_reservation_stops_before_send(self):
        _,directory=self.finish(False);p=json.loads((directory/'pair-execution-001.json').read_bytes())
        opener=PairOpenerFixture();agent=FastPairMovieAgent(TEST_SECRET,_test_opener=opener,token_estimator=self.estimator)
        with patch.object(self.estimator,'estimate',return_value={'tokens':8001,'input_tokens':6977,'output_tokens':1024}):
            with self.assertRaises(Exception):agent.rank(p['effective_request'])
        self.assertEqual((agent.calls,len(opener.calls)),(0,0))

    def test_http429_stops_joint_case_without_second_or_fallback_call(self):
        self.f.opener.failure=HTTPError('https://synthetic.invalid',429,'synthetic quota',{},None)
        job=self.plan(False);pending=self.f.search(job);choice=self.f.choice(pending)
        choice['selected_movie_entity_ids']={'A':[],'B':[]}
        response=self.f.client.post(PREFIX+f"/jobs/{job['job_id']}/confirm-identities",json=choice,headers=self.f.headers)
        self.assertEqual(response.status_code,202);self.f.manager.manager.run_once()
        result=self.f.client.get(PREFIX+f"/jobs/{job['job_id']}").json()
        self.assertEqual(result['status'],'PARTIAL',result);self.assertEqual(len(self.f.opener.calls),1)
        self.assertEqual(result['saved_model_packets'],0)

    def test_default_false_and_illegal_fast_modes_preserve_old_routes(self):
        template=copy.deepcopy(self.f.template)
        self.assertEqual(request_for(template,template['artists'])['schema_version'],2)
        self.assertEqual(request_for(template,template['artists'],self.f.request['preferences'],True,True)['schema_version'],5)
        self.assertFalse(PlanBody(artists=self.f.request['artists']).fast_pair_review)
        for args in ({'fast_pair_review':True},{'preferences':self.f.request['preferences'],'fast_pair_review':True}):
            with self.assertRaises(SchemaError):request_for(template,template['artists'],**args)
        body={'artists':self.f.request['artists'],'fast_pair_review':1}
        self.assertEqual(self.f.client.post(PREFIX+'/plans',json=body,headers=self.f.headers).status_code,422)
