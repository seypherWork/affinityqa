"""Real loopback repeatable app with synthetic providers, accelerated quota time.

No provider credential is read and no non-loopback network is permitted. This is
an application/browser integration fixture, never provider acceptance or human
cultural validation. It adds no test-control HTTP route.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager, ExitStack, suppress
import copy
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import uvicorn
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent
from affinityqa.cinema_discovery_v4_agent import DiscoveryMovieAgent as MovieInputAgent
from affinityqa.cinema_preferences import CinemaMovieAgent
from affinityqa.fast_pair_agent import FastPairMovieAgent
from affinityqa.groq_agent import GroqToolContextMovieAgent
from affinityqa.provider_runtime import PinnedHarmonyTokenEstimator
from affinityqa.provider_scheduler import ProviderScheduler, GROQ_FREE_CONSERVATIVE, QuotaWindow
from affinityqa.public_demo import create_public_app
from affinityqa.qloo import Response, Settings
from affinityqa.qloo_cache import PrivateQlooCache
from affinityqa.repeatable_cases import RepeatableCaseManager
from test_cinema_identity_capture import identity_request, ID_A, ID_B
from test_discovery_agent import Opener as DiscoveryOpener
from test_groq_agent import OpenerFixture, UNIT_SECRET, UNIT_QLOO_SECRET
from test_fast_pair import PairOpenerFixture


def loopback(host):
    try:return ipaddress.ip_address(host).is_loopback
    except (ValueError,TypeError):return False


def network_guards(stack):
    original_dns=socket.getaddrinfo
    original_connection=socket.create_connection
    original_connect=socket.socket.connect
    original_connect_ex=socket.socket.connect_ex
    original_sendto=socket.socket.sendto
    def dns(host,*args,**kwargs):
        if not loopback(host):raise AssertionError('Non-loopback DNS/network denied in offline browser host.')
        return original_dns(host,*args,**kwargs)
    def connection(address,*args,**kwargs):
        if not isinstance(address,tuple) or not loopback(address[0]):raise AssertionError('Provider network denied.')
        return original_connection(address,*args,**kwargs)
    def connect(sock,address):
        if not isinstance(address,tuple) or not loopback(address[0]):raise AssertionError('Provider network denied.')
        return original_connect(sock,address)
    def connect_ex(sock,address):
        if not isinstance(address,tuple) or not loopback(address[0]):raise AssertionError('Provider network denied.')
        return original_connect_ex(sock,address)
    def sendto(sock,data,*args):
        address=args[-1] if args else None
        if not isinstance(address,tuple) or not loopback(address[0]):raise AssertionError('Non-loopback datagram denied.')
        return original_sendto(sock,data,*args)
    for target,value in (('socket.getaddrinfo',dns),('socket.create_connection',connection),
                         ('socket.socket.connect',connect),('socket.socket.connect_ex',connect_ex),
                         ('socket.socket.sendto',sendto)):
        stack.enter_context(patch(target,new=value))


class SyntheticTransport:
    def __init__(self,current_request):self.current_request=current_request;self.calls=[]
    def send(self,path,params):
        request=self.current_request();self.calls.append((path,copy.deepcopy(params)))
        if path=='/search':
            label='A' if params['query']==request['artists']['A'] else 'B'
            body={'results':[{'entity_id':ID_A if label=='A' else ID_B,'name':params['query'],
                              'types':['urn:entity:artist']}]}
        elif path=='/v2/insights':
            allowed=set(params['filter.results.entities'].split(','))
            rows=[{'entity_id':row['entity_id'],'name':row['name'],'types':['urn:entity:movie'],
                   'properties':{'release_year':row['release_year']},'query':{'affinity':1-index/20}}
                  for index,row in enumerate(request['catalog']) if row['entity_id'] in allowed]
            if ID_B in params['signal.interests.entities'].split(','):rows.reverse()
            body={'success':True,'results':{'entities':rows}}
        else:raise AssertionError('Unreviewed fake provider endpoint.')
        return Response(200,body,{},elapsed_ms=0.0)


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('--web-root',type=Path)
    result.add_argument('--storage-parent',type=Path,default=Path(os.environ.get('AFFINITYQA_TEST_STORAGE_ROOT',str(ROOT.parent/'test-private-scratch'))))
    result.add_argument('--port',type=int,default=0)
    result.add_argument('--exit-after-seconds',type=float,default=0.0)
    result.add_argument('--quota-clock-scale',type=float,default=30.0)
    return result


def main():
    args=parser().parse_args()
    if not 0<=args.port<=65535 or not 0<=args.exit_after_seconds<=600 or not 1<=args.quota_clock_scale<=60:
        parser().error('Use a bounded loopback port, test clock and optional test duration.')
    args.storage_parent.mkdir(parents=True,exist_ok=True)
    listener=socket.socket();listener.bind(('127.0.0.1',args.port));listener.listen(128)
    port=listener.getsockname()[1];origin=f'http://127.0.0.1:{port}'
    temp=tempfile.TemporaryDirectory(prefix='rpt-browser-',dir=args.storage_parent)
    parent=Path(temp.name);service=None
    monotonic_start=time.monotonic();epoch=datetime(2026,10,14,20,tzinfo=timezone.utc).timestamp()
    def clock():return epoch+(time.monotonic()-monotonic_start)*args.quota_clock_scale
    def now():return datetime.fromtimestamp(clock(),timezone.utc)
    discovery_opener=DiscoveryOpener();legacy_opener=OpenerFixture();pair_opener=PairOpenerFixture()
    with ExitStack() as stack:
        try:
            network_guards(stack)
            # Keep original capture contracts and sample bytes; remove only their
            # test-local one-second sleeps. The shared durable provider scheduler
            # remains active, using the explicitly accelerated clock above.
            timer=SimpleNamespace(sleep=lambda _:None,monotonic=time.monotonic)
            for module in ('individual_remote_capture','cinema_capture','cinema_identity_capture','cinema_discovery_v3_capture'):
                stack.enter_context(patch('affinityqa.'+module+'.time',new=timer))
            template=identity_request();template.pop('preferences');template['schema_version']=2
            scheduler=ProviderScheduler(parent/'provider-scheduler.sqlite3',clock=clock,limits={
                'groq':GROQ_FREE_CONSERVATIVE,'qloo':(QuotaWindow('rpm',10,60),QuotaWindow('month',10000,31*86400))})
            estimator=PinnedHarmonyTokenEstimator(ROOT/'assets/tokenizers/o200k_base.tiktoken')
            def current_request():
                if service is None or service.manager._active is None:raise AssertionError('No explicitly admitted fake capture.')
                return service.manager._job(service.manager._active)['plan']['request']
            transport=SyntheticTransport(current_request)
            def engine():
                version=current_request()['schema_version']
                cls=FastPairMovieAgent if version==7 else MovieInputAgent if version==6 else DiscoveryMovieAgent if version==5 else CinemaMovieAgent if version in (3,4) else GroqToolContextMovieAgent
                opener=pair_opener if version==7 else discovery_opener if version in (5,6) else legacy_opener
                return cls(UNIT_SECRET,forbidden_secrets=(UNIT_QLOO_SECRET,),_test_opener=opener)
            service=RepeatableCaseManager(parent/'repeatable',template,origin=origin,
                minimum_model_interval_seconds=0.0,execution_enabled=True,
                settings_loader=lambda:Settings(UNIT_QLOO_SECRET),remote_key_loader=lambda:UNIT_SECRET,
                scheduler=scheduler,qloo_cache=PrivateQlooCache(parent/'private-qloo-cache'),token_estimator=estimator,
                _test_adapters=(engine,lambda:transport),_test_now=now)
            app=create_public_app(ROOT,origin=origin,case_manager=service,web_root=args.web_root,
                                  case_session_limit=60,case_write_limit=120,case_read_limit=600)
            server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
            original_lifespan=app.router.lifespan_context
            shutdown_summary={}
            async def ready_and_timeout():
                while not server.started and not server.should_exit:await asyncio.sleep(.01)
                if server.started:
                    print(json.dumps({'ready_origin':origin,'provenance':'SIMULATION_ONLY',
                        'provider_quota_clock_scale':args.quota_clock_scale,'real_provider_calls':0}),flush=True)
                if args.exit_after_seconds:
                    await asyncio.sleep(args.exit_after_seconds);server.should_exit=True
            @asynccontextmanager
            async def lifespan(application):
                async with original_lifespan(application):
                    task=asyncio.create_task(ready_and_timeout())
                    try:yield
                    finally:
                        task.cancel()
                        with suppress(asyncio.CancelledError):await task
                        await asyncio.to_thread(service.manager.close)
                        shutdown_summary.update(provenance='SIMULATION_ONLY',synthetic_qloo_calls=len(transport.calls),
                            synthetic_model_calls=len(pair_opener.calls)+len(discovery_opener.calls)+len(legacy_opener.calls),
                            synthetic_shared_pair_model_calls=len(pair_opener.calls),
                            synthetic_discovery_model_calls=len(discovery_opener.calls),
                            synthetic_causal_or_cinema_model_calls=len(legacy_opener.calls),
                            session_records=service.store.one('SELECT COUNT(*) AS n FROM sessions')['n'],
                            plan_records=service.store.one('SELECT COUNT(*) AS n FROM jobs')['n'],real_provider_calls=0)
            app.router.lifespan_context=lifespan
            previous_handler=signal.signal(signal.SIGTERM,lambda *_:None)
            try:server.run(sockets=[listener])
            finally:signal.signal(signal.SIGTERM,previous_handler)
            # Public APIs never expose these private host/audit counters.
            print(json.dumps(shutdown_summary),flush=True)
        finally:
            if service is not None:service.close()
            listener.close()
            temp.cleanup()
    return 0


if __name__=='__main__':raise SystemExit(main())
