"""Actual loopback application with synthetic open-film providers; no external network."""
import argparse
import asyncio
from contextlib import ExitStack, asynccontextmanager, suppress
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import uvicorn
from affinityqa.open_movie_discovery_agent import OpenMovieAgent
from affinityqa.provider_runtime import PinnedHarmonyTokenEstimator
from affinityqa.provider_scheduler import ProviderScheduler, GROQ_FREE_CONSERVATIVE, QuotaWindow
from affinityqa.public_demo import create_public_app
from affinityqa.qloo import Settings
from affinityqa.repeatable_cases import RepeatableCaseManager
from test_individual_remote_jobs import request_fixture as legacy_request
from test_open_movie_discovery_capture import MovieTransport, ModelOpener
from test_groq_agent import UNIT_SECRET, UNIT_QLOO_SECRET
from serve_repeatable_cases import network_guards


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--web-root',type=Path)
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--exit-after-seconds',type=float,default=60)
    args=parser.parse_args()
    if not 0<=args.port<=65535 or not 0<args.exit_after_seconds<=300:parser.error('Use bounded local port and duration')
    storage=Path(os.environ.get('AFFINITYQA_TEST_STORAGE_ROOT',str(ROOT.parent/'test-private-scratch')))
    storage.mkdir(parents=True,exist_ok=True)
    listener=socket.socket();listener.bind(('127.0.0.1',args.port));listener.listen(128)
    port=listener.getsockname()[1];origin=f'http://127.0.0.1:{port}'
    temp=tempfile.TemporaryDirectory(prefix='open-browser-',dir=storage);parent=Path(temp.name)
    service=None;start=time.monotonic();epoch=datetime(2026,10,17,15,tzinfo=timezone.utc).timestamp()
    def clock():return epoch+(time.monotonic()-start)*30
    transport=MovieTransport();opener=ModelOpener()
    with ExitStack() as stack:
        try:
            network_guards(stack)
            scheduler=ProviderScheduler(parent/'providers.sqlite3',clock=clock,limits={
                'groq':GROQ_FREE_CONSERVATIVE,'qloo':(QuotaWindow('rpm',10,60),)})
            estimator=PinnedHarmonyTokenEstimator(ROOT/'assets/tokenizers/o200k_base.tiktoken')
            service=RepeatableCaseManager(parent/'cases',legacy_request(),origin=origin,
                minimum_model_interval_seconds=0.0,execution_enabled=True,
                settings_loader=lambda:Settings(UNIT_QLOO_SECRET),remote_key_loader=lambda:UNIT_SECRET,
                scheduler=scheduler,token_estimator=estimator,
                _test_adapters=(lambda:OpenMovieAgent(UNIT_SECRET,forbidden_secrets=(UNIT_QLOO_SECRET,),_test_opener=opener),lambda:transport),
                _test_now=lambda:datetime.fromtimestamp(clock(),timezone.utc))
            app=create_public_app(ROOT,origin=origin,case_manager=service,web_root=args.web_root,
                case_session_limit=60,case_write_limit=120,case_read_limit=600)
            server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',access_log=False))
            original=app.router.lifespan_context
            async def timer():
                while not server.started and not server.should_exit:await asyncio.sleep(.01)
                if server.started:print(json.dumps({'ready_origin':origin,'provenance':'SIMULATION_ONLY','real_provider_calls':0}),flush=True)
                await asyncio.sleep(args.exit_after_seconds);server.should_exit=True
            @asynccontextmanager
            async def lifespan(application):
                async with original(application):
                    task=asyncio.create_task(timer())
                    try:yield
                    finally:
                        task.cancel()
                        with suppress(asyncio.CancelledError):await task
                        await asyncio.to_thread(service.manager.close)
                        print(json.dumps({'provenance':'SIMULATION_ONLY','real_provider_calls':0,
                            'synthetic_qloo_calls':len(transport.calls),'synthetic_model_calls':len(opener.calls),
                            'session_records':service.store.one('SELECT COUNT(*) AS n FROM sessions')['n'],
                            'plan_records':service.store.one('SELECT COUNT(*) AS n FROM jobs')['n']}),flush=True)
            app.router.lifespan_context=lifespan
            previous=signal.signal(signal.SIGTERM,lambda *_:None)
            try:server.run(sockets=[listener])
            finally:signal.signal(signal.SIGTERM,previous)
        finally:
            if service is not None:service.close()
            listener.close();temp.cleanup()
    return 0

if __name__=='__main__':raise SystemExit(main())
