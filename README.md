![AffinityQA — Follow the profile. Prove the recovery.](docs/images/hero.svg)

# AffinityQA

**Follow the profile. Prove the recovery.**

AffinityQA traces the requested taste profile through an AI agent's routing, cache and Qloo tool context. It diagnoses three controlled integration faults, applies a supported repair and checks the resulting behavior against a healthy reference.

**Status · 8 October 2026.** The [hosted application](https://affinityqa-review.onrender.com) completed one genuine new case with **39 Groq decisions and four fresh Qloo responses**. All three fault cases passed their integration checks, with nine observed recoveries. The case, evidence, session and consumed admission survived a real service restart; browser reload restored all nine fault/repeat views without starting another capture. Causal attribution is **INCONCLUSIVE** because this hosted run reported 25 distinct known backend fingerprints. Functional and restart acceptance cover this one observed case. Full jury acceptance remains **NO-GO** pending useful judge capacity and independent cultural evaluation; cultural quality is **NOT_VALIDATED** and tested-recommender release **BLOCKED**.

[Quickstart](#quickstart) · [Architecture](#architecture) · [Evidence and acceptance](#evidence-and-acceptance) · [Reviewer guide](docs/DEMO-GUIDE.md) · [MIT license](LICENSE)

## Current review surfaces

| Surface | Verified state | Boundary |
| --- | --- | --- |
| Hosted genuine case and restart | Tested runtime/backend code revision `457fcace665b29a206840cedf24bceac56865b8f`; hosted run `20261008T190353Z-772b6659`; complete browser case, server verification and restart retention passed | One observed case; 25 known fingerprints, causal INCONCLUSIVE; sustained capacity and cultural quality are not established |
| Tested runtime/backend code | Revision `457fcace665b29a206840cedf24bceac56865b8f`; reviewed 14-file publication; [CI run 37824994293](https://github.com/seypherWork/affinityqa/actions/runs/37824994293) passed 295 tests per platform and frontend type checking/build | Windows and Ubuntu source engineering; later documentation commits may differ while runtime modules remain unchanged |
| Separate direct remote case | Run `20261008T182536Z-edb5fd04`; separate recorded-file verifier and independent audit checked 39 Groq packets, four Qloo samples and all three incident cases | Earlier direct execution; 27 distinct known fingerprints; integration PASS and causal INCONCLUSIVE; not the hosted run |

The tested backend code and current hosted service use revision `457fcace665b29a206840cedf24bceac56865b8f`. Documentation can advance independently without changing those runtime bytes. Recorded replay and genuine new cases are separate journeys; replay makes zero new provider calls. Private provider configuration is not exposed. No cloud key, model weights or raw Qloo/provider capture is distributed in public source.

## What it does

- **Find the broken profile link.** Compare requested, transmitted, tool and output identities.
- **Explain a supported cause.** Diagnose a missing profile in the cache scope, a stale request profile or a tool context bound to another profile.
- **Repair the pipeline.** Apply one explicit routing or cache operation, then dispatch again.
- **Show the evidence.** Compare before, after and recorded healthy decisions while keeping failed, partial and inconclusive results visible.

The original capture obtained real Qloo context and fresh local-model decisions. The reviewer replay executes routing, diagnosis and repair against those recorded decisions. It does not replace a new provider trial or an independent study of personal movie preferences.

## Three faults. Three explicit repairs.

| Injected fault | Diagnosis | Repair operation |
| --- | --- | --- |
| Cache key omits the profile | `CACHE_OMITS_PROFILE` | `set-profile-cache` — include profile identity in cache scope |
| A stale profile reaches the agent | `STALE_PROFILE` | `restore-request-profile` — route the current request |
| Tool context belongs to another profile | `WRONG_TOOL_PROFILE` | `bind-request-tool` — bind tool input to the request |

**Detect → Diagnose → Repair → Verify.** Unsupported or ambiguous traces do not become successful repairs.

## Architecture

![Architecture diagram: public source and separate private evidence feed the restricted replay pipeline.](docs/images/architecture.svg)

Both images are original vector diagrams, not product screenshots or provider outputs. The restricted reviewer exposes a summary and one selected incident. Raw evidence exports and the general local API remain outside this public surface. `/healthz` reports liveness and configuration; it does not establish provider readiness.

New-case controls are a separate, explicitly configured operator path with isolated sessions and retained admission limits. See [PUBLIC-NEW-CASES.md](docs/PUBLIC-NEW-CASES.md) for the startup and browser contract. Their source implementation and synthetic checks do not establish a working hosted new-case journey.

## Quickstart

The source preparation uses **Python 3.13 on Windows** and **Python 3.12 on Linux**, with Node.js **24.19.0** and pnpm **11.25.0**. The verified CI interpreters were **3.13.16 on Windows** and **3.12.14 on Ubuntu 24.04**. Run commands from the repository root using an exact installed interpreter path. These version numbers identify observed CI runtimes; they do not certify availability of a particular downloadable installer. The commands below install project dependencies. CI evidence belongs to tested runtime/backend code revision `457fcace665b29a206840cedf24bceac56865b8f`; the separate hosted case and restart have their own runtime observations.

### 1. Install Python dependencies and run source tests

**Windows · PowerShell**

```powershell
& "C:\path\to\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-backend.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Replace the interpreter path with your installed **Python 3.13** executable; CI used 3.13.16. The optional Windows `py` launcher is not required. The private Windows v9 artifact's earlier Python 3.12.14 result belongs to that historical package.

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

Open **http://127.0.0.1:8767/demo/**. Without separately authorized evidence, the preview reports **UNAVAILABLE**. It does not substitute fabricated results. Stop the process with Ctrl+C.

### 4. Replay an authorized capture

Use the evidence directory, run ID and receipt hash supplied by its owner. With the platform-specific virtual-environment interpreter above, run:

```text
python scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767 --evidence-root "<ABSOLUTE_AUTHORIZED_DIRECTORY>" --run-id "<OWNER_PROVIDED_RUN_ID>" --receipt-sha256 "<OWNER_PROVIDED_SHA256>"
```

Verify the complete recorded replay separately:

```text
python scripts/verify_public_demo.py --evidence-root "<ABSOLUTE_AUTHORIZED_DIRECTORY>" --run-id "<OWNER_PROVIDED_RUN_ID>" --receipt-sha256 "<OWNER_PROVIDED_SHA256>"
```

These `python` examples mean the virtual-environment interpreter. The three bracketed values are required private owner inputs, not values supplied by the public repository. See the [full setup guide](docs/PUBLIC-CODE-QUICKSTART.md) and [reviewer click path](docs/DEMO-GUIDE.md).

### 5. Prepare a new case with explicit inputs

A new case requires an owner-supplied private request with two musical interests and twenty resolved movie identities. It does not inherit the historical private catalog.

| Operator | Preparation command | Guide |
| --- | --- | --- |
| Local model | `python scripts/capture_individual_pair.py --request private/request.json --output private/new-local-capture` | [Capture](docs/INDIVIDUAL-CAPTURE.md) · [Verification](docs/INDIVIDUAL-VERIFICATION.md) |
| Groq candidate | `python scripts/capture_individual_remote.py --request private/request.json --output private/new-remote-capture` | [Remote contract](docs/INDIVIDUAL-REMOTE.md) |

Preparation reads the request and source hashes without provider dispatch. Execution requires the exact reviewed plan hash, private credentials and configuration within the reviewed provider/data scope below. The local panel remains bound to loopback. Windows path preflight rejects incompatible storage paths before credentials or provider calls.

The remote v3 operator records each validated response's optional backend fingerprint instead of requiring one fingerprint globally during capture. Its integration gate retains **all nine checks, all three mandatory faults and three repeats**. A complete sample still requires **39 validated decisions**. Causal **PASS** requires both integration **PASS** and 39 known, identical observed fingerprints. Integration **PASS** with varied or absent fingerprints yields causal **INCONCLUSIVE**; partial captures remain **NOT_EVALUATED**. Equal observed fingerprints do not attest immutable model weights.

**Direct execution · 8 October:** run `20261008T182536Z-edb5fd04` finished at **18:39:37 UTC**, and the separate verifier reported **VERIFIED_COMPLETE** at **18:40:49 UTC**. All three integration cases passed, each with the unchanged nine checks and three repeats. Nine recoveries and 27 distinct known fingerprints were observed, so backend comparability is **VARIED** and causal attribution **INCONCLUSIVE**. No retry, resume, model substitution or schema fallback was used.

**Independent audit completed:** the actual remote run was independently reviewed at **18:46:38 UTC on 8 October**. The reviewer re-ran the recorded-file verifier, checked source/plan/admission/process bindings and confirmed the observed integration result while retaining causal INCONCLUSIVE and cultural NOT_VALIDATED.

**Hosted execution and restart · 8 October:** job `20261008T190344Z-a49a92a0`, run `20261008T190353Z-772b6659`, completed from **19:03:53.159 to 19:17:54.786 UTC**, taking **841.627 seconds (14 min 1.627 s)**. Server verification reported COMPLETE for 39 Groq packets and four Qloo samples, with integration PASS, nine observed recoveries and 25 distinct known fingerprints; causal attribution remains INCONCLUSIVE. A real service restart preserved all 62 case-file hashes and the single consumed cumulative admission. Browser reload restored the same session/case and all nine fault/repeat views without a new execution. Independent reviews accepted the selected hosted result and the consistency of the reported restart/restoration evidence, within that one-case scope.

**Capacity and quality remain limited.** This hosted case used 57,600 tokens. Against the observed shared 200,000-token daily budget, that is approximately three similar complete cases per day before other account traffic. It is an arithmetic estimate, not reserved capacity, guaranteed availability or a benchmark for many users. The retained cumulative policy of 100 executions is a separate application admission limit. Independent cultural labels and useful judge access through evaluation still require acceptance.

## Evidence and acceptance

| Evidence | Observed result | Scope |
| --- | --- | --- |
| Hosted recorded replay, 8 October before activation | 54 HTTPS selections; 324 strict checks; 14 routes/assets served; private-route, origin and busy/recovery checks passed | Recorded journey at source `457fcace665b29a206840cedf24bceac56865b8f`; zero new Qloo/model calls |
| Complete hosted case, 8 October | 39 Groq packets; four fresh Qloo samples; all three fault cases passed nine checks and three repeats; nine recoveries; 841.627 s; 57,600 tokens | Run `20261008T190353Z-772b6659`; 25 known fingerprints, none absent; integration PASS, behavioral OBSERVED_RECOVERY, causal INCONCLUSIVE |
| Hosted restart/browser restoration, 8 October | 62 file hashes unchanged; pure verification COMPLETE; same session/case restored; all nine fault/repeat views showed nine checks; no new execution | One retained cumulative admission out of the configured 100; bounded functional and persistence acceptance, not sustained capacity |
| Earlier hosted Linux cache/restart, 7 October | 54 recorded selections; 382 evidence hashes bound and preserved across service-process restart | Prior deployed `e08ddf2a7b7751b07b9c0b4635ad838247c44c00`; no new inference; not a fresh restart test for the later deployment |
| Published CI, 8 October | Windows: 295 tests in 54.247 s; Ubuntu: 295 tests in 58.926 s; source allowlist, frontend type checking/build passed on both | Revision `457fcace665b29a206840cedf24bceac56865b8f`; [run 37824994293](https://github.com/seypherWork/affinityqa/actions/runs/37824994293) |
| Separate direct remote v3 case and audit | 39 validated Groq decisions; four fresh Qloo responses; integration PASS 3/3; nine observed recoveries; independent recorded-file audit VERIFIED_COMPLETE | Earlier direct run `20261008T182536Z-edb5fd04`; known Björk/Bad Bunny request; 27 known fingerprints; causal INCONCLUSIVE; no independent-user claim |
| Targeted remote v3 engineering | 13 reviewed source changes plus manifest; 124 offline fixture tests passed; source/bounded-execution review GO | Offline regression evidence with provider/DNS dispatch denied; the genuine result is listed separately |
| Original real causal capture | 18/18 controlled incident cases; 234 local-model decisions; 24 Qloo observations; 54 recoveries | Six profile pairs, three faults and three repeats; 19 new Qloo requests and five reused search observations with provenance |
| Independent cultural evaluation | NOT_VALIDATED; historical 13/14 development and 4/6 independent movie trial retained as FAIL | Zero verified human labels; requested ratings from two real people for the twenty-movie catalog remain pending |

The 7 October browser review checked desktop stages, keyboard interaction and a 390-pixel mobile viewport. On 8 October, recorded HTTPS checks and the later genuine hosted case/restart were observed separately. These are bounded checks, not universal browser certification, many-user capacity or guaranteed access through judging. Independent hosted reviews checked the selected public result and local observation consistency; remote private hash comparisons and actual browser actions are operator observations, not actions independently repeated by those reviewers. Provider observations have no external-service cryptographic attestation.

See [JUDGE-ACCEPTANCE.md](docs/JUDGE-ACCEPTANCE.md) for the gates and remaining evidence. Passing routing checks does not validate personal preferences, adoption, time saved or production incident reduction.

## Render build configuration

Use the reviewed **Build Command** in the manual service form or Blueprint:

```sh
AFFINITYQA_NODE_EXECUTABLE="$(node -p process.execPath | tail -n 1)" && test -x "$AFFINITYQA_NODE_EXECUTABLE" && PATH="$(dirname "$AFFINITYQA_NODE_EXECUTABLE"):$PATH" python deployment/build_render.py
```

The observed Render console selected Node 24.19.0, while a Python child process found `/usr/bin/node` 24.21.0. Resolving the selected executable and prepending its directory to PATH allowed the build to pass. This records the observed lookup difference without attributing it to an unverified shell mechanism. See [deployment instructions](deployment/README.md) before changing the start command or execution mode.

## Repository map

| Path | Purpose |
| --- | --- |
| [`src/affinityqa/`](src/affinityqa/) | Profile integrity, diagnosis, repair, replay and API operators |
| [`scripts/`](scripts/) | Preview, verification and audit entry points |
| [`web/`](web/) | Next.js reviewer interface and locked frontend dependencies |
| [`tests/`](tests/) | Source-only engineering tests |
| [`docs/`](docs/) | Setup, reviewer flow, deployment boundaries and licensing |
| [`deployment/`](deployment/) | Reviewed hosting preparation |
| [`evals/`](evals/) | Evaluation definitions |
| [`fixtures/`](fixtures/) | Explicitly synthetic test inputs |

## Documentation

| Start here | Read next |
| --- | --- |
| [Source setup](docs/PUBLIC-CODE-QUICKSTART.md) | [Reviewer demonstration](docs/DEMO-GUIDE.md) |
| [Restricted deployment](docs/PUBLIC-DEMO-DEPLOYMENT.md) | [Deployment preparation](deployment/README.md) |
| [Asset provenance](docs/ASSET-PROVENANCE.md) | [Licensing scope](docs/LICENSING.md) |
| [New-case local panel](docs/INDIVIDUAL-PANEL.md) | [Groq transfer boundary](docs/INDIVIDUAL-REMOTE.md) |
| [Acceptance record](docs/JUDGE-ACCEPTANCE.md) | [English submission draft — internal](docs/SUBMISSION-DRAFT.md) |

## License and data

Original AffinityQA code is **MIT licensed**, © 2026 Seypher. See [LICENSE](LICENSE) and [third-party notices](docs/THIRD-PARTY-LICENSES.txt).

Qloo responses, recorded provider outputs, model materials and third-party assets retain their own rights. The MIT grant covers original project code and does not relicense provider data. Keep credentials and raw private evidence outside public Git.

The 8 October review of official Qloo materials supports private server caching and attributed, contextual presentation of results. Sending only the affinity context needed for this project's ranking to an external model is an operational interpretation of the documented agent workflow. The review did not establish an additional individual email-approval gate for that scope. It does not authorize raw-corpus redistribution, model training or universal provider reuse; applicable model-provider processing terms remain separate. [Official Qloo caching guidance](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide#can-i-cache-qloo-api-responses-in-my-app) · [Qloo safe-use guidance](https://github.com/qloo/qloo-hackathon-kit/blob/main/docs/SAFE_USE.md)

## Appendix: retained engineering history

- The 6 October public source candidate passed 285 synthetic tests from its ZIP extraction. Published revision `20d6abfe489eff5ae361d8c45a92bf14d4133de9` later passed 285 tests on each platform in [CI run 37670425795](https://github.com/seypherWork/affinityqa/actions/runs/37670425795). These are earlier revisions.
- Private Windows v9 installed 17 locked dependencies, passed 309 technical fixtures with zero skips and verified 54 recorded selections, 19 read-only API views, 41 static hashes and four browser panels. The failed initial ensurepip environment was retained; the successful install used child-process workspace TMP/TEMP. Listener shutdown was observed after console interruption, without a claim of orderly exit zero or a complete descendant-process audit.
- Earlier 4 October source/full suites recorded 81/380 tests. The initial Render build success concerned source `f929df5763cb8d37c3958c9c6fa9a4b37e469007`, not the later functional deployment.
- The original Groq transport failure returned Cloudflare 403/1010 for the default Python client. An anonymous application User-Agent diagnostic reached credential validation with HTTP 401; that response did not prove authentication. The User-Agent fix was published in `69102a29aa68f4ecea77f7861636ece9a2e7b69f` and passed 289 tests per platform in [run 37820609935](https://github.com/seypherWork/affinityqa/actions/runs/37820609935). Two subsequent diagnostic captures each preserved one authenticated packet before stopping on the second response under the previous global-fingerprint contract; neither was a full case. All attempts remain retained.
- The minimum evidence closure contained 382 files and passed 54 in-process recorded selections on 6 October; its Windows extraction and refusal to overwrite an existing destination were verified. Those records did not establish Linux hosting. The later hosted Linux/restart evidence is listed above.
- Historical cultural failures remain FAIL. None of the transport, replay, completed CI or offline results changes their thresholds or establishes full jury readiness.
