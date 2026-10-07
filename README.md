![AffinityQA — Follow the profile. Prove the recovery.](docs/images/hero.svg)

# AffinityQA

**Follow the profile. Prove the recovery.**

AffinityQA detects when a personalized AI agent loses the requested profile, diagnoses the routing fault, applies a supported repair and checks whether the correct behavior returns. Inspect the identity trace and replay the recovery in a focused reviewer interface.

[Quickstart](#quickstart) · [Architecture](#architecture) · [Local evidence](#local-evidence) · [Reviewer guide](docs/DEMO-GUIDE.md) · [MIT license](LICENSE)

**Candidate update · 6 October 2026.** The source also includes new-case capture
and independent verification for an explicitly configured local model or the
separately versioned Groq operator. The public panel now provides explicit
session, plan, start, progress, saved-case and selected-verification controls,
with disabled-by-default CLI and Render configuration. A complete browser
journey and provider failure have been exercised with labelled synthetic
fixtures. Windows path preflight prevents overlong capture paths before
provider dispatch. Real Groq acceptance and hosted new-case access
remain pending. No cloud key, provider capture or model weights are shipped.

## What it does

- **Find the broken profile link.** Compare requested, transmitted, tool and output identities.
- **Explain a supported cause.** Distinguish three faults through observed traces.
- **Repair the actual pipeline.** Change routing or cache configuration, then dispatch again.
- **Show the proof.** Compare before, after and recorded healthy decisions with six explicit checks.

The reviewer replay uses previously recorded local-model decisions. It executes the routing, diagnosis and repair pipeline again, with **zero new model or Qloo calls**. The initial capture and its provider-derived evidence are separate from this public source repository.

## Three faults. Three explicit repairs.

| Injected fault | Diagnosis | Repair operation |
| --- | --- | --- |
| Cache key omits the profile | `CACHE_OMITS_PROFILE` | `set-profile-cache` — include profile identity in cache scope |
| A stale profile reaches the agent | `STALE_PROFILE` | `restore-request-profile` — route the current request |
| The tool context belongs to another profile | `WRONG_TOOL_PROFILE` | `bind-request-tool` — bind tool input to the request |

**Detect → Diagnose → Repair → Verify.** Select an incident, inspect the mismatch, replay its supported repair and compare the recovered output with the recorded healthy reference. Unsupported or ambiguous traces do not become successful repairs.

## Architecture

![Architecture diagram: public source and separate private evidence feed the restricted replay pipeline.](docs/images/architecture.svg)

Both images are original vector diagrams, not product screenshots or provider
outputs. Replay exposes a summary and one selected incident. Explicitly
configured public new cases use an isolated browser session and shared retained
admission limits; see [the public flow and startup contract](docs/PUBLIC-NEW-CASES.md).
Raw evidence exports and the general local API remain outside this surface.
`/healthz` reports liveness and configuration, not provider readiness.

## Quickstart

**Toolchain used for the current preparation:** Python **3.12.14**, Node.js **24.19.0**, pnpm **11.25.0**. Run from the repository root. Install those runtimes separately; the commands below install project dependencies. Linux commands are provided for portability and have not been validated as a hosted Linux deployment.

### 1. Install Python dependencies and run source tests

**Windows · PowerShell**

```powershell
& "C:\path\to\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-backend.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Replace the interpreter path with your installed Python 3.12.14 executable; the optional Windows `py` launcher is not required.

**Linux · shell**

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-backend.lock.txt
.venv/bin/python -m unittest discover -s tests -v
```

### 2. Build the interface

The same commands work in PowerShell and a Linux shell:

```text
cd web
npx --yes pnpm@11.25.0 install --frozen-lockfile --ignore-scripts
npx --yes pnpm@11.25.0 typecheck
npx --yes pnpm@11.25.0 build
cd ..
```

The lockfile fixes dependency resolution; install lifecycle scripts are disabled. The explicit application build runs afterward. Package installation requires registry access.

### 3. Open the local source preview

| Platform | Command |
| --- | --- |
| Windows | `.\.venv\Scripts\python.exe scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767` |
| Linux | `.venv/bin/python scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767` |

Open **http://127.0.0.1:8767/demo/**. Without separately authorized evidence, the preview reports **UNAVAILABLE**. It does not replace real evidence with fabricated results. Stop the process with Ctrl+C.

### 4. Replay an authorized capture

Use an evidence directory, run ID and receipt hash provided by its owner. With the platform-specific Python executable above, run:

```text
python scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767 --evidence-root "<ABSOLUTE_AUTHORIZED_DIRECTORY>" --run-id "<OWNER_PROVIDED_RUN_ID>" --receipt-sha256 "<OWNER_PROVIDED_SHA256>"
```

Verify the complete recorded replay separately:

```text
python scripts/verify_public_demo.py --evidence-root "<ABSOLUTE_AUTHORIZED_DIRECTORY>" --run-id "<OWNER_PROVIDED_RUN_ID>" --receipt-sha256 "<OWNER_PROVIDED_SHA256>"
```

These `python` examples mean the virtual-environment interpreter, not an arbitrary system executable. See the [full setup guide](docs/PUBLIC-CODE-QUICKSTART.md) and [reviewer click path](docs/DEMO-GUIDE.md).

### 5. Prepare a new case with explicit inputs

The recorded replay and new-case capture are separate entry points. A new case
needs an owner-supplied private request with two musical interests and twenty
resolved movie identities. It does not inherit the historical private catalog.

| Operator | Preparation command | Execution and verification guide |
| --- | --- | --- |
| Local model | `python scripts/capture_individual_pair.py --request private/request.json --output private/new-local-capture` | [Capture](docs/INDIVIDUAL-CAPTURE.md) · [Verify](docs/INDIVIDUAL-VERIFICATION.md) |
| Groq candidate | `python scripts/capture_individual_remote.py --request private/request.json --output private/new-remote-capture` | [Remote contract and commands](docs/INDIVIDUAL-REMOTE.md) |

Replace `python` with your virtual-environment interpreter. Preparation reads
the request and source hashes, creates no capture and makes no provider calls.
Execution requires the exact reviewed plan hash, explicit private credentials
and the provider/data permissions described in the guides. The local panel
remains bound to loopback. Its preparation limits are not a public judging
capacity policy. A causal recovery does not validate personal movie preferences.

For public session/case controls, follow [PUBLIC-NEW-CASES.md](docs/PUBLIC-NEW-CASES.md).
It documents the exact closed owner configuration, preview commands, lazy
private credential paths and separate execution flag. Choose short storage
paths on Windows; both local and remote plans reject incompatible paths before
reading keys or calling providers. Loopback browser proof is not hosted acceptance.

## Local evidence

Dated observations below refer to their named artifacts. They are **not a
passing CI badge** or a verified external demo. Private captures are excluded
from this public source distribution.

| Artifact and check | Observed result | Scope |
| --- | --- | --- |
| Previous public source candidate, 6 October 2026 | **285 synthetic tests passed**, zero skips, from its ZIP extraction | Earlier source-only candidate; not a result for an unexecuted workflow |
| Private Windows v9, 6 October 2026 | **309 technical fixture tests**, zero skips; 17 locked packages installed | Fresh native Windows installation of the separate private judge package |
| Private Windows v9 recorded journey | **54 selections**, 19 read-only API views, 41 static hashes and four browser panels checked | Recorded decisions; no new inference or Qloo calls |
| Original real causal capture | **18/18 controlled cases; 54 observed recoveries** | Six pairs, three fault types, three repeats; not independent users |
| Original capture acquisition | **234 local model decisions; 24 Qloo observations** | 19 new Qloo requests and five reused searches with provenance |
| Historical 4 October source / full suites | **81 / 380 tests** | Earlier revisions, retained as history; not current suite totals |
| Independent cultural recommendation quality | **NOT_VALIDATED**; earlier 13/14 and 4/6 trials failed | No threshold or historical failure has been changed |

**Current acceptance:** the new public source workflow is prepared for Windows
and Ubuntu 24.04; neither job has been observed running for this unpublished
candidate. Current Linux runtime, genuine cloud inference, hosted judge access,
useful capacity and third-party data permission remain pending. The recorded
Windows result does not establish those requirements. The application remains
**NO-GO for the complete jury journey**; the tested agent's release remains
**BLOCKED**. See [the acceptance record](docs/JUDGE-ACCEPTANCE.md).

## Render build configuration

Use this exact **Build Command** in the manual service form or the Blueprint:

```sh
AFFINITYQA_NODE_EXECUTABLE="$(node -p process.execPath | tail -n 1)" && test -x "$AFFINITYQA_NODE_EXECUTABLE" && PATH="$(dirname "$AFFINITYQA_NODE_EXECUTABLE"):$PATH" python deployment/build_render.py
```

In the observed Render console, Node selected version 24.19.0, while a Python child process in this service found `/usr/bin/node` version 24.21.0. Resolving the selected executable and prepending its directory to PATH allowed the complete build to pass. This records the observed lookup difference without attributing it to an unverified shell mechanism. Node/pnpm/Python pins and all build checks remain unchanged.

The corrected command reached **BUILD SUCCESS** on 4 October 2026 for source commit `f929df5763cb8d37c3958c9c6fa9a4b37e469007` (deployment `dep-db193s60tbcc73a43i1g`). This confirms the build only, not evidence installation, demo readiness or cultural recommendation quality, which remains **NOT_VALIDATED**. See [deployment instructions](deployment/README.md) before changing the start command.

## Repository map

| Path | Purpose |
| --- | --- |
| [`src/affinityqa/`](src/affinityqa/) | Profile integrity, diagnosis, repair, replay and API operators |
| [`scripts/`](scripts/) | Local preview, verification and audit entry points |
| [`web/`](web/) | Next.js reviewer interface and locked frontend dependencies |
| [`tests/`](tests/) | Source-only engineering tests |
| [`docs/`](docs/) | Setup, reviewer flow, deployment boundaries and licensing |
| [`deployment/`](deployment/) | Reviewed hosting preparation; does not create a service by itself |
| [`evals/`](evals/) | Evaluation definitions |
| [`fixtures/`](fixtures/) | Explicitly synthetic test inputs |

## Documentation

| Start here | Read next |
| --- | --- |
| [Source setup and commands](docs/PUBLIC-CODE-QUICKSTART.md) | [Reviewer demonstration guide](docs/DEMO-GUIDE.md) |
| [Restricted deployment contract](docs/PUBLIC-DEMO-DEPLOYMENT.md) | [Deployment preparation](deployment/README.md) |
| [Asset provenance](docs/ASSET-PROVENANCE.md) | [Licensing scope](docs/LICENSING.md) |
| [New-case local panel](docs/INDIVIDUAL-PANEL.md) | [Groq candidate and transfer boundary](docs/INDIVIDUAL-REMOTE.md) |
| [Current acceptance and remaining evidence](docs/JUDGE-ACCEPTANCE.md) | [English submission draft — internal](docs/SUBMISSION-DRAFT.md) |

## License and data

Original AffinityQA code is **MIT licensed**, © 2026 Seypher. See [LICENSE](LICENSE) and [third-party notices](docs/THIRD-PARTY-LICENSES.txt).

Qloo responses, recorded provider outputs, model materials and third-party assets retain their own rights. Their display or redistribution requires separate authorization. Keep credentials and private evidence outside the public repository.
