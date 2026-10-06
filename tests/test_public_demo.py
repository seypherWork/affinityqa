"""Synthetic boundary fixtures only. Real captures are verified separately."""
import asyncio
import copy
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fastapi.testclient import TestClient
from affinityqa import public_demo as public
from affinityqa.api import CausalReplayBody
from affinityqa.errors import SchemaError


def fake_result():
    trace = {key: 'a'*64 for key in public.TRACE_FIELDS[:-1]}
    trace['cache_hit'] = False
    film = {'id':'synthetic-not-provider-id','title':'Synthetic movie','year':2001,'raw_provider':'DO_NOT_DISCLOSE'}
    return {'schema_version':1,'status':'PASS','replay_gate':'PASS','run_id':'20261004T000000Z-00000000',
            'pair_id':'causal-validation-01','fault':'stale-profile','repeat':1,
            'source':'recorded-local-llm-replay','new_model_calls':0,'new_qloo_calls':0,
            'recorded_decision_dispatches':4,'diagnosis':'STALE_PROFILE','repair':'restore-request-profile',
            'checks':{key:True for key in ('supported_diagnosis','repair_applied','profile_integrity_restored',
                     'decision_redispatched','matches_recorded_healthy','legitimate_cache_reuse')},
            'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED','notice':'Synthetic unit fixture only.',
            'before':[film],'after':[film],'healthy':[film],'trace':trace,'repaired_trace':trace,
            'source_execution_ids':['DO_NOT_DISCLOSE'],'private_packet':{'credential':'DO_NOT_DISCLOSE'}}


def fake_report():
    return {'status':'COMPLETE','run_id':'20261004T000000Z-00000000','protocol_version':'synthetic-unit-only',
            'causal_gate':'PASS','behavioral_gate':'OBSERVED_RECOVERY','cultural_gate':'NOT_VALIDATED',
            'release_gate':'BLOCKED','passing':3,'denominator':3,'model_calls':39,'qloo_requests':2,
            'behavioral_recoveries_observed':9,'noise_barrier':0,'policy_sha256':'b'*64,
            'pairs':[{'pair_id':'causal-validation-01','artists':{'A':'SyntheticA','B':'SyntheticB'},
                      'split':'validation','cases':[{'fault':'stale-profile','private':'DO_NOT_DISCLOSE'}],
                      'raw_snapshot':'DO_NOT_DISCLOSE'}], 'private_packet':'DO_NOT_DISCLOSE'}


class SyntheticCapture:
    def __init__(self,*args): self.summary = public.summary_dto(fake_report(), 'c'*64)
    def check(self): pass
    def replay(self,body): return public.replay_dto(fake_result(), profile_names={'a'*64:'Synthetic artist'})


