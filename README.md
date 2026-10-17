![AffinityQA — Follow the profile. Prove the recovery.](docs/images/hero.svg)

# AffinityQA

**Follow the profile. Prove the recovery.**

AffinityQA helps engineers catch personalization incidents that ordinary output checks miss. It follows an explicit musical interest through Qloo context, an agent's request routing and its cache, diagnoses the supported fault, applies a repair and checks the recovery against a healthy reference.

[Open the hosted workspace](https://affinityqa-review.onrender.com/demo) · [Judge walkthrough](docs/DEMO-GUIDE.md) · [Engineering review](docs/CLOUD-ENGINEERING-REVIEW.md) · [Acceptance record](docs/JUDGE-ACCEPTANCE.md)

## Review the product

**Local extension tested, 17 October:** the separate **START WITH A FILM**
route confirms one film title and year, retrieves a new Qloo candidate pool for
that case and makes one Groq ranking with individual model interpretations.
Its output is not restricted to the comparative twenty-film task. Two real local
captures completed with Qloo and Groq Free: John Wick (2014) and Scary Movie (2000),
twenty candidates per case, forty distinct candidates in total. They used four
Qloo requests and two Groq sends altogether. A local quota wait interrupted the
second case before its model send; it completed from saved Qloo observations with
no extra Qloo requests. Both orders matched their Qloo baselines. This establishes
bounded technical compatibility, not preference improvement or hosted availability
of this new route. [Contract and limits](docs/OPEN-FILM-DISCOVERY.md).

**Deployed discovery interface, verified 17 October 2026:** enter musical interests,
optionally search favorite films, confirm exact identities and inspect five films
per taste scenario. One shared Groq response ranks both scenarios; older cases
retain their original contracts. The full integration experiment and recorded
repair remain inspectable. [Journey and evidence boundaries](docs/FAST-TASTE-REVIEW.md).

| Path | What you can inspect | Evidence boundary |
| --- | --- | --- |
| **Diagnosis & evidence** | Choose an incident; follow Detect, Diagnose, Repair and Verify; compare the requested profile, consumed context and healthy output | Replays a genuine captured experiment; zero new Qloo/model calls |
| **Discover films** | Open a private visitor session; review musical interests and film preferences; confirm artist and film identities; inspect results and the selected verification | Uses the owner's providers when enabled; review the displayed plan and limits before starting |

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

**Hosted runtime `1bb98f8`, checked 17 October 2026.** The cinematic discovery
interface and shared model pass are deployed. Two real cases completed in one
ownership session; their native downloads and same-session recovery passed.
All earlier cases, original evidence and the existing hosting plan were retained.
Groq remains free. [Dated acceptance and file fingerprints](docs/JUDGE-ACCEPTANCE.md).

| Check | Observed result | Boundary |
| --- | --- | --- |
| Engineering | [CI 38973760142](https://github.com/seypherWork/affinityqa/actions/runs/38973760142) passed Python checks, frontend types and production export on Windows and Ubuntu. All seven Linux browser command steps passed. | Browser checks use synthetic providers; Windows browser steps were skipped. |
| Confirmed film inputs | Sade + Gladiator (2000), Nine Inch Nails + The Matrix (1999); six fresh Qloo requests and one shared Groq response; five eligible films per scenario. | The actual titles and years were explicitly confirmed. This film-input trial searched full titles; the separate Matrix search is listed below. |
| Abbreviated film query | A separate identity-only search for **Matrix** returned **The Matrix (1999)** first, with the same canonical Qloo identity as the earlier full-title search. | Three fresh Qloo searches, zero Groq calls; stopped before confirmation. Not general typo or partial-title coverage. |
| Artists-only case | Four fresh Qloo requests and one shared Groq response, followed by five eligible films per scenario. | These two scenarios are correlated projections of one observation. |
| Timing | Confirmation admission to COMPLETE: 9.030 and 6.492 server seconds, without provider-capacity wait in these two cases. | Excludes human selection, page loading and browser observation delays; no future latency guarantee. |
| Persistence | Both native JSON downloads physically saved and verified; reload and restore recovered both completed cases. | Saved evidence is not new inference. |

All four delivered lists matched their same-input Qloo baselines. This proves
bounded integration, not improvement over Qloo or individual satisfaction.
Cultural quality remains **NOT_VALIDATED**, with **zero verified human participants**.
The separate historical 39-decision remote campaign remains **INCONCLUSIVE**.
Its **BLOCKED** tested-recommender release is distinct from availability of the
diagnostic application. Historical failures and thresholds remain preserved.

No account, installation or judge provider key is needed. Repeatable sessions
remove the lifetime application count cap, not shared provider quotas, storage
limits or uncertainty. New work can wait, pause or stop. Recorded repairs and
saved cases remain separate evidence paths; no unlimited free inference or
future uptime is promised. [Access contract](docs/PUBLIC-REPEATABLE-CASES.md).


<details>
<summary>Historical hosted status through 15 October 2026</summary>

The dated text below is preserved from the earlier source snapshot. Its runtime,
request counts and navigation refer to those earlier versions.

## Verified engineering and live status

**Tested runtime: 15 October 2026, after the 21:11:49 UTC deployment.** The hosted service runs [`ab32065`](https://github.com/seypherWork/affinityqa/commit/ab32065d4e5d45fe73527e9ba925c8c85331db3e), with **repeatable reviewer access enabled**. A visitor can complete another case in the same ownership session. There is no lifetime application plan or execution count cap; durable queuing, storage safeguards and shared provider quotas still apply. Groq remains on its free plan.

[CI run 38801909704](https://github.com/seypherWork/affinityqa/actions/runs/38801909704) passed **546 Python tests on Windows and 546 on Ubuntu**, type checking and production export. All four Linux browser commands passed using synthetic providers. Those regressions are separate from the real hosted acceptance below; they were not rerun during the live journey.

**A new Portishead / Bad Bunny case completed in the existing Windows/Codex browser session.** Both profiles declared Get Out as a known favorite and Everything Everywhere All at Once as an exclusion. The visitor reviewed the plan, explicitly confirmed both artist identities, waited through provider queuing and recovered the same completed case after a reload. It used **4 fresh Qloo HTTP requests and 2 fresh Groq decisions**, with no cache hit or retry of sent failed/unknown work. Each profile received five unique new films respecting both constraints. The native **6,693-byte JSON download** was physically saved, parsed and independently checked. [Case identifier, file hashes and boundaries](docs/JUDGE-ACCEPTANCE.md).

All three recorded repair types also passed their six replay checks on this deployment with **zero new Qloo/model calls**. These are replays of saved experiments, not additional fresh provider trials. The three earlier repeatable cases and receipts remain intact, including the original partial case. After the new journey, **792 pre-existing ordinary files** were byte-identical and **80 pre-existing database rows** were checked: 74 identical and six quota/sequence rows checked against their permitted advances. New case files and rows are counted separately; volatile database sidecars are not treated as historical evidence files.

**Earlier acceptance on `32406c2`, also on 15 October:** two consecutive Sade / Nine Inch Nails cases completed in one session. The first used four fresh Qloo requests and two Groq decisions; the second reused four saved Qloo responses and made two fresh Groq decisions. Both native downloads and recovery of the first case passed. Their complete dated evidence and the retained failed case remain in the [acceptance record](docs/JUDGE-ACCEPTANCE.md).

This is bounded technical acceptance, not a preference study. Both latest top-five lists equalled the same-input Qloo baseline. Cultural quality remains **NOT_VALIDATED**, with **zero verified human participants**. Remote causal attribution for the separate historical 39-decision campaign remains **INCONCLUSIVE**. A **BLOCKED** tested-recommender release is an evaluation result; it does not mean that the diagnostic application is unavailable. Historical quality failures and thresholds are preserved.

Judge access requires no account, installation or provider key. Shared Qloo and Groq Free capacity is unreserved: new work may wait, pause or stop, while saved results and recorded repairs remain readable. There is no promise of unlimited free inference or future uptime. The owner must maintain free testing access through judging. [Repeatable access contract](docs/PUBLIC-REPEATABLE-CASES.md) · [Judge walkthrough](docs/DEMO-GUIDE.md).

</details>

## Run the source checks

CI used Python **3.13.16 on Windows**, **3.12.14 on Ubuntu 24.04**, Node.js **24.19.0** and pnpm **11.25.0**.

**Windows · PowerShell**

~~~powershell
& "C:\path\to\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-backend.lock.txt
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-repeatable.lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

Use your installed Python 3.13 executable in the first command.

**Linux**

~~~bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-backend.lock.txt
.venv/bin/python -m pip install --require-hashes -r requirements-repeatable.lock.txt
.venv/bin/python -m pip check
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
