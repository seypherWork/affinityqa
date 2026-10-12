"""Loopback browser-test host; only explicit fake Qloo/model adapters exist."""
import json
import copy
from pathlib import Path
import socket
import signal
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
import uvicorn
from affinityqa.public_demo import create_public_app
import test_discovery_jobs as fixtures


def main():
    # Reserve a candidate loopback port before provider/DNS guards are installed.
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    fixtures.ORIGIN = origin
    fixture = fixtures.DiscoveryJobTests()
    fixture.setUp()
    try:
        service = fixture.service()
        def repeated_nonmusical_row(body, path, params):
            if path == '/search' and params['query'] != fixture.request['artists']['A']:
                row = copy.deepcopy(body['results'][0])
                row.update(types=['urn:entity:person'], properties={})
                body['results'].append(row)
        fixture.transport.mutation = repeated_nonmusical_row
        app = create_public_app(ROOT, origin=origin, case_manager=service)
        print(json.dumps({'ready_origin': origin}), flush=True)
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
                                             log_level='error', access_log=False))
        # Uvicorn restores and replays SIGTERM after graceful shutdown. Let the
        # replay return so this test host can report its provider-call counts.
        previous_handler = signal.signal(signal.SIGTERM, lambda *_: None)
        try:
            server.run()
        finally:
            signal.signal(signal.SIGTERM, previous_handler)
        print(json.dumps({'synthetic_qloo_calls': len(fixture.transport.calls),
                          'synthetic_model_calls': len(fixture.opener.calls),
                          'session_records': len(service.session_keys),
                          'plan_records': len(service.manager.jobs),
                          'execution_admissions': sum(j['sequence'] > 0 for j in service.manager.jobs.values()),
                          'real_provider_calls': 0}), flush=True)
    finally:
        fixture.doCleanups()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
