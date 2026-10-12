"""Read-only, redacted diagnosis of an already-recorded identity-search stop.

This module is an operator tool, not part of the capture protocol. It never
authenticates, changes a receipt, selects an artist, or starts inference.
"""
from pathlib import Path

from .cinema_identity_capture import music_candidates
from .cinema_identity_verify import _candidates, _events, verify_identity_search
from .cinema_discovery_file_verify import verify_discovery_search
from .cinema_discovery_v3_verify import verify_discovery_search as verify_search_v3, _candidates as candidates_v3
from .search_music_candidates import music_candidates as search_candidates_v3
from .errors import SchemaError
from .individual_verify import checked_path, inventory, need, read


ERROR_CODES = {
    'Qloo returned an invalid or error response envelope.': 'RESPONSE_ENVELOPE_REJECTED',
    'Qloo did not return success=true. Check the recorded response.': 'RESPONSE_SUCCESS_REJECTED',
    'Expected a lookup results array.': 'RESULTS_ARRAY_MISSING',
    'Expected an entity array; documentation examples are not live evidence.': 'RESULTS_ARRAY_MISSING',
    'An entity response entry is not an object.': 'ENTITY_ROW_NOT_OBJECT',
    'Missing or invalid entity_id.': 'ENTITY_ID_MISSING',
    'Live Qloo entity IDs must be UUIDs; fixture IDs cannot be sent live.': 'ENTITY_ID_NOT_UUID',
    'Duplicate entity IDs in one ranking.': 'DUPLICATE_ENTITY_IDS',
    'An entity has no usable name.': 'ENTITY_NAME_MISSING',
    'Entity types must be strings in an array.': 'ENTITY_TYPES_MALFORMED',
    'Entity category metadata is missing; context cannot be verified.': 'ENTITY_TYPE_MISSING',
    'Entity query metadata is not an object.': 'ENTITY_QUERY_MALFORMED',
    'An affinity value is not finite numeric data.': 'ENTITY_AFFINITY_MALFORMED',
    'Affinity is outside the documented 0–1 range.': 'ENTITY_AFFINITY_OUT_OF_RANGE',
    'Entity properties must be an object.': 'ENTITY_PROPERTIES_MALFORMED',
    'Identity search exceeded its declared result bound.': 'SEARCH_RESULT_BOUND_EXCEEDED',
    'No verified musical identity candidates were returned; no substitution.': 'NO_VERIFIED_MUSIC_CANDIDATES',
    'A bounded explicit name is required.': 'CANDIDATE_NAME_BOUND_REJECTED',
    'Use a canonical printable name.': 'CANDIDATE_NAME_CANONICALITY_REJECTED',
    'Invalid profile identity.': 'CANDIDATE_PROFILE_REJECTED',
    'Canonical explicit profile name required.': 'CANDIDATE_NAME_CANONICALITY_REJECTED',
    'Conflicting musical profiles share one search entity ID.': 'CONFLICTING_MUSICAL_PROFILES',
}
KNOWN_ERROR_CLASSES = {'SchemaError', 'TransportError', 'OSError', 'PermissionError', 'FileNotFoundError'}


def classify_candidates(body, *, protocol='cinema-confirmed-identity-v1'):
    """Return fixed codes and counts, never exception text or provider fields."""
    rows = body.get('results') if isinstance(body, dict) else None
    count = len(rows) if isinstance(rows, list) else None
    capture_parser, audit_parser = ((search_candidates_v3, candidates_v3)
        if protocol == 'cinema-confirmed-discovery-v3' else (music_candidates, _candidates))
    try:
        candidates = capture_parser(body)
    except SchemaError as exc:
        return {'code': ERROR_CODES.get(str(exc), 'CANDIDATE_CONTRACT_REJECTED'),
                'returned_rows': count, 'eligible_candidates': None}
    try:
        audited = audit_parser(body)
    except SchemaError:
        return {'code': 'CAPTURE_VERIFIER_DISAGREEMENT', 'returned_rows': count,
                'eligible_candidates': None}
    need(candidates == audited, 'Identity diagnostic: candidate projections disagree.')
    return {'code': 'CANDIDATES_ACCEPTED', 'returned_rows': count,
            'eligible_candidates': len(candidates)}


def diagnose_identity_search(directory):
    """Require complete file verification before diagnosing recorded samples.

    Only the original search phase is supported. A confirmed or modified case
    must use its existing full verifier rather than be treated as a new search.
    """
    directory = checked_path(Path(directory))
    before = inventory(directory)
    plan = read(directory/'individual-plan.json')
    protocol = plan.get('protocol_version')
    verifiers = {'cinema-confirmed-identity-v1': verify_identity_search,
                 'cinema-confirmed-discovery-v2': verify_discovery_search,
                 'cinema-confirmed-discovery-v3': verify_search_v3}
    need(protocol in verifiers, 'Identity diagnostic: unsupported original search protocol.')
    need(not (directory/'individual-report.json').exists(), 'Identity diagnostic: capture already continued.')
    receipt = verifiers[protocol](directory)
    events = _events(directory/'identity-ledger.jsonl', receipt['source'])
    observations = []
    for index, label in ((1, 'A'), (3, 'B')):
        if len(events) <= index or events[index]['kind'] not in ('tool_call', 'transport_failure'):
            continue
        event = events[index]
        if event['kind'] == 'transport_failure':
            observation = {'code': 'TRANSPORT_FAILURE', 'returned_rows': None,
                           'eligible_candidates': None, 'http_status': None}
        else:
            # The verifier already bound this flat artifact to the exact single
            # request, event, response hash and original source revision.
            sample = read(directory/event['data']['sample'])
            observation = (classify_candidates(sample['response'], protocol=protocol) if sample['status'] == 200
                           else {'code': 'PROVIDER_HTTP_FAILURE', 'returned_rows': None,
                                 'eligible_candidates': None})
            observation['http_status'] = sample['status']
        recorded = len(events) > index+1 and events[index+1]['kind'] == 'identity_candidates_recorded'
        observations.append({'profile': label, 'candidate_event_committed': recorded, **observation})
    need(inventory(directory) == before, 'Identity diagnostic: artifacts changed during diagnosis.')
    rejected = [r for r in observations if r['code'] != 'CANDIDATES_ACCEPTED']
    complete = receipt['status'] == 'AWAITING_IDENTITY_CONFIRMATION'
    # If the sample is valid but no candidate event was committed, avoid
    # inventing a schema cause: storage or another boundary may have stopped.
    outcome = ('SEARCH_COMPLETE' if complete else
               'RECORDED_RESPONSE_REJECTION_REPRODUCED' if rejected else
               'STOP_CAUSE_NOT_REPRODUCED')
    error = receipt.get('error_class')
    return {'schema_version': 1, 'run_id': receipt['run_id'], 'protocol': protocol,
            'verification_status': receipt['verification_status'], 'status': receipt['status'],
            'diagnosis': outcome, 'recorded_error_class': error if error in KNOWN_ERROR_CLASSES else
            (None if error is None else 'OTHER_REDACTED_ERROR'),
            'observations': observations, 'original_gates': {
                'cultural_gate': receipt['cultural_gate'], 'release_gate': receipt['release_gate'],
                'preference_gate': receipt['preference_gate']},
            'new_provider_calls': 0, 'new_model_calls': 0, 'capture_artifacts_unchanged': True,
            'boundary': 'Recorded response diagnosis only; no original exception text, provider body, identity, artist query, credentials or paths exported. No approval or retry.'}
