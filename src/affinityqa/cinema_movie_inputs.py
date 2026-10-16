"""Bounded movie queries and confirmed provider identities; no transport or inference."""
from __future__ import annotations
import copy
import unicodedata
from .errors import SchemaError
from .models import canonical_id, normalized_name, parse_entities, validate_response_envelope
from .causal_agent import validate_catalog
from .cinema_discoveries import validate_preferences as legacy_preferences
from .individual_capture import canonical_name

MOVIE_SEARCH_CONTRACT = 'qloo-confirmed-movie-title-year-v1'

def need(condition, message):
    if not condition:
        raise SchemaError('Confirmed movie inputs: ' + message)

def validate_movie_queries(value):
    need(isinstance(value, dict) and set(value) == {'A', 'B'}, 'Declare movie query slots for A and B.')
    result = {}
    for label in ('A', 'B'):
        rows = value[label]
        need(isinstance(rows, list) and len(rows) <= 2, 'At most two movie queries per case.')
        result[label] = []
        for text in rows:
            need(isinstance(text, str) and not any(unicodedata.category(c).startswith('C') for c in text), 'Printable movie query required.')
            text = ' '.join(unicodedata.normalize('NFKC', text).split())
            need(1 <= len(text) <= 200, 'Movie query must contain 1..200 characters without truncation.')
            result[label].append(text)
    need(1 <= sum(map(len, result.values())) <= 2, 'Request6 requires one or two movie queries in total.')
    return result

def movie_identity(value):
    need(isinstance(value, dict) and set(value) == {'entity_id', 'name', 'release_year', 'type'}, 'Closed confirmed movie metadata required.')
    need(value['entity_id'] == canonical_id(value['entity_id']), 'Canonical movie UUID required.')
    canonical_name(value['name'])
    need(value['type'] == 'urn:entity:movie' and type(value['release_year']) is int and 1888 <= value['release_year'] <= 2100, 'Actual movie category and integer release year required.')
    return copy.deepcopy(value)

def movie_candidates(body):
    validate_response_envelope(body, insights=False)
    need(len(body['results']) <= 5, 'Movie search exceeded five raw rows.')
    result, seen = [], {}
    for raw in body['results']:
        row = parse_entities({**body, 'results': [raw]}, insights=False)[0]
        if 'urn:entity:movie' not in row.types:
            continue
        year = row.metadata.get('release_year')
        if type(year) is not int or not 1888 <= year <= 2100:
            continue
        item = movie_identity({'entity_id': row.entity_id, 'name': row.name, 'release_year': year, 'type': 'urn:entity:movie'})
        previous = seen.get(item['entity_id'])
        need(previous is None or previous == item, 'Conflicting movie metadata share a UUID.')
        if previous is None:
            seen[item['entity_id']] = item
            result.append(item)
    need(result, 'No selectable movie has a verified title and release year; no substitution.')
    return result

def selection_movies(receipt, selected_movie_entity_ids):
    need(isinstance(receipt, dict) and receipt.get('verification_status') == 'VERIFIED_IDENTITY_SEARCH' and receipt.get('status') == 'AWAITING_IDENTITY_CONFIRMATION', 'Only a verified successful search may be confirmed.')
    need(isinstance(selected_movie_entity_ids, dict) and set(selected_movie_entity_ids) == {'A', 'B'}, 'Explicit movie choices for A and B required.')
    candidates = receipt.get('movie_candidates')
    need(isinstance(candidates, dict) and set(candidates) == {'A', 'B'}, 'Missing original movie slots.')
    selected = {}
    for label in ('A', 'B'):
        slots, ids = candidates[label], selected_movie_entity_ids[label]
        need(isinstance(slots, list) and isinstance(ids, list) and len(slots) == len(ids) <= 2, 'Select exactly one movie per original query slot.')
        need(all(isinstance(v, str) for v in ids) and len(set(ids)) == len(ids), 'Duplicate movie selection in one profile.')
        selected[label] = []
        for members, entity_id in zip(slots, ids):
            need(isinstance(members, list) and 1 <= len(members) <= 5, 'Bounded original candidate slot required.')
            checked = [movie_identity(v) for v in members]
            need(len({v['entity_id'] for v in checked}) == len(checked), 'Duplicate candidate identity.')
            matches = [v for v in checked if v['entity_id'] == entity_id]
            need(len(matches) == 1, 'Movie choice is outside its recorded slot.')
            selected[label].append(copy.deepcopy(matches[0]))
    need(1 <= sum(map(len, selected.values())) <= 2, 'One or two movie choices in total required.')
    return selected

def validate_preferences(value, catalog):
    need(isinstance(value, dict) and set(value) == {'schema_version', 'favorite_entity_ids', 'excluded_entity_ids', 'external_favorite_movies'} and type(value['schema_version']) is int and value['schema_version'] == 2, 'Closed effective preferences2 required.')
    base = legacy_preferences({k: copy.deepcopy(value[k]) for k in ('favorite_entity_ids', 'excluded_entity_ids')} | {'schema_version': 1}, catalog)
    rows = value['external_favorite_movies']
    need(isinstance(rows, list) and len(rows) <= 2, 'At most two external favorites.')
    external = [movie_identity(v) for v in rows]
    ids = validate_catalog(catalog)
    need(all(v['entity_id'] not in ids for v in external) and len({v['entity_id'] for v in external}) == len(external), 'External seed identities must be unique and outside the catalog.')
    need(len(base['favorite_entity_ids']) + len(external) <= 5, 'At most five combined known favorite inputs per profile.')
    metadata = {v['entity_id']: v for v in catalog}
    all_movies = [metadata[v] for v in base['favorite_entity_ids']] + external
    semantic = [(normalized_name(v['name']), v['release_year']) for v in all_movies]
    need(len(set(semantic)) == len(semantic), 'A favorite movie is repeated under the same title and year.')
    # An external ID naming a catalog movie would leak a known seed into delivery.
    catalog_keys = {(normalized_name(v['name']), v['release_year']) for v in catalog}
    need(all((normalized_name(v['name']), v['release_year']) not in catalog_keys for v in external), 'Alternate ID overlaps a reference catalog movie; stop for explicit identity review.')
    return {**base, 'schema_version': 2, 'external_favorite_movies': sorted(external, key=lambda v: v['entity_id'])}

def compile_preferences(catalog, original, movies):
    base = legacy_preferences(original, catalog)
    need(isinstance(movies, list) and len(movies) <= 2, 'Bounded selected movie inputs required.')
    selected = [movie_identity(v) for v in movies]
    metadata = {v['entity_id']: v for v in catalog}
    favorites = list(base['favorite_entity_ids'])
    external = []
    seen = set(favorites)
    for movie in selected:
        entity_id = movie['entity_id']
        need(entity_id not in seen, 'Selected movie duplicates an existing favorite or query slot.')
        seen.add(entity_id)
        need(entity_id not in base['excluded_entity_ids'], 'Selected favorite conflicts with a hard exclusion.')
        if entity_id in metadata:
            item = metadata[entity_id]
            need(movie['name'] == item['name'] and movie['release_year'] == item['release_year'], 'Selected catalog movie metadata conflicts with frozen catalog.')
            favorites.append(entity_id)
        else:
            external.append(movie)
    return validate_preferences({'schema_version': 2, 'favorite_entity_ids': favorites, 'excluded_entity_ids': base['excluded_entity_ids'], 'external_favorite_movies': external}, catalog)
