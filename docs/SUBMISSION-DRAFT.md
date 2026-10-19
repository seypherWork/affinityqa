# AffinityQA — English submission update

Prepared 19 October 2026 for review of the existing submitted project. This text
has not been saved to Devpost. It does not create another submission.
The project began on 3 October 2026, as declared by the owner.

## Project name

AffinityQA

## Tagline

Follow the profile. Prove the recovery.

## Elevator pitch

An agent can return plausible films for the wrong taste profile. AffinityQA
traces Qloo context through agent requests and caches, diagnoses three supported
integration faults, applies the matching repair and verifies healthy recovery.

## Inspiration

A movie list can pass every format check and still belong to yesterday's
profile. A cache key or tool-routing mistake can quietly survive a change in
taste. We built AffinityQA for engineers who need to see which profile reached
the agent, what broke, what changed and what evidence supports recovery.

## What it does

The hosted application provides two complementary review paths:

- **Diagnosis & evidence:** select a captured incident and follow Detect,
  Diagnose, Repair and Verify. Compare the requested taste, consumed Qloo context,
  faulty output, supported repair and healthy reference. Replay uses saved real
  model decisions and makes zero new Qloo/model calls.
- **Film discovery:** start with a film or artist, optionally add a known
  favorite film in artist mode, review the plan and explicitly confirm the
  returned identities. Explore five films from an actual Qloo pool of up to
  100 candidates per case. An optional direction guides selection in that pool.

Open or restore a private visitor session, download the selected verification
and return to earlier cases without executing them again. Judges need no
installation, account, local model, personal API key or running creator PC.
Earlier twenty-film comparisons keep their original contracts and history.
Current outputs are films; artist/song recommendations and playback are not
implemented.

## How Qloo is used

Qloo resolves explicit artist/film identities and supplies cross-domain film
affinity context. That context reaches the agent and becomes part of the
inspectable request/tool/cache chain. The diagnostic experiment deliberately
breaks that chain in three ways: a cache key omitting the profile, a stale
request profile or another profile's Qloo context. The corresponding adapter,
session or cache repair is checked against healthy behavior and legitimate reuse.
This is a supported integration repair, not arbitrary source-code repair.

In the current discovery route, Groq Free / GPT-OSS 20B selects eligible
indices, and the server reconstructs canonical film identities. The model
supplies no plot or explanation prose. Cards display that film's saved Qloo
description, with language/missing-data labels, and observed images with a
fallback. Faithful metadata display is separate from independent film-fact or
taste validation. The optional direction is sent to the model, not as an
undocumented Qloo free-text query.

## How we built it

Python and FastAPI implement capture, diagnostics, supported repairs, independent
file verification and owned case storage. Next.js and TypeScript provide the
review interface. Persistent plans, confirmed identities, original observations,
failed attempts and verification receipts survive recovery.

The original controlled experiment used a local model. Hosted discovery uses
Groq Free with GPT-OSS 20B. A durable queue reserves request/token capacity before
dispatch and distinguishes fresh, reused and restored work. Repeatable sessions
remove a lifetime application count cap, not finite provider quotas or storage
safeguards. Sent failures or uncertain responses are not silently retried.

## Challenges we ran into

Real identity searches mixed artist, person and collaboration results. We
preserved explicit confirmation, prioritized exact musical matches and kept
other matches inspectable without exposing internal codes on ordinary screens.

Model prose also proved too weak a basis for film descriptions. The current
contract accepts indices only and reconstructs identity and literal descriptions
from the selected source. Original failures and earlier verification contracts
remain retained rather than rewritten as successes.

Recovery had to preserve accepted work after interrupted browser responses and
fresh-page session restoration. Private caches, versioned receipts, ownership,
CSRF and provider accounting remain part of the tested boundary.

## Accomplishments and verified results

The completed 18 October hosted acceptance used code `0faa96d`:

- Two real hosted trials, Eminem and John Wick (2014), each retained 100
  candidates and delivered five films. Together they used six actual Qloo HTTP
  requests and two Groq selections, without cache hits, unknown attempts or retry.
- Both native verification downloads were physically saved and checked; both
  completed cases restored on a fresh page in the same browser profile. Matching
  images and source descriptions were observed.
- Each of the three recorded repair types passed all six replay controls, with
  zero fresh Qloo/model calls.
