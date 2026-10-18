"""Synthetic literal-source, indices and independent reconstruction boundaries."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
from affinityqa.models import parse_entities
from affinityqa.wide_cinema_grounding import grounding_registry,validate_registry,display_for_receipt,FALLBACK
from affinityqa.wide_cinema_discovery import context_from_samples,qloo_request,make_decision,model_input,validate_output,result_for
from affinityqa.wide_cinema_agent import wire,model_manifest
from affinityqa.wide_cinema_verify import _context,verify_discoveries,verify_packet
from test_wide_cinema_capture import request_fixture,seed_fixture,WideTransport
import test_wide_cinema_capture as capture_fixtures
from test_wide_cinema_discovery import output_fixture

ES='Una ficha sintética en español describe únicamente este registro de prueba, sin afirmar preferencias personales.'
EN='A synthetic English description belongs only to this fixture record and makes no claim about personal taste.'


def fixture(descriptions=None,*,duplicate=False):
    def mutate(body,page):
        for row in body['results']['entities']:
            row['properties']['short_descriptions']=copy.deepcopy(descriptions)
    transport=WideTransport(pages={1:[1,2,3,4,5],2:[1,2,3,4,5] if duplicate else []},mutation=mutate)
    samples=[];seed=seed_fixture()
    for page in (1,2):
        request=qloo_request('movie',seed,None,page);response=transport.send(request['path'],request['params'])
        sample={'source':'test-double-only','request':request,'status':200,'response':response.body,
            'response_sha256':fingerprint(response.body),'response_headers':{},'elapsed_ms':1,'attempt':1,'live_network_request':False}
        samples.append({'sample':sample,'sample_sha256':fingerprint(sample)})
    return context_from_samples('movie',seed,None,samples),samples


class SourceGroundingTests(unittest.TestCase):
    def test_exact_es_preferred_and_duplicate_literal_deduplicated(self):
        context,_=fixture([{'languages':['en'],'value':EN},{'languages':['es'],'value':ES},{'languages':['es'],'value':ES}])
        reason=context['grounded_explanations'][0]
        self.assertEqual(reason['text'],ES);self.assertEqual(reason['evidence']['language'],'es')
        self.assertEqual(reason['evidence']['value_pointer'],'/response/results/entities/0/properties/short_descriptions/1/value')
        self.assertEqual(reason['evidence']['value_sha256'],hashlib.sha256(ES.encode()).hexdigest())
        self.assertEqual(context['grounding_sha256'],fingerprint(context['grounded_explanations']))

    def test_english_only_is_literal_and_explicitly_labelled(self):
        context,_=fixture([{'languages':['en'],'value':EN}]);row=context['grounded_explanations'][0]
        self.assertEqual((row['text'],row['evidence']['language'],row['kind']),(EN,'en','SOURCE_EXTRACT'))

    def test_missing_malformed_conflicting_and_unsafe_values_use_closed_fallback(self):
        cases=[None,[],{},[None],[{'languages':'es','value':ES}],[{'languages':['es'],'value':None}],
            [{'languages':['es'],'value':ES},{'languages':['es'],'value':ES+' Otro.'},{'languages':['en'],'value':EN}],
            [{'languages':['es'],'value':'x'*39},{'languages':['en'],'value':EN}],
            [{'languages':['es'],'value':'x'*241}], [{'languages':['es'],'value':' '+ES}],
            [{'languages':['es'],'value':ES+'\x00'}],[{'languages':['es'],'value':ES+'\u200b'}],
            [{'languages':['es'],'value':'gsk_'+'s'*40+' '+ES}],[{'languages':['es'],'value':'PRIVATE_SECRET_CANARY '+ES}]]
        for values in cases:
            with self.subTest(values=values):
                context,_=fixture(values);row=context['grounded_explanations'][0]
                self.assertEqual((row['text'],row['kind']),(FALLBACK,'RETRIEVAL_CONTEXT'))
                self.assertEqual((row['evidence']['language'],row['evidence']['value_pointer'],row['evidence']['value_sha256']),(None,None,None))
                self.assertEqual(row['evidence']['page'],1)

    def test_unicode_is_literal_without_nfkc_or_translation_and_html_is_data(self):
        for literal in ('Ｆｉｃｈａ sintética conserva caracteres compatibles y acentos e\u0301 exactamente como aparecen en esta prueba.',
                        '<script>window.syntheticPwned=true</script> Esta ficha es texto sintético, no HTML ejecutable.'):
            context,_=fixture([{'languages':['es'],'value':literal}])
            self.assertEqual(context['grounded_explanations'][0]['text'],literal)

    def test_first_observation_only_no_later_page_rescue(self):
        context,samples=fixture(None,duplicate=True)
        samples[1]['sample']['response']['results']['entities'][0]['properties']['short_descriptions']=[{'languages':['es'],'value':ES}]
        samples[1]['sample']['response_sha256']=fingerprint(samples[1]['sample']['response'])
        rows=grounding_registry(context['candidate_catalog'],samples)
        self.assertEqual(rows[0]['text'],FALLBACK);self.assertEqual(rows[0]['evidence']['page'],1)

    def test_independent_context_reconstructs_registry_and_rejects_producer_dependency(self):
        context,samples=fixture([{'languages':['es'],'value':ES}])
        from unittest.mock import patch
        independent=[(row['sample'],row['sample_sha256'],parse_entities(row['sample']['response'],insights=True)) for row in samples]
        with patch('affinityqa.wide_cinema_grounding.grounding_registry',side_effect=AssertionError('Producer must not validate itself')):
            self.assertEqual(_context('movie',seed_fixture(),None,independent),context)

    def test_closed_registry_rejects_identity_pointer_language_and_hash_tamper(self):
        context,_=fixture([{'languages':['es'],'value':ES}]);original=context['grounded_explanations']
        for change in ({'entity_id':context['candidate_catalog'][1]['entity_id']},{'title':'Wrong film'},
            {'release_year':True},{'value_pointer':'/etc/passwd'},{'languages_pointer':'/wrong'},
            {'value_sha256':'0'*64},{'language':'fr'},{'sample_sha256':'not-a-hash'}):
            rows=copy.deepcopy(original);rows[0]['evidence'].update(change)
            with self.subTest(change=change),self.assertRaises(SchemaError):validate_registry(context['candidate_catalog'],rows)

    def test_model_wire_has_only_index_output_contract_and_no_source_metadata(self):
        context,_=fixture([{'languages':['es'],'value':ES}]);decision=make_decision(request_fixture(),context,'source-only-server')
        data=model_input(decision);payload=wire(decision,model_manifest('test-double-only'))
        self.assertNotIn(ES,json.dumps(payload,ensure_ascii=False));self.assertNotIn('grounded_explanations',data)
        self.assertEqual(set(data['output_contract']['properties']['ordered_catalog_indices']['items']['properties']),{'catalog_index'})
        output=output_fixture(decision);checked=validate_output(decision,output)
        self.assertEqual(set(checked),{'ranking','choices'})
        for key in ('text','reason','reason_refs','synopsis'):
            bad=copy.deepcopy(output);bad['ordered_catalog_indices'][0][key]='Invented plot content must be impossible.'
            with self.subTest(key=key),self.assertRaisesRegex(SchemaError,'OUTPUT_CHOICE_SHAPE'):validate_output(decision,bad)
        self.assertTrue(all(reason['text']==ES for reason in result_for(decision,output)['reasons']))


class CapturedGroundingTests(unittest.TestCase):
    def setUp(self):
        self.f=capture_fixtures.WideCaptureTests('test_movie100_actual_candidates_three_qloo_one_model');self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_envelope_remains_actual_indices_separate_from_server_reason(self):
        self.f.finish();packet=json.loads((self.f.directory/'wide-execution-001.json').read_bytes())
        block=packet['observation']['provider_envelope']['choice']['ordered_catalog_indices']
        self.assertTrue(all(set(row)=={'catalog_index'} for row in block))
        self.assertNotIn('reasons',packet['response']);self.assertEqual(packet['response']['selected_catalog_indices'],block)
        manifest=json.loads((self.f.directory/'wide-model-manifest.json').read_bytes())
        forged=copy.deepcopy(packet);forged['observation']['provider_envelope']['choice']['ordered_catalog_indices'][0]['text']=ES
        with self.assertRaisesRegex(SchemaError,'eligible catalog index'):verify_packet(forged,manifest,forged['effective_request'])

    def test_rehashed_registry_forgery_cannot_replace_independent_raw_reconstruction(self):
        self.f.finish();path=self.f.directory/'wide-context.json';ledger=self.f.directory/'ledger.jsonl'
        context=json.loads(path.read_bytes());context['grounded_explanations'][0]['text']=ES
        context['grounded_explanations'][0]['evidence']['value_sha256']=hashlib.sha256(ES.encode()).hexdigest()
        context['grounding_sha256']=fingerprint(context['grounded_explanations'])
        context['context_sha256']=fingerprint({k:v for k,v in context.items() if k!='context_sha256'})
        path.write_text(json.dumps(context),encoding='utf8')
        events=[json.loads(line) for line in ledger.read_bytes().splitlines()]
        next(row['data'] for row in events if row['kind']=='wide_context_frozen')['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        ledger.write_text(''.join(json.dumps(row)+'\n' for row in events),encoding='utf8')
        with self.assertRaisesRegex(SchemaError,'independently reconstructed frozen universe'):verify_discoveries(self.f.directory)

    def test_read_only_display_is_outside_receipt_and_rejects_changed_raw_page(self):
        _,receipt=self.f.finish();before=copy.deepcopy(receipt)
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.f.directory.iterdir() if p.is_file()}
        display=display_for_receipt(self.f.directory,receipt,'a'*64)
        self.assertEqual(receipt,before);self.assertEqual(display['delivered'],receipt['wide_cinema_results']['delivered'])
        self.assertEqual(display['binding_sha256'],fingerprint({k:v for k,v in display.items() if k!='binding_sha256'}))
        self.assertEqual(files,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.f.directory.iterdir() if p.is_file()})
        context=json.loads((self.f.directory/'wide-context.json').read_bytes())
        name=next(name for name,digest in receipt['artifact_sha256'].items() if digest==context['pages'][0]['sample_sha256'])
        page=self.f.directory/name;page.write_bytes(page.read_bytes()+b' ')
        with self.assertRaises(SchemaError):display_for_receipt(self.f.directory,receipt,'a'*64)


if __name__=='__main__':unittest.main()
