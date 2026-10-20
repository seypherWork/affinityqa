"""Synthetic public HTTP regressions; no private capture or provider access."""
import copy
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from affinityqa.errors import TransportError
import test_wide_cinema_repeatable as wide_fixture
BASE=wide_fixture.BASE


class PartialIdentityProjectionTests(unittest.TestCase):
    def setUp(self):
        self.f=wide_fixture.WideRepeatableTests('test_complete_owned_journey_100pool_download_and_restart_restore')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def partial(self,version=9,transport_failure=False):
        f=self.f
        if transport_failure:f.transport.failure=TransportError('Synthetic pre-response transport failure')
        else:f.transport.search_mutation=lambda body,params:body.update(results=[])
        if version==9:job=f.plan(mode='music',seed_query='Synthetic unknown musician')
        else:
            response=f.client.post(BASE+'/open-movies/plans',json={'movie_query':'Synthetic unknown film'},headers=f.headers)
            self.assertEqual(response.status_code,201,response.text)
            job=response.json()
        response=f.client.post(BASE+'/jobs/'+job['job_id']+'/execute',json={'plan_sha256':job['plan_sha256']},headers=f.headers)
        self.assertEqual(response.status_code,202,response.text)
        self.assertTrue(f.manager.manager.run_once())
        return job,f.read(job)

    def check_readable(self,version=9,transport_failure=False):
        job,view=self.partial(version,transport_failure)
        self.assertEqual(view['status'],'PARTIAL',view)
        self.assertEqual(view['result']['verification_status'],'VERIFIED_PARTIAL')
        self.assertEqual(view['saved_provider_samples'],0 if transport_failure else 1)
        self.assertEqual(view['saved_model_packets'],0)
        self.assertEqual(view['provider_stats']['qloo']['http_attempts'],1)
        response=self.f.client.get(BASE+'/jobs/'+job['job_id']+'/verification')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['result']['verification_status'],'VERIFIED_PARTIAL')
        self.assertNotIn('provider_envelope',response.text)
        self.assertFalse(self.f.manager.manager.run_once())
        self.assertEqual((len(self.f.transport.calls),len(self.f.opener.calls)),(1,0))
        return job,view,response.content

    def test_wide_empty_search_partial_is_readable_and_downloadable(self):
        self.check_readable()

    def test_open_movie_empty_search_partial_is_readable_and_downloadable(self):
        self.check_readable(8)

    def test_transport_attempt_is_not_counted_as_saved_sample(self):
        job,view=self.partial(transport_failure=True)
        self.assertEqual(view['status'],'UNKNOWN',view)
        self.assertEqual(view['saved_provider_samples'],0)
        self.assertEqual(view['saved_model_packets'],0)
        self.assertEqual(view['provider_stats']['qloo']['http_attempts'],1)
        self.assertEqual(view['provider_stats']['qloo']['unknown_attempts'],1)
        self.assertEqual(self.f.client.get(BASE+'/jobs/'+job['job_id']+'/verification').status_code,409)
        self.assertFalse(self.f.manager.manager.run_once())
        self.assertEqual((len(self.f.transport.calls),len(self.f.opener.calls)),(1,0))

    def test_partial_restore_retains_bytes_history_and_no_resend(self):
        job,view,download=self.check_readable()
        f=self.f
        root=f.manager.root/'jobs'/job['job_id']
        before={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
        token=f.client.cookies.get('__Host-affinityqa-case')
        f.manager.close()
        f.manager=f.make_manager()
        f.client,f.headers=f.make_client(f.manager,token)
        self.assertEqual(f.read(job)['status'],'PARTIAL')
        self.assertEqual(f.client.get(BASE+'/jobs/'+job['job_id']+'/verification').content,download)
        self.assertFalse(f.manager.manager.run_once())
        self.assertEqual(before,{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()})
        self.assertEqual((len(f.transport.calls),len(f.opener.calls)),(1,0))

    def test_partial_tampered_sample_still_blocks_download(self):
        job,view,_=self.check_readable()
        directory=Path(self.f.manager.manager._job(job['job_id'])['directory'])
        sample=next(directory.glob('http-*.json'))
        with sample.open('ab') as stream:stream.write(b' ')
        self.assertEqual(self.f.read(job)['status'],'EVIDENCE_CHANGED')
        self.assertEqual(self.f.client.get(BASE+'/jobs/'+job['job_id']+'/verification').status_code,409)

    def test_partial_tampered_receipt_still_blocks_download(self):
        job,view,_=self.check_readable()
        directory=Path(self.f.manager.manager._job(job['job_id'])['directory'])
        receipt=next(p for p in (directory.parent.parent/'verification.json',directory.parent.parent/'identity-verification.json') if p.is_file())
        with receipt.open('ab') as stream:stream.write(b' ')
        self.assertEqual(self.f.read(job)['status'],'EVIDENCE_CHANGED')
        self.assertEqual(self.f.client.get(BASE+'/jobs/'+job['job_id']+'/verification').status_code,409)

    def test_full_capture_missing_final_counters_still_fails_closed(self):
        f=self.f
        job=f.finish()
        self.assertEqual(job['status'],'COMPLETE',job)
        receipt=f.manager.manager.receipt(job['job_id'])
        broken=copy.deepcopy(receipt)
        broken.pop('verified_provider_samples')
        with patch.object(f.manager.manager,'_receipt',return_value=broken):
            self.assertEqual(f.read(job)['status'],'EVIDENCE_CHANGED')
            self.assertEqual(f.client.get(BASE+'/jobs/'+job['job_id']+'/verification').status_code,409)


if __name__=='__main__':unittest.main()
