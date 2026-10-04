import copy,math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from affinityqa.keyword_calibrator import (PREFIX,profile_vector,cosine_scores,pooled_vector,signals_for_pair,features,fit,capture,samples,movie_keywords,cosine_signals,combined_profile)
from affinityqa.errors import SchemaError


class KeywordCalibratorTests(unittest.TestCase):
    def setUp(self):
        self.ids=[str(i) for i in range(20)]
        self.docs={i:[PREFIX+'shared'] for i in self.ids}

    def test_unknown_keywords_remain_in_denominator(self):
        one=cosine_scores({PREFIX+'shared':1},self.docs)
        unknown=cosine_scores({PREFIX+'shared':1,PREFIX+'missing':1},self.docs)
        expected=1/math.sqrt(1+(math.log(21)+1)**2)
        self.assertAlmostEqual(one['0'],1);self.assertAlmostEqual(unknown['0'],expected)

    def test_pooling_precedes_cosine_not_scores(self):
        a={PREFIX+'shared':1};b={PREFIX+'missing':1}
        out=signals_for_pair(a,b,self.docs)
        self.assertEqual(out['pooled'],cosine_scores(pooled_vector(a,b),self.docs))
        self.assertNotAlmostEqual(out['pooled']['0'],(out['A']['0']+out['B']['0'])/2)
        self.assertEqual(pooled_vector(a,b),pooled_vector(b,a))

    def test_profile_schema_exclusion_and_invalid_values(self):
        rows=[{'tag_id':PREFIX+str(i),'name':str(i),'affinity':.5} for i in range(11)]
        self.assertEqual(len(profile_vector(rows,['0'])),10)
        for v in (True,None,math.nan,math.inf,-.01,1.01):
            bad=copy.deepcopy(rows);bad[0]['affinity']=v
            with self.assertRaises(SchemaError):profile_vector(bad)
        bad=copy.deepcopy(rows);bad[0]['reference']=1
        with self.assertRaises(SchemaError):profile_vector(bad)
        bad=copy.deepcopy(rows);bad[0]['tag_id']='urn:tag:genre:rock'
        with self.assertRaises(SchemaError):profile_vector(bad)
        with self.assertRaises(SchemaError):profile_vector(rows,['0','1'])

    def test_catalog_coverage_and_signal_values(self):
        for docs in ({k:v for k,v in self.docs.items() if k!='0'},{**self.docs,'extra':[PREFIX+'shared']}):
            with self.assertRaises(SchemaError):cosine_scores({PREFIX+'shared':1},docs)
        ctx={i:[.5]*6 for i in self.ids};s={i:.5 for i in self.ids}
        for bad in ({**s,'reference':.5},{i:v for i,v in s.items() if i!='0'},{**s,'0':math.nan}):
            with self.assertRaises(SchemaError):features(self.ids,ctx,bad)

    def test_raw_movie_metadata_binary_and_canonical(self):
        rows=[{'entity_id':f'AAAAAAAA-0000-4000-8000-{i:012d}','types':['urn:entity:movie'],'tags':[{'type':'urn:tag:keyword:media','tag_id':PREFIX+'shared'}]*2} for i in range(20)]
        movies=movie_keywords(rows)
        self.assertTrue(all(len(tags)==1 for tags in movies.values()));self.assertTrue(all(i.startswith('aaaaaaaa') for i in movies))
        a={PREFIX+'shared':1};self.assertTrue(all(abs(v-1)<1e-12 for v in cosine_signals(movies,combined_profile(a,a)).values()))
        bad=copy.deepcopy(rows);bad[-1]=bad[0]
        with self.assertRaises(SchemaError):movie_keywords(bad)
        bad=copy.deepcopy(rows);bad[0]['tags']=[]
        with self.assertRaises(SchemaError):movie_keywords(bad)

    def test_eight_dimensional_solver_residual_and_equal_weighting(self):
        rows=[[(math.sin((i+1)*(j+1))+1)/2 for j in range(8)] for i in range(20)]
        y=[i/19 for i in range(20)];beta=fit([(rows,y)])
        means=[sum(r[j] for r in rows)/20 for j in range(8)];mean_y=sum(y)/20
        for j in range(8):
            residual=sum((r[j]-means[j])*(sum((r[k]-means[k])*beta[k] for k in range(8))-(v-mean_y)) for r,v in zip(rows,y))/20+.001*beta[j]
            self.assertLess(abs(residual),1e-10)
        for a,b in zip(beta,fit([(rows,y)]*3)):self.assertAlmostEqual(a,b,places=12)
        for penalty in (.01,True,math.nan):
            with self.assertRaises(SchemaError):fit([(rows,y)],penalty)

    def case(self):
        a={i:n/19 for n,i in enumerate(self.ids)};b={i:1-n/19 for n,i in enumerate(self.ids)}
        return {'pair_id':'test','baseline':{p:[self.ids[:]]*3 for p in ('A','B')},'movie':{'A':[a]*3,'B':[b]*3},'individual':{p:[{'entity_id':str(n),'affinity':.5,'values':values} for n in range(3)] for p,values in [('A',a),('B',b)]}}

    def test_capture_constructs_each_arm_with_its_own_signal(self):
        c=self.case();a={i:n/19 for n,i in enumerate(self.ids)};b={i:1-n/19 for n,i in enumerate(self.ids)};pooled={i:float(i=='7') for i in self.ids}
        signals={'test':{'A':a,'B':b,'pooled':pooled}}
        out=capture([c],signals,[0]*7+[1],'frozen')['cases'][0]['rankings']
        self.assertEqual(out['qloo_graph']['A'][0],self.ids[::-1]);self.assertEqual(out['swapped_graph']['A'][0],self.ids)
        self.assertEqual(out['neutral_graph']['A'][0][0],'7');self.assertEqual(out['neutral_graph']['A'],out['neutral_graph']['B'])
        previous=capture([c],signals,[0,1]+[0]*6,'frozen')['cases'][0]['rankings']
        self.assertEqual(previous['neutral_graph']['A'][0],self.ids)
        with self.assertRaises(SchemaError):capture([{**c,'reference':[]}],signals,[0]*8,'frozen')

    def test_excluded_references_never_accessed(self):
        class NoReferences(dict):
            def __getitem__(self,key):raise AssertionError('Excluded reference accessed')
        self.assertEqual(samples([{'pair_id':'held'}],{},NoReferences(),exclude='held'),([],[]))


if __name__=='__main__':unittest.main()
