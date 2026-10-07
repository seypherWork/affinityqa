"""Restricted recorded-demo surface. Does not grant permission to publish data."""
from __future__ import annotations

import base64
import asyncio
import copy
import hashlib
import re
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from .api import CausalReplayBody
from . import causal_review as review
from .errors import AffinityQAError, SchemaError

SHA = re.compile(r'^[a-f0-9]{64}$')
RUN = re.compile(r'^\d{8}T\d{6}Z-[a-f0-9]{8}$')
TRACE_FIELDS = ('requested_profile_sha256', 'transmitted_profile_sha256',
                'tool_profile_sha256', 'output_profile_sha256', 'cache_hit')


def canonical_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment
            or value != f'{parsed.scheme}://{parsed.netloc}' or '*' in value):
        raise ValueError('Provide one exact origin without a trailing slash.')
    if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('HTTP preview must use a loopback origin. External demo requires HTTPS.')
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError('Invalid origin port.')
    return value


def summary_dto(report: dict, receipt_sha: str) -> dict:
    """Allowlist only. No provider response, ranking, filesystem or model packet."""
    return {'schema_version': 1, 'status': report['status'], 'run_id': report['run_id'],
            'protocol_version': report['protocol_version'], 'causal_gate': report['causal_gate'],
            'behavioral_gate': report['behavioral_gate'], 'cultural_gate': report['cultural_gate'],
            'release_gate': report['release_gate'], 'release_approved': False,
            'passing': report['passing'], 'denominator': report['denominator'],
            'source_model_calls': report['model_calls'],
            'source_qloo_requests': report.get('total_qloo_requests', report['qloo_requests']),
            'observed_repeat_recoveries': report['behavioral_recoveries_observed'],
            'noise_barrier': report['noise_barrier'], 'policy_sha256': report['policy_sha256'],
            'receipt_sha256': receipt_sha,
            'pairs': [{'pair_id': p['pair_id'], 'artists': {'A': p['artists']['A'], 'B': p['artists']['B']},
                       'split': p['split'], 'faults': [c['fault'] for c in p['cases']]}
                      for p in report['pairs']],
            'historical_quality': {'development': {'passing': 13, 'denominator': 14, 'gate': 'FAIL'},
                                   'independent': {'passing': 4, 'denominator': 6, 'gate': 'FAIL'}},
            'execution_mode': 'recorded-local-llm-replay',
            'notice': 'Recorded replay. The original capture used real Qloo inputs and local model decisions. '
                      'Each replay executes routing, diagnosis and repair with saved decisions; zero new '
                      'model/API calls. Controlled repeats are not independent user trials.'}


def replay_dto(result: dict, *, profile_names: dict[str, str]) -> dict:
    """One selected incident; no bulk exports, entity UUIDs or source packets."""
    def films(rows):
        return [{'position': i + 1, 'title': row['title'], 'year': row['year']}
                for i, row in enumerate(rows[:5])]
    def trace(value): return {key: value[key] for key in TRACE_FIELDS}
    fields = ('schema_version', 'status', 'replay_gate', 'run_id', 'pair_id', 'fault', 'repeat',
              'source', 'new_model_calls', 'new_qloo_calls', 'recorded_decision_dispatches',
              'diagnosis', 'repair', 'cultural_gate', 'release_gate', 'notice')
    check_fields = ('supported_diagnosis', 'repair_applied', 'profile_integrity_restored',
                    'decision_redispatched', 'matches_recorded_healthy', 'legitimate_cache_reuse')
    if any(type(result['checks'].get(key)) is not bool for key in check_fields):
        raise SchemaError('Unexpected replay checks.')
    def identities(value):
        names = {key: profile_names.get(value[key]) for key in TRACE_FIELDS[:-1]}
        if any(not isinstance(name, str) or not name for name in names.values()):
            raise SchemaError('An observed profile has no verified name.')
        return names
    before_names, after_names = identities(result['trace']), identities(result['repaired_trace'])
    return {**{key: copy.deepcopy(result[key]) for key in fields},
            'checks': {key: result['checks'][key] for key in check_fields},
            'requested_artist': before_names['requested_profile_sha256'],
            'identity_before': before_names, 'identity_after': after_names,
            'before': films(result['before']), 'after': films(result['after']),
            'healthy': films(result['healthy']), 'trace': trace(result['trace']),
            'repaired_trace': trace(result['repaired_trace'])}