class PublicDemoTests(unittest.TestCase):
    def client(self, root=ROOT, **kwargs):
        return TestClient(public.create_public_app(root, origin='https://review.example', **kwargs),
                          base_url='https://review.example',raise_server_exceptions=False)

    def test_exact_origin_and_http_loopback_only(self):
        for value in ('https://review.example','http://127.0.0.1:8767','http://[::1]:8767'):
            self.assertEqual(public.canonical_origin(value),value)
        for value in ('http://review.example','https://review.example/','https://x@review.example',
                      'https://*.example','https://review.example?secret=1','ftp://review.example'):
            with self.assertRaises(ValueError): public.canonical_origin(value)

    def test_projection_is_allowlist_not_secret_field_deletion(self):
        result = fake_result(); result['trace']['raw_context'] = 'DO_NOT_DISCLOSE'
        dto = public.replay_dto(result, profile_names={'a'*64:'Synthetic artist'})
        self.assertNotIn('DO_NOT_DISCLOSE',str(dto));self.assertNotIn('id',dto['before'][0])
        self.assertEqual(set(dto['trace']),set(public.TRACE_FIELDS))
        self.assertNotIn('DO_NOT_DISCLOSE',str(public.summary_dto(fake_report(),'c'*64)))
        result['checks']['repair_applied'] = 'false'
        with self.assertRaises(SchemaError): public.replay_dto(result, profile_names={'a'*64:'Synthetic artist'})
        with self.assertRaises(SchemaError): public.replay_dto(fake_result(), profile_names={})

    def test_source_only_preview_has_no_false_evidence(self):
        with self.client() as client:
            body = client.get('/api/demo/summary').json()
            self.assertEqual(body['status'],'UNAVAILABLE'); self.assertEqual(body['pairs'],[])
            self.assertEqual(client.get('/healthz').json()['live_inference'],False)
            self.assertEqual(client.post('/api/demo/replay',headers={'Origin':'https://review.example'},
                             json={'pair_id':'causal-validation-01','fault':'stale-profile','repeat':1}).status_code,503)

    def test_private_and_write_routes_are_not_registered(self):
        with self.client() as client:
            for path in ('/api/review','/api/causal-repair/export','/api/runs','/api/live/jobs',
                         '/api/regression-pack','/api/repair-decisions','/docs','/redoc','/openapi.json','/.env','/runs/a'):
                self.assertEqual(client.get(path).status_code,404,path)
            for path in ('/api/references','/api/comparisons','/api/live/jobs'):
                self.assertEqual(client.post(path,json={}).status_code,404,path)

    def test_noncanonical_routes_never_redirect_to_http_behind_tls_proxy(self):
        app = public.create_public_app(ROOT, origin='https://review.example')
        with TestClient(app, base_url='http://review.example', follow_redirects=False) as client:
            for forwarded in ('https', 'http', 'https, http'):
                headers = {'Origin': 'https://review.example', 'X-Forwarded-Proto': forwarded}
                for method, path in (('GET', '/healthz/'), ('GET', '/api/demo/summary/'),
                                     ('POST', '/api/demo/replay/')):
                    response = client.request(method, path, headers=headers)
                    self.assertEqual(response.status_code, 404, (method, path, forwarded))
                    self.assertNotIn('location', response.headers)
            self.assertEqual(client.get('/healthz').status_code, 200)
            self.assertEqual(client.get('/api/demo/summary').status_code, 200)

    def test_own_https_origin_host_stream_bound_schema(self):
        body={'pair_id':'causal-validation-01','fault':'stale-profile','repeat':1}
        with patch.object(public,'_Capture',SyntheticCapture), self.client(run_id='20261004T000000Z-00000000',receipt_sha256='c'*64) as client:
            own={'Origin':'https://review.example'}
            self.assertEqual(client.post('/api/demo/replay',headers=own,json=body).status_code,200)
            for headers in ({},{'Origin':'http://review.example'},{'Origin':'https://attacker.example'}):
                self.assertEqual(client.post('/api/demo/replay',headers=headers,json=body).status_code,403)
            self.assertEqual(client.get('/healthz',headers={'Host':'attacker.example'}).status_code,400)
            self.assertEqual(client.post('/api/demo/replay',headers=own,json={**body,'repeat':True}).status_code,422)
            self.assertEqual(client.post('/api/demo/replay',headers=own,json={**body,'model_url':'DO_NOT_DISCLOSE'}).status_code,422)
            self.assertEqual(client.post('/api/demo/replay',headers={**own,'Content-Type':'text/plain'},content='x').status_code,415)
            chunks=(b'x'*1024 for _ in range(5))
            self.assertEqual(client.post('/api/demo/replay',headers={**own,'Content-Type':'application/json'},content=chunks).status_code,413)
            self.assertEqual(client.get('/api/demo/summary').headers['cache-control'],'no-store')

    def test_generic_integrity_error_does_not_echo_paths_or_secrets(self):
        with patch.object(public,'_Capture',SyntheticCapture), self.client(run_id='20261004T000000Z-00000000',receipt_sha256='c'*64) as client:
            with patch.object(SyntheticCapture,'check',side_effect=SchemaError('DO_NOT_DISCLOSE C:/private')):
                response=client.get('/api/demo/summary')
                self.assertEqual(response.status_code,503); self.assertNotIn('DO_NOT_DISCLOSE',response.text)

    def test_rate_limit_and_busy_capture_do_not_queue_execution(self):
        with patch.object(public,'_Capture',SyntheticCapture), self.client(run_id='20261004T000000Z-00000000',receipt_sha256='c'*64,replay_limit=1) as client:
            args={'headers':{'Origin':'https://review.example'},'json':{'pair_id':'causal-validation-01','fault':'stale-profile','repeat':1}}
            self.assertEqual(client.post('/api/demo/replay',**args).status_code,200)
            self.assertEqual(client.post('/api/demo/replay',**args).status_code,429)
        capture=public._Capture.__new__(public._Capture)
        capture.allowed={('causal-validation-01','stale-profile',1)};capture.lock=threading.Lock();capture.lock.acquire()
        try:self.assertIsNone(capture.replay(CausalReplayBody(**args['json'])))
        finally:capture.lock.release()

    def test_summary_rate_limit_does_not_disable_cheap_liveness(self):
        with patch.object(public,'_Capture',SyntheticCapture), self.client(run_id='20261004T000000Z-00000000',receipt_sha256='c'*64) as client:
            with patch.object(SyntheticCapture,'check') as check:
                for _ in range(120): self.assertEqual(client.get('/api/demo/summary').status_code,200)
                self.assertEqual(client.get('/api/demo/summary').status_code,429)
                for _ in range(125):
                    response=client.get('/healthz')
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.json()['status'],'alive')
                self.assertEqual(check.call_count,120)

    def test_unsupported_methods_do_not_consume_replay_quota(self):
        with patch.object(public,'_Capture',SyntheticCapture), self.client(run_id='20261004T000000Z-00000000',receipt_sha256='c'*64,replay_limit=1) as client:
            self.assertEqual(client.get('/api/demo/replay').status_code,405)
            self.assertEqual(client.options('/api/demo/replay').status_code,405)
            self.assertEqual(client.post('/api/demo/replay',headers={'Origin':'https://review.example'},
                json={'pair_id':'causal-validation-01','fault':'stale-profile','repeat':1}).status_code,200)

    def test_capture_file_change_and_added_file_fail_closed(self):
        temporary = ROOT / '.test-runs';temporary.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as directory:
            root=Path(directory);run=root/'runs/synthetic';run.mkdir(parents=True)
            (root/'evidence').mkdir();sample=run/'sample.json';sample.write_text('{}','utf8')
            capture=public._Capture.__new__(public._Capture)
            capture.root=root;capture.run=run;capture.members={'sample.json'};capture.receipt_names=()
            capture.bound={sample:public.review._sha(sample)};capture.check()
            sample.write_text('{"changed":true}','utf8')
            with self.assertRaises(SchemaError):capture.check()
            sample.write_text('{}','utf8');(run/'unbound.json').write_text('{}','utf8')
            with self.assertRaises(SchemaError):capture.check()

    def test_static_is_bounded_and_has_script_hash_policy(self):
        temporary = ROOT / '.test-runs'
        temporary.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as directory:
            root=Path(directory);static=root/'web/out';(static/'_next/static').mkdir(parents=True)
            (static/'demo.html').write_text('<html><script>console.log("synthetic")</script></html>','utf8')
            (static/'_next/static/app.js').write_text('console.log("synthetic")','utf8')
            (root/'.env').write_text('DO_NOT_DISCLOSE','utf8')
            with self.client(root=root) as client:
                response=client.get('/');self.assertEqual(response.status_code,200)
                self.assertIn("'sha256-",response.headers['content-security-policy'])
                self.assertNotIn("script-src 'self' 'unsafe-inline'",response.headers['content-security-policy'])
                self.assertEqual(client.get('/_next/static/app.js').status_code,200)
                self.assertEqual(client.get('/_next/static/file.json').status_code,404)
                self.assertEqual(client.get('/_next/static/%2e%2e/%2e%2e/%2e%2e/.env').status_code,404)


    def test_exported_icon_link_resolves_without_opening_other_svg_files(self):
        temporary = ROOT / '.test-runs'
        temporary.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as directory:
            root = Path(directory)
            static = root / 'web/out'
            static.mkdir(parents=True)
            icon = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><path d="M0 0h64v64H0z"/></svg>'
            (static / 'demo.html').write_text('<html><head><link rel="icon" href="/icon.svg?a37278455bd553ab"></head></html>', 'utf8')
            (static / 'icon.svg').write_bytes(icon)
            (static / 'private.svg').write_text('DO_NOT_DISCLOSE', 'utf8')
            (root / '.env').write_text('DO_NOT_DISCLOSE', 'utf8')
            with self.client(root=root) as client:
                page = client.get('/demo')
                self.assertEqual(page.status_code, 200)
                self.assertIn('href="/icon.svg?a37278455bd553ab"', page.text)
                for uri in ('/icon.svg', '/icon.svg?a37278455bd553ab', '/icon.svg?file=../.env'):
                    response = client.get(uri)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.content, icon)
                    self.assertEqual(response.headers['content-type'], 'image/svg+xml')
                    self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
                    self.assertEqual(response.headers['content-security-policy'], "default-src 'none'; frame-ancestors 'none'")
                for uri in ('/private.svg', '/.env', '/icon.svg/', '/_next/static/private.svg'):
                    response = client.get(uri)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotIn('DO_NOT_DISCLOSE', response.text)

    def test_missing_exported_icon_is_not_replaced_by_another_asset(self):
        temporary = ROOT / '.test-runs'
        temporary.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as directory:
            root = Path(directory)
            static = root / 'web/out'
            static.mkdir(parents=True)
            (static / 'demo.html').write_text('<html></html>', 'utf8')
            (root / 'icon.svg').write_text('DO_NOT_DISCLOSE', 'utf8')
            with self.client(root=root) as client:
                response = client.get('/icon.svg')
                self.assertEqual(response.status_code, 404)
                self.assertNotIn('DO_NOT_DISCLOSE', response.text)

    def test_linked_exported_icon_does_not_disclose_an_outside_file(self):
        temporary = ROOT / '.test-runs'
        temporary.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as directory:
            root = Path(directory)
            static = root / 'web/out'
            static.mkdir(parents=True)
            (static / 'demo.html').write_text('<html></html>', 'utf8')
            outside = root / 'private.svg'
            outside.write_text('DO_NOT_DISCLOSE', 'utf8')
            try:
                (static / 'icon.svg').symlink_to(outside)
            except OSError as error:
                if getattr(error, 'winerror', None) == 1314:
                    self.skipTest('This Windows host lacks the privilege to create a symlink.')
                raise
            with self.client(root=root) as client:
                response = client.get('/icon.svg')
                self.assertEqual(response.status_code, 404)
                self.assertNotIn('DO_NOT_DISCLOSE', response.text)



