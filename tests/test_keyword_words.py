import math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from affinityqa.keyword_words import PREFIX,profile_words,word_signals,tokens
from affinityqa.keyword_calibrator import cosine_signals
from affinityqa.errors import SchemaError


class KeywordWordsTests(unittest.TestCase):
    def setUp(self):self.movies={str(i):{PREFIX+'blue_ocean'} for i in range(20)}

    def test_composition_matches_words_without_equating_ids(self):
        profile={PREFIX+'ocean_blue':1}
        self.assertEqual(cosine_signals(self.movies,profile)['0'],0)
        signals,_=word_signals(self.movies,profile,profile)
        self.assertAlmostEqual(signals['A']['0'],1)
        self.assertEqual(tokens(PREFIX+'Blue_OCEAN_2020'),{'blue','ocean','2020'})

    def test_unknown_tokens_remain_in_norm(self):
        a={PREFIX+'blue_ocean':1};b={PREFIX+'blue_ocean_unknown':1}
        signals,_=word_signals(self.movies,a,b)
        expected=2/(math.sqrt(2+(math.log(21)+1)**2)*math.sqrt(2))
        self.assertAlmostEqual(signals['A']['0'],1);self.assertAlmostEqual(signals['B']['0'],expected)

    def test_max_affinity_not_sum_duplicate_inflation(self):
        a={PREFIX+'blue_ocean':.6,PREFIX+'ocean_blue':.4,PREFIX+'blue_blue':.8}
        self.assertEqual(profile_words(a),{'blue':.8,'ocean':.6})
        original=word_signals(self.movies,{PREFIX+'blue_ocean':.6},None)[0]['A']
        duplicate=word_signals(self.movies,{PREFIX+'blue_ocean':.6,PREFIX+'ocean_blue':.6},None)[0]['A']
        self.assertEqual(original,duplicate)

    def test_none_masks_and_pool_requires_both(self):
        a={PREFIX+'blue_ocean':1}
        signals,observed=word_signals(self.movies,a,None)
        self.assertEqual(observed,{'A':True,'B':False,'pooled':False});self.assertEqual(set(signals['B'].values()),{0.});self.assertEqual(signals['B'],signals['pooled'])
        signals,observed=word_signals(self.movies,None,None)
        self.assertEqual(observed,{'A':False,'B':False,'pooled':False});self.assertTrue(all(set(v.values())=={0.} for v in signals.values()))

    def test_pooled_vector_precedes_cosine(self):
        a={PREFIX+'blue_ocean':1};b={PREFIX+'unknown':1};signals,_=word_signals(self.movies,a,b)
        direct=word_signals(self.movies,{**a,**b},None)[0]['A']
        self.assertEqual(signals['pooled'],direct);self.assertNotAlmostEqual(signals['pooled']['0'],(signals['A']['0']+signals['B']['0'])/2)

    def test_invalid_namespaces_values_fields_and_catalog(self):
        for invalid in ({},{'reference':1},{'urn:tag:genre:blue':1},{PREFIX+'':1},{PREFIX+'blue':True},{PREFIX+'blue':math.nan},{PREFIX+'blue':math.inf},{PREFIX+'blue':-1},{PREFIX+'blue':0},{PREFIX+'blue':1.1},{PREFIX+'blue':{'reference':1}}):
            with self.assertRaises(SchemaError):word_signals(self.movies,invalid,None)
        for movies in ({},dict(list(self.movies.items())[:-1]),{**self.movies,'extra':{PREFIX+'blue'}},{**self.movies,'0':set()},{**self.movies,'0':{'reference'}}):
            with self.assertRaises(SchemaError):word_signals(movies,None,None)


if __name__=='__main__':unittest.main()
