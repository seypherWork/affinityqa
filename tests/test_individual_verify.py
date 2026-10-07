"""Adversarial offline evidence tests; no provider or model execution."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from affinityqa.individual_capture import prepare_plan, execute_capture
from affinityqa.individual_verify import verify_individual, write_receipt
from affinityqa.causal_agent import ToolContextMovieAgent, PROTOCOL, PROMPT
from affinityqa.evidence import fingerprint
from affinityqa.errors import SchemaError
from affinityqa.qloo import Settings
from affinityqa.errors import TransportError
from test_individual_capture import fixture, EngineDouble, TransportDouble


class AuditEngine(EngineDouble):
    def rank(self, request):
        response = super().rank(request)
        schema = {'type':'object','properties':{'ordered_catalog_indices':{'type':'array',
            'items':{'type':'integer','enum':list(range(20))},'minItems':20,'maxItems':20}},
            'required':['ordered_catalog_indices'],'additionalProperties':False}
        self.last_input = self.adapter.decision_input(request, schema)
        self.observations[-1].update(input_sha256=fingerprint(self.last_input), done=True,
            done_reason='stop', private_thinking_recorded=False, prompt_eval_count=300)
        return response


class InterruptedAuditEngine(AuditEngine):
    def rank(self, request):
        if self.calls == 8:
            self.calls += 1
            raise TransportError('Synthetic interruption after policy freezing.')
        return super().rank(request)


class RegressiveAuditEngine(AuditEngine):
    def rank(self, request):
        response = super().rank(request)
        if self.calls > 6:
            ids = [r['entity_id'] for r in request['catalog']]
            response['ranked_entity_ids'] = ids[7:]+ids[:7]
            self.observations[-1]['output_sha256'] = fingerprint(response['ranked_entity_ids'])
        return response


class ReadinessContractDouble(AuditEngine):
    """Production-shaped metadata; ledger provenance always remains simulated."""
    def __init__(self):
        super().__init__()
        self.manifest.pop('source')
        self.manifest.update(provider='ollama-local',prompt_version=PROTOCOL,prompt_sha256=fingerprint(PROMPT),
            options={'temperature':0,'seed':7,'num_ctx':8192,'num_predict':1024},private_thinking_recorded=False,
            inference_timeout_seconds=180,tool_contract='qloo-context-input-not-quality-label-v1')
    def warmup(self):
        return {'source':'test-double-only','status':'READY','model':self.manifest['model'],
            'model_digest':self.manifest['model_digest'],'context_length':8192,'inference_calls':0,'new_qloo_requests':0}


class IndividualVerifyTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT/'.test-runs'
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.request = fixture()
        self.output = self.parent/'capture'

    def capture(self, engine=None, transport=None):
        plan = prepare_plan(self.request, self.output, 'http://127.0.0.1:11434')
        with patch('affinityqa.individual_capture.time.sleep'):
            report, self.run = execute_capture(self.request, self.output, 'http://127.0.0.1:11434',
                plan['plan_sha256'], Settings('unit-key-only'), _test_adapters=(
                    lambda: engine or AuditEngine(), lambda: transport or TransportDouble(self.request)))
        return report

    def inventory(self):
        return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.run.iterdir()}

    def edit(self, name, action):
        path = self.run/name
        value = json.loads(path.read_text('utf-8'))
        action(value)
        path.write_text(json.dumps(value), 'utf-8')

    def events(self, action):
        path = self.run/'ledger.jsonl'
        rows = [json.loads(line) for line in path.read_text('utf-8').splitlines()]
        action(rows)
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows), 'utf-8')

    def test_complete_simulation_is_verified_readonly_and_never_promoted(self):
        self.capture()
        before = self.inventory()
        receipt = verify_individual(self.run)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_COMPLETE')
        self.assertEqual(receipt['recorded_source'], 'test-double-only')
        self.assertEqual(receipt['provenance'], 'SIMULATION_ONLY')
        self.assertFalse(receipt['external_service_attested'])
        self.assertEqual((receipt['verified_model_packets'], receipt['verified_provider_samples']), (39,4))
        self.assertEqual(receipt['independent_score_reports'], 3)
        self.assertEqual(self.inventory(), before)

    def test_partial_provider_failure_preserves_attempt_without_filling_sample(self):
        self.capture(transport=TransportDouble(self.request, fail=True))
        receipt = verify_individual(self.run)
        self.assertEqual(receipt['verification_status'], 'VERIFIED_PARTIAL')
        self.assertEqual((receipt['qloo_attempts'],receipt['verified_provider_samples'],receipt['verified_model_packets']), (1,0,0))
        self.assertEqual(receipt['causal_gate'], 'NOT_EVALUATED')

    def test_partial_model_failure_preserves_attempt_without_filling_packet(self):
        self.capture(engine=AuditEngine(fail=True))
        receipt = verify_individual(self.run)
        self.assertEqual((receipt['model_attempts'],receipt['verified_model_packets'],receipt['verified_provider_samples']), (1,0,4))

    def test_partial_after_policy_and_incident_is_reviewable_without_completion(self):
        self.capture(engine=InterruptedAuditEngine())
        receipt = verify_individual(self.run)
        self.assertEqual((receipt['verification_status'],receipt['model_attempts'],receipt['verified_model_packets']), ('VERIFIED_PARTIAL',9,8))
        self.assertEqual(receipt['behavioral_gate'],'NOT_EVALUATED')

    def test_complete_failure_is_verified_and_not_hidden_as_pass(self):
        self.capture(engine=RegressiveAuditEngine())
        receipt = verify_individual(self.run)
        self.assertEqual(receipt['verification_status'],'VERIFIED_COMPLETE')
        self.assertEqual(receipt['causal_gate'],'FAIL')
        self.assertEqual(receipt['behavioral_gate'],'INCONCLUSIVE')

    def test_boolean_counter_in_ledger_is_not_equal_to_numeric_zero(self):
        self.capture()
        self.events(lambda rows:rows[0]['data'].update(model_calls=False))
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_partial_attempt_counter_cannot_claim_two_or_many_unrecorded_decisions(self):
        self.capture(engine=InterruptedAuditEngine())
        for invented in (10,39):
            with self.subTest(invented=invented):
                self.edit('individual-report.json',lambda r:r.update(model_attempts=invented))
                with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_production_readiness_contract_refuses_boolean_zero_counters(self):
        self.capture(engine=ReadinessContractDouble())
        # Reach the strict metadata branch without relabeling a simulated ledger
        # or treating this unit test as evidence of an external service.
        with patch('affinityqa.individual_verify.STATES',('test-double-only','unused-test-label')):
            self.assertEqual(verify_individual(self.run)['provenance'],'SIMULATION_ONLY')
            for key in ('inference_calls','new_qloo_requests'):
                with self.subTest(counter=key):
                    self.edit('model-readiness.json',lambda r:r.update(inference_calls=0,new_qloo_requests=0))
                    self.edit('model-readiness.json',lambda r:r.update({key:False}))
                    with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_packet_hash_change_is_rejected(self):
        self.capture()
        self.edit('causal-execution-007.json', lambda p:p['observation'].update(input_sha256='0'*64))
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_incomplete_termination_is_rejected(self):
        self.capture()
        self.edit('causal-execution-007.json', lambda p:p['observation'].update(done_reason='length'))
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_source_change_even_with_new_plan_hash_is_rejected(self):
        self.capture()
        plan = json.loads((self.run/'individual-plan.json').read_text('utf-8'))
        plan['source_sha256']['causal_agent.py'] = '0'*64
        plan['plan_sha256'] = fingerprint({k:v for k,v in plan.items() if k!='plan_sha256'})
        (self.run/'individual-plan.json').write_text(json.dumps(plan), 'utf-8')
        self.edit('individual-report.json', lambda r:r.update(plan_sha256=plan['plan_sha256']))
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_provider_host_change_is_rejected(self):
        self.capture()
        name = sorted(self.run.glob('http-*.json'))[0].name
        self.edit(name, lambda s:s['request'].update(host='https://other.invalid'))
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_mixed_simulation_and_live_source_is_rejected(self):
        self.capture()
        self.events(lambda rows:rows[0].update(source='qloo-tool+local-llm'))
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_complete_report_cannot_hide_missing_decision(self):
        self.capture()
        path = self.run/'causal-execution-039.json'
        retained = path.with_name('retained-packet.json')
        # Test-owned fixture only: preserve bytes; unknown extra file must reject.
        retained.write_bytes(path.read_bytes())
        path.unlink()
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_duplicate_boundary_multiplicity_is_rejected(self):
        self.capture()
        def alter(rows):
            boundaries = [i for i,r in enumerate(rows) if r['kind']=='observed_session_boundary']
            rows[boundaries[-1]]['data'] = copy.deepcopy(rows[boundaries[-2]]['data'])
        self.events(alter)
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_policy_after_first_incident_is_rejected(self):
        self.capture()
        def alter(rows):
            frozen = next(i for i,r in enumerate(rows) if r['kind']=='policy_frozen')
            seventh = [i for i,r in enumerate(rows) if r['kind']=='observed_model_execution'][6]
            rows[frozen]['kind'],rows[seventh]['kind'] = rows[seventh]['kind'],rows[frozen]['kind']
            rows[frozen]['data'],rows[seventh]['data'] = rows[seventh]['data'],rows[frozen]['data']
        self.events(alter)
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_report_recovery_claim_is_recomputed(self):
        self.capture()
        self.edit('individual-report.json', lambda r:r['observed_recoveries_by_fault'].update({'wrong-tool-profile':0}))
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_boolean_budget_and_duplicate_json_key_are_rejected(self):
        self.capture()
        self.edit('individual-report.json', lambda r:r.update(model_attempts=True))
        with self.assertRaises(SchemaError):verify_individual(self.run)
        path = self.run/'individual-plan.json'
        path.write_text('{"schema_version":1,"schema_version":1}', 'utf-8')
        with self.assertRaises(SchemaError):verify_individual(self.run)

    def test_receipt_exclusive_and_outside_evidence(self):
        self.capture()
        receipt = verify_individual(self.run)
        with self.assertRaises(SchemaError):write_receipt(receipt,self.run/'receipt.json',self.run)
        target = self.parent/'receipt.json'
        write_receipt(receipt,target,self.run)
        original = target.read_bytes()
        with self.assertRaises(FileExistsError):write_receipt(receipt,target,self.run)
        self.assertEqual(target.read_bytes(),original)
        self.assertEqual(json.loads(original)['artifact_sha256'],self.inventory())

    def test_cli_dry_verification_needs_no_credentials_and_does_not_write(self):
        self.capture()
        before = self.inventory()
        result = subprocess.run([sys.executable,'-B',str(ROOT/'scripts/verify_individual_capture.py'),str(self.run)],
            capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['provenance'],'SIMULATION_ONLY')
        self.assertEqual(self.inventory(),before)


if __name__ == '__main__':unittest.main()
