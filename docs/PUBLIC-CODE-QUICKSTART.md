# Source-only review

This distribution contains code and synthetic engineering tests. It excludes Qloo snapshots, recorded model decisions, evidence receipts, credentials and compiled output. Successful unit tests do not reproduce the private real-service experiment. Original AffinityQA code is MIT licensed under the included `LICENSE`, Copyright (c) 2026 Seypher. Local packaging does not authorize the agent to publish or submit the project.

## Install and test

Use Python 3.12.14 in a new virtual environment to match the declared reference toolchain. Current private v9 installation evidence is Windows-only; current Linux and hosted execution remain unverified. Other Python versions require their own acceptance. Installation accesses the package index unless you supply an authorized local wheelhouse. The Windows example below accepts an exact interpreter path and does not require the optional `py` launcher; replace the placeholder with your installed executable. If `py -3` is available, it can be used for the first command instead.

```powershell
& "C:\path\to\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-backend.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The packaged test allowlist is synthetic and does not require private captures. Its fake engines and fabricated tool envelopes are test inputs, not attestations of live requests. Run private evidence integration tests separately in an authorized environment; do not count missing or skipped private tests as passing validation.

The required allowlist includes the local and Groq new-case drivers, independent
verifiers and their complete fixture dependencies. Missing required files stop
packaging. The repository workflow runs the complete packaged test directory;
it does not silently skip a missing suite. Running it here is a local check,
not an observation of a new GitHub Actions run. The unpublished workflow
prepares separate Windows and Ubuntu 24.04 jobs with explicit PowerShell
Core commands, locked dependencies and failure propagation. No CI job
for this candidate has been executed or observed. CI source checks
cannot establish provider acceptance or external demo availability.

## Build the interface

Install a supported Node.js runtime and pnpm. From `web`, run `pnpm install --frozen-lockfile --ignore-scripts`, `pnpm typecheck` and `pnpm build`. Dependency installation needs registry access; no model or Qloo key is involved. Dependency lifecycle scripts are disabled during installation; the explicit build remains a separate command. The resulting static export is local build output, not a published site. No provider snapshots are embedded by the package builder.

The application demonstration is **not** a synthetic replacement for recorded evidence. Without authorized captures it is a source preview and reports **UNAVAILABLE**. With a separately authorized capture it executes the real routing, diagnosis and repair pipeline using the recorded local-model decisions. It does not generate fresh model decisions or call Qloo. Synthetic fixtures belong to engineering tests only.

See [the reviewer click path](DEMO-GUIDE.md), when included, for the recorded demonstration and its expected controls. The hosted demo is the intended primary review path; this source package alone is not a substitute for the separately authorized evidence or an externally tested application.

After building the interface, return to the project root and start the restricted local preview:

```powershell
.\.venv\Scripts\python.exe scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767
```

Open `http://127.0.0.1:8767/demo/`. For an authorized private evidence bundle, use the owner's exact extracted absolute directory, run ID and receipt fingerprint in place of these placeholders:

```powershell
.\.venv\Scripts\python.exe scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767 --evidence-root "<ABSOLUTE_AUTHORIZED_BUNDLE_DIRECTORY>" --run-id "<OWNER_PROVIDED_RUN_ID>" --receipt-sha256 "<OWNER_PROVIDED_RECEIPT_SHA256>"
```

Keep the default loopback binding for local review. With no case configuration,
this surface exposes `/healthz`, `/api/demo/summary`, `/api/demo/replay` and the
built frontend. An explicit owner case configuration adds the owned routes in
[PUBLIC-NEW-CASES.md](PUBLIC-NEW-CASES.md). It does not expose raw evidence exports
or the general local API. Starting a local preview does not publish a site.

## Separately authorized evidence

The audit drivers `run_causal_repair.py`, `continue_causal_validation.py`, `resume_causal_identity.py` and `verify_causal_repair.py` are included for inspection. They refer to historical run identifiers and require additional inputs; their presence is not permission to query a provider, retry an experiment or distribute its data.

To review a private capture, obtain explicit authorization for that dataset and use a separate private working directory. Obtain the matching evidence package and original source versions from its owner. Verify receipt hashes and source bindings with the supplied verification procedure before replay. Do not edit a receipt to fit different source. Keep captures in ignored `runs/` and receipts in ignored `evidence/`; never add them to a public source commit. No private evidence is downloaded automatically by this package.

The generated `.gitignore` also excludes credential files, archives, dependency directories and generated web output. Use the allowlist and inspect the exact archive contents; ignore rules alone do not prove absence of secrets or licensed data. `PUBLIC-SOURCE-MANIFEST.json` binds each included file to its SHA-256 hash. The built-in credential-pattern check is deliberately narrow and does not replace a final secret and attribution review.

## New-case entry points

Use the [local capture guide](INDIVIDUAL-CAPTURE.md), [local verifier](INDIVIDUAL-VERIFICATION.md)
and [panel contract](INDIVIDUAL-PANEL.md) for an explicitly configured local model.
Use [the separate remote guide](INDIVIDUAL-REMOTE.md) for the Groq candidate.
The latter has its own v2 request, plan, source bindings and verifier; a local v1
receipt does not certify a remote run. Plans do not read private keys, load a
model or call providers. Real execution requires deliberate configuration and
the exact reviewed plan fingerprint. The restricted public server accepts the
explicit remote case configuration described in PUBLIC-NEW-CASES.md; its
execution flag defaults to disabled. Loopback preparation is not hosted acceptance.

The source archive preserves the reviewed README and the two original SVG
diagrams it references. It generates a new public-source manifest and excludes
historical deployment/source manifests, raw evidence and private files. Existing
Render preparation accepts recorded replay, explicit public cases, or both.
Building or starting a local preview does not deploy or authorize either mode.

## Acceptance and submission materials

Read [JUDGE-ACCEPTANCE.md](JUDGE-ACCEPTANCE.md) for the exact separation
between original real capture, private Windows recorded verification and
pending current Linux/cloud/hosted cases. [SUBMISSION-DRAFT.md](SUBMISSION-DRAFT.md)
is an internal English draft, not a submitted entry. The private Windows
309-test result is not a test count for this source package or its CI.

## Licensing scope

The owner approved MIT for original code; `LICENSE` contains the grant. `LICENSING-NOTES.md`, `docs/LICENSING.md` and `THIRD-PARTY-LICENSES.txt`, when included, explain scope and dependency notices. Qloo data, recorded model decisions, third-party dependencies, models, trademarks and external assets retain their own rights and terms.

The builder checks the complete approved MIT text and includes its exact bytes. If `LICENSE` is absent, its manifest reports no grant and it generates only `LICENSE-PROPOSAL.md`; this guide alone does not grant a license. An altered or incomplete license stops packaging for review. Publication and submission by the agent remain separate actions requiring authorization.