class _Capture:
    """Fixed receipt and complete selected capture, checked again before use."""
    def __init__(self, root: Path, run_id: str, receipt_sha: str):
        if not RUN.fullmatch(run_id) or not SHA.fullmatch(receipt_sha):
            raise ValueError('A fixed run ID and exact receipt SHA-256 are required.')
        self.root, self.run_id = root, run_id
        self.path = review._file(root, 'evidence/CAUSAL-REPAIR-' + run_id + '.json')
        if review._sha(self.path) != receipt_sha:
            raise SchemaError('The selected receipt fingerprint differs.')
        self.run, self.report, self.receipt = review._verified(root, self.path)
        selected, _ = review._selection(root)
        if selected is None or selected[1]['run_id'] != run_id or self.report['status'] != 'COMPLETE':
            raise SchemaError('The fixed complete capture must be the selected verified capture.')
        self.members = set(self.receipt['artifact_sha256'])
        self.receipt_names = tuple(sorted(p.name for p in (root / 'evidence').glob('CAUSAL-REPAIR-*.json')))
        self.bound = {self.path: receipt_sha}
        self.bound.update({review._file(self.run, n): h for n, h in self.receipt['artifact_sha256'].items()})
        self.bound.update({review._file(root / 'src/affinityqa', n): h for n, h in self.receipt['source_sha256'].items()})
        installed = Path(review.__file__).resolve().parent
        self.bound.update({review._file(installed, n): h for n, h in self.receipt['source_sha256'].items()})
        self.bound.update({review._file(root, n): h for n, h in self.receipt['source_artifact_sha256'].items()})
        drivers = [p for p in (root / 'scripts').glob('*causal*.py')
                   if p.is_file() and review._sha(p) == self.receipt['driver_sha256']]
        if not drivers: raise SchemaError('The bound capture driver is missing.')
        self.bound.update({review._file(root, p.relative_to(root).as_posix()): self.receipt['driver_sha256'] for p in drivers})
        self.summary = summary_dto(self.report, receipt_sha)
        self.allowed = {(p['pair_id'], c['fault'], repeat) for p in self.report['pairs']
                        for c in p['cases'] for repeat in (1, 2, 3)}
        self.profile_names = {}
        for pair in self.report['pairs']:
            record = review._read(review._file(self.run, 'causal-pair-' + pair['pair_id'] + '.json'))
            self.profile_names[pair['pair_id']] = {review.profile_hash(profile): profile['name']
                                                 for profile in record['profiles'].values()}
        self.lock = threading.Lock()
        self.check()

    def check(self):
        if tuple(sorted(p.name for p in (self.root / 'evidence').glob('CAUSAL-REPAIR-*.json'))) != self.receipt_names:
            raise SchemaError('The capture selection changed. Restart only after re-review.')
        current = {p.relative_to(self.run).as_posix() for p in self.run.rglob('*') if p.is_file()}
        if current != self.members: raise SchemaError('The captured artifact tree changed.')
        for path, expected in self.bound.items():
            base = self.root if path.is_relative_to(self.root) else Path(review.__file__).resolve().parent
            safe = review._file(base, path.relative_to(base).as_posix())
            if review._sha(safe) != expected: raise SchemaError('A bound file changed.')

    def replay(self, body):
        if (body.pair_id, body.fault, body.repeat) not in self.allowed:
            raise SchemaError('The selected incident is not installed.')
        if not self.lock.acquire(blocking=False): return None
        try:
            self.check()
            result = review.replay_causal(self.root, body.pair_id, body.fault, body.repeat)
            if (result['run_id'] != self.run_id or (result['pair_id'],result['fault'],result['repeat']) !=
                    (body.pair_id,body.fault,body.repeat) or result['new_model_calls'] != 0 or result['new_qloo_calls'] != 0):
                raise SchemaError('Replay identity or execution mode differs.')
            self.check()
            return replay_dto(result, profile_names=self.profile_names[body.pair_id])
        finally: self.lock.release()


