"""Search-only identity projection; movie rankings retain strict unique IDs.

Every raw row is validated. Nonmusical rows do not become choices, and repeated
musical UUIDs collapse only when their complete selectable profiles agree.
The provider response itself is never rewritten.
"""
from .cinema_identity_capture import music_candidates as legacy_candidates
from .errors import SchemaError
from .individual_capture import need
from .models import validate_response_envelope

CONTRACT = 'qloo-search-musical-profile-uniqueness-v1'
NO_MUSIC = 'No verified musical identity candidates were returned; no substitution.'


def music_candidates(body):
    validate_response_envelope(body, insights=False)
    need(len(body['results']) <= 5, 'Identity search exceeded its declared result bound.')
    candidates, seen = [], {}
    for row in body['results']:
        try:
            members = legacy_candidates({**body, 'results': [row]})
        except SchemaError as exc:
            if str(exc) == NO_MUSIC:
                continue
            raise
        profile = members[0]
        previous = seen.get(profile['entity_id'])
        need(previous is None or previous == profile,
             'Conflicting musical profiles share one search entity ID.')
        if previous is None:
            seen[profile['entity_id']] = profile
            candidates.append(profile)
    need(candidates, NO_MUSIC)
    return candidates
