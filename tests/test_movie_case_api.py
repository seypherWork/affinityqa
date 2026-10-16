"""Offline owned HTTP, conditioning and retained-case regressions for movie inputs."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from fastapi import FastAPI
from fastapi.testclient import TestClient
from affinityqa.cinema_discovery_agent import DiscoveryMovieAgent as LegacyAgent
from affinityqa.cinema_discovery_v4_agent import DiscoveryMovieAgent
from affinityqa.qloo import Response
from affinityqa.repeatable_case_api import routes
from affinityqa.repeatable_cases import RepeatableCaseManager
from affinityqa.qloo_cache import PrivateQlooCache
from test_cinema_identity_capture import identity_request, ID_A, ID_B
from test_discovery_capture import DiscoveryTransport
from test_discovery_agent import Opener, TEST_SECRET
from test_groq_agent import UNIT_QLOO_SECRET
import test_repeatable_cases as legacy_fixtures

ORIGIN = legacy_fixtures.ORIGIN

PREFIX = '/api/demo/cases'
FILM_A = '40000000-0000-4000-8000-000000000001'
FILM_ALT = '40000000-0000-4000-8000-000000000002'
FILM_B = '40000000-0000-4000-8000-000000000003'


class FilmTransport(DiscoveryTransport):
    def send(self, path, params):
        if path == '/search' and params.get('types') == 'urn:entity:movie':
            self.calls.append((path, copy.deepcopy(params)))
            choices = [(FILM_A, 'Gladiator', 2000), (FILM_ALT, 'Gladiator', 1992)] if params['query'] == 'Gladiator' else [(FILM_B, 'The Matrix', 1999)]
            return Response(200, {'results': [{'entity_id': identity, 'name': name,
                'types': ['urn:entity:movie'], 'properties': {'release_year': year}}
                for identity, name, year in choices]}, {})
        return super().send(path, params)


class MovieCaseApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy_fixtures.RepeatableTests('test_same_session_three_complete_cases_no_lifetime_caps_and_owned_receipts')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.request = identity_request()
        self.request['schema_version'] = 6
        self.request['movie_queries'] = {'A': ['Gladiator'], 'B': ['The Matrix']}
        self.request['preferences'] = {label: {'schema_version': 1, 'favorite_entity_ids': [], 'excluded_entity_ids': []} for label in ('A', 'B')}
        self.transport = FilmTransport(self.request)
        self.opener = Opener()
        self.agent_class = DiscoveryMovieAgent
        template = {k: copy.deepcopy(v) for k, v in self.request.items() if k not in ('preferences', 'movie_queries')}
        template['schema_version'] = 2
        def engine():
            return self.agent_class(TEST_SECRET, forbidden_secrets=(UNIT_QLOO_SECRET,), _test_opener=self.opener)
        self.template = template
        self.engine_factory = engine
        self.scheduler = self.fixture.scheduler()
        self.cache = PrivateQlooCache(self.fixture.parent/'private-movie-cache')
        self.manager = RepeatableCaseManager(self.fixture.parent/'repeatable-movies', template,
            origin=ORIGIN, minimum_model_interval_seconds=0.0, execution_enabled=True,
            settings_loader=self.fixture.settings, remote_key_loader=lambda: TEST_SECRET,
            scheduler=self.scheduler, qloo_cache=self.cache, _test_adapters=(engine, lambda: self.transport),
            _test_now=lambda: self.fixture.now, _test_autostart=False)
        self.addCleanup(self.manager.close)
        app = FastAPI()
        app.include_router(routes(self.manager, origin=ORIGIN))
        self.app = app
        self.client = TestClient(app, base_url=ORIGIN)
        self.addCleanup(self.client.close)
        self.headers = self.access(self.client)

    def access(self, client):
        response = client.post(PREFIX+'/session', json={}, headers={'origin': ORIGIN})
        self.assertEqual(response.status_code, 200, response.text)
        return {'origin': ORIGIN, 'x-affinityqa-csrf': response.json()['csrf_token']}

    def plan(self, *, movies=True):
        body = {'artists': self.request['artists'], 'preferences': self.request['preferences'],
                'confirm_identities': True, 'discover_new_movies': True}
        if movies:
            body['movie_queries'] = self.request['movie_queries']
        response = self.client.post(PREFIX+'/plans', json=body, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def search(self, job):
        response = self.client.post(PREFIX+f"/jobs/{job['job_id']}/execute", json={'plan_sha256': job['plan_sha256']}, headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        self.manager.manager.run_once()
        pending = self.client.get(PREFIX+f"/jobs/{job['job_id']}").json()
        self.assertEqual(pending['status'], 'AWAITING_IDENTITY_CONFIRMATION', pending)
        return pending

    def choice(self, pending, *, movies=True):
        value = {'plan_sha256': pending['plan_sha256'], 'identity_receipt_sha256': pending['identity_receipt_sha256'],
                 'selected_entity_ids': {'A': ID_A, 'B': ID_B}}
        if movies:
            value['selected_movie_entity_ids'] = {'A': [FILM_A], 'B': [FILM_B]}
        return value

    def confirm(self, pending, *, movies=True):
        response = self.client.post(PREFIX+f"/jobs/{pending['job_id']}/confirm-identities", json=self.choice(pending, movies=movies), headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        self.manager.manager.run_once()
        result = self.client.get(PREFIX+f"/jobs/{pending['job_id']}").json()
        self.assertEqual(result['status'], 'COMPLETE', result)
        return result

    def test_external_films_condition_both_recorded_inputs_and_download_restores(self):
        cap = self.client.get(PREFIX+'/capabilities').json()
        self.assertTrue(cap['movie_input_search_supported'])
        self.assertEqual(cap['maximum_movie_queries_per_case'], 2)
        job = self.plan()
        self.assertEqual(len(self.transport.calls), 0)
        self.assertEqual(job['maximum_qloo_requests'], 6)
        pending = self.search(job)
        self.assertEqual(len(self.transport.calls), 4)
        self.assertEqual(len(self.opener.calls), 0)
        self.assertEqual([row['release_year'] for row in pending['movie_candidates']['A'][0]], [2000, 1992])
        result = self.confirm(pending)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (6, 2))
        self.assertEqual(result['chosen_movie_inputs']['A'][0]['release_year'], 2000)
        for label, seed in [('A', FILM_A), ('B', FILM_B)]:
            rows = result['result']['cinema_results'][label]['delivered']
            self.assertEqual(len(rows), 5)
            self.assertEqual(len(set(rows)), 5)
            self.assertNotIn(seed, rows)
            self.assertTrue(set(rows) <= {r['entity_id'] for r in self.request['catalog']})
        insights = [params for path, params in self.transport.calls if path == '/v2/insights']
        self.assertIn(FILM_A, insights[0]['signal.interests.entities'].split(','))
        self.assertIn(FILM_B, insights[1]['signal.interests.entities'].split(','))
        for index, seed in enumerate((FILM_A, FILM_B)):
            model_input = self.opener.calls[index][1]['messages'][1]['content']
            self.assertIn(seed, model_input)
            self.assertNotIn('reserved_ratings', model_input)
        url = PREFIX+f"/jobs/{job['job_id']}/verification"
        receipt = self.client.get(url)
        self.assertEqual(receipt.status_code, 200)
        self.assertIn('attachment;', receipt.headers['content-disposition'])
        self.assertEqual(receipt.json()['result']['chosen_movie_inputs'], result['chosen_movie_inputs'])
        before = (len(self.transport.calls), len(self.opener.calls))
        self.access(self.client)
        self.assertEqual(self.client.get(PREFIX+f"/jobs/{job['job_id']}").json()['chosen_movie_inputs'], result['chosen_movie_inputs'])
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), before)
        repeated = self.client.post(PREFIX+f"/jobs/{job['job_id']}/confirm-identities", json=self.choice(pending), headers=self.headers)
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), before)

    def test_cached_search_and_changed_confirmed_remake_keep_intents_separate(self):
        first = self.confirm(self.search(self.plan()))
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (6, 2))
        pending = self.search(self.plan())
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (6, 2))
        selection = self.choice(pending)
        selection['selected_movie_entity_ids']['A'] = [FILM_ALT]
        response = self.client.post(PREFIX+f"/jobs/{pending['job_id']}/confirm-identities", json=selection, headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        self.manager.manager.run_once()
        second = self.client.get(PREFIX+f"/jobs/{pending['job_id']}").json()
        self.assertEqual(second['status'], 'COMPLETE', second)
        self.assertEqual(second['chosen_movie_inputs']['A'][0]['release_year'], 1992)
        self.assertEqual(first['chosen_movie_inputs']['A'][0]['release_year'], 2000)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (8, 4))
        final_insights = [params for path, params in self.transport.calls if path == '/v2/insights'][-2:]
        self.assertIn(FILM_ALT, final_insights[0]['signal.interests.entities'].split(','))
        self.assertNotIn(FILM_A, final_insights[0]['signal.interests.entities'].split(','))
        self.assertNotEqual(first['result']['cinema_results']['A']['intent_sha256'], second['result']['cinema_results']['A']['intent_sha256'])

    def test_wrong_slot_missing_and_forged_receipt_never_dispatch_model(self):
        pending = self.search(self.plan())
        url = PREFIX+f"/jobs/{pending['job_id']}/confirm-identities"
        missing = self.choice(pending, movies=False)
        wrong = self.choice(pending)
        wrong['selected_movie_entity_ids'] = {'A': [FILM_B], 'B': [FILM_A]}
        forged = self.choice(pending)
        forged['identity_receipt_sha256'] = '0'*64
        arbitrary = self.choice(pending)
        arbitrary['selected_movie_entity_ids']['A'] = ['40000000-0000-4000-8000-000000000099']
        for value in (missing, wrong, forged, arbitrary):
            response = self.client.post(url, json=value, headers=self.headers)
            self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (4, 0))
        self.assertEqual(self.client.get(PREFIX+f"/jobs/{pending['job_id']}").json()['status'], 'AWAITING_IDENTITY_CONFIRMATION')

    def test_closed_bodies_and_global_search_budget(self):
        body = {'artists': self.request['artists'], 'preferences': self.request['preferences'], 'confirm_identities': True, 'discover_new_movies': True}
        for queries in ({'A': ['one', 'two'], 'B': ['three']}, {'A': [''], 'B': []}, {'A': ['x'*201], 'B': []}):
            response = self.client.post(PREFIX+'/plans', json={**body, 'movie_queries': queries}, headers=self.headers)
            self.assertEqual(response.status_code, 422, response.text)
        fake = self.client.post(PREFIX+'/plans', json={**body, 'movie_queries': self.request['movie_queries'], 'chosen_movie_inputs': {'A': [], 'B': []}}, headers=self.headers)
        self.assertEqual(fake.status_code, 422)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (0, 0))

    def test_other_owner_and_csrf_cannot_confirm_or_read_movie_choices(self):
        pending = self.search(self.plan())
        url = PREFIX+f"/jobs/{pending['job_id']}/confirm-identities"
        self.assertEqual(self.client.post(url, json=self.choice(pending), headers={'origin': ORIGIN}).status_code, 403)
        with TestClient(self.app, base_url=ORIGIN) as other:
            headers = self.access(other)
            self.assertEqual(other.get(PREFIX+f"/jobs/{pending['job_id']}").status_code, 404)
            self.assertEqual(other.post(url, json=self.choice(pending), headers=headers).status_code, 404)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (4, 0))

    def test_saved_movie_confirmation_survives_restart_without_repeating_search(self):
        pending = self.search(self.plan())
        response = self.client.post(PREFIX+f"/jobs/{pending['job_id']}/confirm-identities", json=self.choice(pending), headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        root = self.manager.root
        # Use the actual configured cookie name, without inventing a second identity.
        from affinityqa.public_case_api import cookie_name
        token = self.client.cookies.get(cookie_name(ORIGIN))
        self.manager.close()
        restored = RepeatableCaseManager(root, self.template, origin=ORIGIN,
            minimum_model_interval_seconds=0.0, execution_enabled=True,
            settings_loader=self.fixture.settings, remote_key_loader=lambda: TEST_SECRET,
            scheduler=self.scheduler, qloo_cache=self.cache, _test_adapters=(self.engine_factory, lambda: self.transport),
            _test_now=lambda: self.fixture.now, _test_autostart=False)
        self.addCleanup(restored.close)
        self.assertEqual(restored.view(token, pending['job_id'])['status'], 'QUEUED')
        restored.manager.run_once()
        result = restored.view(token, pending['job_id'])
        self.assertEqual(result['status'], 'COMPLETE', result)
        self.assertEqual(result['chosen_movie_inputs']['A'][0]['entity_id'], FILM_A)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (6, 2))

    def test_changed_confirmation_checkpoint_blocks_before_keys_or_dispatch(self):
        pending = self.search(self.plan())
        response = self.client.post(PREFIX+f"/jobs/{pending['job_id']}/confirm-identities", json=self.choice(pending), headers=self.headers)
        self.assertEqual(response.status_code, 202, response.text)
        checkpoint = self.manager.manager.root/pending['job_id']/'identity-confirmation.json'
        saved = json.loads(checkpoint.read_bytes())
        saved['selected_movie_entity_ids']['A'] = [FILM_ALT]
        checkpoint.write_text(json.dumps(saved), encoding='utf-8')
        before = tuple(self.fixture.reads)
        self.manager.manager.run_once()
        result = self.client.get(PREFIX+f"/jobs/{pending['job_id']}").json()
        self.assertEqual(result['status'], 'FAILED', result)
        self.assertEqual(result['error_class'], 'SchemaError')
        self.assertEqual(tuple(self.fixture.reads), before)
        self.assertEqual((len(self.transport.calls), len(self.opener.calls)), (4, 0))

    def test_old_discovery_case_kept_byte_for_byte_while_new_case_completes(self):
        self.agent_class = LegacyAgent
        old = self.confirm(self.search(self.plan(movies=False)), movies=False)
        old_root = self.manager.manager.root/old['job_id']
        hashes = lambda: {p.relative_to(old_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in old_root.rglob('*') if p.is_file()}
        before = hashes()
        old_download = self.client.get(PREFIX+f"/jobs/{old['job_id']}/verification").content
        self.agent_class = DiscoveryMovieAgent
        new = self.confirm(self.search(self.plan()))
        self.assertNotEqual(new['job_id'], old['job_id'])
        self.assertEqual(hashes(), before)
        self.assertEqual(self.client.get(PREFIX+f"/jobs/{old['job_id']}/verification").content, old_download)
        self.assertEqual(self.client.get(PREFIX+f"/jobs/{old['job_id']}").json()['status'], 'COMPLETE')


if __name__ == '__main__':
    unittest.main()
