"""Exact private Qloo samples, including original observation provenance.

Only validated, redacted samples enter this cache. It is intentionally separate
from the fault-injected agent cache and must reside outside public source trees.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3

from .evidence import fingerprint, redact
from .models import parse_entities

SCOPE_FIELDS = frozenset(('identity', 'profile', 'catalog', 'preferences', 'source_namespace'))


class PrivateQlooCache:
    def __init__(self, private_directory, *, public_roots=()):
        directory = Path(private_directory).resolve()
        roots = (Path(__file__).resolve().parents[2],) + tuple(Path(p).resolve() for p in public_roots)
        if any(directory == root or root in directory.parents for root in roots):
            raise ValueError('Private Qloo samples cannot be stored inside a public source tree.')
        if any((parent / '.git').exists() for parent in (directory, *directory.parents)):
            raise ValueError('Private Qloo cache must be outside Git checkouts.')
        directory.mkdir(parents=True, exist_ok=True)
        if os.name != 'nt':
            os.chmod(directory, 0o700)
        self.path = directory / 'qloo-private-cache.sqlite3'
        with self._connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS samples (key TEXT PRIMARY KEY, value TEXT NOT NULL, sha TEXT NOT NULL)')
        if os.name != 'nt':
            os.chmod(self.path, 0o600)

    @staticmethod
    def key(request, scope):
        if (not isinstance(scope, dict) or not SCOPE_FIELDS <= set(scope)
                or not scope['source_namespace'] or not isinstance(request, dict)
                or set(request) != {'method', 'host', 'path', 'params'}
                or request['method'] != 'GET' or request['host'] != 'https://hackathon.api.qloo.com'):
            raise ValueError('Full private Qloo query and semantic scope are required.')
        # JSON fingerprints preserve full values and ordering of arrays. Never
        # discard filters, exclusions, catalog metadata or identity selections.
        return fingerprint({'schema_version': 1, 'request': request, 'scope': scope})

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, request, scope):
        key = self.key(request, scope)
        with self._connection() as db:
            row = db.execute('SELECT value,sha FROM samples WHERE key=?', (key,)).fetchone()
        if row is None:
            return None
        value = json.loads(row[0])
        if fingerprint(value) != row[1] or value.get('cache_key_sha256') != key:
            raise RuntimeError('Private cached Qloo sample failed its stored integrity binding.')
        self._validate(value['sample'], scope)
        return value

    @staticmethod
    def _validate(sample, scope=None):
        required = {'source', 'request', 'status', 'response', 'response_sha256', 'response_headers',
                    'elapsed_ms', 'attempt', 'live_network_request'}
        if (not isinstance(sample, dict) or set(sample) != required or sample['status'] != 200
                or sample['response_sha256'] != fingerprint(sample['response']) or sample['attempt'] != 1
                or type(sample['live_network_request']) is not bool):
            raise ValueError('Only an intact accepted first-attempt Qloo observation can be cached.')
        from .search_music_candidates import CONTRACT, music_candidates
        contract=scope.get('identity_candidate_contract') if isinstance(scope,dict) else None
        if contract is not None and contract != CONTRACT:
            raise ValueError('Unrecognized private identity-cache contract.')
        movie_contract=scope.get('movie_candidate_contract') if isinstance(scope,dict) else None
        if movie_contract is not None:
            from .cinema_movie_inputs import MOVIE_SEARCH_CONTRACT, movie_candidates
            if movie_contract != MOVIE_SEARCH_CONTRACT:
                raise ValueError('Unrecognized private movie-cache contract.')
        identity_search=(contract == CONTRACT and scope.get('phase') == 'identity-search'
                         and sample['request']['path'] == '/search')
        params=sample['request']['params']
        if identity_search and movie_contract is not None and params.get('types') == 'urn:entity:movie':
            if (set(params) != {'query','take','types'} or type(params['take']) is not int or params['take'] != 5
                    or not isinstance(params['query'],str) or not 1 <= len(params['query']) <= 200):
                raise ValueError('Movie cache requires the pinned bounded film search.')
            movie_candidates(sample['response'])
        elif identity_search:
            if (set(params) != {'query','take','types'} or type(params['take']) is not int or params['take'] != 5
                    or params['types'] != 'urn:entity:artist,urn:entity:person'
                    or not isinstance(params['query'],str) or not params['query'].strip()):
                raise ValueError('Identity cache requires the pinned bounded musical search.')
            # The pinned v3 search contract validates every raw row and rejects
            # conflicting selectable profiles. Keep its raw response unchanged.
            # This discriminator is part of the full cache key, on read and write.
            music_candidates(sample['response'])
        else:
            parse_entities(sample['response'], insights=sample['request']['path'] == '/v2/insights',
                           synthetic=sample['source'] == 'test-double-only')

    def put(self, request, scope, sample, *, received_at, secrets=()):
        key = self.key(request, scope)
        if sample['request'] != request or redact(sample, secrets) != sample:
            raise ValueError('Private Qloo cache refuses an unbound or unredacted sample.')
        self._validate(sample, scope)
        value = {'schema_version': 1, 'cache_key_sha256': key, 'sample': copy.deepcopy(sample),
                 'original_sample_sha256': fingerprint(sample), 'original_received_at': received_at}
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        with self._connection() as db:
            # Retain the first accepted exact observation; no automatic pruning
            # or replacement of provenance, expiry or historical raw samples.
            db.execute('INSERT OR IGNORE INTO samples VALUES(?,?,?)', (key, encoded, fingerprint(value)))
        return self.get(request, scope)
