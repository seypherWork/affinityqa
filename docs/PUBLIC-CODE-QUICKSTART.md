# AffinityQA — source setup and review

**Updated · 8 October 2026.** Tested runtime/backend code revision `457fcace665b29a206840cedf24bceac56865b8f` passed [CI run 37824994293](https://github.com/seypherWork/affinityqa/actions/runs/37824994293): 295 source-only tests on each of Windows and Ubuntu, source allowlist checks, frontend type checking and build. The hosted service uses that code and completed one genuine new case, server verification, service restart and saved browser-case restoration. Useful judge capacity and independent cultural quality remain unvalidated. A later documentation-only commit may differ without changing runtime modules; no new CI result is implied.

This distribution contains code and synthetic engineering tests. It excludes Qloo snapshots, recorded model decisions, private evidence receipts, credentials and compiled output. Passing source tests does not reproduce a provider experiment. Original project code is MIT licensed under `LICENSE`, Copyright (c) 2026 Seypher; provider data retains its own terms.

## Choose the Python interpreter

| Platform | Source setup | Observed CI runtime |
| --- | --- | --- |
| Windows | Python 3.13 | Python 3.13.16; 295 tests in 54.247 s |
| Ubuntu 24.04 / Linux | Python 3.12 | Python 3.12.14; 295 tests in 58.926 s |

Use an exact installed interpreter path on Windows. The optional `py` launcher is not required. The CI version numbers identify tested runtimes; this guide does not establish availability of a particular official downloadable installer. Other runtime versions need their own checks.

Private Windows v9 used Python 3.12.14 in its separately verified 6 October installation. That historical result is not the current Windows source recommendation, an installer-availability claim or a fresh Linux package installation result.

## Install dependencies and run source tests

Run from the repository root in a new virtual environment. Replace the Windows interpreter path with your installed Python 3.13 executable. Package installation accesses the package index unless an authorized local wheelhouse is supplied.

**Windows · PowerShell**

```powershell
& "C:\path\to\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-backend.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

**Linux · shell**

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-backend.lock.txt
.venv/bin/python -m unittest discover -s tests -v
```

The packaged tests use labelled fake engines and fabricated tool envelopes. They require no Qloo or Groq key and are not attestations of live requests. The allowlist includes local/remote capture drivers, verifiers and their fixture dependencies; required missing files stop packaging. The published workflow runs the complete packaged test directory with locked dependencies and propagates failures.

Running these commands creates a new local engineering observation. The dated 295-test CI result belongs to the named published revision; a later source change needs matching validation. Missing or skipped private tests are not passing provider acceptance.

## Build the interface

The preparation uses Node.js 24.19.0 and pnpm 11.25.0. With the installed runtimes available, use the same commands on Windows and Linux:

```text
cd web
npx --yes pnpm@11.25.0 install --frozen-lockfile --ignore-scripts
npx --yes pnpm@11.25.0 typecheck
npx --yes pnpm@11.25.0 build
cd ..
```

Dependency installation requires registry access. Lifecycle scripts are disabled during installation; the explicit application build runs afterward. No model or Qloo key is used by these source commands, and the build embeds no private provider snapshots. Static export is local output until separately deployed.

## Open the source preview

After building, run the appropriate command from the repository root:

| Platform | Command |
| --- | --- |
| Windows | `.\.venv\Scripts\python.exe scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767` |
| Linux | `.venv/bin/python scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767` |

Open **http://127.0.0.1:8767/demo/**. Without matching authorized evidence, the application reports **UNAVAILABLE**. It does not invent a demonstration or substitute synthetic fixtures for real recorded decisions. Keep the default loopback binding for local review and stop the server with Ctrl+C.

With an owner-supplied matching capture, replace the three bracketed inputs below. `python` means the platform's virtual-environment interpreter:

```text
python scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767 --evidence-root "<ABSOLUTE_AUTHORIZED_BUNDLE_DIRECTORY>" --run-id "<OWNER_PROVIDED_RUN_ID>" --receipt-sha256 "<OWNER_PROVIDED_RECEIPT_SHA256>"
```

Verify the capture separately:

```text
python scripts/verify_public_demo.py --evidence-root "<ABSOLUTE_AUTHORIZED_BUNDLE_DIRECTORY>" --run-id "<OWNER_PROVIDED_RUN_ID>" --receipt-sha256 "<OWNER_PROVIDED_RECEIPT_SHA256>"
```

Recorded replay re-executes routing, diagnosis and supported repair using captured decisions. It makes no new model or Qloo calls. The three inputs are private owner-supplied identifiers, not values included in public source. See [DEMO-GUIDE.md](DEMO-GUIDE.md) for the click path.

## Separate evidence and configuration

Without new-case configuration, the restricted server exposes liveness, recorded summary/replay and the built frontend. An explicit owner configuration adds the session-owned routes described in [PUBLIC-NEW-CASES.md](PUBLIC-NEW-CASES.md). Raw evidence exports and the general local API remain outside this surface. Starting a preview does not publish a service or start provider inference.

The historical audit drivers are supplied for inspection and refer to specific historical inputs. Their presence does not make those datasets public. For private review, use the owner's matching dataset and source versions in a separate private directory. Verify receipts and source bindings before replay; do not edit a receipt to fit a changed source.

Keep captures and receipts in their ignored private locations. The `.gitignore` also excludes credentials, archives, dependencies and generated frontend output. Inspect the exact allowlisted archive: ignore rules and the narrow credential-pattern check alone do not prove the absence of secrets or provider data. `PUBLIC-SOURCE-MANIFEST.json` binds included files to SHA-256 hashes.

## New-case entry points

Use the [local capture](INDIVIDUAL-CAPTURE.md), [local verification](INDIVIDUAL-VERIFICATION.md) and [panel](INDIVIDUAL-PANEL.md) guides for an explicitly configured local model. Use [INDIVIDUAL-REMOTE.md](INDIVIDUAL-REMOTE.md) for the Groq operator.

The remote operator uses a v2 request template and separately versioned v3 plan/report and redacted response contract. A local v1 receipt cannot certify a remote run. Preparation reads source/request hashes without keys, model loading or provider calls. Real execution requires the exact reviewed plan fingerprint and private configuration. The execution flag defaults to disabled in source; the owner explicitly enabled the hosted deployment on 8 October.

The earlier direct run `20261008T182536Z-edb5fd04` obtained 39 valid Groq packets and four fresh Qloo samples. Its verifier and independent audit confirmed integration PASS across all three faults, nine checks and three repeats. Nine recoveries and 27 distinct known fingerprints produced causal INCONCLUSIVE. This direct case remains separate from the later hosted run, which reported 25 fingerprints.

For 39 model starts at the current 22-second minimum spacing, the pacing lower bound is **38 × 22 = 836 seconds**, or **13 minutes 56 seconds**, before any additional work. It is not an account quota guarantee or completion promise. Preserve partial/failed attempts; the operator uses no automatic retry, resume, model substitution or schema fallback.

## Current hosted access and acceptance

The [hosted application](https://affinityqa-review.onrender.com) uses tested runtime/backend code revision `457fcace665b29a206840cedf24bceac56865b8f`. Its recorded HTTPS review passed 54 selections and 324 strict checks on 8 October before activation. The enabled deployment subsequently completed hosted job `20261008T190344Z-a49a92a0`, run `20261008T190353Z-772b6659`, from **19:03:53.159 to 19:17:54.786 UTC**, taking **841.627 seconds (14 min 1.627 s)**.

The hosted run obtained **39 Groq packets and four fresh Qloo samples**. All three fault cases passed nine unchanged checks with three repeats, and nine recoveries were observed. Its **25 distinct known fingerprints, with none absent**, produced backend VARIED and causal INCONCLUSIVE. Server verification reported COMPLETE; the selected public result received bounded independent review. This is one functional case, not independent cultural or population validation.

A real service restart changed the Render instance and preserved all **62 case-file hashes**, the same owned session/case and **one consumed cumulative admission out of the configured 100**. Pure verification remained COMPLETE. Actual browser reload restored all nine fault/repeat views, with nine displayed checks per view, without starting another capture. The independent restart supplement checked consistency of those operator-reported remote/hash/browser observations against the selected result; it did not repeat those remote actions or provide external-service attestation.

The hosted case used **57,600 tokens**. Against the observed shared **200,000-token daily budget**, approximately three similar complete cases fit before other account traffic. This is an arithmetic estimate, not guaranteed capacity; the cumulative 100-execution application limit is separate from provider quota. Useful free judge capacity through evaluation and independent cultural quality remain pending.

The 7 October browser/restart record belongs to earlier hosted source `e08ddf2a7b7751b07b9c0b4635ad838247c44c00`, with bounded desktop/keyboard/mobile interaction and 382 retained evidence hashes. The enabled deployment's new 62-file case/restart evidence is separate. The 6 October private Windows 309-test result likewise belongs to its historical package.

Read [JUDGE-ACCEPTANCE.md](JUDGE-ACCEPTANCE.md) for revision-specific evidence and remaining gates. [SUBMISSION-DRAFT.md](SUBMISSION-DRAFT.md) is an internal English draft, not a submitted entry. Cultural quality remains NOT_VALIDATED and tested-recommender release BLOCKED. Historical 13/14 development and independent 4/6 movie-quality results remain FAIL.

## License and reviewed data scope

Original code is MIT licensed under the included `LICENSE`. Qloo data, recorded provider decisions, dependencies, models, trademarks and external assets retain their separate rights. See [LICENSING.md](LICENSING.md) and [third-party notices](THIRD-PARTY-LICENSES.txt).

The 8 October review of official Qloo materials supports private server caching and attributed contextual results. Sending only necessary affinity context to an external model for this project's ranking is an operational interpretation of the documented workflow; no additional individual email-approval gate was identified for that scope. This does not grant raw-corpus redistribution, training, MIT licensing of Qloo outputs or universal provider reuse. Model-provider processing terms remain separate. [Official caching guidance](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide#can-i-cache-qloo-api-responses-in-my-app) · [Safe use](https://github.com/qloo/qloo-hackathon-kit/blob/main/docs/SAFE_USE.md)

Keep credentials and raw provider captures outside public Git. The builder verifies the complete approved MIT text and its bytes; a missing, altered or incomplete grant cannot be replaced by this guide. Source setup is distinct from publication and submission.
