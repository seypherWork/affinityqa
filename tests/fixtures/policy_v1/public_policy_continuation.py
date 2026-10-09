"""Explicit, append-only continuation of source seals; never reset admissions.

The owner runs the driver against stopped storage after reviewing a proposal.
Startup never creates this marker or edits existing policy/session/job files.
"""
from pathlib import Path

from .evidence import fingerprint
from .individual_jobs import need, read, write
from .individual_capture import execution_lease, safe_directory_path, sha

MARKER = 'public-policy-continuation.json'


def validate_continuation(previous, current, marker):
    source_fields = {'controller_sha256', 'manager_sha256', 'policy_sha256'}
    need(set(previous) == set(current), 'Public policy fields differ.')
    need(previous.get('policy_sha256') == fingerprint({k:v for k,v in previous.items() if k != 'policy_sha256'}),
         'Previous public policy seal differs.')
    need({k:v for k,v in previous.items() if k not in source_fields} ==
         {k:v for k,v in current.items() if k not in source_fields},
         'Continuation cannot change template, origin, pacing or budgets.')
    expected = {'schema_version':1, 'previous_binding_sha256':fingerprint(previous),
                'current_controller_sha256':current['controller_sha256'],
                'current_manager_sha256':current['manager_sha256'],
                'admissions_reset':False}
    need(fingerprint(marker) == fingerprint(expected), 'Reviewed source continuation does not match this storage or code.')
    return expected


def propose(root, *, _held_lease=False):
    root = safe_directory_path(Path(root))
    need(root.is_dir() and not (root/MARKER).exists(), 'Existing stopped storage without a continuation marker is required.')
    previous = read(root/'public-policy.json')
    source = Path(__file__).resolve().parent
    current = {**previous, 'controller_sha256':sha(source/'public_cases.py'),
               'manager_sha256':sha(source/'individual_jobs.py')}
    current['policy_sha256'] = fingerprint({k:v for k,v in current.items() if k != 'policy_sha256'})
    marker = {'schema_version':1, 'previous_binding_sha256':fingerprint(previous),
              'current_controller_sha256':current['controller_sha256'],
              'current_manager_sha256':current['manager_sha256'], 'admissions_reset':False}
    validate_continuation(previous, current, marker)
    files = {}
    for path in sorted(root.rglob('*')):
        safe_directory_path(path)
        if path.is_file():
            name = path.relative_to(root).as_posix()
            if _held_lease and name == 'jobs/.affinityqa-individual.lock':
                # Windows denies reading locked bytes. The acquired lease already
                # validated this exact retained marker before yielding.
                import hashlib
                from .individual_capture import LOCK_MARKER
                files[name] = hashlib.sha256(LOCK_MARKER).hexdigest()
            else:
                try:
                    files[name] = sha(path)
                except OSError:
                    need(False, 'Stop the public service before inspecting its storage.')
    need(set(files).issuperset({'public-policy.json','jobs/.affinityqa-individual.lock'}), 'Unrecognized public storage.')
    result = {'schema_version':1, 'storage':str(root), 'marker':marker, 'preserved_files_sha256':files,
              'scope':'One new source-continuation marker; all policies, sessions, ownership, jobs and admissions preserved.'}
    result['proposal_sha256'] = fingerprint(result)
    return result


def execute(root, expected_proposal_sha256):
    root = safe_directory_path(Path(root))
    jobs = safe_directory_path(root/'jobs')
    lock = safe_directory_path(jobs/'.affinityqa-individual.lock')
    need(root.is_dir() and jobs.is_dir() and lock.is_file(),
         'Existing reviewed storage and its retained lock are required before any lease.')
    with execution_lease(jobs):
        proposal = propose(root, _held_lease=True)
        need(proposal['proposal_sha256'] == expected_proposal_sha256, 'Reviewed storage inventory or source changed.')
        write(root/MARKER, proposal['marker'])
        need(all(name == 'jobs/.affinityqa-individual.lock' or sha(root/name) == digest for name,digest in proposal['preserved_files_sha256'].items()),
             'Original public records changed; stop and inspect.')
        need(read(root/MARKER) == proposal['marker'], 'Continuation marker was not verified.')
        return proposal
