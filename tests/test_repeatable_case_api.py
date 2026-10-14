"""Owned repeatable HTTP behavior; offline providers and no client credentials."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from fastapi import FastAPI
from fastapi.testclient import TestClient
from affinityqa.repeatable_case_api import routes
from affinityqa.repeatable_case_config import read_configuration
from affinityqa.repeatable_cases import repeatable_policy
from affinityqa.individual_jobs import write
import test_repeatable_cases as fixtures
ORIGIN=fixtures.ORIGIN

PREFIX='/api/demo/cases'


class RepeatableApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.RepeatableTests('test_same_session_three_complete_cases_no_lifetime_caps_and_owned_receipts')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.manager=self.fixture.manager(scheduler=self.fixture.scheduler())
        app=FastAPI();app.include_router(routes(self.manager,origin=ORIGIN))
        self.client=TestClient(app,base_url=ORIGIN);self.addCleanup(self.client.close)

    def access(self,client=None):
        client=client or self.client
        response=client.post(PREFIX+'/session',json={},headers={'origin':ORIGIN})
        self.assertEqual(response.status_code,200,response.text)
        return {'origin':ORIGIN,'x-affinityqa-csrf':response.json()['csrf_token']}

    def plan(self,headers):
        response=self.client.post(PREFIX+'/plans',json={'artists':self.fixture.request['artists']},headers=headers)
        self.assertEqual(response.status_code,201,response.text)
        value=response.json();self.assert_zero_provider_stats(value)
        return value

    def assert_zero_provider_stats(self,job):
        self.assertEqual(set(job['provider_stats']),{'qloo','groq'})
        for provider in ('qloo','groq'):
            self.assertEqual(job['provider_stats'][provider],{'http_attempts':0,'cache_hits':0,
                'reconstructed_steps':0,'unknown_attempts':0})

    def test_owned_full_api_repeatability_and_same_origin_csrf(self):
        self.assertEqual(self.client.post(PREFIX+'/session',json={},headers={'origin':'https://foreign.invalid'}).status_code,403)
        headers=self.access();session=self.client.post(PREFIX+'/session',json={},headers={'origin':ORIGIN})
        self.assertEqual(session.json()['admission_mode'],'repeatable-v1')
        self.assertNotIn(self.client.cookies.get('__Host-affinityqa-case'),session.text)
        self.assertIn('HttpOnly',session.headers['set-cookie']);self.assertIn('SameSite=strict',session.headers['set-cookie'])
        for bad in ({'origin':ORIGIN},{'origin':'https://foreign.invalid','x-affinityqa-csrf':headers['x-affinityqa-csrf']}):
            self.assertEqual(self.client.post(PREFIX+'/plans',json={'artists':self.fixture.request['artists']},headers=bad).status_code,403)
        self.assertEqual(self.client.post(PREFIX+'/plans',json={'artists':self.fixture.request['artists'],'provider':'groq'},headers=headers).status_code,422)
        for _ in range(3):
            job=self.plan(headers);base=PREFIX+'/jobs/'+job['job_id']
            response=self.client.post(base+'/execute',json={'plan_sha256':job['plan_sha256']},headers=headers)
            self.assertEqual(response.status_code,202,response.text)
            self.assertEqual(response.json()['status'],'QUEUED')
            self.assert_zero_provider_stats(response.json())
            self.manager.manager.run_once()
            status=self.client.get(base);self.assertEqual(status.json()['status'],'COMPLETE',status.text)
            receipt=self.client.get(base+'/verification');self.assertEqual(receipt.status_code,200)
            self.assertEqual(set(receipt.json()),{'schema_version','job_id','plan_sha256','receipt_sha256','result','notice'})
            for private in ('artifact_sha256','provider_envelope','source_sha256','output_directory','owner_sha256','provider-provenance.json'):
                self.assertNotIn(private,receipt.text)
                self.assertNotIn(private,status.text)
            self.assertNotIn(str(self.manager.root),receipt.text)
            self.assertIn('attachment',receipt.headers['content-disposition'])
            self.assertEqual(self.client.post(base+'/execute',json={'plan_sha256':job['plan_sha256']},headers=headers).status_code,409)
        cap=self.client.get(PREFIX+'/capabilities').json();self.assertIsNone(cap['remaining_plans']);self.assertIsNone(cap['remaining_executions'])
        self.assertEqual(len(cap['jobs']),3)
        calls=(len(self.fixture.transport.calls),len(self.fixture.opener.calls))
        other=TestClient(self.client.app,base_url=ORIGIN);self.addCleanup(other.close);self.access(other)
        self.assertEqual(other.get(base).status_code,404);self.assertEqual(other.get(base+'/verification').status_code,404)
        self.client.get(base);self.client.get(base+'/verification')
        self.assertEqual(calls,(len(self.fixture.transport.calls),len(self.fixture.opener.calls)))

    def test_reject_duplicate_cookie_and_do_not_clear_unknown_owner_cookie(self):
        headers=self.access();token=self.client.cookies.get('__Host-affinityqa-case')
        self.assertEqual(self.client.get(PREFIX+'/capabilities',headers={'cookie':f'__Host-affinityqa-case={token}; __Host-affinityqa-case={token}'}).status_code,400)
        response=self.client.post(PREFIX+'/session',json={},headers={'origin':ORIGIN,'cookie':'__Host-affinityqa-case='+'a'*43})
        self.assertEqual(response.status_code,404)
        self.assertNotIn('set-cookie',response.headers)

    def test_closed_new_configuration_and_long_paths_fail_before_files(self):
        value={'schema_version':2,'admission_mode':'repeatable-v1','request':self.fixture.request,
               'policy':repeatable_policy(),'minimum_model_interval_seconds':0.0,
               'http_limits':{'case_session_limit':10,'case_write_limit':10,'case_read_limit':60},
               'provider_limits':{'qloo':[{'name':'rpm','capacity':3,'seconds':60,'metric':'requests','basis':'conservative'}],
                  'groq':[{'name':'tokens','capacity':8000,'seconds':60,'metric':'tokens','basis':'conservative'}]}}
        config=self.fixture.parent/'config.json';write(config,value)
        self.assertEqual(read_configuration(config)['admission_mode'],'repeatable-v1')
        invalid=copy.deepcopy(value);invalid['policy']['lifetime_plan_limit']=3
        bad=self.fixture.parent/'bad-config.json';write(bad,invalid)
        with self.assertRaises(Exception):read_configuration(bad)
        if sys.platform=='win32':
            path=self.fixture.parent/('long-path-'+'x'*170)
            with self.assertRaises(Exception):self.fixture.manager(root=path)
            self.assertFalse(path.exists())

    def test_owned_history_seek_pages_handle_ties_without_admission_or_file_changes(self):
        headers=self.access();original=self.plan(headers)
        token=self.client.cookies.get('__Host-affinityqa-case');owner=self.manager._identity(token)
        other=TestClient(self.client.app,base_url=ORIGIN);self.addCleanup(other.close);self.access(other)
        foreign=self.manager._identity(other.cookies.get('__Host-affinityqa-case'))
        # Controlled synthetic rows exercise pagination, not provider captures.
        # One actual retained plan above supplies immutable file-preservation proof.
        with self.manager.store.transaction() as db:
            for index in range(425):
                job_id=f'20260101T120000Z-{index:08x}'
                created='2026-11-02T12:00:00.000+00:00' if index<17 else '2026-11-01T12:00:00.000+00:00'
                plan={'request':{'artists':{'A':'Synthetic history A','B':f'Synthetic history B {index}'}}}
                db.execute('INSERT INTO jobs(job_id,owner,created,plan_json,envelope_sha,status) VALUES(?,?,?,?,?,?)',
                    (job_id,owner,created,json.dumps(plan),'0'*64,'PLANNED'))
            foreign_id='20260101T120000Z-fffffff0'
            db.execute('INSERT INTO jobs(job_id,owner,created,plan_json,envelope_sha,status) VALUES(?,?,?,?,?,?)',
                (foreign_id,foreign,'2026-11-03T12:00:00.000+00:00',json.dumps(plan),'0'*64,'PLANNED'))
        expected=[row['job_id'] for row in self.manager.store.rows(
            'SELECT job_id FROM jobs WHERE owner=? ORDER BY created DESC,job_id DESC',(owner,))]
        before_changes=self.manager.store.db.total_changes
        original_files={str(path.relative_to(self.manager.root)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (self.manager.root/'jobs').rglob('*') if path.is_file() and path.name!='.affinityqa-individual.lock'}
        capability=self.client.get(PREFIX+'/capabilities')
        self.assertEqual(capability.status_code,200,capability.text)
        first=capability.json();self.assertEqual(len(first['jobs']),200)
        self.assertNotIn(original['job_id'],[entry['job_id'] for entry in first['jobs']])
        self.assertTrue(first['jobs_truncated']);cursor=first['next_cursor_job_id']
        self.assertEqual(cursor,first['jobs'][-1]['job_id'])
        collected=[entry['job_id'] for entry in first['jobs']];page_sizes=[]
        while cursor is not None:
            response=self.client.get(PREFIX+'/jobs/older-than/'+cursor)
            self.assertEqual(response.status_code,200,response.text)
            page=response.json();self.assertEqual(set(page),{'schema_version','jobs','jobs_truncated','next_cursor_job_id'})
            self.assertEqual(response.headers['cache-control'],'no-store')
            page_sizes.append(len(page['jobs']))
            for entry in page['jobs']:
                self.assertEqual(set(entry),{'job_id','status','artists','legacy_case','read_only'})
                self.assertFalse(entry['legacy_case']);self.assertFalse(entry['read_only'])
            self.assertNotIn(owner,response.text);self.assertNotIn(foreign,response.text)
            self.assertNotIn('plan_json',response.text);self.assertNotIn('envelope_sha',response.text)
            collected.extend(entry['job_id'] for entry in page['jobs'])
            self.assertEqual(page['jobs_truncated'],page['next_cursor_job_id'] is not None)
            cursor=page['next_cursor_job_id']
        self.assertEqual(page_sizes,[200,26])
        self.assertEqual(collected,expected);self.assertEqual(len(set(collected)),426)
        self.assertEqual(self.client.get(PREFIX+'/jobs/'+original['job_id']).json()['status'],'PLANNED')
        self.assertEqual(other.get(PREFIX+'/jobs/older-than/'+first['next_cursor_job_id']).status_code,404)
        self.assertEqual(self.client.get(PREFIX+'/jobs/older-than/'+foreign_id).status_code,404)
        self.assertEqual(self.client.get(PREFIX+'/jobs/older-than/20200101T000000Z-ffffffff').status_code,404)
        self.assertEqual(self.manager.store.db.total_changes,before_changes)
        self.assertEqual(original_files,{str(path.relative_to(self.manager.root)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (self.manager.root/'jobs').rglob('*') if path.is_file() and path.name!='.affinityqa-individual.lock'})
        self.assertEqual((len(self.fixture.transport.calls),len(self.fixture.opener.calls)),(0,0))
        self.assertEqual(self.manager.health()['queued'],0)


if __name__=='__main__':unittest.main()
