# AffinityQA — submission draft

Internal review draft, 6 October 2026. Not submitted or published. The current private v9 recorded-review package is verified on Windows. The public repository main branch was observed at `e08ddf2a7b7751b07b9c0b4635ad838247c44c00`; this local candidate is not a claim that the current v9 files have been published there. New real cloud cases, v9 Linux acceptance, the hosted judge journey and third-party data permissions remain pending. See [the acceptance record](JUDGE-ACCEPTANCE.md).

## Project name and tagline

**AffinityQA — Follow the profile. Prove the recovery.**

Find the integration faults that make personalized agents use the wrong taste profile.

## Elevator pitch

AffinityQA helps engineers find and repair the integration faults that make personalized agents ignore a change in taste. It follows an explicit musical interest through Qloo cultural context, agent routing and caching, then shows whether one supported repair restores the agent's healthy behavior.

## The problem

A movie-discovery agent can produce valid, plausible recommendations for the wrong profile. Ordinary output-schema checks will pass. The user changes their musical interest, but a stale cache, an old profile or a mismatched tool response silently carries the previous person's context forward.

Our first audience is the engineer deciding whether to release that agent. A plausible movie list cannot show which profile the pipeline actually used. A reproducible incident, an observable cause and a checked repair make that release decision inspectable.

## What we built

AffinityQA is a web application with a Screening room, case library and evidence archive. Its current private Windows package provides a verified recorded incident-and-repair journey. A separate new-case interface and remote service have passed synthetic integration checks, but no new real cloud case or external hosted acceptance is established. Its causal test keeps a 20-movie catalog fixed and changes one explicit artist interest. Qloo supplies a real, profile-bound movie-context response consumed by the local model.

The runner exercises three controlled faults: a cache that omits profile identity, a stale transmitted profile, and a tool response bound to the wrong profile. During the original capture, it obtained fresh model decisions before and after each supported session-policy repair. The reviewer demo now executes the routing, diagnosis and repair workflow against those recorded decisions, without making new Qloo or model calls. Healthy controls must remain unaffected, and legitimate cache reuse must keep working.

The evidence archive preserves failed attempts and separates integration recovery from recommendation quality. The application is built with a Next.js/React interface and a Python/FastAPI backend; the captured agent uses the installed local Qwen model through Ollama.

## Why Qloo matters

Qloo is an actual tool input in the tested agent, not decoration in its explanation. Its API provides movie affinities for an explicit musical interest across a fixed catalog. That introduces a cultural dependency whose identity and routing can be observed—and whose accidental substitution creates a concrete personalization incident.

AffinityQA verifies that the intended profile's cultural context reaches the decision process. The current evidence supports that narrower integration claim. It does not establish that this recommender outperforms every LLM-only alternative or predicts an individual's preferences.

## What is demonstrated today

Development run `20261004T114624Z-a1722335`, checked by the separate verifier, recorded 39 real local model decisions and two Qloo requests. All three controlled fault cases passed their causal checks, with nine observed recoveries across three repeats per fault. These are development observations from one known profile pair, not nine independent users.

The new six-pair causal validation passed the separate verifier: 18 of 18 incident cases, 234 real local model executions, 24 total Qloo queries and 54 observed recoveries across three repeats per fault. The policy and noise barrier remained frozen; every repaired top-five decision matched healthy behavior. The 24-query total comprises 19 new requests and five reused search observations with recorded provenance. These are controlled repeats, not independent user trials. Earlier quality experiments remain visible, including the separate movie-quality trial that passed four of six cases and therefore failed its overall gate. We do not relabel those results as successful quality validation.

## Current private v9 verification — Windows, 6 October 2026

A new archive extraction installed 17 locked dependencies from the official Python package index and started the actual default server with Python 3.12.14. Its installed interpreter passed **309 technical fixture tests, zero skips**, and the installation verifier checked **54 recorded pair/fault/repeat selections**. An actual browser traversed all four panels; 19 read-only API views and all 41 static files matched the archive. New inference was disabled. These observations concern this private Windows artifact, not Linux, Render, genuine cloud inference or cultural quality.

The first environment attempt failed during ensurepip in the sandbox temporary directory and was retained. A distinct clean extraction succeeded using workspace TMP/TEMP for that child process only. After testing, the owned console was interrupted and the browser refused a new connection; no orderly exit-zero or complete descendant-process audit is claimed.

## Historical installation and Linux rehearsal — earlier artifact, 4 October 2026

The following earlier measurements are retained for context. **They do not validate Linux or hosted performance of the current v9 artifact.**

A clean judge installation, restart and all 54 recorded selections passed. A separate Linux HTTP rehearsal completed the same 54 selections with six checks per selection, rejected a foreign-origin request, kept private routes inaccessible, handled concurrent requests with one valid response and one busy response, and recovered afterward.