class BodyAdmissionTests(unittest.IsolatedAsyncioTestCase):
    def scope(self):
        return {'type':'http','method':'POST','path':'/api/demo/replay',
                'headers':[(b'host',b'review.example'),(b'origin',b'https://review.example'),
                           (b'content-type',b'application/json')]}

    async def test_body_timeout_reserves_quota_before_receive(self):
        async def app(scope,receive,send): self.fail('Incomplete body reached the app.')
        boundary=public._Boundary(app,origin='https://review.example',replay_limit=1,read_timeout=.02)
        messages=[]
        async def send(message): messages.append(message)
        async def stalled(): await asyncio.Future()
        await boundary(self.scope(),stalled,send)
        self.assertEqual(messages[0]['status'],408)
        messages.clear()
        async def forbidden_receive(): self.fail('Exhausted request attempted to read a body.')
        await boundary(self.scope(),forbidden_receive,send)
        self.assertEqual(messages[0]['status'],429)
        self.assertTrue(boundary.readers.acquire(blocking=False))
        boundary.readers.release()

    async def test_only_four_unfinished_body_readers_are_admitted(self):
        async def app(scope,receive,send):
            await send({'type':'http.response.start','status':200,'headers':[]})
        boundary=public._Boundary(app,origin='https://review.example',read_timeout=.5)
        release=asyncio.Event(); entered=[asyncio.Event() for _ in range(4)]
        async def send(message): pass
        def receiver(index):
            async def receive():
                entered[index].set(); await release.wait()
                return {'type':'http.request','body':b'{}','more_body':False}
            return receive
        tasks=[asyncio.create_task(boundary(self.scope(),receiver(i),send)) for i in range(4)]
        try:
            await asyncio.gather(*(event.wait() for event in entered))
            messages=[]
            async def fifth_send(message): messages.append(message)
            async def forbidden_receive(): self.fail('Fifth reader was admitted.')
            await boundary(self.scope(),forbidden_receive,fifth_send)
            self.assertEqual(messages[0]['status'],429)
        finally:
            release.set(); await asyncio.gather(*tasks)
        self.assertEqual(len(boundary.replay_times),4)


if __name__=='__main__': unittest.main()
