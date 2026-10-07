"""Denied-network cadence, consumed slots and full causal-protocol regressions."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from affinityqa.agents import AgentError
from affinityqa.errors import SchemaError
from affinityqa.evidence import fingerprint
from affinityqa.groq_agent import GroqToolContextMovieAgent
from affinityqa.individual_remote_capture import prepare_plan,execute_capture
from affinityqa.individual_remote_verify import verify_individual_remote
from affinityqa.qloo import Settings
from affinityqa.remote_pacing import PacedRemoteAgent,pacing_policy
from test_groq_agent import OpenerFixture,UNIT_SECRET,UNIT_QLOO_SECRET
from test_individual_capture import TransportDouble
from test_individual_remote import request_fixture


class Clock:
    def __init__(self):self.value=100.0;self.waits=[]
    def now(self):return self.value
    def sleep(self,seconds):self.waits.append(seconds);self.value+=seconds


class MemoryLedger:
    def __init__(self):self.events=[]
    def record(self,kind,data):self.events.append((kind,copy.deepcopy(data)))


class Engine:
    source='test-double-only'
    def __init__(self,clock):self.calls=0;self.starts=[];self.clock=clock;self.fail_on=None;self.duration=0
    def rank(self,request):
        self.calls+=1;self.starts.append(self.clock.value);self.clock.value+=self.duration
        if self.calls==self.fail_on:raise AgentError('unit simulated transport failure')
        return request


class RemotePacingTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.engine=Engine(self.clock);self.ledger=MemoryLedger()
        for name in ('socket.socket','socket.create_connection','socket.getaddrinfo'):
            guard=patch(name,side_effect=AssertionError('Network and DNS forbidden in pacing fixtures'))
            guard.start();self.addCleanup(guard.stop)

    def pacer(self,interval=2):
        return PacedRemoteAgent(self.engine,pacing_policy(interval),self.ledger,
                                _test_clock=(self.clock.now,self.clock.sleep))

    def test_policy_is_closed_and_does_not_claim_account_quota(self):
        self.assertFalse(pacing_policy()['configured'])
        for value in (0,2.5,65):
            policy=pacing_policy(value)
            self.assertIs(type(policy['minimum_interval_seconds']),float)
            self.assertFalse(policy['provider_quota_attested'])
            self.assertFalse(policy['external_capacity_reserved'])
        for value in (True,-1,66,float('nan'),float('inf'),'2'):
            with self.subTest(value=value),self.assertRaises(SchemaError):pacing_policy(value)
        policy=pacing_policy(2);policy['configured']=1
        with self.assertRaises(SchemaError):PacedRemoteAgent(self.engine,policy,self.ledger)

    def test_all_thirty_nine_dispatch_starts_are_spaced_and_budget_is_consumed(self):
        pacer=self.pacer()
        for i in range(39):self.assertEqual(pacer.rank({'index':i}),{'index':i})
        self.assertEqual(self.engine.starts,[100+2*i for i in range(39)])
        self.assertEqual((pacer.calls,pacer.slots,len(self.ledger.events)),(39,39,39))
        self.assertTrue(all(data['external_completion_attested'] is False for _,data in self.ledger.events))
        with self.assertRaises(SchemaError):pacer.rank({})
        self.assertEqual(self.engine.calls,39)

    def test_early_sleep_return_is_checked_before_dispatch(self):
        def early(seconds):self.clock.waits.append(seconds);self.clock.value+=min(seconds,0.25)
        self.clock.sleep=early
        pacer=self.pacer();pacer.rank({});pacer.rank({})
        self.assertEqual(self.engine.starts,[100,102])
        self.assertGreater(len(self.clock.waits),1)

    def test_previous_provider_duration_reduces_wait(self):
        self.engine.duration=3
        pacer=self.pacer();pacer.rank({});pacer.rank({})
        self.assertEqual(self.engine.starts,[100,103])
        self.assertEqual(self.clock.waits,[])

    def test_variable_ledger_latency_does_not_shorten_model_dispatch_spacing(self):
        original=self.ledger.record
        def slow_first(kind,data):
            original(kind,data)
            if data['slot']==1:self.clock.value+=10
        self.ledger.record=slow_first
        pacer=self.pacer();pacer.rank({});pacer.rank({})
        self.assertEqual(self.engine.starts,[110,112])
        self.assertEqual(self.clock.waits,[2.0])

    def test_sleep_slices_are_bounded_and_zero_clock_progress_stops_without_dispatch(self):
        self.clock.sleep=lambda seconds:self.clock.waits.append(seconds)
        pacer=self.pacer(65);pacer.rank({})
        with self.assertRaises(SchemaError):pacer.rank({})
        self.assertEqual((self.engine.calls,pacer.slots),(1,1))
        self.assertLessEqual(sum(self.clock.waits),70)
        self.assertLessEqual(max(self.clock.waits),5)
        with self.assertRaisesRegex(SchemaError,'no retry'):pacer.rank({})

    def test_backward_or_nonfinite_clock_never_dispatches_an_extra_call(self):
        for bad in (99.0,float('nan'),float('inf'),True):
            with self.subTest(bad=bad):
                clock=Clock();engine=Engine(clock)
                pacer=PacedRemoteAgent(engine,pacing_policy(2),MemoryLedger(),_test_clock=(clock.now,clock.sleep))
                pacer.rank({});clock.value=bad
                with self.assertRaises(SchemaError):pacer.rank({})
                self.assertEqual((engine.calls,pacer.slots),(1,1))

    def test_interrupted_wait_consumes_no_second_slot_and_cannot_retry(self):
        def interrupt(seconds):raise KeyboardInterrupt()
        self.clock.sleep=interrupt
        pacer=self.pacer();pacer.rank({})
        with self.assertRaises(KeyboardInterrupt):pacer.rank({})
        self.assertEqual((self.engine.calls,pacer.slots,len(self.ledger.events)),(1,1,1))
        with self.assertRaisesRegex(SchemaError,'no retry'):pacer.rank({})

    def test_failed_model_attempt_consumes_its_slot_and_cannot_retry(self):
        self.engine.fail_on=2
        pacer=self.pacer();pacer.rank({})
        with self.assertRaises(AgentError):pacer.rank({})
        self.assertEqual((self.engine.calls,pacer.slots,len(self.ledger.events)),(2,2,2))
        with self.assertRaisesRegex(SchemaError,'no retry'):pacer.rank({})

    def test_mutated_policy_and_ledger_write_failure_stop_before_next_dispatch(self):
        pacer=self.pacer();pacer.rank({});pacer.policy['minimum_interval_seconds']=0.0
        with self.assertRaises(SchemaError):pacer.rank({})
        self.assertEqual(self.engine.calls,1)
        other=Engine(self.clock)
        ledger=MemoryLedger()
        with patch.object(ledger,'record',side_effect=OSError('unit recording failure')):
            pacer=PacedRemoteAgent(other,pacing_policy(0),ledger,_test_clock=(self.clock.now,self.clock.sleep))
            with self.assertRaises(OSError):pacer.rank({})
        self.assertEqual((other.calls,pacer.slots),(0,0))
        with self.assertRaisesRegex(SchemaError,'no retry'):pacer.rank({})

    def test_concurrent_callers_share_the_same_serial_cadence(self):
        pacer=self.pacer()
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(pacer.rank,[{},{}]))
        self.assertEqual(self.engine.starts,[100,102])
        self.assertEqual([data['slot'] for _,data in self.ledger.events],[1,2])

    def test_unconfigured_real_source_and_simulated_clock_are_rejected(self):
        # Synthetic object used only for constructor rejection; never dispatched.
        self.engine.source='remote-llm'
        with self.assertRaises(SchemaError):PacedRemoteAgent(self.engine,pacing_policy(),self.ledger)
        with self.assertRaises(SchemaError):self.pacer(0)
        self.assertEqual(self.engine.calls,0)


class PacedCaptureTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'.test-runs';base.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temp.cleanup)
        self.parent=Path(self.temp.name);self.output=self.parent/'capture'
        self.request=request_fixture();self.clock=Clock()
        for name in ('socket.socket','socket.create_connection','socket.getaddrinfo',
                     'affinityqa.individual_remote_capture.LiveTransport'):
            guard=patch(name,side_effect=AssertionError('Actual provider transport forbidden'))
            guard.start();self.addCleanup(guard.stop)

    def capture(self,interval=2,opener=None):
        self.opener=opener or OpenerFixture()
        self.engine=GroqToolContextMovieAgent(UNIT_SECRET,forbidden_secrets=(UNIT_QLOO_SECRET,),_test_opener=self.opener)
        plan=prepare_plan(self.request,self.output,minimum_model_interval_seconds=interval)
        with patch('affinityqa.individual_remote_capture.time.sleep'):
            self.report,self.run=execute_capture(self.request,self.output,plan['plan_sha256'],Settings(UNIT_QLOO_SECRET),UNIT_SECRET,
                minimum_model_interval_seconds=interval,_test_adapters=(lambda:self.engine,lambda:TransportDouble(self.request)),
                _test_pacing_clock=(self.clock.now,self.clock.sleep))
        return self.report

    def test_complete_thirty_nine_decision_capture_has_independently_checked_slots(self):
        report=self.capture()
        self.assertEqual((report['status'],report['model_attempts'],report['admitted_model_slots']),('COMPLETE',39,39))
        receipt=verify_individual_remote(self.run)
        self.assertEqual((receipt['verification_status'],receipt['verified_model_packets']),('VERIFIED_COMPLETE',39))
        self.assertFalse(receipt['external_service_attested'])
        self.assertEqual(receipt['provenance'],'SIMULATION_ONLY')
        self.assertEqual(self.clock.value,176)
        self.assertEqual(receipt['cultural_gate'],'NOT_VALIDATED')

    def test_unconfigured_real_execution_is_rejected_before_output_or_factories(self):
        plan=prepare_plan(self.request,self.output)
        with patch('affinityqa.individual_remote_capture.GroqToolContextMovieAgent',side_effect=AssertionError('No model construction')):
            with self.assertRaisesRegex(SchemaError,'reviewed model interval'):
                execute_capture(self.request,self.output,plan['plan_sha256'],Settings(UNIT_QLOO_SECRET),UNIT_SECRET)
        self.assertFalse(self.output.exists())

    def test_cadence_change_after_preparation_fails_before_factories(self):
        plan=prepare_plan(self.request,self.output,minimum_model_interval_seconds=2)
        with patch('affinityqa.individual_remote_capture.GroqToolContextMovieAgent',side_effect=AssertionError('No model construction')):
            with self.assertRaises(SchemaError):
                execute_capture(self.request,self.output,plan['plan_sha256'],Settings(UNIT_QLOO_SECRET),UNIT_SECRET,
                                minimum_model_interval_seconds=1)
        self.assertFalse(self.output.exists())

    def test_wait_failure_preserves_one_complete_packet_without_second_admission(self):
        def fail(seconds):raise OSError('unit interrupted pacing')
        self.clock.sleep=fail
        report=self.capture()
        self.assertEqual((report['status'],report['model_attempts'],report['admitted_model_slots']),('INCOMPLETE',1,1))
        self.assertEqual(len(self.opener.calls),1)
        self.assertEqual(verify_individual_remote(self.run)['verification_status'],'VERIFIED_PARTIAL')

    def test_partial_capture_rejects_forged_third_slot_after_failed_second_attempt(self):
        class SecondFailure(OpenerFixture):
            def open(self,request,timeout):
                if len(self.calls)==1:
                    self.failure=HTTPError('https://unit.invalid',429,'unit simulated rate limit',{},None)
                return super().open(request,timeout)

        report=self.capture(opener=SecondFailure())
        self.assertEqual((report['status'],report['model_attempts'],report['admitted_model_slots']),('INCOMPLETE',2,2))
        self.assertEqual(len(self.opener.calls),2)
        self.assertEqual(verify_individual_remote(self.run)['verified_model_packets'],1)
        ledger=self.run/'ledger.jsonl'
        events=[json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(events[-1]['kind'],'stopped_without_retry')
        slots=[event for event in events if event['kind']=='remote_model_attempt_admitted']
        forged=copy.deepcopy(slots[-1])
        forged['timestamp_utc']=events[-1]['timestamp_utc']
        forged['data'].update(slot=3,adapter_calls_before_dispatch=2,
                              relative_start_seconds=4.0,scheduled_wait_seconds=2.0)
        events.insert(len(events)-1,forged)
        for sequence,event in enumerate(events,1):event['sequence']=sequence
        ledger.write_text(''.join(json.dumps(event)+'\n' for event in events),encoding='utf-8')
        report_path=self.run/'individual-report.json'
        report=json.loads(report_path.read_text(encoding='utf-8'))
        report['admitted_model_slots']=3
        report_path.write_text(json.dumps(report),encoding='utf-8')
        with self.assertRaisesRegex(SchemaError,'slot accounting'):
            verify_individual_remote(self.run)

    def test_rehashed_policy_or_forged_slot_cannot_pass_independent_audit(self):
        self.capture()
        path=self.run/'individual-plan.json';original=path.read_bytes()
        plan=json.loads(original.decode('utf-8'));plan['execution_pacing']['provider_quota_attested']=True
        plan['plan_sha256']=fingerprint({k:v for k,v in plan.items() if k!='plan_sha256'})
        path.write_text(json.dumps(plan),encoding='utf-8')
        with self.assertRaises(SchemaError):verify_individual_remote(self.run)
        path.write_bytes(original)
        ledger=self.run/'ledger.jsonl';events=[json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
        slots=[event for event in events if event['kind']=='remote_model_attempt_admitted']
        slots[1]['data']['relative_start_seconds']=0
        ledger.write_text(''.join(json.dumps(event)+'\n' for event in events),encoding='utf-8')
        with self.assertRaisesRegex(SchemaError,'cadence'):verify_individual_remote(self.run)
