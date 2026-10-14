![AffinityQA — Follow the profile. Prove the recovery.](docs/images/hero.svg)

# AffinityQA

**Follow the profile. Prove the recovery.**

AffinityQA helps engineers catch personalization incidents that ordinary output checks miss. It follows an explicit musical interest through Qloo context, an agent's request routing and its cache, diagnoses the supported fault, applies a repair and checks the recovery against a healthy reference.

[Open the hosted workspace](https://affinityqa-review.onrender.com/demo) · [Judge walkthrough](docs/DEMO-GUIDE.md) · [Engineering review](docs/CLOUD-ENGINEERING-REVIEW.md) · [Acceptance record](docs/JUDGE-ACCEPTANCE.md)

## Review the product

| Path | What you can inspect | Evidence boundary |
| --- | --- | --- |
| **Recorded repair** | Choose an incident; follow Detect, Diagnose, Repair and Verify; compare the requested profile, consumed context and healthy output | Replays a genuine captured experiment; zero new Qloo/model calls |
| **New individual case** | Open a private visitor session; review musical interests and film preferences; confirm artist identities; inspect results and the selected verification | Uses the owner's providers when enabled; review the displayed plan and limits before starting |

The hosted workspace needs a browser. Judges do not install Docker, run a local model or supply API keys. Start with the recorded repair; the [walkthrough](docs/DEMO-GUIDE.md) gives the short click path and the separate fresh-case path.

## The integration problem

A plausible movie list can belong to the wrong taste profile. AffinityQA makes the profile chain inspectable and checks three controlled incidents:

| Incident | Supported diagnosis | Repair |
| --- | --- | --- |
| A cache key omits the profile | `CACHE_OMITS_PROFILE` | Bind the cache to profile identity |
| An old profile reaches the agent | `STALE_PROFILE` | Restore the requested profile |
| Qloo context belongs to another profile | `WRONG_TOOL_PROFILE` | Bind the tool context to the request |

Repairs affect the supported adapter and session/cache configuration. They are checked against healthy behavior and legitimate cache reuse.

![Architecture and evidence boundaries](docs/images/architecture.svg)

Qloo supplies real cross-domain movie context for musical interests. That context is consumed by the tested agent, so its identity and routing boundary can be tested. Movie preferences remain explicit user inputs; Qloo affinities are not individual ground truth.

## Verified engineering and live status

**Tested runtime: 14 October 2026.** The hosted service runs [`2c2f28a`](https://github.com/seypherWork/affinityqa/commit/2c2f28a9866920031c84779a38af340e3a724966). Discovery v3 validates raw artist-search rows before projecting selectable musical identities, collapsing only identical musical candidates while retaining the raw responses and rejecting conflicting identities. Interrupted progress observation can recover without starting the job again.

[CI run 38472962653](https://github.com/seypherWork/affinityqa/actions/runs/38472962653) passed **479 Python tests on Windows and 479 on Ubuntu**, type checking and production export. Three Linux browser regressions used synthetic providers. Their HTTP verification check is separate from the genuine native-browser acceptance below.

**One complete real hosted journey passed in Brave on Windows.** A declared engineering visitor selected Sade and Nine Inch Nails, used Get Out as a known favorite and Everything Everywhere All at Once as an exclusion for both profiles, reviewed the plan, confirmed the returned identities and obtained five eligible films per profile. Case `20261014T144251Z-c1eb0039` completed with **four Qloo requests and two Groq model attempts**. Its native JSON download was physically saved and checked; reloading and restoring the same session recovered the same completed case and plan, preference, intent and delivery fingerprints without another capture. An independent local review checked the retained observations and downloaded file.

This is bounded technical acceptance, not a human preference study. Both top-five lists equalled the same-input Qloo baseline. Cultural quality remains **NOT_VALIDATED**, with **zero verified human participants**. Remote causal attribution for the separate 39-decision campaign remains **INCONCLUSIVE**. A **BLOCKED** tested-recommender release is an evaluation result; it does not mean that the diagnostic application is unavailable.

The original v2 case `20261012T230633Z-8a5793a9` remains PARTIAL after two Qloo searches and zero model calls. Its raw responses and consumed admission were preserved. The successful v3 case is a separate trial; no historical result or threshold was rewritten.

Judge access is browser-based and free to the reviewer. New cases use the owner's Groq Free and Qloo capacity; application admissions do not reserve provider quota. Retained cases and recorded repairs remain inspectable when new execution is unavailable. The owner must maintain testing access through the judging period; this one-case acceptance cannot guarantee future capacity. [Detailed acceptance and limits](docs/JUDGE-ACCEPTANCE.md).

The source also includes [repeatable reviewer access](docs/PUBLIC-REPEATABLE-CASES.md):
multiple plans in the same ownership session, a durable provider-capacity queue,
explicit recovery provenance and a separate store with read-only historical
cases. Activating this mode is a separate deployment step. It keeps Groq Free;
it does not promise unlimited provider capacity or change evaluation gates.

## Run the source checks

CI used Python **3.13.16 on Windows**, **3.12.14 on Ubuntu 24.04**, Node.js **24.19.0** and pnpm **11.25.0**.

**Windows · PowerShell**

~~~powershell
& "C:\path\to\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-backend.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

Use your installed Python 3.13 executable in the first command.

**Linux**

~~~bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-backend.lock.txt
.venv/bin/python -m unittest discover -s tests -v
~~~

**Web build · either platform**

~~~text
cd web
npx --yes pnpm@11.25.0 install --frozen-lockfile --ignore-scripts
npx --yes pnpm@11.25.0 typecheck
npx --yes pnpm@11.25.0 build
cd ..
~~~

Dependency installation requires registry access. [Full source setup](docs/PUBLIC-CODE-QUICKSTART.md) covers the local preview. Without matching owner-supplied recorded evidence, that preview reports UNAVAILABLE; public source contains no fabricated replacement results, provider captures or credentials. The hosted link is the judge entry point.

For synthetic browser regressions on Linux, after the web build:

~~~text
cd web
npx --yes pnpm@11.25.0 exec playwright install --with-deps chromium
npx --yes pnpm@11.25.0 test:recovery
npx --yes pnpm@11.25.0 test:case-journey
~~~

## Project map

| Area | Contents |
| --- | --- |
| `src/affinityqa/` | Capture protocols, diagnostics, supported repairs, independent file verifiers and retained case store |
| `web/` | Jury workspace and private review interface |
| `tests/` | Synthetic contract, integrity and failure regressions; browser scenarios |
| `scripts/` | Source packaging, server entry points, verification and read-only diagnosis |
| `deployment/` | Render build/start instructions and explicit owner configuration |
| `docs/` | Walkthrough, acceptance, protocol contracts and provenance |

Existing storage needs the reviewed, stopped-store continuation in [PUBLIC-NEW-CASES.md](docs/PUBLIC-NEW-CASES.md) when manager sources change. Preserve sessions, receipts, original capture paths and consumed admissions; do not reset them to make a deployment pass.

## License and data

Original AffinityQA code is **MIT licensed**; see [LICENSE](LICENSE). Qloo data, model decisions, models and third-party assets retain their own terms. Raw captures and provider credentials remain private. [Licensing scope](docs/LICENSING.md) · [Asset provenance](docs/ASSET-PROVENANCE.md)