The Linux rehearsal imposed 0.5 CPU, 512 MiB of memory and zero swap. With the reviewed source and evidence copied to local Linux tmpfs storage, the observed p95 was approximately 520 ms and peak memory was 252.01 MiB, including the evidence copies, server and test client. These are local measurements on the development PC, with no new inference or Qloo request in the replay. They do not certify Render performance. An earlier Windows-bind rehearsal passed but had a p95 of approximately 23.31 seconds; both results and an intervening failed source-count guard remain preserved.

## Audience, impact and current limits

The demonstrated use case is an engineer debugging a movie-discovery agent whose context silently belongs to an earlier taste profile. AffinityQA gives that engineer a complete chain from the requested artist to the Qloo context and the decision, with a supported repair and a reproducible comparison against healthy behavior.

We have not measured adoption, time saved, user satisfaction or a reduction in production incidents. The current results cover three deliberately injected integration faults in the tested adapter. They do not establish general bug detection, autonomous source-code rewriting or independent cultural recommendation quality. The tested recommender's quality gate remains NOT_VALIDATED and its production promotion remains BLOCKED; those gates are distinct from the diagnostic application's functional review.

## How it is built

Python and FastAPI handle the request contracts, trace checks, bounded repairs, evidence verification and recorded execution. Next.js, React and TypeScript provide the Screening room, case library and evidence archive. The original real capture used the installed local Qwen model through Ollama and the Qloo API. The restricted reviewer application uses separately held authorized evidence; public source excludes provider captures and credentials. Original project code is MIT licensed, Copyright (c) 2026 Seypher; the grant excludes provider data and other third-party material.

## Reviewer access

The intended judge access is a functional externally hosted application, free to judges and requiring no personal provider key or installed model. The recorded incident review and the new remote case are distinct journeys. Only the private Windows recorded path has current real runtime evidence; the new-case path still requires approved account capacity, genuine inference and external acceptance. The service at `affinityqa-review.onrender.com` currently serves provisioning health only; it must not be presented as the functional demo. Add the final clickable demo link after the matching evidence is authorized, installed and externally verified.

The optional local judge package includes compiled interface assets and authorized recorded evidence. The verified clean installation uses Python 3.12.14 and locked dependencies; it does not require Node.js, Ollama or Qloo credentials. A separate source-only installation builds the code but displays UNAVAILABLE until an authorized matching evidence package is supplied. These installations are described separately, so a source preview cannot be mistaken for a verified demonstration.

## Two-minute interactive walkthrough of the recorded capture

1. **0:00–0:20 — Understand the request.** Open the Screening room. Show two explicit musical interests and the same candidate movie catalog. Identify the selected evidence run and its execution mode.
2. **0:20–0:50 — Inspect the incident.** Select the cache/profile/tool fault. Compare the requested profile, transmitted profile, selected Qloo context and returned decision. Explain which observed boundary is inconsistent.
3. **0:50–1:20 — Review the repair.** Show the supported repair and the before/after decisions. Explain that the original real capture obtained fresh repaired model outputs; the displayed recorded replay makes no new provider calls.
4. **1:20–1:45 — Check the controls.** Show healthy behavior, legitimate cache reuse, the frozen noise barrier and the full case denominator. A failure or an inconclusive result must remain visible.
5. **1:45–2:00 — Inspect provenance and limits.** Open **Protocol & provenance** for the run, policy and receipt fingerprints. Distinguish causal recovery from independent cultural quality. Point to retained failed experiments. Full receipts belong to the separately authorized local review package; the restricted demo does not expose raw evidence downloads.

This walkthrough uses recorded model decisions throughout. An optional video complements the functional application; it must identify that execution mode. See [the precise click path, narration and separate pending new-case path](DEMO-GUIDE.md). The public source repository is available; final external application access still requires verification. [Official submission requirements](https://qloo.devpost.com/)

## Submission readiness

An earlier public MIT source revision is available. Before submitting, verify that the final public revision includes the current code, necessary assets and accurate setup instructions. Supply the externally verified functional demo URL, resolve third-party display/transfer permissions and demonstrate useful free judge access through the end of evaluation. Keep raw provider captures outside public source. Complete the new real-case and hosted journey, and resolve the separately required cultural acceptance without changing historical thresholds. All submitted materials must be in English or include an English translation. The official deadline is 30 October 2026 at 23:45 EDT. [Official rules](https://qloo.devpost.com/rules)

The four equally weighted judging criteria are technological implementation, design, potential impact and quality of the idea. Our review package should make the causal incident easy to reproduce, the Qloo dependency easy to inspect and the supported claim easy to distinguish from unvalidated recommendation quality. No competition outcome is guaranteed. [Official judging criteria](https://qloo.devpost.com/rules)

Publication, submission and any external contact require the user's separate authorization. This draft performs none of those actions.
