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

**Tested runtime: 15 October 2026.** The hosted service runs [`32406c2`](https://github.com/seypherWork/affinityqa/commit/32406c295fa436476e42b6a5779b635d8493bc51), with **repeatable reviewer access enabled**. A visitor can complete another case in the same ownership session. There is no lifetime application plan or execution count cap; durable queuing, storage safeguards and shared provider quotas still apply. Groq remains on its free plan.

[CI run 38785730767](https://github.com/seypherWork/affinityqa/actions/runs/38785730767) passed **544 Python tests on Windows and 544 on Ubuntu**, type checking and production export. All four Linux browser commands passed using synthetic providers. Those regressions are separate from the real hosted acceptance below.

**Two consecutive real cases completed in one Windows/Codex browser session.** Both reviewed Sade / Nine Inch Nails with Get Out as a known favorite and Everything Everywhere All at Once excluded in both profiles. Each delivered five unique new films per profile, respecting both constraints. The first used **4 fresh Qloo HTTP attempts and 2 fresh Groq decisions**. The second reused **4 saved Qloo responses and made 2 fresh Groq decisions**. Both native JSON downloads were physically saved and verified. After a reload, restoring the same session recovered the first completed case, its plan and its saved result without a new capture. [Case identifiers, file hashes and boundaries](docs/JUDGE-ACCEPTANCE.md).

The rollout preserved all **297 files** in the historical store and all **11 files** of the original failed 15 October case, checked again after session restoration. The correction aligns the private artist-search cache with the existing versioned identity contract and makes the original partial receipt readable. It does not turn the failed case into a success, retry it or refund its consumed work.

This is bounded technical acceptance, not a preference study. Both top-five lists equalled the same-input Qloo baseline. Cultural quality remains **NOT_VALIDATED**, with **zero verified human participants**. Remote causal attribution for the separate 39-decision campaign remains **INCONCLUSIVE**. A **BLOCKED** tested-recommender release is an evaluation result; it does not mean that the diagnostic application is unavailable.

Judge access requires no account, installation or provider key. Shared Qloo and Groq Free capacity is unreserved: new work may wait, pause or stop, while saved results and recorded repairs remain readable. There is no promise of unlimited free inference or future uptime. The owner must maintain free testing access through judging. [Repeatable access contract](docs/PUBLIC-REPEATABLE-CASES.md) · [Judge walkthrough](docs/DEMO-GUIDE.md).

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
