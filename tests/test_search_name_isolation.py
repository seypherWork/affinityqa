"""Synthetic response-shape regression; no real provider observations embedded."""
import copy
import hashlib
import unittest
from pathlib import Path
from uuid import UUID
import test_wide_cinema_repeatable as wide_fixture
BASE=wide_fixture.BASE
from affinityqa.wide_cinema_verify import verify_identity_search


class SearchNameIsolationTests(unittest.TestCase):
    def setUp(self):
        self.f=wide_fixture.WideRepeatableTests('test_complete_owned_journey_100pool_download_and_restart_restore')
        self.f.setUp();self.addCleanup(self.f.doCleanups)

    def mutate(self,body,params):
        original=body['results'][0]
        original['name']='Synthetic artist'
        bad=copy.deepcopy(original)
        bad.update(entity_id=str(UUID(int=30000)),name='Synthetic  collaboration')
        body['results'].append(bad)

    def test_unrelated_noncanonical_name_does_not_block_identity_confirmation(self):
        f=self.f;f.transport.search_mutation=self.mutate
        job=f.plan(mode='music',seed_query='Synthetic artist')
        pending=f.search(job)
        self.assertEqual([r['name'] for r in pending['seed_candidates']],['Synthetic artist'])
        directory=Path(f.manager.manager._job(job['job_id'])['directory'])
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()}
        receipt=verify_identity_search(directory)
        self.assertEqual(receipt['verification_status'],'VERIFIED_IDENTITY_SEARCH')
        self.assertEqual(len(receipt['seed_candidates']),1)
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()})
        self.assertEqual((len(f.transport.calls),len(f.opener.calls)),(1,0))

    def test_mixed_names_complete_five_source_bound_films_download_and_restore(self):
        f=self.f;f.transport.search_mutation=self.mutate
        final=f.finish(mode='music',seed_query='Synthetic artist')
        self.assertEqual(final['status'],'COMPLETE',final)
        self.assertEqual(len(final['result']['wide_cinema_results']['delivered']),5)
        self.assertEqual((len(f.transport.calls),len(f.opener.calls)),(3,1))
        download=f.client.get(BASE+'/jobs/'+final['job_id']+'/verification')
        self.assertEqual(download.status_code,200)
        token=f.client.cookies.get('__Host-affinityqa-case')
        f.manager.close();f.manager=f.make_manager();f.client,f.headers=f.make_client(f.manager,token)
        self.assertEqual(f.read(final)['status'],'COMPLETE')
        self.assertEqual(f.client.get(BASE+'/jobs/'+final['job_id']+'/verification').content,download.content)
        self.assertEqual((len(f.transport.calls),len(f.opener.calls)),(3,1))

    def stopped(self,mutation):
        f=self.f;f.transport.search_mutation=mutation
        job=f.plan(mode='music')
        r=f.client.post(BASE+'/jobs/'+job['job_id']+'/execute',json={'plan_sha256':job['plan_sha256']},headers=f.headers)
        self.assertEqual(r.status_code,202)
        self.assertTrue(f.manager.manager.run_once())
        final=f.read(job)
        self.assertEqual(final['status'],'PARTIAL',final)
        self.assertEqual(final['result']['verification_status'],'VERIFIED_PARTIAL')
        self.assertEqual((len(f.transport.calls),len(f.opener.calls)),(1,0))
        self.assertFalse(f.manager.manager.run_once())
        return job,final

    def test_all_noncanonical_names_stop_without_query_identity_substitution(self):
        self.stopped(lambda b,p:b['results'][0].update(name='Synthetic  invalid'))

    def test_invalid_uuid_on_unusable_alternative_still_rejects_whole_search(self):
        def mutate(body,params):
            self.mutate(body,params);body['results'][1]['entity_id']='not-a-uuid'
        self.stopped(mutate)

    def test_conflicting_musical_uuid_not_hidden_by_name_filter(self):
        def mutate(body,params):
            self.mutate(body,params);body['results'][1]['entity_id']=body['results'][0]['entity_id']
        self.stopped(mutate)

    def test_bad_affinity_on_unusable_alternative_still_rejects_whole_search(self):
        def mutate(body,params):
            self.mutate(body,params);body['results'][1]['query']={'affinity':2.0}
        self.stopped(mutate)

    def test_name_filter_does_not_hide_invalid_envelope(self):
        def mutate(body,params):self.mutate(body,params);body['errors']=[]
        self.stopped(mutate)

    def test_control_character_alternative_cannot_be_selected(self):
        def mutate(body,params):
            self.mutate(body,params);body['results'][1]['name']='Synthetic\x00name'
        self.f.transport.search_mutation=mutate
        pending=self.f.search(self.f.plan(mode='music'))
        self.assertEqual(len(pending['seed_candidates']),1)

    def test_nonmusical_person_uuid_variant_is_not_a_conflict(self):
        def mutate(body,params):
            self.mutate(body,params)
            person=copy.deepcopy(body['results'][0]);person.update(types=['urn:entity:person'],properties={},name='Synthetic person')
            body['results'].append(person)
        self.f.transport.search_mutation=mutate
        pending=self.f.search(self.f.plan(mode='music'))
        self.assertEqual(len(pending['seed_candidates']),1)


if __name__=='__main__':unittest.main()
