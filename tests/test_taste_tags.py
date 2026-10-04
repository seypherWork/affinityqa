import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from affinityqa.taste_tags import NAMESPACE,parse_media_tags,validate_tag_request,TasteTagClient
from affinityqa.errors import SchemaError,BudgetError,TransportError
from affinityqa.qloo import Response


class TasteTagTests(unittest.TestCase):
    def setUp(self):
        self.params={'filter.type':'urn:tag','filter.tag.types':NAMESPACE,'filter.parents.types':'urn:entity:movie','take':20,'signal.interests.entities':'11111111-1111-4111-8111-111111111111'}
        self.body={'success':True,'results':{'tags':[{'tag_id':NAMESPACE+':friendship','name':'Friendship','types':['urn:entity:movie'],'subtype':NAMESPACE,'query':{'affinity':.7}}]}}
    def test_unknown_demographic_parameters_are_rejected_before_request(self):
        for extra in ('reference_ranking','signal.demographics.age','explainability'):
            with self.assertRaises(SchemaError):validate_tag_request({**self.params,extra:'x'})
    def test_wrong_namespace_duplicate_or_missing_movie_context_rejected(self):
        for kind in ('namespace','duplicate','movie'):
            b=copy.deepcopy(self.body)
            if kind=='namespace':b['results']['tags'][0]['subtype']='urn:tag:demographics'
            if kind=='duplicate':b['results']['tags']*=2
            if kind=='movie':b['results']['tags'][0]['types']=[]
            with self.assertRaises(SchemaError):parse_media_tags(b)
    def test_missing_affinity_remains_unavailable(self):
        self.body['results']['tags'][0]['query']={}
        self.assertIsNone(parse_media_tags(self.body)[0]['affinity'])
    def test_tag_projection_rejects_original_artist_and_incomplete_catalog(self):
        p={'filter.type':'urn:entity:movie','take':20,'bias.trends':'off','signal.interests.tags':NAMESPACE+':friendship','filter.results.entities':','.join(f'{i:08d}-1111-4111-8111-111111111111' for i in range(20))}
        validate_tag_request(p)
        for bad in ({**p,'signal.interests.entities':self.params['signal.interests.entities']},{**p,'filter.results.entities':self.params['signal.interests.entities']}):
            with self.assertRaises(SchemaError):validate_tag_request(bad)
    def test_provider_error_is_sampled_once_and_never_retried(self):
        class Ledger:
            secrets=();live_requests=0;samples=0
            def sample(self,*a,**kw):self.samples+=1
        class Transport:
            calls=0
            def send(self,*a):self.calls+=1;return Response(429,{'error':'limited'},{})
        t=Transport();l=Ledger();c=TasteTagClient(t,l,max_requests=1)
        with self.assertRaises(TransportError):c.get(self.params)
        self.assertEqual((t.calls,l.samples,l.live_requests),(1,1,1))
        with self.assertRaises(BudgetError):c.get(self.params)
        self.assertEqual(t.calls,1)

if __name__=='__main__':unittest.main()
