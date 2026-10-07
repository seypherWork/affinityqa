"""Owner-sealed local cadence, not an attestation of provider quota or billing."""
import copy
import math
import threading
import time

from .errors import SchemaError
from .evidence import fingerprint


def need(condition,message):
    if not condition:
        raise SchemaError('Remote pacing: '+message)


def pacing_policy(seconds=None):
    need(seconds is None or type(seconds) in (int,float) and math.isfinite(seconds)
         and 0 <= seconds <= 65,'select a finite interval from zero through 65 seconds.')
    return {'schema_version':1,'configured':seconds is not None,
            'minimum_interval_seconds':None if seconds is None else float(seconds),
            'clock':'monotonic','maximum_model_attempts':39,'maximum_scheduled_wait_seconds':70,
            'maximum_sleep_slice_seconds':5,'maximum_wait_wakeups':100,
            'provider_quota_attested':False,'external_capacity_reserved':False,
            'automatic_retry':False,'automatic_model_or_schema_fallback':False}


class PacedRemoteAgent:
    """Serialize and seal every consumed slot before delegating one ranking call."""
    def __init__(self,engine,policy,ledger,*,_test_clock=None):
        need(type(policy) is dict and fingerprint(policy)==fingerprint(pacing_policy(policy.get('minimum_interval_seconds'))),
             'pacing policy differs from its closed contract.')
        need(policy['configured'] or engine.source=='test-double-only',
             'real inference needs an explicitly configured cadence.')
        need(_test_clock is None or engine.source=='test-double-only',
             'a simulated clock is restricted to simulated transport.')
        need(engine.calls==0,'the operator must be unused before pacing admission.')
        self.engine,self.policy,self.ledger=engine,copy.deepcopy(policy),ledger
        self._policy_sha=fingerprint(self.policy)
        self._clock,self._sleep=_test_clock or (time.monotonic,time.sleep)
        self._lock=threading.Lock()
        self._last_read=self._last_start=self._origin=None
        self.slots=0
        self._stopped=False

    def __getattr__(self,name):
        return getattr(self.engine,name)

    def _now(self):
        value=self._clock()
        need(type(value) in (int,float) and math.isfinite(value) and value>=0,
             'clock is not a finite monotonic observation.')
        need(self._last_read is None or value>=self._last_read,'clock moved backwards; stopped.')
        self._last_read=value
        return value

    def rank(self,request):
        with self._lock:
            need(not self._stopped,'a previous failure stopped this operator; no retry.')
            try:
                need(fingerprint(self.policy)==self._policy_sha,'the sealed pacing policy changed.')
                need(self.slots<39,'the admitted model budget is exhausted.')
                interval=self.policy['minimum_interval_seconds'] or 0.0
                now=self._now()
                scheduled=0.0
                wakeups=0
                while self._last_start is not None and now-self._last_start<interval:
                    delay=min(5.0,interval-(now-self._last_start))
                    need(wakeups<100 and scheduled+delay<=70,
                         'waiting exceeded the sealed local bound; no dispatch.')
                    scheduled+=delay
                    wakeups+=1
                    self._sleep(delay)
                    now=self._now()
                origin=now if self._origin is None else self._origin
                slot=self.slots+1
                self.ledger.record('remote_model_attempt_admitted',{
                    'schema_version':1,'execution_source':self.engine.source,'slot':slot,
                    'adapter_calls_before_dispatch':self.engine.calls,
                    'relative_start_seconds':now-origin,'scheduled_wait_seconds':scheduled,
                    'minimum_interval_seconds':interval,'external_completion_attested':False})
                self.slots=slot
                # The durable admission itself may be delayed by disk/scheduling.
                # Start the next-call interval after that write, immediately before
                # delegating the model decision. The earlier saved clock is only
                # an admission observation, not external transport attestation.
                self._origin=origin
                self._last_start=self._now()
                return self.engine.rank(request)
            except BaseException:
                self._stopped=True
                raise