class _Boundary:
    def __init__(self, app, *, origin: str, max_bytes=4096, replay_limit=60, clock=time.monotonic,
                 read_timeout=5.0, case_session_limit=12, case_write_limit=30, case_read_limit=240):
        self.app, self.origin, self.host = app, origin, urlsplit(origin).netloc
        self.max_bytes, self.replay_limit, self.clock = max_bytes, replay_limit, clock
        self.replay_times = deque()
        self.read_times = deque()
        self.lock = threading.Lock()
        self.read_timeout = read_timeout
        self.readers = threading.BoundedSemaphore(4)
        self.case_queues = {name: deque() for name in ('session', 'write', 'read')}
        self.case_limits = {'session': case_session_limit, 'write': case_write_limit, 'read': case_read_limit}

    def admit_case(self, kind):
        now = self.clock()
        with self.lock:
            queue = self.case_queues[kind]
            while queue and queue[0] <= now - 60: queue.popleft()
            if len(queue) >= self.case_limits[kind]: return False
            queue.append(now)
            return True

    def admit(self, replay):
        now = self.clock()
        with self.lock:
            queue = self.replay_times if replay else self.read_times
            while queue and queue[0] <= now - 60: queue.popleft()
            if len(queue) >= (self.replay_limit if replay else 120): return False
            queue.append(now)
            return True

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http': return await self.app(scope, receive, send)
        async def reject(status, message):
            await JSONResponse({'error': message}, status_code=status, headers={'Cache-Control':'no-store'})(scope, receive, send)
        raw_headers = scope['headers']
        if len(raw_headers) > 64 or sum(len(k) + len(v) for k, v in raw_headers) > 8192:
            return await reject(431, 'Request headers too large.')
        critical = {'host', 'origin', 'cookie', 'x-affinityqa-csrf', 'content-type',
                    'content-length', 'transfer-encoding'}
        headers = {}
        for key, value in raw_headers:
            key, value = key.decode('latin1').lower(), value.decode('latin1')
            if key in critical and key in headers:
                return await reject(400, 'Ambiguous request headers.')
            headers[key] = value
        if 'transfer-encoding' in headers and ('content-length' in headers or headers['transfer-encoding'].lower() != 'chunked'):
            return await reject(400, 'Ambiguous request framing.')
        if headers.get('host') != self.host: return await reject(400, 'Invalid demo host.')
        origin = headers.get('origin')
        if origin is not None and origin != self.origin: return await reject(403, 'This demo requires its own origin.')
        replay = scope['path'] == '/api/demo/replay' and scope['method'] == 'POST'
        case = scope['path'].startswith('/api/demo/cases/')
        case_write = case and scope['method'] == 'POST'
        if case and scope.get('query_string'):
            return await reject(400, 'Case routes do not accept URL parameters.')
        if replay or case_write:
            if origin != self.origin: return await reject(403, 'This action requires this demo origin.')
            if headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                return await reject(415, 'Use application/json.')
            declared = headers.get('content-length')
            if declared is not None and not re.fullmatch(r'[0-9]{1,10}', declared):
                return await reject(400, 'Invalid request length.')
            if declared is not None and int(declared) > self.max_bytes:
                return await reject(413, 'Request too large.')
            if not self.readers.acquire(blocking=False): return await reject(429, 'Demo request readers are busy.')
            chunks, size = [], 0
            try:
                accepted = self.admit(True) if replay else self.admit_case('session' if scope['path'] == '/api/demo/cases/session' else 'write')
                if not accepted: return await reject(429, 'Demo request limit reached. Try again shortly.')
                deadline = time.monotonic() + self.read_timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0: return await reject(408, 'Request body timed out.')
                    try: message = await asyncio.wait_for(receive(), timeout=remaining)
                    except asyncio.TimeoutError: return await reject(408, 'Request body timed out.')
                    if message['type'] == 'http.disconnect': return
                    chunk = message.get('body', b''); size += len(chunk)
                    if size > self.max_bytes: return await reject(413, 'Request too large.')
                    chunks.append(chunk)
                    if not message.get('more_body'): break
                if declared is not None and int(declared) != size:
                    return await reject(400, 'Request length differs.')
                from .individual_capture import strict_json
                try: strict_json(b''.join(chunks))
                except (AffinityQAError, ValueError, UnicodeError):
                    return await reject(422, 'Invalid JSON body.')
            finally:
                self.readers.release()
            delivered = False
            original_receive = receive
            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type':'http.request','body':b''.join(chunks),'more_body':False}
                return await original_receive()
            receive = bounded_receive
        if scope['path'] == '/api/demo/summary' and scope['method'] == 'GET' and not self.admit(False):
            return await reject(429, 'Demo request limit reached. Try again shortly.')
        if case and scope['method'] == 'GET' and not self.admit_case('read'):
            return await reject(429, 'Demo request limit reached. Try again shortly.')
        async def secured(message):
            if message['type'] == 'http.response.start':
                message['headers'] = list(message.get('headers', [])) + [
                    (b'x-content-type-options',b'nosniff'), (b'referrer-policy',b'no-referrer'),
                    (b'x-frame-options',b'DENY'), (b'permissions-policy',b'camera=(), microphone=(), geolocation=()')]
            await send(message)
        await self.app(scope, receive, secured)


