"""Pure wide contracts: synthetic metadata never proves taste quality."""
import copy
import json
from pathlib import Path
import sys
import unittest
from uuid import UUID

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.errors import SchemaError
from affinityqa.agents import AgentError
from affinityqa.evidence import fingerprint
from affinityqa.wide_cinema_discovery import (validate_request,validate_context,make_decision,model_input,output_schema,
    validate_output,result_for,cache_key,qloo_request,presentation_asset)
from affinityqa.wide_cinema_agent import WideCinemaAgent,model_manifest,wire
from affinityqa.wide_cinema_tokens import WideHarmonyTokenEstimator
from test_wide_cinema_capture import request_fixture,context_fixture,WideTransport,WideOpener,SEED_ID,FAVORITE_ID,UNIT_SECRET


def choice_fixture(decision,index,text=None):
    value={'catalog_index':index}
    if text is not None:value['text']=text
    return value


def output_fixture(decision,first=False):
    ranking=(decision['eligible_catalog_indices'] if first else list(reversed(decision['eligible_catalog_indices'])))[:5]
    return {'ordered_catalog_indices':[choice_fixture(decision,i) for i in ranking]}


class WideContractTests(unittest.TestCase):
    def decision(self,**kwargs):return make_decision(request_fixture(**kwargs),context_fixture(),'synthetic-only')
    def test_closed_request_has_no_artist_pair_catalog_or_client_model(self):
        request=request_fixture();self.assertEqual(validate_request(request),request)
        for change in ({'catalog':[]},{'artists':{'A':'x','B':'y'}},{'schema_version':True},{'model':{'provider':'other','name':'paid'}},
                {'favorite_movie_query':'not allowed in movie'},{'favorite_movie_query':[]},{'mode':'artist-output'}):
            with self.subTest(change=change),self.assertRaises(SchemaError):validate_request({**request,**change})
    def test_normalization_and_bounds_are_explicit(self):
        request=validate_request(request_fixture(seed_query='  Film   2000 '));self.assertEqual(request['seed_query'],'Film 2000')
        for change in ({'seed_query':''},{'seed_query':'x'*201},{'intent_text':'x'*601},{'intent_text':'bad\ntext'},
                {'excluded_entity_ids':['fake']},{'excluded_entity_ids':[str(UUID(int=1))]*2},{'excluded_entity_ids':[str(UUID(int=i)) for i in range(16)]}):
            with self.subTest(change=change),self.assertRaises(SchemaError):validate_request(request_fixture(**change))
    def test_pool_is_actual_union_not_any_global_catalog(self):
        context=context_fixture();self.assertEqual(len(context['candidate_catalog']),100)
        self.assertEqual(context['raw_provider_order'],[str(UUID(int=i)) for i in range(1,101)])
        self.assertEqual(context['candidate_catalog'][-1]['name'],'Synthetic film 100')
    def test_empty_second_page_is_valid_with_at_least_five_actual_movies(self):
        context=context_fixture(transport=WideTransport(pages={1:[1,2,3,4,5],2:[]}));self.assertEqual(len(context['candidate_catalog']),5)
        decision=make_decision(request_fixture(),context,'synthetic-only');self.assertEqual(len(result_for(decision,output_fixture(decision))['delivered']),5)
    def test_conflicting_duplicate_identity_is_terminal(self):
        def mutate(body,page):
            if page==2:body['results']['entities'][0]['name']='Conflicting identity'
        with self.assertRaises(SchemaError):context_fixture(transport=WideTransport(pages={1:list(range(1,51)),2:list(range(1,51))},mutation=mutate))
    def test_conflict_after_missing_year_is_not_silently_deduplicated(self):
        def mutate(body,page):
            if page==1:body['results']['entities'][0]['properties'].pop('release_year')
            else:body['results']['entities'][0]['name']='Different title for same ID'
        with self.assertRaises(SchemaError):context_fixture(transport=WideTransport(pages={1:list(range(1,51)),2:list(range(1,51))},mutation=mutate))
    def test_known_seed_and_missing_or_nonfinite_affinity_and_wrong_type_rejected(self):
        changes=[lambda r:r.update(entity_id=SEED_ID),lambda r:r.update(types=['urn:entity:artist']),
            lambda r:r['query'].pop('affinity'),lambda r:r['query'].update(affinity=True),lambda r:r['query'].update(affinity=1.1),lambda r:r.update(entity_id='invented')]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(SchemaError):
                context_fixture(transport=WideTransport(mutation=lambda b,p:change(b['results']['entities'][0])))
    def test_artist_favorite_signal_never_uses_fixed_results_filter(self):
        context=context_fixture('music',True);http=qloo_request('music',context['seed_identity'],context['known_favorite_movie'],2)
        self.assertEqual(http['params']['page'],2);self.assertEqual(http['params']['take'],50)
        self.assertNotIn('filter.results.entities',http['params']);self.assertEqual(http['params']['filter.exclude.entities'],FAVORITE_ID)
        self.assertEqual(len(http['params']['signal.interests.entities'].split(',')),2)
    def test_bad_context_sources_counts_hashes_assets_and_classification_rejected(self):
        mutations=[lambda v:v.update(source='unobserved'),lambda v:v.update(catalog_sha256='0'*64),
            lambda v:v['pages'][0].update(request_sha256='0'*64),lambda v:v['pages'][0].update(row_count=49),
            lambda v:v['provider_observations'][0].update(position=99),lambda v:v['provider_observations'][0].update(affinity=float('inf')),
            lambda v:v['presentation_assets'][0].update(identity_sha256='0'*64),lambda v:v['presentation_assets'][0].update(url='https://evil.invalid/no.jpg')]
        for mutation in mutations:
            context=context_fixture();mutation(context)
            with self.subTest(mutation=mutation),self.assertRaises(SchemaError):validate_context(context)
    def test_rehashed_context_cannot_add_unsafe_asset_or_lose_raw_classification(self):
        for mutate in (lambda v:v['presentation_assets'][0].update(url='https://127.0.0.1/i/'+str(UUID(int=1))+'-420x-auto.jpg'),
                lambda v:v['provider_observations'].pop(),lambda v:v['duplicate_rows'].append({'page':2,'position':0,'entity_id':str(UUID(int=51))})):
            context=context_fixture();mutate(context);context['context_sha256']=fingerprint({k:v for k,v in context.items() if k!='context_sha256'})
            with self.subTest(mutate=mutate),self.assertRaises(SchemaError):validate_context(context)
    def test_model_selects_only_five_unique_eligible_indices_no_full100_permutation(self):
        decision=self.decision(excluded_entity_ids=[str(UUID(int=100)),str(UUID(int=99))]);output=output_fixture(decision)
        checked=validate_output(decision,output);self.assertEqual(checked['ranking'],[str(UUID(int=i)) for i in (98,97,96,95,94)])
        schema=output_schema(decision)['properties']['ordered_catalog_indices'];self.assertEqual((schema['type'],schema['minItems'],schema['maxItems']),('array',5,5))
        for ranking in (list(range(100)),[0,0,1,2,3],[0,1,2,3,True],[0,1,2,3,100],[0,1,2,3,99]):
            value=copy.deepcopy(output);value['ordered_catalog_indices']=[{'catalog_index':i} for i in ranking]
            with self.subTest(ranking=ranking),self.assertRaises(SchemaError):validate_output(decision,value)
    def test_model_reason_references_and_text_bounds(self):
        for mutate in (lambda b:b[0].update(extra='not allowed'),lambda b:b[0].update(text='short'),
                lambda b:b[0].update(text='x'*241),lambda b:b[0].update(text='x'*45+'\x00')):
            decision=self.decision();output=output_fixture(decision);mutate(output['ordered_catalog_indices'])
            with self.subTest(mutate=mutate),self.assertRaises(SchemaError):validate_output(decision,output)
    def test_v10_has_one_indices_array_and_never_normalizes_model_prose(self):
        decision=self.decision();output=output_fixture(decision);checked=validate_output(decision,output)
        self.assertTrue(all(set(row)=={'catalog_index'} for row in checked['choices']))
        self.assertEqual(decision['protocol'],'qloo-wide-cinema-discovery-v10')
        for prose in ('  Ｌａ\t opción\r\n sintética podría encajar como interpretación.  ',' '*1000+'Una explicación sintética.'):
            value=copy.deepcopy(output);value['ordered_catalog_indices'][0]['text']=prose
            with self.assertRaisesRegex(SchemaError,'OUTPUT_CHOICE_SHAPE'):validate_output(decision,value)
        old={'ordered_catalog_indices':{'ranking':[c['catalog_index'] for c in output['ordered_catalog_indices']],'reasons':output['ordered_catalog_indices']}}
        with self.assertRaises(SchemaError):validate_output(decision,old)
    def test_v10_text_transport_with_explicit_contract_is_independently_reconstructed(self):
        from affinityqa.wide_cinema_verify import expected_manifest,_wire
        decision=self.decision();manifest=model_manifest('test-double-only');payload=wire(decision,manifest)
        self.assertEqual(manifest,expected_manifest('test-double-only'))
        self.assertEqual(manifest['prompt_version'],'qloo-wide-cinema-discovery-v10')
        self.assertEqual(manifest['response_contract'],'wide-five-ordered-catalog-indices-v10')
        marker={'type':'text'}
        self.assertEqual(manifest['provider_response_format'],marker)
        self.assertEqual(payload['response_format'],marker)
        self.assertEqual(json.loads(payload['messages'][1]['content'])['output_contract'],output_schema(decision))
        self.assertEqual(payload,_wire(decision,manifest))
        self.assertNotIn('json_schema',json.dumps(payload));self.assertIn('output_contract',json.dumps(payload))
        self.assertEqual((manifest['max_inference_calls'],manifest['maximum_token_reservation'],payload['max_completion_tokens']),(1,8000,2048))
        self.assertEqual(output_schema(decision)['properties']['ordered_catalog_indices']['maxItems'],5)
    def test_v10_transport_manifest_cannot_switch_unconfigured_mode(self):
        decision=self.decision()
        for mode in ({'type':'json_schema'},{'type':'json_object'},None,{'type':'text','extra':True},
                     {'type':'json_schema','json_schema':{'name':'affinityqa_wide_cinema_v4','strict':False}}):
            manifest=model_manifest('test-double-only');manifest['provider_response_format']=mode
            with self.subTest(mode=mode),self.assertRaises(AgentError):wire(decision,manifest)
    def test_model_prose_is_forbidden_even_when_plausible_or_correctly_labelled(self):
        decision=self.decision();output=output_fixture(decision)
        for raw in ('No está garantizado que encaje; podría resultar interesante como interpretación del gusto.',
                    'La película titulada 100% podría encajar como una interpretación personal del gusto.'):
            value=copy.deepcopy(output);value['ordered_catalog_indices'][0]['text']=raw
            with self.assertRaisesRegex(SchemaError,'OUTPUT_CHOICE_SHAPE'):validate_output(decision,value)
        self.assertEqual(result_for(decision,output)['cultural_quality'],'NOT_VALIDATED')
        output['cultural_gate']='VALIDATED'
        with self.assertRaises(SchemaError):validate_output(decision,output)
    def test_taste_first_input_is_explicit_model_only_and_not_a_quality_gate(self):
        context=context_fixture();request=request_fixture(intent_text='Primero humor absurdo, como preferencia interpretada.')
        decision=make_decision(request,context,'synthetic-only');data=model_input(decision)
        self.assertEqual(data['intent_text'],request['intent_text']);self.assertTrue(data['priority'].startswith('stated taste first'))
        result=result_for(decision,output_fixture(decision));self.assertFalse(result['information_policy']['intent_text_sent_to_qloo'])
        self.assertFalse(result['information_policy']['same_explicit_information']);self.assertEqual(result['information_policy']['taste_quality_gate'],'NOT_VALIDATED')
        equal=result_for(decision,output_fixture(decision,first=True));self.assertEqual(equal['delivered'],equal['baseline_delivered'])
    def test_intent_exclusion_or_signal_change_has_distinct_cache_namespace(self):
        context=context_fixture();manifest=model_manifest('test-double-only');a=make_decision(request_fixture(),context,'one')
        b=make_decision(request_fixture(intent_text='Humor primero como sugerencia.'),context,'one')
        x=make_decision(request_fixture(excluded_entity_ids=[str(UUID(int=1))]),context,'one')
        other=make_decision(request_fixture(),context,'two')
        self.assertNotEqual(cache_key(a,manifest),cache_key(b,manifest));self.assertNotEqual(cache_key(a,manifest),cache_key(x,manifest))
        self.assertEqual(cache_key(a,manifest),cache_key(other,manifest));self.assertEqual(model_input(a),model_input(other))
    def test_unsafe_image_urls_never_become_artwork_and_film_is_retained(self):
        safe=f'https://images.qloo.com/i/{str(UUID(int=1)).upper()}-420x-auto.jpg'
        urls=[safe.replace('https:','http:'),safe+'?token=bad',safe+'#fragment',safe.replace('images.qloo.com','user@images.qloo.com'),
            safe.replace('images.qloo.com','images.qloo.com:443'),safe.replace('images.qloo.com','images.qloo.com.evil.invalid'),
            safe.replace(str(UUID(int=1)).upper(),str(UUID(int=2)).upper()),safe.replace('/i/','/\ni/')]
        for url in urls:
            def mutate(body,page):
                if page==1:body['results']['entities'][0]['properties']['image']['url']=url
            with self.subTest(url=url):
                context=context_fixture(transport=WideTransport(mutation=mutate));self.assertEqual(len(context['candidate_catalog']),100)
                self.assertNotIn(str(UUID(int=1)),[v['entity_id'] for v in context['presentation_assets']])
    def test_presentation_identity_hash_is_exact_title_year_and_uuid(self):
        context=context_fixture();asset=context['presentation_assets'][0];movie=context['candidate_catalog'][0]
        self.assertEqual(asset['identity_sha256'],fingerprint(movie));self.assertEqual(asset['url'],f"https://images.qloo.com/i/{movie['entity_id'].upper()}-420x-auto.jpg")
        self.assertIn(asset['sample_sha256'],[p['sample_sha256'] for p in context['pages']])
    def test_oversized_wire_is_rejected_before_any_model_send(self):
        def mutate(body,page):
            for row in body['results']['entities']:row['name']='映'*290+' '+row['entity_id'][-5:]
        context=context_fixture(transport=WideTransport(mutation=mutate));decision=make_decision(request_fixture(),context,'synthetic')
        opener=WideOpener();estimator=WideHarmonyTokenEstimator(ROOT/'assets/tokenizers/o200k_base.tiktoken')
        engine=WideCinemaAgent(UNIT_SECRET,_test_opener=opener,token_estimator=estimator)
        with self.assertRaises(Exception):engine.rank(decision)
        self.assertEqual((engine.calls,len(opener.calls)),(0,0))


if __name__=='__main__':unittest.main()
