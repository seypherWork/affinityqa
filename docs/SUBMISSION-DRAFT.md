# AffinityQA — submission draft

**Internal review draft · 8 October 2026. Not submitted.** The [functional hosted application](https://affinityqa-review.onrender.com) uses tested runtime/backend code revision `457fcace665b29a206840cedf24bceac56865b8f`. One genuine hosted case completed with 39 Groq decisions, four Qloo responses, integration **PASS**, nine observed recoveries and causal attribution **INCONCLUSIVE** under 25 distinct known backend fingerprints. A real restart retained the case, evidence, session and consumed admission; browser reload restored the nine fault/repeat views without a new capture. Functional acceptance covers this one case and its retention. Independent cultural evaluation and useful judge capacity remain pending. Full jury gate: **NO-GO**. See [the acceptance record](JUDGE-ACCEPTANCE.md).

## Project name and tagline

**AffinityQA — Follow the profile. Prove the recovery.**

Find the integration faults that make personalized agents use the wrong taste profile.

## Elevator pitch

AffinityQA helps engineers find and repair the integration faults that make personalized agents ignore a change in taste. It follows an explicit musical interest through Qloo cultural context, agent routing and caching, then shows whether a supported repair restores the agent's healthy behavior.

## The problem

A movie-discovery agent can produce valid, plausible recommendations for the wrong profile. Ordinary output-schema checks pass, while a stale cache, an old request profile or a mismatched tool response silently carries earlier context forward.

Our first audience is the engineer deciding whether to release that agent. A plausible movie list cannot show which profile the pipeline used. An observable incident, a supported diagnosis and a checked repair make that decision inspectable.

## What we built

AffinityQA is a web application with a Screening room, case library and evidence archive. The hosted reviewer lets a judge inspect and replay a previously captured incident and its repair without a local model or personal provider key. Its current mode is explicitly recorded: the review itself makes no new Qloo or model calls.

The causal test keeps a twenty-movie catalog fixed and changes one explicit artist interest. Qloo supplies real, profile-bound movie context consumed by the agent. The runner exercises three controlled faults: a cache that omits profile identity, a stale transmitted profile and a tool response bound to the wrong profile. Supported repairs change session routing or cache configuration; they do not rewrite arbitrary source code.

The original capture obtained fresh local-model decisions before and after repair. The hosted reviewer now runs the routing, diagnosis and repair workflow against those recorded decisions. Healthy controls and legitimate cache reuse remain part of the checks. Partial, failed and inconclusive evidence is retained.

A separate new-case interface and Groq operator are enabled in the hosted deployment. A genuine browser-started case completed all unchanged integration checks, and its saved case survived a service restart and browser reload. Its integration recovery remains separate from inconclusive causal attribution. An earlier direct remote case has its own independently audited record; the two runs are not combined into independent-user evidence.

## Why Qloo matters

Qloo is an actual tool input in the tested agent. Its API supplies movie affinities for an explicit musical interest across a fixed catalog. That cultural dependency has an identity and routing boundary that can be observed; substituting another profile's context creates a concrete personalization incident.

The demonstrated claim is integration integrity: whether the intended profile's cultural context reaches the decision process and whether a supported repair restores the checked behavior. The evidence does not establish that the recommender predicts an individual's preferences or outperforms all LLM-only alternatives.

## What is demonstrated today

| Demonstration | Verified result | Interpretation |
| --- | --- | --- |
| Original real causal capture | 18/18 controlled incident cases; 234 local-model decisions; 24 Qloo observations; 54 recoveries | Six profile pairs, three fault types and three repeats; controlled repeats, not independent users |
| Hosted recorded reviewer, 8 October before activation | All 54 HTTPS selections and 324 strict checks passed; private-route, origin and busy/recovery checks passed | Recorded journey at source `457fcace665b29a206840cedf24bceac56865b8f`; no new provider calls during replay |
| Genuine hosted case, 8 October | 39 Groq packets; four fresh Qloo samples; integration PASS 3/3, each with nine checks and three repeats; nine recoveries; 841.627 s; 57,600 tokens | Hosted run `20261008T190353Z-772b6659`; 25 distinct known fingerprints, none absent; causal INCONCLUSIVE |
| Hosted restart and browser restoration | 62 case-file hashes unchanged; server verification COMPLETE; same session and case restored with all nine fault/repeat views and no new capture | One observed case; consumed cumulative admission retained; independent consistency review of operator-reported restart evidence |
| Earlier hosted Linux cache/restart, 7 October | 54 recorded selections; 382 evidence hashes bound and preserved across service-process restart | Prior source `e08ddf2a7b7751b07b9c0b4635ad838247c44c00`; separate historical restart evidence |
| Tested runtime/backend code engineering | 295 source-only tests on each of Windows and Ubuntu, plus source allowlist, frontend type checking and build | [CI run 37824994293](https://github.com/seypherWork/affinityqa/actions/runs/37824994293) for code revision `457fcace665b29a206840cedf24bceac56865b8f`; later documentation revisions are separate |
| Earlier direct remote v3 case and audit | 39 validated Groq decisions; four fresh Qloo responses; all three incidents passed nine checks and three repeats; nine recoveries; independent audit VERIFIED_COMPLETE | Direct run `20261008T182536Z-edb5fd04`; known Björk/Bad Bunny request; 27 known fingerprints; integration PASS and causal INCONCLUSIVE |
| Targeted remote v3 engineering | 124 offline fixture tests passed; independent source/bounded-execution GO; 14 published files match the reviewed delta | Offline regressions, source review and publication are separate from the genuine run and hosted acceptance |

The original 24 Qloo observations comprise 19 new requests and five reused search observations with provenance. The policy, repeats and noise barrier remain frozen. Earlier cultural experiments remain visible: the 13/14 development result and independent 4/6 movie trial both failed their overall gates. No threshold or failed result has been relabelled.

## New-case acceptance still required

The previous remote contract stopped when a later valid Groq response reported a different backend fingerprint. Published v3 records an optional fingerprint for every validated response and separates integration checks from causal comparability.

All nine integration checks, all three mandatory faults and three repeats remain required. A full sample contains 39 validated model decisions. Causal **PASS** requires integration **PASS** and 39 known, identical observed fingerprints. Integration **PASS** with varied or absent fingerprints produces **INCONCLUSIVE** attribution; a partial capture is **NOT_EVALUATED**. Matching observed fingerprints do not attest immutable model weights.

The earlier direct run `20261008T182536Z-edb5fd04` completed at **18:39:37 UTC** on 8 October. Its separate verifier reported **VERIFIED_COMPLETE** at **18:40:49 UTC**, checking 39 packets, four Qloo samples, protocol and arithmetic. All fingerprints were present, but 27 distinct values prevented stable-backend comparability. Its result was integration **PASS**, behavioral **OBSERVED_RECOVERY** and causal **INCONCLUSIVE**, with no retry, resume, model substitution or schema fallback.

An independent auditor reviewed the actual remote run at **18:46:38 UTC**, re-ran the recorded-file verifier and checked the source, plan, admission and process bindings. The audit confirmed complete observed integration evidence while retaining causal INCONCLUSIVE and cultural NOT_VALIDATED.

The separate hosted job `20261008T190344Z-a49a92a0`, run `20261008T190353Z-772b6659`, completed from **19:03:53.159 to 19:17:54.786 UTC**, taking **14 min 1.627 s**. It obtained 39 Groq decisions and four Qloo responses and passed all three fault cases, with nine observed recoveries. Its 25 distinct known fingerprints produced causal INCONCLUSIVE. The selected result was independently checked; an actual service restart preserved all 62 case-file hashes and the single consumed admission. Browser reload restored the same case and all nine fault/repeat views without another execution. A scoped independent supplement checked that restart/restoration observations were consistent with the selected result; the reviewer did not independently repeat remote UI or private hash checks.

**Still pending:** independent cultural evaluation and useful judge capacity through evaluation. The hosted case consumed **57,600 tokens**. At the observed shared **200,000-token daily budget**, approximately three comparable complete cases fit before other traffic; this is arithmetic, not guaranteed or reserved capacity. Anonymous sessions are not verified people, and the application's cumulative 100-execution admission policy is separate from provider quota.

## Audience, impact and limits

The demonstrated use case is an engineer debugging a movie-discovery agent whose context silently belongs to an earlier profile. AffinityQA exposes the chain from the requested artist to the Qloo context and decision, then provides a reproducible comparison against healthy behavior.

We have not measured adoption, time saved, user satisfaction or production incident reduction. Results cover three deliberately injected faults in the tested adapter. They do not establish general bug detection, autonomous code rewriting or independent cultural recommendation quality.

There are **zero verified human preference labels**. Ratings from **two real people for the twenty-movie catalog** have been requested and remain pending. The cultural gate remains **NOT_VALIDATED** and promotion of the tested recommender remains **BLOCKED**. Those gates are separate from the recorded diagnostic application's functional evidence.

## How it is built

Python and FastAPI handle request contracts, trace checks, bounded repairs, evidence verification and recorded execution. Next.js, React and TypeScript provide the reviewer interface. The original capture used a local Qwen model through Ollama and the Qloo API; the candidate remote operator uses Groq.

Public source excludes credentials, model weights and raw Qloo/provider captures. Original project code is MIT licensed, Copyright (c) 2026 Seypher. Provider data and other third-party materials retain their separate rights.

## Reviewer access

Open the [hosted application](https://affinityqa-review.onrender.com). It requires no judge provider key or installed model. Its tested runtime/backend code is `457fcace665b29a206840cedf24bceac56865b8f`; recorded replay and genuine new cases retain separate execution labels. The genuine hosted case, verification, service restart and saved browser-case restoration have been observed. This one-case functional acceptance does not establish availability for every user or through the judging period.

The earlier recorded browser review has bounded desktop, keyboard and mobile checks. The 8 October recorded journey passed 54 HTTPS selections, 324 strict checks and origin/private-route and busy/recovery guards. The later hosted case and restart have their own evidence. Continued usable capacity through evaluation remains unverified; the recorded and hosted checks provide no many-user benchmark or fixed completion promise.

The optional private local review package contains compiled interface assets and separately authorized evidence. A source-only installation displays **UNAVAILABLE** until matching authorized evidence is supplied. Raw evidence is not made publicly downloadable by the restricted demo.

## Two-minute walkthrough of the recorded capture

1. **0:00–0:20 — Understand the request.** Open the Screening room. Show the two explicit musical interests, fixed movie catalog, selected evidence run and recorded execution mode.
2. **0:20–0:50 — Inspect the incident.** Select a cache/profile/tool fault. Compare requested profile, transmitted profile, selected Qloo context and returned decision.
3. **0:50–1:20 — Review the repair.** Show the supported repair and before/after decisions. Explain that the original capture obtained fresh outputs; this replay makes no new provider calls.
4. **1:20–1:45 — Check the controls.** Show healthy behavior, legitimate cache reuse, the frozen noise barrier and full denominator. Keep failures and inconclusive states visible.
5. **1:45–2:00 — Inspect provenance and limits.** Open **Protocol & provenance** for run, policy and receipt fingerprints. Distinguish causal recovery from cultural quality and point to retained failed experiments.

An optional video must show the demonstrated execution mode accurately. See [DEMO-GUIDE.md](DEMO-GUIDE.md) for the detailed click path and the separate new-case journey.

## Submission readiness

The official deadline is **30 October 2026 at 23:45 EDT**. Judging runs **2–16 November 2026**. The four equally weighted criteria are technological implementation, design, potential impact and quality of the idea. These dates and requirements were checked against the [official rules](https://qloo.devpost.com/rules) on 8 October 2026; no outcome or ranking is predicted.

Before submission, bind the final reviewed documentation, demo configuration and English materials to tested runtime code and actual evidence. The one-case hosted and restart checks are complete; independent cultural evaluation and usable free judge access through evaluation remain pending. Maintain the reviewed Qloo scope and applicable model-provider terms. Keep raw provider evidence outside public Git.

The 8 October review of official Qloo materials supports private server caching and attributed, contextual results. Applying the documented external-model workflow to the minimum affinity context needed by this project is an operational interpretation, not a universal license for Groq or redistribution of provider data. No additional individual email-approval requirement was identified for this limited scope. Raw-corpus redistribution, training rights and MIT licensing of Qloo outputs are not claimed. [Official Qloo guidance](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide#can-i-cache-qloo-api-responses-in-my-app) · [Safe use](https://github.com/qloo/qloo-hackathon-kit/blob/main/docs/SAFE_USE.md)

This draft is for review and submits no entry. Code publication, engineering checks and one-case functional acceptance do not satisfy the remaining capacity or cultural gates.

## Appendix: retained development history

- Development run `20261004T114624Z-a1722335` recorded 39 real local-model decisions, two Qloo requests and nine recoveries across three faults and three repeats for one known profile pair. It was development evidence, not nine independent users.
- Private Windows v9, verified on 6 October, installed 17 locked dependencies and passed 309 fixtures, zero skips, 54 recorded selections, 19 API views, 41 static hashes and four browser panels. The failed initial environment and observed interrupted listener stop remain recorded.
- The earlier 4 October constrained Linux rehearsal measured approximately 520 ms p95 and 252.01 MiB peak memory on development-PC Linux tmpfs. It was local recorded replay, not Render performance or a cloud inference benchmark. Earlier slower bind-storage and failed source-count attempts were retained.
- The initial Groq 403/1010 failure was diagnosed through anonymous client-header comparison. The application User-Agent fix passed 289 tests per platform in published CI; two later authenticated diagnostic captures each stopped on a second response under the former global-fingerprint rule. Those partial attempts remain preserved separately from the complete v3 run.
- Historical 13/14 and 4/6 cultural failures remain FAIL; cultural quality remains NOT_VALIDATED and recommender release BLOCKED.
