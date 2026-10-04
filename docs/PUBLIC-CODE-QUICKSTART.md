# Source-only review

This distribution contains code and synthetic engineering tests. It excludes Qloo snapshots, recorded model decisions, evidence receipts, credentials and compiled output. Successful unit tests do not reproduce the private real-service experiment. Original AffinityQA code is MIT licensed under the included `LICENSE`, Copyright (c) 2026 Seypher. Local packaging does not authorize the agent to publish or submit the project.

## Install and test

Use an existing Python 3.11+ installation in a new virtual environment. The recorded dependency set was exercised on Python 3.12; verify your platform rather than assuming compatibility. Installation accesses the package index unless you supply an authorized local wheelhouse. The Windows example below accepts an exact interpreter path and does not require the optional `py` launcher; replace the placeholder with your installed executable. If `py -3` is available, it can be used for the first command instead.

```powershell
& "C:\path\to\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-backend.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The packaged test allowlist is synthetic and does not require private captures. Its fake engines and fabricated tool envelopes are test inputs, not attestations of live requests. Run private evidence integration tests separately in an authorized environment; do not count missing or skipped private tests as passing validation.

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

Keep the default loopback binding for local review. This restricted surface exposes three functional endpoints (`/healthz`, `/api/demo/summary`, `/api/demo/replay`) plus the built frontend assets. It does not expose raw evidence exports, general backend routes or live inference. Starting a local preview does not publish a site. See `PUBLIC-DEMO-DEPLOYMENT.md`, when included, for the separately reviewed deployment boundary.

## Separately authorized evidence

The audit drivers `run_causal_repair.py`, `continue_causal_validation.py`, `resume_causal_identity.py` and `verify_causal_repair.py` are included for inspection. They refer to historical run identifiers and require additional inputs; their presence is not permission to query a provider, retry an experiment or distribute its data.

To review a private capture, obtain explicit authorization for that dataset and use a separate private working directory. Obtain the matching evidence package and original source versions from its owner. Verify receipt hashes and source bindings with the supplied verification procedure before replay. Do not edit a receipt to fit different source. Keep captures in ignored `runs/` and receipts in ignored `evidence/`; never add them to a public source commit. No private evidence is downloaded automatically by this package.

The generated `.gitignore` also excludes credential files, archives, dependency directories and generated web output. Use the allowlist and inspect the exact archive contents; ignore rules alone do not prove absence of secrets or licensed data. `PUBLIC-SOURCE-MANIFEST.json` binds each included file to its SHA-256 hash. The built-in credential-pattern check is deliberately narrow and does not replace a final secret and attribution review.

## Licensing scope

The owner approved MIT for original code; `LICENSE` contains the grant. `LICENSING-NOTES.md`, `docs/LICENSING.md` and `THIRD-PARTY-LICENSES.txt`, when included, explain scope and dependency notices. Qloo data, recorded model decisions, third-party dependencies, models, trademarks and external assets retain their own rights and terms.

The builder checks the complete approved MIT text and includes its exact bytes. If `LICENSE` is absent, its manifest reports no grant and it generates only `LICENSE-PROPOSAL.md`; this guide alone does not grant a license. An altered or incomplete license stops packaging for review. Publication and submission by the agent remain separate actions requiring authorization.
