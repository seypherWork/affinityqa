"""Conservative source-only distribution. Inventory by default; never publish."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TESTS=('test_causal_agent.py','test_causal_runner.py','test_causal_evaluator.py',
       'test_keyword_calibrator.py','test_keyword_words.py','test_pairwise_rank_calibrator.py',
       'test_broad_movie_context.py','test_taste_tags.py','test_public_source_package.py',
       'test_public_demo.py','test_public_demo_verifier.py','test_groq_agent.py',
       'test_individual_capture.py','test_individual_verify.py','test_individual_jobs.py',
       'test_individual_remote.py','test_individual_remote_jobs.py','test_remote_pacing.py','test_public_cases.py',
       'test_public_case_api.py','test_public_case_config.py','test_capture_paths.py',
       'test_cinema_preferences.py','test_cinema_capture.py','test_cinema_panel.py','test_public_policy_continuation.py','test_public_policy_chain.py',
       'test_cinema_identity_capture.py','test_cinema_identity_jobs.py',
       'test_discovery_context.py','test_discovery_delivery.py',
       'test_discovery_agent.py','test_discovery_session.py','test_discovery_capture.py',
       'test_discovery_jobs.py','test_discovery_pacing.py','test_discovery_diagnostics.py',
       'test_discovery_slots.py','test_discovery_failure_evidence.py')
DRIVERS=('affinityqa.py','run_causal_repair.py','continue_causal_validation.py',
         'resume_causal_identity.py','verify_causal_repair.py','build_public_source.py',
         'serve_public_demo.py','verify_public_demo.py','capture_individual_pair.py',
         'verify_individual_capture.py','capture_individual_remote.py','verify_individual_remote.py','continue_public_policy.py')
EXACT=('pyproject.toml','requirements-backend.lock.txt','fixtures/synthetic.json',
       'tests/fixtures/policy_v1/public_cases.py','tests/fixtures/policy_v1/public_policy_continuation.py',
       'src/affinityqa/remote_pacing.py','docs/CINEMA-PREFERENCES.md',
       'src/affinityqa/public_cases.py','src/affinityqa/public_case_api.py',
       'src/affinityqa/public_case_config.py','docs/PUBLIC-NEW-CASES.md',
       'evals/qloo.json','evals/film-suite.json','docs/PUBLIC-CODE-QUICKSTART.md',
       '.github/workflows/public-source-tests.yml','web/package.json','web/pnpm-lock.yaml',
       'web/next.config.mjs','web/tsconfig.json','web/next-env.d.ts',
       'docs/INDIVIDUAL-CAPTURE.md','docs/INDIVIDUAL-VERIFICATION.md',
       'docs/INDIVIDUAL-PANEL.md','docs/INDIVIDUAL-REMOTE.md','docs/REMOTE-MODEL-CANDIDATE.md',
       'docs/images/hero.svg','docs/images/architecture.svg','docs/ASSET-PROVENANCE.md',
       'docs/DEMO-GUIDE.md','docs/PUBLIC-DEMO-DEPLOYMENT.md',
       'docs/JUDGE-ACCEPTANCE.md','docs/SUBMISSION-DRAFT.md',
       'render.yaml','deployment/README.md','deployment/build_render.py',
       'deployment/start_render.py','deployment/provision_only.py')
BLOCKED={'.git','.env','.private','runs','evidence','node_modules','.next','out',
         '__pycache__','.test-runs','.venv','venv','coverage'}
README='''# AffinityQA

**Follow the profile. Prove the recovery.**

AffinityQA helps an engineer inspect the integration faults that make a
personalized movie agent use the wrong taste profile. It follows an explicit
musical interest through Qloo cultural context, agent routing and cache state,
then checks whether one supported repair restores the healthy execution.

The controlled protocol covers a cache key missing profile identity, a stale
transmitted profile, and a Qloo context response bound to the wrong profile.
The interface exposes Detect, Diagnose, Repair and Verify, with named profile
provenance and separate causal, cultural-quality and release gates.

## Build and review

See [source setup](docs/PUBLIC-CODE-QUICKSTART.md) for dependency installation,
synthetic engineering tests and the frontend build. See [the reviewer guide](docs/DEMO-GUIDE.md)
for the recorded-capture demonstration and [deployment boundaries](docs/PUBLIC-DEMO-DEPLOYMENT.md)
for the restricted application. The public hosted address is not supplied by
this archive and must be approved and verified separately.

This is the source-only package. It contains synthetic tests, not recorded
Qloo responses or captured model decisions. No credentials, model weights,
provider snapshots or compiled web export are included. A source preview
without separately authorized evidence reports UNAVAILABLE; it does not
fabricate a verified demonstration. A replay with matching authorized evidence
executes the pipeline using recorded decisions and makes zero new provider calls.

Code for historical capture and verification is included for audit, but needs
separately authorized inputs. Running the source tests does not reproduce the
private real-service experiment or establish individual movie preferences.
PUBLIC-SOURCE-MANIFEST.json records every included file hash.
{licensing}
'''
LICENSE_PROPOSAL='''# License proposal — NOT GRANTED

Proposal for the project owner: MIT for original AffinityQA code, after confirming
the copyright holder and year. This document is not an MIT license and grants no
permission. No LICENSE file is activated by the builder.

Provider responses, external datasets, trademarks, models and dependency assets
remain outside any proposed grant. Confirm their own terms separately. No
publication or submission is authorized by building or testing this archive.
'''
IGNORE='''runs/
evidence/
.env
.env.*
.private/
private/
*.zip
.venv/
.test-runs/
__pycache__/
*.py[cod]
*.egg-info/
node_modules/
.next/
web/out/
web/*.tsbuildinfo
'''


def digest(data):return hashlib.sha256(data).hexdigest()


# Complete owner-approved MIT text, normalized only for whitespace.
# Preserve original LICENSE bytes; this builder never creates a license grant.
APPROVED_MIT_SHA256='abce7fb657b48e69249cad3acc047aba05c9fa647e3884827d69b40d8689c14a'
LICENSING_NOTES='''# Licensing scope

Original AffinityQA code is MIT licensed, Copyright (c) 2026 Seypher; see LICENSE.
Qloo responses, recorded model decisions, models, external datasets, trademarks
and third-party dependency assets retain their own rights and terms.
See docs/THIRD-PARTY-LICENSES.txt and docs/LICENSING.md when included.
Local packaging does not authorize the agent to publish or submit this project.
'''


def licensing(blobs):
    if 'LICENSE' not in blobs:return False
    normalized=' '.join(blobs['LICENSE'].decode('utf8').split()).encode('utf8')
    if digest(normalized)!=APPROVED_MIT_SHA256:
        raise ValueError('LICENSE does not match the complete owner-approved MIT text.')
    return True


def read_safe(relative):
    relative=Path(relative)
    if relative.is_absolute() or '..' in relative.parts or any(p in BLOCKED or p.startswith('.env') for p in relative.parts):raise ValueError('Forbidden source path: '+str(relative))
    path=ROOT/relative
    if not path.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Source escapes package root.')
    for node in (path,*path.parents):
        if node==ROOT.parent:break
        if node.is_symlink() or (hasattr(node,'is_junction') and node.is_junction()):raise ValueError('Linked source input is forbidden.')
    if not path.is_file():raise ValueError('Missing allowlisted source: '+str(relative))
    data=path.read_bytes()
    if any((b'-----BEGIN '+kind+b'-----') in data for kind in (b'PRIVATE KEY',b'RSA PRIVATE KEY')):raise ValueError('Private key marker in source: '+str(relative))
    # High-specificity guard, not a certification that every possible secret is absent.
    if re.search(rb'\b(?:sk-[A-Za-z0-9_-]{24,}|gsk_[A-Za-z0-9_-]{32,})\b',data):raise ValueError('Credential-shaped token in source: '+str(relative))
    return data


def inventory():
    names=set(EXACT)|{'tests/'+n for n in TESTS}|{'scripts/'+n for n in DRIVERS}
    for directory,suffixes in (('src',{'.py'}),('web/app',{'.tsx','.ts','.css','.svg'}),('web/components',{'.tsx','.ts','.css'}),('web/lib',{'.ts','.tsx'})):
        base=ROOT/directory
        if not base.is_dir():raise ValueError('Missing source directory: '+directory)
        for path in sorted(base.rglob('*')):
            if any(p in BLOCKED for p in path.relative_to(ROOT).parts):continue
            if path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction()):raise ValueError('Linked source directory or file is forbidden.')
            if path.is_file() and path.suffix in suffixes:names.add(path.relative_to(ROOT).as_posix())
    # Retain the reviewed repository README when present. Historical manifests
    # are not input files: this build generates its own current hash inventory.
    for optional in ('README.md','LICENSE','docs/THIRD-PARTY-LICENSES.txt','docs/LICENSING.md'):
        if (ROOT/optional).exists():names.add(optional)
    return {name:digest(read_safe(name)) for name in sorted(names)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--output',type=Path);args=parser.parse_args()
    files=inventory();approved_mit=licensing({n:read_safe(n) for n in files if n=='LICENSE'})
    summary={'mode':'source-only','source_file_count':len(files),'source_bytes':sum(len(read_safe(n)) for n in files),'provider_captures_included':False,'license_granted':approved_mit,'mit_original_code':approved_mit}
    if not args.execute:print(json.dumps(summary,indent=2));return 0
    if args.output is None or args.output.suffix.lower()!='.zip':raise ValueError('An explicit new ZIP destination is required.')
    output=args.output.resolve()
    if output.exists():raise ValueError('Output already exists; refusing to overwrite.')
    if not output.parent.is_dir():raise ValueError('Destination parent must exist.')
    blobs={n:read_safe(n) for n in files}
    if any(digest(blobs[n])!=h for n,h in files.items()):raise ValueError('Source changed after inventory; no archive created.')
    if licensing(blobs)!=approved_mit:raise ValueError('License state changed after inventory.')
    licensing_text=('Original AffinityQA code is MIT licensed; see LICENSE and LICENSING-NOTES.md. '
                    'Third-party data, models and dependencies retain their own terms. '
                    'Local packaging does not authorize the agent to publish or submit.' if approved_mit else
                    'LICENSE-PROPOSAL.md is only a proposal. No license is granted; publication remains a separate owner decision.')
    generated={'.gitignore':IGNORE.encode()}
    if 'README.md' not in blobs:
        generated['README.md']=README.format(licensing=licensing_text).encode()
    generated['LICENSING-NOTES.md' if approved_mit else 'LICENSE-PROPOSAL.md']=(LICENSING_NOTES if approved_mit else LICENSE_PROPOSAL).encode()
    if set(generated)&set(blobs):raise ValueError('Generated/source path collision.')
    blobs.update(generated);manifest={**summary,'schema_version':1,'files':{n:digest(b) for n,b in sorted(blobs.items())},'boundaries':['Synthetic tests are not real-service evidence.','Historical capture drivers require separately authorized inputs.','A credential-pattern scan is not a comprehensive secret audit.']}
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,body in sorted(blobs.items()):archive.writestr('affinityqa-source/'+name,body)
        archive.writestr('affinityqa-source/PUBLIC-SOURCE-MANIFEST.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:raise ValueError('ZIP integrity failure; preserve archive for review.')
        for name,expected in manifest['files'].items():
            if digest(archive.read('affinityqa-source/'+name))!=expected:raise ValueError('Archive member hash mismatch.')
    print(json.dumps({**summary,'output':str(output),'zip_sha256':digest(output.read_bytes()),'verified_members':len(blobs)},indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
