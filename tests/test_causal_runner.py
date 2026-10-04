"""Synthetic integration only; never a live-model or Qloo evidence receipt."""
import sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'src')]
import test_causal_agent as fixture_module
from affinityqa.causal_runner import capture_pair,freeze_policy
from affinityqa.evidence import fingerprint
from affinityqa.agents import AgentError


class CausalRunnerTests(unittest.TestCase):
    def setUp(self):
        fixtures=fixture_module.CausalAgentTests();fixtures.setUp()
        self.catalog=fixtures.catalog;self.contexts=fixtures.contexts;self.profiles=dict(zip(('A','B'),fixtures.profiles))
        self.pair={'pair_id':'synthetic-unit-pair','artists':{p:r['name'] for p,r in self.profiles.items()},'split':'development'}
        self.engine=fixture_module.FakeEngine();self.ledger=fixture_module.FakeLedger();self.freeze_calls=[]

    def freeze(self,noise,healthy,controls):
        self.freeze_calls.append(self.engine.calls)
        self.assertEqual(self.engine.calls,6);self.assertEqual(len(controls),9)
        self.assertEqual(len(self.ledger.files),6)
        plan={'catalog_sha256':fingerprint(self.catalog),'source_sha256':{'fixture':'synthetic-unit-only'},'pairs':[self.pair]}
        return freeze_policy(noise,healthy,controls,plan=plan,manifest=self.engine.manifest,ledger=self.ledger)

    def test_full_pipeline_39_calls_policy_precedes_incidents_all_controls(self):
        record,summary,policy=capture_pair(self.engine,self.ledger,self.pair,self.catalog,self.profiles,self.contexts,freeze=self.freeze)
        self.assertEqual(self.engine.calls,39);self.assertEqual(self.freeze_calls,[6]);self.assertEqual(policy['noise_barrier'],0)
        self.assertEqual(len(record['healthy_controls']),9);self.assertEqual(sum(c['expected_cache_hit'] for c in record['healthy_controls']),3)
        after_controls=[control for case in record['cases'] for repeat in case['repeats'] for control in repeat['after_controls']]
        self.assertEqual(len(after_controls),9);self.assertTrue(all(c['expected_cache_hit'] and c['trace']['cache_hit'] for c in after_controls))
        self.assertTrue(all(c['diagnosis']['diagnosis']=='NONE' and not c['patch']['applied'] for c in record['healthy_controls']+after_controls))
        self.assertEqual(len(summary['cases']),3)
        for case in summary['cases']:
            self.assertTrue(case['passing']);self.assertTrue(all(case['checks'].values()));self.assertEqual(case['behavior_changed_repeats'],3);self.assertEqual(case['behavioral_recovery_observed_repeats'],3)
        self.assertEqual(policy['cultural_gate'],'NOT_VALIDATED');self.assertEqual(policy['release_gate'],'BLOCKED')
        frozen_index=next(i for i,(kind,_) in enumerate(self.ledger.events) if kind=='policy_frozen')
        executed_before=[data for kind,data in self.ledger.events[:frozen_index] if kind=='observed_model_execution']
        self.assertEqual(len(executed_before),6)
        self.assertIn('causal-summary-synthetic-unit-pair.json',self.ledger.files)

    def test_truncated_engine_stops_without_successful_pair_record(self):
        self.engine.damage='short'
        with self.assertRaises(AgentError):capture_pair(self.engine,self.ledger,self.pair,self.catalog,self.profiles,self.contexts,freeze=self.freeze)
        self.assertEqual(self.engine.calls,1);self.assertEqual(self.freeze_calls,[]);self.assertEqual(self.ledger.files,{})


if __name__=='__main__':unittest.main()