- [CI 39163714448](https://github.com/seypherWork/affinityqa/actions/runs/39163714448)
  passed 723 Windows tests and 719 Ubuntu tests. Four native Windows tests were
  skipped on Ubuntu and passed on Windows. Types/export passed on both; ten
  Linux browser steps used synthetic providers. Windows CI browser steps were
  skipped, not counted as passes.
- Existing hosted history, evidence and consumed work were preserved under
  explicit pre/post checks and separately reviewed operational transitions.

These are bounded technical observations, not independent human participants,
proof of ranking improvement over Qloo or a guarantee for every future input.
[Exact dated acceptance and public file fingerprints](https://github.com/seypherWork/affinityqa/blob/main/docs/JUDGE-ACCEPTANCE.md).

## What we learned

Profile integrity, backend comparability and cultural quality require different
evidence. The supported diagnostic experiment can pass recovery checks while a
separate historical remote causal campaign remains **INCONCLUSIVE**. Cultural
quality remains **NOT_VALIDATED**, with **zero verified human preference
participants**. Role-play inputs remain synthetic; prior failures retain their
scores and thresholds. The historical evaluated-agent **BLOCKED** result is
separate from the diagnostic application's availability.

## What comes next

Independent human preference evaluation and broader controlled fault coverage
need their own evidence. The hosted review keeps saved results and a recorded
repair path available independently of new inference capacity. Groq stays free;
no unlimited throughput or future uptime is promised. Original code is MIT
licensed; provider data, models and third-party assets retain their own terms.
Raw captures, credentials and private stores are excluded from the public source.

## Links

- [Hosted diagnostic path](https://affinityqa-review.onrender.com/demo#recorded)
- [Hosted film discovery](https://affinityqa-review.onrender.com/demo#wide)
- [Public source and MIT license](https://github.com/seypherWork/affinityqa)
- [Judge walkthrough](https://github.com/seypherWork/affinityqa/blob/main/docs/DEMO-GUIDE.md)

## Owner review boundary

The existing project was observed as submitted on 19 October. Replacing its
public story requires the owner's final approval; this file has not done so.
The [official rules](https://qloo.devpost.com/rules), rechecked 19 October, set the
deadline at 30 October 2026, 23:45 EDT (31 October, 04:45 in Belgium).
Required materials remain in English. The
[official overview](https://qloo.devpost.com/) says a video is optional; the
functional externally hosted demo and open-source repository are the required
review surfaces. No new video is represented as completed.

<details>
<summary>Earlier English working drafts, retained verbatim; not the current story</summary>

# AffinityQA — English submission draft

English working entry, 15 October 2026, reconciled after the ab32065 hosted acceptance. Prepared for factual review; not submitted.

## Project name

AffinityQA

## Tagline

Follow the profile. Prove the recovery.

## Elevator pitch

A personalized agent can return a valid movie list for the wrong taste profile. AffinityQA traces Qloo context through agent requests and caches, diagnoses three supported integration faults, and checks whether a repair restores healthy behavior.

## Inspiration

A movie list can pass every format check and still belong to yesterday's profile. A stale cache or a mismatched tool response can silently survive a change in taste. We built AffinityQA to make that failure visible: which profile reached the decision, what broke, what changed, and what evidence supports recovery?

## What it does

Built for teams engineering personalized agents, the hosted workspace gives judges two complementary paths:

- **Recorded repair:** select a controlled incident and follow Detect, Diagnose, Repair and Verify. Compare the requested interest, consumed Qloo context, faulty output, repaired output and healthy reference. These genuine saved experiments can be replayed without new provider calls.
- **New individual case:** open a private browser session, declare two musical interests and optional film favorites or exclusions, review the plan, and explicitly confirm the artist identities returned by Qloo. Inspect five new films per profile, the original model ranking, the Qloo baseline and a downloadable verification receipt. This short preference route is separate from the controlled-fault campaign.

Reviewers can complete another case in the same session and restore their saved cases after a reload. They need no account, Docker installation, local model or API key. Fresh, cached and restored work are labelled separately. Musical interests supply context for film recommendations; song recommendations and music playback are not current functions.

## How Qloo is used

Qloo supplies real artist-identity candidates and cross-domain movie-affinity context for explicit musical interests. The agent consumes that context to rank a fixed twenty-film catalog. Known favorites guide both Qloo and the model; favorites and exclusions stay outside the delivered five.

The evaluator follows identity across the requested interest, transmitted model input, consumed tool context and output. Three deliberately injected incidents break that chain: a cache key omitting the profile, a stale request profile and another profile's Qloo response. Supported repairs change the adapter's session routing or cache configuration, then verification checks recovery against healthy behavior and legitimate reuse. It does not claim arbitrary source-code repair.

## How we built it

Next.js and TypeScript provide the review workspace; Python and FastAPI run the capture, diagnostics, repairs and file verifiers. Persistent storage retains plans, confirmed identities, original observations, failed attempts and selected verification receipts.

The original controlled experiment used a local model. The hosted operator uses Groq Free with GPT-OSS 20B. A durable provider queue reserves conservative request and token capacity before dispatch. Accepted work can be restored without resending it; exact Qloo context can be reused privately with explicit provenance. There is no lifetime application count cap, while shared provider quotas and storage safeguards still apply. Free inference is finite, and waiting estimates are not promises.

## Challenges we ran into

A real artist search contained mixed musical and nonmusical duplicate IDs. Discovery v3 validates raw rows before projecting selectable musical identities, collapses only identical musical candidates and rejects conflicting identities. A later live trial exposed a private-cache validator still applying the stricter ranking contract to those searches. We aligned cache semantics with the pinned versioned identity contract and repaired the reader for historical partial search receipts. The failed trials, original responses and consumed work remain intact.

The final engineering review also hardened restart handling for terminal jobs with unsent reservations and recovery after an ambiguous browser response. Original cases and consumed requests remain preserved.

We also separated application access from provider capacity. Repeatable sessions do not create unlimited model quota. The queue reports waiting, preserves accepted work and exposes fresh versus reused context rather than silently retrying sent failures or switching to a paid provider.

## Accomplishments and verified results

| Evidence | Observed result |
| --- | --- |
| Engineering checks | Runtime `ab32065`; [CI 38801909704](https://github.com/seypherWork/affinityqa/actions/runs/38801909704): 546 Python tests on each of Windows and Ubuntu, type checks, production export and four Linux browser commands with synthetic providers. CI is separate from the subsequent real-provider journey. |
| Real browser journey, 15 October after deployment | Case `20261015T211609Z-022dda74`: Portishead / Bad Bunny, explicitly confirmed artist identities, one existing Windows/Codex browser session, 4 fresh Qloo HTTP requests and 2 fresh Groq decisions. COMPLETE, with no retry of sent failed/unknown work. |
| Delivery, download and recovery | Five unique films per profile; Get Out favorite and Everything Everywhere All at Once excluded. An actual 6,693-byte native verification download was saved and checked. Reloading during provider waiting and restoring the same session recovered the same completed case without a new capture. |
| Preservation and recorded checks | All 792 old ordinary files remained identical; all 80 old database rows were checked: 74 identical plus six quota/sequence rows with permitted advances. Three older cases and receipts, including PARTIAL, remain intact. All three recorded repair types passed six replay checks each with zero new provider calls. |
| Original controlled capture, historical | Six artist pairs, three injected faults and three repeats: 18 controlled cases and 54 observed recoveries from 234 local-model decisions and 24 Qloo observations. These repeats are not independent users or new runs of the current deployment. |

Earlier on 15 October, runtime `32406c2` completed two consecutive Sade / Nine Inch Nails cases: first 4 fresh Qloo requests and 2 Groq decisions, then 4 cached Qloo responses and 2 fresh Groq decisions. Both native downloads and restoration of the first case passed. These historical trials remain separate from the new Portishead / Bad Bunny case.

## What we learned

Profile integrity, backend comparability and cultural quality answer different questions. A pipeline can pass integration checks while remote backend fingerprints vary; causal attribution for that separate 39-decision remote campaign therefore remains **INCONCLUSIVE**. A coherent recommendation list also does not establish that a person would enjoy the films.

Both latest top-five deliveries equalled the same-input Qloo baseline: this demonstrates integration and preference constraints, not improvement over Qloo. Cultural quality remains **NOT_VALIDATED**, verified human participants **0**, and historical quality failures retain their scores and thresholds. Role-play inputs are synthetic engineering inputs. The tested-recommender release gate remains **BLOCKED**; that is an evaluator finding, separate from the diagnostic web application's availability.

## What comes next

Independent human preference evaluation and broader controlled fault coverage need their own evidence. We will keep the hosted review freely accessible during judging, with preserved results and a zero-new-call recorded path when shared inference capacity is unavailable. Groq stays free; no unlimited throughput or future uptime is claimed. Raw provider captures and credentials remain private; original code is MIT licensed and third-party data retain their terms.

## Links

- [Hosted judge workspace](https://affinityqa-review.onrender.com/demo)
- [Public source, MIT original code and setup commands](https://github.com/seypherWork/affinityqa)
- [Judge click path](https://github.com/seypherWork/affinityqa/blob/main/docs/DEMO-GUIDE.md)
- [Exact acceptance evidence](https://github.com/seypherWork/affinityqa/blob/main/docs/JUDGE-ACCEPTANCE.md)

This draft requires the owner's final approval before submission. The [official rules](https://qloo.devpost.com/rules), checked 15 October 2026, set the deadline at **30 October 2026, 23:45 EDT** (**31 October, 04:45 in Belgium**). The project began on **3 October 2026**, as declared by the owner. Required materials are in English; the hosted demo and public source are linked above.

## Retained historical submission drafts

The complete earlier draft follows unchanged, including the two earlier Sade / Nine Inch Nails cases and every older result. Version and date labels inside this archive retain their historical meaning.

<details>
<summary>Earlier 15 October draft on 32406c2, followed by all older drafts</summary>

# AffinityQA — English submission draft

English working entry, 15 October 2026. Prepared for factual review; not submitted.

## Project name

AffinityQA

## Tagline

Follow the profile. Prove the recovery.

## Elevator pitch

A personalized agent can return a valid movie list for the wrong taste profile. AffinityQA traces Qloo context through agent requests and caches, diagnoses three supported integration faults, and checks whether a repair restores healthy behavior.

## Inspiration

A movie list can pass every format check and still belong to yesterday's profile. A stale cache or a mismatched tool response can silently survive a change in taste. We built AffinityQA to make that failure visible: which profile reached the decision, what broke, what changed, and what evidence supports recovery?

## What it does

The hosted workspace gives judges two complementary paths:

- **Recorded repair:** select a controlled incident and follow Detect, Diagnose, Repair and Verify. Compare the requested interest, consumed Qloo context, faulty output, repaired output and healthy reference. These genuine saved experiments can be replayed without new provider calls.
- **New individual case:** open a private browser session, declare two musical interests and optional film favorites or exclusions, review the plan, and explicitly confirm the artist identities returned by Qloo. Inspect five new films per profile, the original model ranking, the Qloo baseline and a downloadable verification receipt. This short preference route is separate from the controlled-fault campaign.

Reviewers can complete another case in the same session and restore their saved cases after a reload. They need no account, Docker installation, local model or API key. Fresh, cached and restored work are labelled separately.

## How Qloo is used

Qloo supplies real artist-identity candidates and cross-domain movie-affinity context for explicit musical interests. The agent consumes that context to rank a fixed twenty-film catalog. Known favorites guide both Qloo and the model; favorites and exclusions stay outside the delivered five.

The evaluator follows identity across the requested interest, transmitted model input, consumed tool context and output. Three deliberately injected incidents break that chain: a cache key omitting the profile, a stale request profile and another profile's Qloo response. Supported repairs change the adapter's session routing or cache configuration, then verification checks recovery against healthy behavior and legitimate reuse. It does not claim arbitrary source-code repair.

## How we built it

Next.js and TypeScript provide the review workspace; Python and FastAPI run the capture, diagnostics, repairs and file verifiers. Persistent storage retains plans, confirmed identities, original observations, failed attempts and selected verification receipts.

The original controlled experiment used a local model. The hosted operator uses Groq Free with GPT-OSS 20B. A durable provider queue reserves conservative request and token capacity before dispatch. Accepted work can be restored without resending it; exact Qloo context can be reused privately with explicit provenance. There is no lifetime application count cap, while shared provider quotas and storage safeguards still apply. Free inference is finite, and waiting estimates are not promises.

## Challenges we ran into

A real artist search contained mixed musical and nonmusical duplicate IDs. Discovery v3 validates raw rows before projecting selectable musical identities, collapses only identical musical candidates and rejects conflicting identities. A later live trial exposed a private-cache validator still applying the stricter ranking contract to those searches. We aligned cache semantics with the pinned versioned identity contract and repaired the reader for historical partial search receipts. The failed trials, original responses and consumed work remain intact.

We also separated application access from provider capacity. Repeatable sessions do not create unlimited model quota. The queue reports waiting, preserves accepted work and exposes fresh versus reused context rather than silently retrying sent failures or switching to a paid provider.

## Accomplishments and verified results

| Evidence | Observed result |
| --- | --- |
| Engineering checks | Tested runtime `32406c2`; [CI 38785730767](https://github.com/seypherWork/affinityqa/actions/runs/38785730767): 544 Python tests on each of Windows and Ubuntu, type checks and production build. Four Linux browser commands used synthetic providers. |
| Real repeatable browser journey, 15 October | Two consecutive Sade / Nine Inch Nails cases in one Windows/Codex browser session. First: 4 fresh Qloo HTTP attempts and 2 fresh Groq decisions. Second: 4 saved Qloo responses, no fresh Qloo attempt and 2 fresh Groq decisions. Both completed. |
| Delivery, download and recovery | Five unique films per profile, with Get Out favorite and Everything Everywhere All at Once excluded. Two actual 6,693-byte native verification downloads were saved and checked. Reloading and restoring recovered the first completed case without a new capture. |
| Preservation | Post-restoration comparison retained all 297 historical-store file hashes and all 11 files of the original failed 15 October case. No failed result was promoted to complete. |
| Original controlled capture | Six artist pairs, three injected faults and three repeats: 18 controlled cases and 54 observed recoveries from 234 local-model decisions and 24 Qloo observations. These repeats are not independent users. |

## What we learned

Profile integrity, backend comparability and cultural quality answer different questions. A pipeline can pass integration checks while remote backend fingerprints vary; causal attribution for that separate 39-decision remote campaign therefore remains **INCONCLUSIVE**. A coherent recommendation list also does not establish that a person would enjoy the films.

Both latest top-five deliveries equalled the same-input Qloo baseline: this demonstrates integration and preference constraints, not improvement over Qloo. Cultural quality remains **NOT_VALIDATED**, verified human participants **0**, and historical quality failures retain their scores and thresholds. Role-play inputs are synthetic engineering inputs. The tested-recommender release gate remains **BLOCKED**; that is an evaluator finding, separate from the diagnostic web application's availability.

## What comes next

Independent human preference evaluation and broader controlled fault coverage need their own evidence. We will keep the hosted review freely accessible during judging, with preserved results and a zero-new-call recorded path when shared inference capacity is unavailable. Groq stays free; no unlimited throughput or future uptime is claimed. Raw provider captures and credentials remain private; original code is MIT licensed and third-party data retain their terms.

## Links

- [Hosted judge workspace](https://affinityqa-review.onrender.com/demo)
- [Public source, MIT original code and setup commands](https://github.com/seypherWork/affinityqa)
- [Judge click path](https://github.com/seypherWork/affinityqa/blob/main/docs/DEMO-GUIDE.md)
- [Exact acceptance evidence](https://github.com/seypherWork/affinityqa/blob/main/docs/JUDGE-ACCEPTANCE.md)

This draft requires the owner's final approval before submission. The [official rules](https://qloo.devpost.com/rules), checked 15 October 2026, set the deadline at **30 October 2026, 23:45 EDT** (**31 October, 04:45 in Belgium**). The project began on **3 October 2026**, as declared by the owner. Required materials are in English; the hosted demo and public source are linked above.

<details>
<summary>Historical submission drafts through 14 October 2026</summary>

# AffinityQA — English submission draft

English working entry, 14 October 2026. Not submitted. One complete live discovery-v3 Windows/Brave journey, native download and same-session recovery are verified; provider capacity through the future judging period remains unreserved.

## Project name

AffinityQA

## Tagline

Follow the profile. Prove the recovery.

## Elevator pitch

A personalized agent can return a perfectly valid movie list for the wrong taste profile. AffinityQA follows an explicit musical interest through Qloo context, agent requests and caches, diagnoses three supported integration faults, and checks whether a repair restores the healthy behavior. Every result keeps its evidence and its limits visible.

## Inspiration

Output validation can tell us that an agent returned twenty valid movie IDs. It cannot tell us whether those movies were ranked using the current person's interest, an earlier profile, or another profile's tool response. We built an evaluator for that missing boundary: which profile actually reached the decision, and what evidence supports the recovery?

## What it does

The hosted workspace provides two review modes:

- **Recorded repair:** choose an artist pair, a controlled incident and a repeat. Follow detection, diagnosis, supported repair and verification against captured real Qloo and model decisions. Replaying this evidence starts no fresh Qloo or model requests.
- **New individual case:** open a private browser session, declare two musical interests and optional film favorites or exclusions, inspect the plan, explicitly choose the musical identities returned by Qloo, and inspect the saved recommendation checks. This separate, short preference review permits at most four Qloo requests and two model attempts. It does not claim a controlled-fault repair experiment.

Saved cases are kept with the visitor's session. Verification receipts expose the selected result and consistency checks rather than provider credentials or the private raw corpus. Judges use the hosted application without installing Docker, running a local model or supplying API keys.

A **BLOCKED** tested-agent release gate is an evaluation result: the evaluator has not accepted the recommender for production. It is separate from whether the web application is available. We preserve that distinction rather than changing a threshold to make the screen look successful.

## How Qloo is used

Qloo supplies actual artist identity candidates and movie-affinity context for explicit musical interests. The agent consumes that context to rank a fixed twenty-film catalog. The evaluator follows profile identity across requested interest, transmitted model input, consumed Qloo context and output.

In the controlled campaign, three faults deliberately break that chain: a cache key missing profile identity, a stale request profile, or a tool response bound to the wrong profile. The supported corrections change session routing or cache configuration. AffinityQA does not rewrite arbitrary source code or claim to repair every agent failure.

## How we built it

The project uses a Next.js and TypeScript interface with a Python/FastAPI service, persistent case storage, bounded execution admissions and source-bound verification. The original causal experiment used local-model inference; the hosted new-case operator uses Groq with GPT-OSS 20B. Raw provider observations and validated model packets are retained privately so failed, partial and inconclusive attempts can be reviewed without silent retries or admission refunds.

Discovery v3 validates raw search rows before projecting selectable musical identities. It collapses only identical musical candidates and rejects conflicting identities. This handles a real mixed musical/nonmusical duplicate-ID response while preserving the original failed v2 trial and its consumed admission.

## Results we can support

| Observation | Evidence and boundary |
| --- | --- |
| Public source and build | Revision `2c2f28a9866920031c84779a38af340e3a724966`; [GitHub run 38472962653](https://github.com/seypherWork/affinityqa/actions/runs/38472962653) passed 479 Python tests on Windows and 479 on Ubuntu, type checking and production build. Three Linux browser regressions used synthetic providers. |
| Hosted source update | The same revision is LIVE on the existing Render service. The reviewed continuation retained all 264 original inventoried files unchanged and added only its marker and retained staging payload. Reattachment preserved all 266 inventoried files. These counts exclude two auxiliary files whose metadata, rather than contents, was compared. |
| Original controlled causal capture | Six artist pairs, three injected faults and three repeats: 18 controlled cases and 54 observed recoveries, using 234 local-model decisions and 24 Qloo observations. These repeats are not independent users. |
| Earlier genuine hosted integration case | A complete 39-decision Groq campaign passed the three unchanged fault checklists and recorded nine recoveries. Its saved case survived a real restart and session restoration. This is dated, one-case technical evidence rather than acceptance of the latest discovery-v3 browser path. |
| Real discovery-v3 browser journey, 14 October | One Windows/Brave engineering visitor completed Sade / Nine Inch Nails with explicit favorite/exclusion inputs, four Qloo requests and two Groq attempts. The actual 5,605-byte native JSON download and reload/restoration of the same completed case were checked independently against retained local evidence. Both deliveries met the preference guard and equalled the Qloo baseline. |

## What we learned

Profile integrity, backend comparability and recommendation quality answer different questions. A pipeline can pass its integration checks while the remote model reports different backend fingerprints. We therefore retain **INCONCLUSIVE** causal attribution for that remote experiment. A coherent movie list also does not establish that a person would enjoy the films.

Historical quality failures remain unchanged. Verified human preference participants: **0**. Role-play profiles are synthetic engineering inputs. Cultural quality remains **NOT_VALIDATED**; no precision of 100%, population reliability, superiority to the Qloo baseline or production recommender approval is claimed.

## What comes next

Independent preference evaluation and sustained testing access through judging require their own evidence. Groq remains on its free plan: application admissions do not reserve provider quota, and quota failures remain visible rather than triggering a hidden fallback. The owner must keep the project freely available for the official testing period; current one-case acceptance cannot guarantee future quota or uptime.

## Links

- [Hosted judge workspace](https://affinityqa-review.onrender.com/demo)
- [Public source, MIT original code and setup commands](https://github.com/seypherWork/affinityqa)
- [Detailed acceptance record](https://github.com/seypherWork/affinityqa/blob/main/docs/JUDGE-ACCEPTANCE.md)

This copy is prepared for final factual review. Entry submission requires the owner's separate final approval. The [official rules](https://qloo.devpost.com/rules), checked 14 October 2026, set the submission deadline at 30 October 2026, 23:45 EDT, and judging at 2–16 November 2026. Required materials are in English; the public repository and hosted demo links are provided above.


<details>
<summary>Retained earlier submission drafts and development history</summary>

These dated drafts retain their original observations and unresolved items at those dates. They do not override the current entry above.

# AffinityQA — submission draft

**Status reconciliation · 13 October 2026.** Render is still LIVE at source `250aac1258535db593db644747a5659003fced82` (deploy `dep-db6l70lg1s2s739prm70`). PR #1 is source `f2a780877322d8e788bf55100ae9d600bf3e25e5`; its 479-test Windows/Ubuntu CI and three Linux synthetic browser scenarios passed. It fixes polling recovery and proposes discovery v3 for mixed musical/nonmusical duplicate IDs, but is not yet deployed. The original v2 live job `20261012T230633Z-8a5793a9` remains PARTIAL after two Qloo searches and zero model calls; no failed admission was refunded.

The 12 October deployment preserved all 248 observed case files (17,950,918 bytes) and owner configuration at its dated before/after inspection. That inventory predates the cloud's additional partial trial and is not a current total. The current source-browser regression checks the selected verification over HTTP; native file download is still unverified. A complete real v3 browser journey and usable capacity through judging remain pending. Human participants: 0; cultural quality NOT_VALIDATED; varied remote backend fingerprints retain causal INCONCLUSIVE. This snapshot neither submits the project nor declares full jury acceptance.

**Historical observed runtime · 11 October 2026.** The [hosted demo](https://affinityqa-review.onrender.com/demo) runs source [`760b4df`](https://github.com/seypherWork/affinityqa/commit/760b4df4dade75430ba25d907f342f96b88acc49). The authorized storage continuation and two configuration deployments completed; final deployment `dep-db5lcsjbc2fs739a3q0g` was observed LIVE. **New cases are enabled with their persistent store attached.** GPT-OSS 20B, the 22-second minimum interval, credentials, plan and automatic-deployment setting were preserved.

Two authorized owner trials completed with **eight Qloo requests and 41 Groq decisions in total**. Cinema job `20261011T094456Z-85c5729d` delivered five eligible films per profile, with no favorite or excluded film delivered; both deliveries equalled the preferences-aware Qloo baseline. Its two model responses used 10,131 tokens. Causal job `20261011T095441Z-3212bc72` retained four Qloo responses and 39 unique model decisions, using 57,544 tokens. All nine integration checks passed for each of the three mandatory faults, with nine observed recoveries. Integration is **PASS**; causal attribution remains **INCONCLUSIVE** under 25 distinct known backend fingerprints. These are technical demonstrations, not independent cultural validation or evidence of quality improvement.

At **18:05:40 UTC**, a read-only inspection found 217 case files, with all 127 original file hashes unchanged, the continuation marker and staging retained, five retained sessions, six consumed plan admissions and four consumed execution admissions. Four jobs were COMPLETE and two historical jobs remained PLANNED. At **18:06:51 UTC**, public health returned alive, configured and capture inactive. These dated observations do not reserve provider quota. Cinema had actual owned HTTPS completion, verification and readback. After loss of the local observer, the causal result was recovered by reading the exact owner's server files and running the current pure file verifier; no missing HTTPS completion/download/readback or post-run session-capability observation is claimed. No cookies were recovered and no case was repeated.

**Full jury acceptance remains NO-GO.** A complete new-case browser journey on this runtime, sustained judge access, causal comparability and independent cultural quality remain open. Verified human participants: **0**. The original failed evaluations and thresholds remain unchanged. This is a submission draft, not a submitted entry; the complete project is not ready for judging.

**Historical recorded-runtime snapshot · 9 October 2026, 23:26–23:52 UTC.** The [hosted demo](https://affinityqa-review.onrender.com/demo) ran source [`760b4df`](https://github.com/seypherWork/affinityqa/commit/760b4df4dade75430ba25d907f342f96b88acc49) (`760b4df4dade75430ba25d907f342f96b88acc49`), deployed as `dep-db4nf8p42hec73cvqs7g`. [CI run 38002413304](https://github.com/seypherWork/affinityqa/actions/runs/38002413304) passed **461 tests on each of Windows and Ubuntu**, plus source allowlist, frontend type checking and build. Actual hosted acceptance passed **54 recorded HTTPS replays and four browser replay/repair checks**. The 127 retained case files and owner configuration remained unchanged. **At that snapshot, new cases were disabled and their storage was detached** pending the separately authorized storage continuation and its verification. This acceptance made zero new Qloo/Groq calls. Full jury acceptance was **NO-GO** at that date: new hosted cinema execution, remote causal comparability, sustained access and independent cultural quality were not closed.

**Historical internal draft · 8 October 2026. Not submitted.** The [functional hosted application](https://affinityqa-review.onrender.com) used tested runtime/backend code revision `457fcace665b29a206840cedf24bceac56865b8f`. One genuine hosted case completed with 39 Groq decisions, four Qloo responses, integration **PASS**, nine observed recoveries and causal attribution **INCONCLUSIVE** under 25 distinct known backend fingerprints. A real restart retained the case, evidence, session and consumed admission; browser reload restored the nine fault/repeat views without a new capture. Functional acceptance covers this one case and its retention. Independent cultural evaluation and useful judge capacity remain pending. Full jury gate: **NO-GO**. See [the acceptance record](JUDGE-ACCEPTANCE.md).

## Project name and tagline

**AffinityQA — Follow the profile. Prove the recovery.**

Find the integration faults that make personalized agents use the wrong taste profile.

## Elevator pitch

AffinityQA helps engineers find and repair the integration faults that make personalized agents ignore a change in taste. It follows an explicit musical interest through Qloo cultural context, agent routing and caching, then shows whether a supported repair restores the agent's healthy behavior.

## The problem

A movie-discovery agent can produce valid, plausible recommendations for the wrong profile. Ordinary output-schema checks pass, while a stale cache, an old request profile or a mismatched tool response silently carries earlier context forward.

Our first audience is the engineer deciding whether to release that agent. A plausible movie list cannot show which profile the pipeline used. An observable incident, a supported diagnosis and a checked repair make that decision inspectable.

## What we built

AffinityQA is a web application with a Screening room, case library and evidence archive. The hosted reviewer lets a judge inspect and replay a previously captured incident and its repair without a local model or personal provider key. Recorded replay makes no new Qloo or model calls. A separate enabled new-case path uses the owner-configured providers and retained admission limits; two owner API trials have the bounded acceptance described above.

The causal test keeps a twenty-movie catalog fixed and changes one explicit artist interest. Qloo supplies real, profile-bound movie context consumed by the agent. The runner exercises three controlled faults: a cache that omits profile identity, a stale transmitted profile and a tool response bound to the wrong profile. Supported repairs change session routing or cache configuration; they do not rewrite arbitrary source code.

The original capture obtained fresh local-model decisions before and after repair. The hosted reviewer now runs the routing, diagnosis and repair workflow against those recorded decisions. Healthy controls and legitimate cache reuse remain part of the checks. Partial, failed and inconclusive evidence is retained.

A separate new-case interface and Groq operator were enabled during the 8 October hosted observation. A genuine browser-started case completed all unchanged integration checks, and its saved case survived a service restart and browser reload. Its integration recovery remains separate from inconclusive causal attribution. An earlier direct remote case has its own independently audited record; the two runs are not combined into independent-user evidence. The paths were reactivated on 11 October with preserved storage. A cinema owner API trial passed technical checks on the current runtime; complete new-case browser acceptance and independent preference satisfaction remain unverified.

## Why Qloo matters

Qloo is an actual tool input in the tested agent. Its API supplies movie affinities for an explicit musical interest across a fixed catalog. That cultural dependency has an identity and routing boundary that can be observed; substituting another profile's context creates a concrete personalization incident.

The demonstrated claim is integration integrity: whether the intended profile's cultural context reaches the decision process and whether a supported repair restores the checked behavior. The evidence does not establish that the recommender predicts an individual's preferences or outperforms all LLM-only alternatives.

## What is demonstrated today

| Demonstration | Verified result | Interpretation |
| --- | --- | --- |
| Authorized activation and cinema API trial, 11 October | Source `760b4df`; LIVE deploy `dep-db5lcsjbc2fs739a3q0g`; cinema job `20261011T094456Z-85c5729d` | New cases enabled/store attached; four Qloo requests, two model decisions, ten compliant delivered films; equal baseline, no demonstrated uplift; full new-case browser journey and human satisfaction unverified. |
| Authorized causal trial, 11 October | Job `20261011T095441Z-3212bc72`; run `20261011T095519Z-34d729e0`; exact receipt and current private file verifier | Four Qloo samples, 39 unique model decisions, nine observed recoveries; integration PASS, 25 known fingerprints and causal INCONCLUSIVE; owner-file recovery does not establish lost HTTP/readback observations or full jury readiness. |
| Source CI and recorded hosted runtime, 9 October | [`760b4df`](https://github.com/seypherWork/affinityqa/commit/760b4df4dade75430ba25d907f342f96b88acc49); [CI 38002413304](https://github.com/seypherWork/affinityqa/actions/runs/38002413304); LIVE deploy `dep-db4nf8p42hec73cvqs7g` | 461 tests per Windows/Ubuntu platform; 54 actual recorded HTTPS replays; 4 browser checks; 127 case files and owner configuration unchanged; zero new provider calls. At that snapshot, new cases were disabled/storage detached and fresh-case acceptance remained pending. |
| Separate private Windows portable, checked 9 October 22:30 UTC | Recorded-only package; Windows 11/Python 3.12.14; 461 tests; 54 actual HTTP replays; 2,087 payload files and 1,728 historical files preserved; browser repair and idle launcher restart passed | Different artifact and frozen 218-file source scope; no fresh inference or power-loss recovery; private evidence distribution is not authorized; this is not a public downloadable submission. |
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

A separate read-only inspection at **23:49:40 UTC on 9 October** found two COMPLETE jobs, two PLANNED jobs and three retained, unexpired sessions. At that date, the cumulative policy had **98 execution admissions, 196 plan admissions and 997 new-session admissions** remaining. These are internal counters, not reserved Groq capacity or a promise that 98 cases can run. Expired sessions and failed or abandoned admissions receive no automatic refund. No providers were called and no sessions were created by this inspection.

**Latest cumulative counters · 11 October, 18:05:40 UTC:** 96 execution admissions, 194 plan admissions and 995 new-session admissions remained. These internal limits are separate from Groq quota and do not guarantee that those cases can execute. Expired sessions and failed or abandoned admissions are not automatically refunded.

Historical cultural results remain **13/14 development FAIL** and **4/6 independent movie-trial FAIL**, with their original thresholds. Verified human participants: **0**. Role-play and synthetic profiles are engineering/regression inputs, not a human study. The earlier 39-decision hosted case retains integration PASS and causal INCONCLUSIVE; the separate two-decision film-preference/discovery protocol does not close that causal gate.

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

The current review artifact is the [restricted hosted demo](https://affinityqa-review.onrender.com/demo), observed on source `760b4df4dade75430ba25d907f342f96b88acc49`. Recorded review needs no judge-supplied provider key or local model. New cases are enabled with preserved storage; the 11 October API trials establish bounded technical cinema and integration results, with causal attribution inconclusive. The complete new-browser path, sustained availability through judging and independent cultural quality remain unverified. The 8 October case and restart retain their separate historical scope.

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

The official deadline is **30 October 2026 at 23:45 EDT**. Judging runs **2–16 November 2026**. The four equally weighted criteria are technological implementation, design, potential impact and quality of the idea. These dates and requirements were checked against the [official rules](https://qloo.devpost.com/rules) on 10 October 2026 (Europe/Brussels); no outcome or ranking is predicted. Continued review access still needs to be demonstrated; this draft makes no new availability commitment.

Before submission, bind the final reviewed documentation, demo configuration and English materials to tested runtime code and actual evidence. The one-case hosted and restart checks are complete; independent cultural evaluation and usable free judge access through evaluation remain pending. Maintain the reviewed Qloo scope and applicable model-provider terms. Keep raw provider evidence outside public Git.

The 8 October review of official Qloo materials supports private server caching and attributed, contextual results. Applying the documented external-model workflow to the minimum affinity context needed by this project is an operational interpretation, not a universal license for Groq or redistribution of provider data. No additional individual email-approval requirement was identified for this limited scope. Raw-corpus redistribution, training rights and MIT licensing of Qloo outputs are not claimed. [Official Qloo guidance](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide#can-i-cache-qloo-api-responses-in-my-app) · [Safe use](https://github.com/qloo/qloo-hackathon-kit/blob/main/docs/SAFE_USE.md)

This draft is for review and submits no entry. Code publication, engineering checks and one-case functional acceptance do not satisfy the remaining capacity or cultural gates.

## Appendix: retained development history

- Development run `20261004T114624Z-a1722335` recorded 39 real local-model decisions, two Qloo requests and nine recoveries across three faults and three repeats for one known profile pair. It was development evidence, not nine independent users.
- Private Windows v9, verified on 6 October, installed 17 locked dependencies and passed 309 fixtures, zero skips, 54 recorded selections, 19 API views, 41 static hashes and four browser panels. The failed initial environment and observed interrupted listener stop remain recorded.
- The earlier 4 October constrained Linux rehearsal measured approximately 520 ms p95 and 252.01 MiB peak memory on development-PC Linux tmpfs. It was local recorded replay, not Render performance or a cloud inference benchmark. Earlier slower bind-storage and failed source-count attempts were retained.
- The initial Groq 403/1010 failure was diagnosed through anonymous client-header comparison. The application User-Agent fix passed 289 tests per platform in published CI; two later authenticated diagnostic captures each stopped on a second response under the former global-fingerprint rule. Those partial attempts remain preserved separately from the complete v3 run.
- Historical 13/14 and 4/6 cultural failures remain FAIL; cultural quality remains NOT_VALIDATED and recommender release BLOCKED.


</details>

</details>

</details>

</details>
