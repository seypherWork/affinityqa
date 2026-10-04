import copy,math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from affinityqa.pairwise_rank_calibrator import training_pairs,objective_derivatives,logistic_terms,fit
from affinityqa.errors import SchemaError


class PairwiseRankCalibratorTests(unittest.TestCase):
    def setUp(self):
        self.rows=[[(math.sin((i+1)*(j+1))+1)/2 for j in range(8)] for i in range(20)]
        self.targets=[1-i/19 for i in range(20)]
        self.data=[(self.rows,self.targets)]

    def test_top_five_85_pairs_weight_formula_and_coverage(self):
        rows=[[i/19]+[0]*7 for i in range(20)];pairs=training_pairs([(rows,self.targets)])
        self.assertEqual(len(pairs),85);self.assertAlmostEqual(sum(w for _,w in pairs),1)
        expected=[(j-i)*(1/math.log2(i+2)-(1/math.log2(j+2) if j<5 else 0)) for i in range(5) for j in range(i+1,20)]
        total=sum(expected)
        for (_,w),wanted in zip(pairs,expected):self.assertAlmostEqual(w,wanted/total)
        self.assertEqual([d[0] for d,_ in pairs],[i/19-j/19 for i in range(5) for j in range(i+1,20)])

    def test_finite_difference_gradient_and_hessian(self):
        pairs=training_pairs(self.data);w=[(i-3)*.07 for i in range(8)];_,g,h=objective_derivatives(w,pairs);eps=1e-5
        for j in range(8):
            plus=w[:];minus=w[:];plus[j]+=eps;minus[j]-=eps
            vp,gp,_=objective_derivatives(plus,pairs);vm,gm,_=objective_derivatives(minus,pairs)
            self.assertAlmostEqual((vp-vm)/(2*eps),g[j],places=8)
            for i in range(8):self.assertAlmostEqual((gp[i]-gm[i])/(2*eps),h[i][j],places=8)

    def test_profile_duplication_preserves_objective_and_solution(self):
        one=fit(self.data);three=fit(self.data*3)
        self.assertEqual(three['training_pairs'],255)
        self.assertAlmostEqual(one['objective'],three['objective'],places=12)
        for a,b in zip(one['coefficients'],three['coefficients']):self.assertAlmostEqual(a,b,places=10)

    def test_invalid_targets_rows_and_penalties_stop(self):
        variants=[]
        for value in (True,math.nan,math.inf,-1,1.01,.12345):
            y=self.targets[:];y[0]=value;variants.append((self.rows,y))
        variants.extend([(self.rows,self.targets[:-1]),(self.rows[:-1],self.targets),([r[:-1] for r in self.rows],self.targets)])
        y=self.targets[:];y[0]=y[1];variants.append((self.rows,y))
        rows=copy.deepcopy(self.rows);rows[0][0]=True;variants.append((rows,self.targets))
        for sample in variants:
            with self.assertRaises(SchemaError):fit([sample])
        for penalty in (True,0,.01,math.nan):
            with self.assertRaises(SchemaError):fit(self.data,penalty)

    def test_overflow_safe_logistic_extremes(self):
        for margin in (-1e300,-1000,-1,0,1,1000,1e300):
            loss,p,c=logistic_terms(margin)
            self.assertTrue(all(math.isfinite(v) for v in (loss,p,c)));self.assertGreaterEqual(loss,0);self.assertTrue(0<=p<=1);self.assertTrue(0<=c<=.25)
        self.assertEqual(logistic_terms(-1000),(1000.,1.,0.));self.assertEqual(logistic_terms(1000),(0.,0.,0.))

    def test_solver_converges_and_improves_fixed_toy(self):
        initial=objective_derivatives([0]*8,training_pairs(self.data))[0];result=fit(self.data)
        self.assertTrue(result['converged']);self.assertLessEqual(result['gradient_inf_norm'],1e-8);self.assertLessEqual(result['iterations'],50);self.assertLess(result['objective'],initial);self.assertEqual(len(result['coefficients']),8)
        self.assertEqual(result,fit(self.data))


if __name__=='__main__':unittest.main()
