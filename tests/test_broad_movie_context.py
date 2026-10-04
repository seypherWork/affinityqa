import math,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from affinityqa.models import Entity
from affinityqa.broad_movie_context import select_movies
from affinityqa.errors import SchemaError

def movie(i,name,value=.5,aliases=()):return Entity(i,name,('urn:entity:movie',),value,{'release_year':2000,'aliases':list(aliases)})

class BroadMovieContextTests(unittest.TestCase):
    def setUp(self):
        self.catalog=[movie('c'+str(i),'Catalog '+str(i)) for i in range(20)]
        self.rows=[movie('e'+str(i),'External '+str(i),.5+i/100) for i in range(20)]
    def test_catalog_alias_cannot_enter_indirect_context(self):
        forbidden=movie('new','Another name',1,['Catalog 1']);selected,audit=select_movies([forbidden,*self.rows],self.catalog)
        self.assertEqual({e.entity_id for e in selected},{e.entity_id for e in self.rows});self.assertEqual(audit[0]['reason'],'catalog_identity_overlap')
    def test_transitive_alias_exclusion_is_order_independent(self):
        a=movie('a','Catalog 1',1,['Bridge']);b=movie('b','Bridge',.9,['Third']);c=movie('d','Third',.8)
        for rows in ([a,b,c,*self.rows],[c,b,a,*reversed(self.rows)]):
            selected,audit=select_movies(rows,self.catalog);self.assertEqual({e.entity_id for e in selected},{e.entity_id for e in self.rows});self.assertEqual(len(audit),3)
    def test_duplicate_identity_cannot_count_twice(self):
        d=movie('different','External 1',.99);selected,audit=select_movies([d,*self.rows],self.catalog)
        self.assertIn('different',{e.entity_id for e in selected});self.assertNotIn('e1',{e.entity_id for e in selected});self.assertEqual(audit[0]['reason'],'duplicate_movie_identity')
    def test_partial_or_nonfinite_context_stops(self):
        with self.assertRaises(SchemaError):select_movies(self.rows[:19],self.catalog)
        for value in (None,True,math.nan,math.inf,-.1,1.1):
            with self.assertRaises(SchemaError):select_movies([movie('bad','Bad',value),*self.rows],self.catalog)
    def test_missing_year_is_recorded_not_invented(self):
        missing=Entity('missing','Unknown',('urn:entity:movie',),.9,{})
        selected,audit=select_movies([missing,*self.rows],self.catalog);self.assertEqual(len(selected),20);self.assertEqual(audit[0]['reason'],'missing_release_year')

if __name__=='__main__':unittest.main()