def create_public_app(root: Path, *, origin: str, run_id: str | None = None,
                      receipt_sha256: str | None = None, replay_limit: int = 60,
                      web_root: Path | None = None, case_manager=None,
                      case_session_limit: int = 12, case_write_limit: int = 30,
                      case_read_limit: int = 240) -> FastAPI:
    origin = canonical_origin(origin)
    if type(replay_limit) is not int or not 1 <= replay_limit <= 120:
        raise ValueError('Replay limit must be 1..120 per minute.')
    if (run_id is None) != (receipt_sha256 is None): raise ValueError('Both evidence bindings are required.')
    if any(type(value) is not int or not 1 <= value <= 600 for value in
           (case_session_limit, case_write_limit, case_read_limit)):
        raise ValueError('Public case request limits must be 1..600 per minute.')
    if case_manager is not None:
        from .public_cases import PublicCaseManager
        if not isinstance(case_manager, PublicCaseManager) or case_manager.origin != origin:
            raise ValueError('One explicit case manager must use the exact demo origin.')
    capture = _Capture(root, run_id, receipt_sha256) if run_id is not None else None
    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if case_manager is not None:
                await run_in_threadpool(case_manager.close)
    # Keep the explicit route allowlist behind TLS ingress; backend HTTP must not
    # generate scheme-downgrading redirects for unregistered slash variants.
    app = FastAPI(title='AffinityQA recorded reviewer demo', docs_url=None, redoc_url=None,
                  openapi_url=None, redirect_slashes=False, lifespan=lifespan)
    app.add_middleware(_Boundary, origin=origin, replay_limit=replay_limit,
                       case_session_limit=case_session_limit, case_write_limit=case_write_limit,
                       case_read_limit=case_read_limit)
    app.state.capture = capture
    app.state.case_manager = case_manager
    from .public_case_api import routes
    app.include_router(routes(case_manager, origin=origin))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, error):
        return JSONResponse({'error':'Invalid incident selection.'},status_code=422,headers={'Cache-Control':'no-store'})

    @app.exception_handler(AffinityQAError)
    @app.exception_handler(FileNotFoundError)
    @app.exception_handler(Exception)
    async def unavailable(request: Request, error):
        return JSONResponse({'error':'Recorded evidence could not be verified. No result approved.'},status_code=503,headers={'Cache-Control':'no-store'})

    @app.get('/healthz')
    def health():
        # Cheap liveness only. Integrity and approval belong to summary/replay, never this route.
        if case_manager is not None:
            worker = case_manager.manager.worker
            return JSONResponse({'status': 'alive', 'capture_configured': capture is not None,
                'execution': 'recorded-replay-and-remote-cases' if capture is not None else 'remote-cases',
                'new_cases_configured': True,
                'remote_execution_configured': case_manager.manager.enabled,
                'admissions_blocked': case_manager._mutations_blocked or case_manager.manager.closed,
                'capture_active': bool(worker and worker.is_alive()),
                'provider_readiness': 'NOT_CHECKED_BY_LIVENESS'}, headers={'Cache-Control': 'no-store'})
        return JSONResponse({'status':'alive','capture_configured':capture is not None,
                             'execution':'recorded-replay','live_inference':False},headers={'Cache-Control':'no-store'})

    @app.get('/api/demo/summary')
    def summary():
        if capture is None:
            return JSONResponse({'schema_version':1,'status':'UNAVAILABLE','causal_gate':'NOT_EVALUATED',
                                 'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED','pairs':[],
                                 'notice':'Source preview: no authorized verified capture installed.'},headers={'Cache-Control':'no-store'})
        capture.check()
        return JSONResponse(copy.deepcopy(capture.summary),headers={'Cache-Control':'no-store'})

    @app.post('/api/demo/replay')
    def replay(body: CausalReplayBody):
        if capture is None: raise SchemaError('No capture installed.')
        result = capture.replay(body)
        if result is None:
            return JSONResponse({'error':'Another recorded replay is running. Try again shortly.'},status_code=429,headers={'Cache-Control':'no-store'})
        return JSONResponse(result,headers={'Cache-Control':'no-store'})

    static = web_root or root / 'web/out'
    demo = static / 'demo.html'
    if not demo.is_file(): demo = static / 'demo/index.html'
    if demo.is_file():
        demo = review._file(static, demo.relative_to(static).as_posix())
        scripts = re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',demo.read_text('utf8'),re.DOTALL)
        hashes = ' '.join("'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'" for s in scripts if s)
        csp = f"default-src 'none'; script-src 'self' {hashes}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        @app.get('/')
        @app.get('/demo')
        @app.get('/demo/')
        def page():
            return FileResponse(demo,headers={'Content-Security-Policy':csp,'Cache-Control':'no-store'})

        @app.get('/icon.svg')
        def icon():
            try: path = review._file(static, 'icon.svg')
            except SchemaError: return JSONResponse({'error':'Not found.'},status_code=404)
            if not path.is_file(): return JSONResponse({'error':'Not found.'},status_code=404)
            return FileResponse(path, media_type='image/svg+xml',
                                headers={'Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'",
                                         'Cache-Control':'no-store'})

        @app.get('/_next/static/{asset:path}')
        def assets(asset: str):
            if Path(asset).suffix not in ('.js','.css','.woff','.woff2','.ttf'):
                return JSONResponse({'error':'Not found.'},status_code=404)
            try: path = review._file(static / '_next/static', asset)
            except SchemaError: return JSONResponse({'error':'Not found.'},status_code=404)
            if not path.is_file(): return JSONResponse({'error':'Not found.'},status_code=404)
            return FileResponse(path)
    return app
