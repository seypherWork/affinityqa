"""Owned loopback preview of a fabricated capture; never use private inputs."""
import argparse
import json
from pathlib import Path
import signal
import socket
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
import uvicorn
from affinityqa.public_demo import create_public_app
from causal_evidence_fixture import build_synthetic_capture

NOTICE='SYNTHETIC LOCAL VALIDATION · NO REAL PROVIDER CALLS'


class SyntheticNotice:
    """Test host only: visibly mark the HTML and source notices as fabricated."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        collected=[]
        async def collect(message):collected.append(message)
        await self.app(scope,receive,collect)
        start=next((m for m in collected if m['type']=='http.response.start'),None)
        if start is None:return
        headers=dict(start.get('headers',[]))
        kind=headers.get(b'content-type',b'')
        body=b''.join(m.get('body',b'') for m in collected if m['type']=='http.response.body')
        if b'text/html' in kind:
            banner=('<aside role="note" style="position:relative;z-index:99;background:#edba61;'
                    'color:#151310;padding:14px 20px;font:700 13px system-ui;text-align:center">'
                    +NOTICE+'</aside>').encode()
            body=body.replace(b'<body',b'<body',1)
            index=body.find(b'>',body.find(b'<body'))
            if index>=0:body=body[:index+1]+banner+body[index+1:]
        elif b'application/json' in kind and scope['path'] in ('/api/demo/summary','/api/demo/replay'):
            value=json.loads(body)
            if 'notice' in value:
                value['notice']=NOTICE+'. Generated test artists, films, Qloo-shaped responses and model packets. Not real API evidence or human validation.'
                body=json.dumps(value).encode()
        headers[b'content-length']=str(len(body)).encode()
        start['headers']=list(headers.items())
        await send(start)
        await send({'type':'http.response.body','body':body})


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--exit-after-seconds',type=int,default=180)
    parser.add_argument('--capture-root',type=Path)
    args=parser.parse_args()
    if not 0<=args.exit_after_seconds<=900:parser.error('Expected0..900seconds')
    parent=ROOT.parent/'.test-runs'
    parent.mkdir(exist_ok=True)
    capture=args.capture_root or Path(tempfile.mkdtemp(prefix='diagnostic-synthetic-',dir=parent))/'capture'
    bundle=build_synthetic_capture(capture,source_root=ROOT)
    listener=socket.socket()
    listener.bind(('127.0.0.1',0))
    port=listener.getsockname()[1]
    origin=f'http://127.0.0.1:{port}'
    app=create_public_app(capture,origin=origin,run_id=bundle.run_id,
                          receipt_sha256=bundle.receipt_sha256,web_root=ROOT/'web/out')
    server=uvicorn.Server(uvicorn.Config(SyntheticNotice(app),log_level='error',access_log=False))
    def stop():server.should_exit=True
    def read_commands():
        for line in sys.stdin:
            if line.strip()=='stop':stop();return
    threading.Thread(target=read_commands,daemon=True).start()
    previous=signal.signal(signal.SIGTERM,lambda *_:stop())
    timer=None
    if args.exit_after_seconds:
        timer=threading.Timer(args.exit_after_seconds,stop)
        timer.daemon=True
        timer.start()
    def announce_ready():
        while not server.started and not server.should_exit:time.sleep(.01)
        if server.started:
            print(json.dumps({'ready_origin':origin,'fixture_provenance':'synthetic-only',
                             'capture_root':str(capture),'real_provider_calls':0}),flush=True)
    threading.Thread(target=announce_ready,daemon=True).start()
    try:server.run(sockets=[listener])
    finally:
        if timer:timer.cancel()
        signal.signal(signal.SIGTERM,previous)
        listener.close()
    print(json.dumps({'closed':True,'real_provider_calls':0}),flush=True)


if __name__=='__main__':main()
