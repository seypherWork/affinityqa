"""Controlled SYNTHETIC comparisons, not evidence of real user preference."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from affinityqa import causal_review, context_contrast as contract, public_demo
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
import causal_evidence_fixture as fixture

SOURCE=Path(causal_review.__file__).resolve().parents[2]


class ContextContrastTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='aq-context-synthetic-')
        self.addCleanup(self.tmp.cleanup)
        self.capture=fixture.build_synthetic_capture(Path(self.tmp.name)/'capture',source_root=SOURCE)

    def inputs(self):
        calls=[]
        def observe(*args,**kwargs):
            calls.append((copy.deepcopy(args),copy.deepcopy(kwargs)))
            return contract.context_contrast(*args,**kwargs)
        with patch.object(causal_review,'context_contrast',side_effect=observe):
            result=causal_review.replay_causal(self.capture.root,fixture.PAIR_ID,'wrong-tool-profile',1)
        return result,*calls[0]

    def test_context_only_swap_has_thirteen_controls_and_distinct_phase_requests(self):
        inventory=self.capture.inventory()
        result,args,kwargs=self.inputs()
        value=result['context_contrast']
        self.assertNotEqual(args[1]['request_id'],args[2]['request_id'])
        self.assertEqual(value['status'],'CONTRAST_AVAILABLE')
        self.assertEqual(value['behavioral_effect'],'OBSERVED_CHANGE')
        self.assertEqual(set(value['checks']),set(contract.CHECKS))
        self.assertEqual(len(value['checks']),13)
        self.assertTrue(all(value['checks'].values()))
        self.assertTrue(value['metrics']['recovery_observed'])
        self.assertEqual(self.capture.inventory(),inventory)
        dto=public_demo.replay_dto(result,profile_names=self.capture.profile_names)
        self.assertEqual(dto['schema_version'],3)
        contract.validate_context_contrast(dto['context_contrast'],'wrong-tool-profile',before=dto['before'],after=dto['after'])

    def test_manifest_difference_suppresses_all_positive_effect_metrics(self):
        _,args,kwargs=self.inputs()
        kwargs['manifest']['model']='different-recorded-model'
        value=contract.context_contrast(*args,**kwargs)
        self.assertEqual(value['status'],'CONFOUNDED')
        self.assertFalse(value['checks']['model_manifest_fixed'])
        self.assertEqual(value['behavioral_effect'],'NOT_EVALUATED')
        self.assertIsNone(value['metrics'])

    def test_bound_source_ranking_mismatch_cannot_be_used_as_an_effect(self):
        _,args,kwargs=self.inputs()
        selected=next(p for p in args[5] if p['execution_id']==args[3]['trace']['execution_id'])
        packet=next(p for p in args[6] if p['execution_id']==selected['observation']['source_execution_id'])
        packet['response']['ranked_entity_ids'].reverse()
        with self.assertRaises(SchemaError):contract.context_contrast(*args,**kwargs)

    def test_duplicate_healthy_executions_cannot_establish_a_reference(self):
        _,args,kwargs=self.inputs()
        kwargs['healthy']=[copy.deepcopy(kwargs['healthy'][0])]*3
        with self.assertRaises(SchemaError):contract.context_contrast(*args,**kwargs)

    def test_healthy_variation_above_frozen_noise_is_confounded(self):
        _,args,kwargs=self.inputs()
        control=kwargs['healthy'][1]
        packet=next(p for p in args[6] if p['execution_id']==control['trace']['execution_id'])
        control['ranking'].reverse()
        packet['response']['ranked_entity_ids']=copy.deepcopy(control['ranking'])
        packet['observation']['output_sha256']=fingerprint(control['ranking'])
        control['trace']['output_sha256']=fingerprint(control['ranking'])
        value=contract.context_contrast(*args,**kwargs)
        self.assertEqual(value['status'],'CONFOUNDED')
        self.assertTrue(value['checks']['healthy_reference_fixed'])
        self.assertFalse(value['checks']['healthy_variation_within_frozen_noise'])
        self.assertIsNone(value['metrics'])

    def test_valid_healthy_decision_from_other_profile_does_not_establish_fixed_input(self):
        _,args,kwargs=self.inputs()
        record=json.loads((self.capture.run/('causal-pair-'+fixture.PAIR_ID+'.json')).read_text('utf8'))
        kwargs['healthy'][1]=record['healthy']['A'][1]
        value=contract.context_contrast(*args,**kwargs)
        self.assertEqual(value['status'],'CONFOUNDED')
        self.assertFalse(value['checks']['healthy_reference_fixed'])
        self.assertIsNone(value['metrics'])

    def test_no_effect_is_a_valid_result_even_when_context_changes(self):
        original=fixture.SyntheticEngine.rank
        def stable(engine,request):
            value=original(engine,request)
            value['ranked_entity_ids']=[r['entity_id'] for r in request['catalog']]
            engine.observations[-1]['output_sha256']=fingerprint(value['ranked_entity_ids'])
            return value
        with patch.object(fixture.SyntheticEngine,'rank',stable):
            captured=fixture.build_synthetic_capture(Path(self.tmp.name)/'no-effect',source_root=SOURCE)
        result=causal_review.replay_causal(captured.root,fixture.PAIR_ID,'wrong-tool-profile',1)
        value=result['context_contrast']
        self.assertEqual(value['status'],'CONTRAST_AVAILABLE')
        self.assertEqual(value['behavioral_effect'],'NO_OBSERVED_EFFECT')
        self.assertEqual(value['metrics']['ranking_distance'],0)
        self.assertFalse(value['metrics']['recovery_observed'])
        self.assertTrue(value['metrics']['recovery_verified'])

    def test_other_supported_faults_do_not_claim_context_isolation(self):
        for fault in ('cache-omits-profile','stale-profile'):
            value=causal_review.replay_causal(self.capture.root,fixture.PAIR_ID,fault,1)['context_contrast']
            self.assertEqual(value['status'],'NOT_APPLICABLE')
            self.assertIsNone(value['checks']);self.assertIsNone(value['metrics'])

    def test_closed_contract_rejects_extra_truthy_nonfinite_and_inconsistent_claims(self):
        result,_,_=self.inputs()
        base=result['context_contrast']
        mutations=[lambda v:v.update(private_packet='PRIVATE_CANARY'),
            lambda v:v['checks'].update(task_fixed=1),
            lambda v:v['checks'].pop('catalog_fixed'),
            lambda v:v['metrics'].update(ranking_distance=float('nan')),
            lambda v:v['metrics'].update(recorded_noise_barrier=float('inf')),
            lambda v:v['metrics'].update(changed_top_five=True),
            lambda v:v['metrics'].update(top_five_order_changed=False),
            lambda v:v['metrics'].update(ranking_distance=0),
            lambda v:v['metrics'].update(recovery_observed=False),
            lambda v:v.update(behavioral_effect='NO_OBSERVED_EFFECT')]
        for mutate in mutations:
            value=copy.deepcopy(base);mutate(value)
            with self.subTest(value=value),self.assertRaises(SchemaError):
                contract.validate_context_contrast(value,'wrong-tool-profile')

    def test_exact_noise_boundary_and_recovery_are_separate(self):
        result,_,_=self.inputs()
        value=copy.deepcopy(result['context_contrast']);m=value['metrics']
        m['recorded_noise_barrier']=m['ranking_distance']
        m['recovery_observed']=False;value['behavioral_effect']='NO_OBSERVED_EFFECT'
        contract.validate_context_contrast(value,'wrong-tool-profile')
        value=copy.deepcopy(result['context_contrast']);m=value['metrics']
        m['maximum_after_healthy_distance']=1;m['recovery_verified']=False;m['recovery_observed']=False
        contract.validate_context_contrast(value,'wrong-tool-profile')
        self.assertEqual(value['behavioral_effect'],'OBSERVED_CHANGE')

    def test_public_metrics_must_match_displayed_film_identities(self):
        result,_,_=self.inputs()
        result['before']=copy.deepcopy(result['after'])
        with self.assertRaises(SchemaError):
            public_demo.replay_dto(result,profile_names=self.capture.profile_names)

    def test_context_projection_requires_diagnosis_and_old_readers_stay_explicit(self):
        result,_,_=self.inputs()
        del result['diagnostic_evidence']
        with self.assertRaises(SchemaError):public_demo.replay_dto(result,profile_names=self.capture.profile_names)


if __name__=='__main__':unittest.main()
