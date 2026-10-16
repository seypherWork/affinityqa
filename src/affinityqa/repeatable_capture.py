"""Versioned queue admission: accepted protocol evidence is reconstructed, never resent."""
from contextlib import nullcontext
from pathlib import Path
import copy
import builtins

from .evidence import fingerprint
from .individual_jobs import need, read
from .individual_verify import inventory


def protocol(request):
    version = request.get('schema_version')
    if version == 2:
        from .individual_remote_capture import prepare_plan, execute_capture
        from .individual_remote_verify import verify_individual_remote
        return prepare_plan, execute_capture, verify_individual_remote, None, None
    if version == 3:
        from .cinema_capture import prepare_plan, execute_capture
        from .cinema_verify import verify_cinema
        return prepare_plan, execute_capture, verify_cinema, None, None
    if version == 4:
        from .cinema_identity_capture import prepare_plan, search_identities, capture_confirmed
        from .cinema_identity_verify import verify_identity_search, verify_confirmed_cinema
        return prepare_plan, capture_confirmed, verify_confirmed_cinema, search_identities, verify_identity_search
    if version == 5:
        from .cinema_discovery_v3_capture import prepare_plan, search_identities, capture_confirmed
        from .cinema_discovery_v3_verify import verify_discovery_search, verify_confirmed_discoveries
        return prepare_plan, capture_confirmed, verify_confirmed_discoveries, search_identities, verify_discovery_search
    if version == 6:
        from .cinema_discovery_v4_capture import prepare_plan, search_identities, capture_confirmed
        from .cinema_discovery_v4_verify import verify_discovery_search, verify_confirmed_discoveries
        return prepare_plan, capture_confirmed, verify_confirmed_discoveries, search_identities, verify_discovery_search
    need(False, 'Unsupported repeatable request version.')


def request_for(template, artists, preferences=None, confirm_identities=False, discover_new_movies=False, movie_queries=None):
    need(type(confirm_identities) is bool and type(discover_new_movies) is bool, 'Explicit mode booleans required.')
    need(not discover_new_movies or confirm_identities, 'Discoveries require explicit identity confirmation.')
    need(not confirm_identities or preferences is not None, 'Identity confirmation requires cinema preferences.')
    request = {**copy.deepcopy(template), 'artists': copy.deepcopy(artists)}
    version = 2
    if preferences is not None:
        version = 5 if discover_new_movies else 4 if confirm_identities else 3
        request['preferences'] = copy.deepcopy(preferences)
    if movie_queries is not None:
        need(discover_new_movies and confirm_identities and preferences is not None,
             'Movie searches require confirmed discovery preferences.')
        version = 6
        request['movie_queries'] = copy.deepcopy(movie_queries)
    request['schema_version'] = version
    validators = {}
    from .individual_remote_capture import validate_request
    from .cinema_capture import validate_request as cinema
    from .cinema_identity_capture import validate_request as identity
    from .cinema_discovery_capture import validate_request as discovery
    validators.update({2:validate_request, 3:cinema, 4:identity, 5:discovery})
    if version == 6:
        from .cinema_discovery_v4_capture import validate_request as movie_inputs
        validators[6] = movie_inputs
    return validators[version](request)


def prepare_protocol(request, output, interval):
    return protocol(request)[0](request, output, minimum_model_interval_seconds=interval)


def check_storage_report(report):
    failure_type=getattr(builtins,report.get('error_class') or '',None)
    if isinstance(failure_type,type) and issubclass(failure_type,OSError):
        # Legacy runners retain their stop report before returning. Detect a
        # swallowed local I/O failure BEFORE invoking a verifier that might
        # otherwise obscure it with a missing-artifact SchemaError.
        raise OSError('Local capture storage failed; owner inspection required.')


def execute_stage(request, output, settings, remote_key, *, stage, interval, adapters, runtime,
                  confirmation=None, reviewed_protocol_plan=None):
    """A new immutable capture directory per reconstruction; old captures remain intact.

    The runtime authorizes an accepted exact operation replay and refuses unknown or
    failed sends. Legacy packets remain observations of their original dispatch.
    A versioned outer receipt declares present network/reconstruction counters.
    """
    planner, capture, verifier, search, search_verify = protocol(request)
    plan = planner(request, output, minimum_model_interval_seconds=interval)
    if reviewed_protocol_plan is not None:
        # Only the explicitly versioned output relocation differs. Execution
        # contracts and sources may not drift while a paused case is resumed.
        semantic = lambda value: {k:v for k,v in value.items() if k not in ('plan_sha256','output_directory')}
        need(fingerprint(semantic(plan)) == fingerprint(semantic(reviewed_protocol_plan)),
             'Reviewed protocol source or operator changed before the next dispatch.')
    if search is not None:
        # Search is rebuilt solely from the accepted exact search calls once a
        # user has selected identities; permission is bound to the original receipt.
        with runtime.activate(namespace='identity-search') if runtime else nullcontext():
            report, directory = search(request, output, plan['plan_sha256'], settings,
                minimum_model_interval_seconds=interval, _test_adapters=adapters)
        check_storage_report(report)
        receipt = search_verify(directory)
        if stage == 'identity-search':
            return directory, receipt
        need(confirmation is not None, 'Explicit saved identity confirmation required.')
        original = confirmation['identity_receipt']
        need(receipt['identity_candidates'] == original['identity_candidates']
             and receipt['identity_queries'] == original['identity_queries'],
             'Reconstructed identities differ from the explicitly selected observations.')
        if request['schema_version'] == 6:
            need(receipt['movie_candidates'] == original['movie_candidates']
                 and receipt['movie_queries'] == original['movie_queries'],
                 'Reconstructed movie choices differ from the explicitly confirmed observations.')
        with runtime.activate(namespace='capture') if runtime else nullcontext():
            report, directory = capture(directory, confirmation['selected_entity_ids'], receipt,
                settings, remote_key, _test_adapters=adapters,
                **({'selected_movie_entity_ids':confirmation['selected_movie_entity_ids']}
                   if request['schema_version'] == 6 else {}))
        check_storage_report(report)
        return directory, verifier(directory)
    with runtime.activate(namespace='capture') if runtime else nullcontext():
        report, directory = capture(request, output, plan['plan_sha256'], settings, remote_key,
            minimum_model_interval_seconds=interval, _test_adapters=adapters)
    check_storage_report(report)
    return directory, verifier(directory)


def outer_receipt(receipt, *, plan_hash, provider_stats, attempts, confirmation=None):
    result = copy.deepcopy(receipt)
    result['repeatable_contract'] = {
        'schema_version': 1, 'admission_mode': 'repeatable-v1',
        'reviewed_plan_sha256': plan_hash, 'capture_plan_sha256': receipt['plan_sha256'],
        'provider_stats': copy.deepcopy(provider_stats),
        'capture_attempts': attempts,
        'accepted_operation_reconstruction_is_new_dispatch': False,
        'legacy_packets_are_original_dispatch_observations': True,
        'automatic_failed_or_unknown_send_retry': False,
        'verified_human_participants': 0,
        'cultural_quality': 'NOT_VALIDATED',
    }
    if confirmation:
        result['repeatable_contract']['original_identity_receipt_sha256'] = confirmation['identity_receipt_sha256']
        result['repeatable_contract']['explicit_selection_sha256'] = fingerprint(confirmation['selected_entity_ids'])
        if 'selected_movie_entity_ids' in confirmation:
            result['repeatable_contract']['explicit_movie_selection_sha256'] = fingerprint(confirmation['selected_movie_entity_ids'])
    return result
