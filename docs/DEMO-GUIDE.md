# AffinityQA — judge walkthrough

Open [the hosted application](https://affinityqa-review.onrender.com/demo#recorded).
A browser is sufficient: no account, installation, Docker, local model or judge
API key is needed. The creator's PC does not need to be running.

The latest completed hosted acceptance was on **18 October 2026**, code
`0faa96d`. On 19 October, a read-only check found the public demo alive with new
cases enabled. That check made no inference and does not establish available
provider quota. [Dated evidence](JUDGE-ACCEPTANCE.md).

## Start with diagnosis and repair

1. Open **DIAGNOSIS & EVIDENCE**. Choose **Alice Coltrane / Lil Nas X**,
   **Profile missing from cache key**, and a repeat requesting **Lil Nas X**.
2. Press **Replay this incident** once. This executes the retained pipeline with
   saved real-model decisions: zero new model and Qloo calls.
3. Follow **DETECT**, **DIAGNOSE**, **REPAIR** and **VERIFY**. Before repair,
   compare requested Lil Nas X with the incorrectly consumed Alice Coltrane
   profile. After repair, follow Lil Nas X through the restored chain.
4. Inspect all six recovery controls. They cover the supported diagnosis, repair,
   profile integrity, redispatch, healthy-reference agreement and legitimate
   cache reuse; they do not validate individual movie taste.
5. The other incident choices are **Stale profile passed to agent** and
   **Qloo context bound to wrong profile**. Each has its own recorded experiment
   and supported repair. The 18 October acceptance checked all three.

This route demonstrates the engineering core using captured observations.
The separate advanced 39-decision campaign is not required for this opening;
its remote causal result remains INCONCLUSIVE.

## Try a new discovery

1. Open **FILM DISCOVERY**, then **OPEN OR RESTORE MY SESSION**. Choose
   **START WITH A FILM** or **START WITH AN ARTIST**. Enter a starting point;
   artist mode can also include one known favorite film and an optional direction.
2. Press **REVIEW MY DISCOVERY PLAN**. Opening ownership, typing and reviewing
   the plan do not send Qloo/model requests. Inspect its request limits.
3. Use the displayed **FIND MY FILM**, **FIND MY ARTIST** or
   **FIND MY ARTIST & FAVORITE FILM** button once. Explicitly choose the intended
   identity; check a film's title and year. Exact full-name artist matches appear
   first when present; alternatives stay in **Other matches & collaborations**.
4. Press **CONFIRM & DISCOVER FIVE** once. The application retrieves a Qloo
   pool of up to 100 films and requests one constrained Groq Free selection.
   No fixed twenty-film whitelist governs this route.
5. Inspect five cards. Names/years come from the selected candidate identities.
   Descriptions are literal saved Qloo metadata, with language and missing-data
   labels; they are not model-generated explanations. Images can use a fallback.
   **HOW THESE WERE CHOSEN** explains the pool and ordering.
6. Use **DOWNLOAD DISCOVERY VERIFICATION**. Open **SAVED**; on a fresh page in
   the same browser profile, restore the same session and case. Reading retained
   evidence does not start another selection.

Both film-led and artist-led paths output **films**, not artists or songs.
The optional direction reaches the model, not an undocumented Qloo query.
Internal codes remain out of ordinary screens; the verification retains audit
identifiers. Saved results belong to their host and ownership session: a local
preview does not share the hosted history.

## If work waits or stops

Shared Qloo/Groq Free capacity is finite. Inspect the saved status and the
displayed wait/pause reason rather than sending the same work again. Keep the
same browser profile and ownership cookies. Failed or uncertain sends are not
silently retried, and the application does not promise instant or unlimited
free inference. A partial result is retained as partial.

You can inspect saved cases or return to the recorded repair path without
spending provider capacity. **PREVIOUS COMPARISONS** preserves older two-profile
twenty-film tasks and their original evidence; it is not the current discovery
entry point. Do not start the long advanced campaign merely to test the short
discovery flow.

## Read the claims separately

- Recorded repair checks supported integration recovery; it is not new inference.
- Synthetic engineering/browser tests check contracts and UI behavior.
- The two 18 October real hosted trials check those inputs, downloads and
  restoration. They are not a human preference study or universal seed coverage.
- Source-bound descriptions do not establish that the metadata is true.
- Cultural quality remains NOT_VALIDATED, with zero verified human preference
  participants. The historical evaluated-agent BLOCKED result is separate from
  the diagnostic application's availability.

[Latest hosted acceptance](JUDGE-ACCEPTANCE.md) ·
[Discovery contract](WIDE-CINEMA-DISCOVERY.md) ·
[Source setup](PUBLIC-CODE-QUICKSTART.md)

<details>
<summary>Earlier walkthrough snapshots, retained verbatim</summary>

# AffinityQA — reviewer walkthrough

**18 October 2026: locally accepted v10 interface; release consolidation only.**
The integrated discovery interface below is the locally checked version. A new
Render deployment and public CI run for this consolidation have not been
verified. The [earlier hosted workspace](https://affinityqa-review.onrender.com/demo)
still ran revision `abf9840` when the owner checked its health and revision on
18 October. Its dated 17 October browser acceptance remains a separate record;
it may show the older workflow. Local use needs the owner's running service;
reviewers never provide their own API keys.

## Start with the diagnostic evidence

Open **DIAGNOSIS & EVIDENCE**, select a captured incident, then follow **Detect**,
**Diagnose**, **Repair** and **Verify**. Compare the requested profile, the Qloo
context actually consumed, the faulty output, the supported repair and the
healthy reference. Use **Replay this incident** to execute the retained pipeline
with saved decisions; this makes zero new Qloo or model calls.

The three controlled faults are a cache key missing profile identity, a stale
profile sent to the agent and a tool context bound to the wrong profile. Their
verifiers check the declared routing/cache recovery; they do not establish
arbitrary code repair, external-service attestation or human movie preferences.
The full 39-decision experiment is a separate advanced path with its own budget
and inconclusive remote causal result, not a required short demonstration.

## Discover five films in the integrated interface

1. Open **DISCOVER** and **OPEN OR RESTORE MY SESSION**. Choose **START WITH A
   FILM** or **START WITH AN ARTIST**. Enter one starting point; artist mode may
   also include one known favorite film. Add a direction only if wanted.
2. Use **REVIEW MY DISCOVERY PLAN**. Opening a session, typing and reviewing a
   plan make no Qloo or model requests. Read the request limits before using
   **FIND MY FILM**, **FIND MY ARTIST** or **FIND MY ARTIST & FAVORITE FILM**.
3. Explicitly choose the intended returned identity. An exact full-name music
   artist appears first when present. **Other matches & collaborations** keeps
   person profiles and alternative matches selectable. Nothing is preselected;
   a restored previous choice still needs confirmation. For films, check title
   and year. Then use **CONFIRM & DISCOVER FIVE** once.
4. Inspect five cards drawn from the actual retrieved pool of up to 100 films.
   AI ranks eligible indices; the server reconstructs film identities. The text
   under each card is literal Qloo metadata with an accessible Spanish/English
   label, or a fixed no-plot fallback. It is not a model-written explanation.
   Posters are observed presentation assets and can have an unavailable-image
   fallback. Use **HOW THESE WERE CHOSEN** to inspect the ordering and pool.
5. Use **DOWNLOAD DISCOVERY VERIFICATION**. Open **SAVED**, reload and restore
   the same session to inspect the completed case. Reading or downloading saved
   work does not request a new recommendation. Original historical downloads
   remain unchanged by the current top-level source-description display.

The application outputs films, including when the input is a musical artist.
It does not output artists or songs. Optional direction goes to the model, not
to an undocumented Qloo free-text parameter; source descriptions stay off the
model input. Ordinary cards hide internal identifiers, which remain available
in the explicit inspection details.

Saved cases belong to their host and ownership session. Local acceptance cases
remain local; the Render service keeps a separate history. This release
preparation does not migrate or merge those stores, and deployment must preserve
the existing hosted cases and sessions.

If work waits for capacity or reports an uncertain response, check its saved
status. Do not repeat a sent failure, clear ownership cookies or reset consumed
work to hide it. Shared Groq Free/Qloo limits and storage safeguards remain;
there is no guaranteed latency or unreserved unlimited capacity.

## What the 18 October local check established

One new Eminem v10 case completed with three Qloo requests and one Groq Free
selection. It retained 100 candidate films and delivered **8 Mile**, **Get Rich
or Die Tryin'**, **Notorious**, **Coach Carter** and **American Gangster**. All
five descriptions were independently matched to literal Spanish Qloo values;
the five matching posters loaded, the native download was saved and checked,
and the same case restored after reloading. All 14 earlier cases were retained.
The preceding v9 title-echo rejection remains PARTIAL, with its charges and
evidence unchanged. No new native Massive Attack v10 success is claimed.

The frozen source passed 723 Windows tests, production export and synthetic
desktop/mobile browser checks. Those results do not establish CI or Render
acceptance of this release preparation. Cultural quality remains NOT_VALIDATED
with zero verified human preference participants. Qloo metadata can itself be
inaccurate: this verifies faithful source display, not general movie truth or
individual satisfaction.

[Dated local acceptance record](LOCAL-ACCEPTANCE-20261018.md) ·
[v10 contract and evidence limits](WIDE-CINEMA-DISCOVERY.md) ·
[Historical hosted acceptance](JUDGE-ACCEPTANCE.md)

## Historical guides

Earlier guides are preserved below. References to "current", twenty-film
catalogs, two-profile shared passes, buttons and timing belong to their dates.

<details>
<summary>Hosted guide snapshot — 17 October 2026</summary>

# AffinityQA — reviewer walkthrough

**Current hosted interface: `1bb98f8`, verified 17 October 2026.**
Open [the hosted workspace](https://affinityqa-review.onrender.com/demo) in a browser.
No account, Docker, local model or personal API key is required.

The local source also contains a capability-gated **START WITH A FILM** extension.
It is separate from the hosted acceptance below. Two real local provider captures
completed; the new route's hosted-browser acceptance remains pending.
See [its contract and results](OPEN-FILM-DISCOVERY.md).

## Discover films

1. Open **DISCOVER FILMS**, then open or restore your private visitor session.
   Enter two musical interests. Optionally search up to two favorite films across
   the two scenarios. Outputs come from the disclosed twenty-film catalog.
2. Review the plan, then use **FIND ARTISTS** or **FIND ARTISTS & FILMS** once.
   Explicitly choose each intended artist and each film by its returned title and
   year. Typing alone sends no provider request. No identity is silently guessed.
3. Confirm once to obtain context and one shared Groq ranking response. Inspect
   five eligible films per scenario; **WHY THESE INPUTS?** exposes the raw model
   order, same-input Qloo baseline and constraints.
4. Download the selected verification JSON. Reload, restore the same session and
   open a saved case. This reads retained work without executing it again.

QUEUED or waiting for provider capacity means shared capacity is pending. Read
the saved status rather than starting again after an uncertain response. Do not
clear cookies, reset admissions or silently repeat a sent failure.

The two 17 October real cases used 6 Qloo + 1 Groq and 4 Qloo + 1 Groq respectively.
Server confirmation admission to COMPLETE took 9.030 and 6.492 seconds, with no
provider-capacity wait in these trials. This excludes human selection, page loads
and browser observation delays. It is not a future end-to-end latency guarantee.

An additional real identity-only check typed **Matrix** and returned
**The Matrix (1999)** first, with the same canonical identity as the full-title
search. It used three Qloo searches and zero Groq calls, stopping before
confirmation. Other abbreviations, spelling errors and languages were not
established by this check.

## Diagnosis and evidence

Open **DIAGNOSIS & EVIDENCE** for the recorded path. Choose a captured incident;
follow **Detect**, **Diagnose**, **Repair** and **Verify**. Compare the requested
profile, consumed Qloo context, faulty output, repaired output and healthy reference.
The six checks concern the supported routing/cache repair. Recorded replay makes
zero new Qloo or model calls and does not establish new provider readiness.

The full 39-decision controlled experiment is a separate advanced option with its
own reviewed plan and waiting time. It is not the short film-discovery route.

## Read the scope of each result

Two scenarios share one model observation, rather than constituting independent
evaluations or participants. All four latest film lists equalled their Qloo
baselines. External favorite-film inputs are positive seeds; they do not expand
the twenty-film output catalog. The application recommends films, not songs.

Cultural quality remains NOT_VALIDATED with zero verified human participants;
remote causal attribution for the historical 39-decision campaign is INCONCLUSIVE.
The tested-recommender BLOCKED gate is separate from the diagnostic application's
bounded technical acceptance. Groq Free quotas remain shared and finite.

[Current acceptance and native file hashes](JUDGE-ACCEPTANCE.md) ·
[Shared-pass contract](FAST-TASTE-REVIEW.md)

</details>

## Earlier guide snapshots

The following original guide is retained unchanged. Earlier references to
"current", runtime versions, buttons and budgets belong to their stated dates.

<details>
<summary>Guide snapshot through 16 October 2026, including earlier hosted journeys</summary>

# AffinityQA — reviewer walkthrough

**16 October local source candidate:** the new discovery-first interface and the
capability-gated shared model pass are described in [the taste journey](FAST-TASTE-REVIEW.md).
This guide's dated hosted acceptances remain historical records; they are not a
claim that the new candidate is deployed or has passed a live speed test.

## Start here — jury click path

Open [the hosted workspace](https://affinityqa-review.onrender.com/demo). A browser is sufficient; no Docker, local model or personal provider key is needed.

### Suggested 60-second opening — a wrong-profile incident

This is a diagnostic workspace for teams building personalized agents. Musical interests provide context for movie recommendations; the application does not recommend songs or play music. The browser path requires no local installation.

| Time | Action | Explain what the judge is seeing |
| --- | --- | --- |
| 0:00–0:15 | Open **Recorded repair**. Select **Alice Coltrane / Lil Nas X**, **Profile missing from cache key**, and a repeat requesting **Lil Nas X**. Press **Replay this incident**. | "The requested taste changed to Lil Nas X, but a cache key omitted the profile. A valid movie list can therefore carry Alice Coltrane's context." |
| 0:15–0:30 | In **Detect**, compare requested taste, Qloo context, agent input and decision-associated profile. Open **Diagnose**. | "This controlled fault is CACHE_OMITS_PROFILE. Qloo's entity IDs and profile-bound context let us trace which interest reached the decision; a display name or valid list alone cannot establish that." |
| 0:30–0:45 | Open **Repair** and compare before, after and healthy results. | "The supported repair binds the cache to the profile. The repaired route must match the recorded healthy reference, while legitimate cache reuse still works." |
| 0:45–1:00 | Open **Verify** and inspect all six recovery controls. | "Diagnosis, repair, restored profile integrity, decision dispatch, healthy match and legitimate cache reuse passed. This is saved real-provider/model evidence: three recorded decisions dispatched, zero new Qloo or model calls." |

This opening is a suggested presentation pace, not a measured latency guarantee. The Alice Coltrane / Lil Nas X cache replay was checked on the `ab32065` deployment on 15 October. The fault is deliberately injected into a controlled adapter; the repair is scoped to its supported routing/cache behavior. It does not establish new inference, human preference quality or arbitrary source-code repair.

### Extended recorded repair — about two minutes

1. Open **Recorded repair**.
2. Choose **Mogwai / Kesha**, **Qloo context bound to wrong profile**, and **Repeat 3 · request Kesha**.
3. Press **Replay this incident**.
4. In **Detect**, compare the requested interest with the consumed Qloo profile.
5. Open **Diagnose**, then **Repair**. Inspect the supported diagnosis, the correction and the before/after/healthy outputs.
6. Open **Verify**. Inspect the six checks and the evidence boundaries.

This path replays saved real-provider/model decisions. It adds no new Qloo/model requests or independent trial. Cultural quality and tested-agent release retain their separate results.

### A fresh individual case — separate provider execution

Repeatable new-case access is enabled on runtime `ab32065`, tested on 15 October after deployment. The Portishead / Bad Bunny case completed in the existing session, with a native download and same-case recovery after a reload during provider waiting. Earlier that day, two consecutive Sade / Nine Inch Nails cases passed on `32406c2`; their dated evidence is retained in the acceptance record. Groq remains free; shared provider capacity can delay or pause work.

1. Open **New individual case**, then **OPEN OR RESTORE MY SESSION**.
2. Keep **FILM PREFERENCES** selected for the short review. Enter two musical interests and optionally mark known favorites and exclusions. The latest verified example used **Portishead / Bad Bunny**, **Get Out** as a known favorite and **Everything Everywhere All at Once** as an exclusion in both profiles. These are declared inputs, not inferred personal data.
3. Press **REVIEW A NEW PLAN**. Inspect the mode, artists, declared Qloo/model budget and preferences. The short discovery protocol allows at most four Qloo requests and two model attempts; the separate causal campaign has 39 model decisions.
4. Press **FIND ARTISTS** once. Inspect each proposed identity and choose one verified musical identity per profile. No artist is chosen automatically. For an ambiguous name such as Bad Bunny, verify the artist type and identity rather than selecting a homonymous person.
5. Press **CONFIRM ARTISTS & START REVIEW** once. Follow progress. QUEUED or WAITING FOR PROVIDER CAPACITY means the durable queue is waiting for shared capacity, not that another start is needed. A displayed eligibility estimate is not a guaranteed start time. If it becomes unavailable, use **CHECK CURRENT STATUS**; a lost response does not authorize a second execution.
6. Inspect the completed result, favorite/exclusion guards, verification and honest gate labels. Technical compliance does not establish individual satisfaction or superiority to the Qloo baseline.
7. Press **DOWNLOAD SELECTED VERIFICATION**. Check that the JSON belongs to the selected case.
8. After completion you may review another plan in the same session. The completed-case count has no lifetime application cap. Exact saved Qloo context can be reused; inspect the separate fresh HTTP, cached and restored-work counters. Each admitted model request is still a fresh bounded decision.
9. Download the second result if you ran another case. Reload, restore the same session and open the first saved case by its ID. Opening it reads the existing result without a new plan or provider capture.

If the session is expired, capacity is exhausted, evidence changed or a provider stops the case, retain the displayed result and receipt. Preserve failed admissions; do not clear cookies or repeat an admitted case to hide a failure. Recorded repair remains a separate review path.

### Current acceptance boundary

On runtime `ab32065`, case `20261015T211609Z-022dda74` used Portishead / Bad Bunny with Get Out as a favorite and Everything Everywhere All at Once excluded in both profiles. It made four fresh Qloo HTTP requests and two fresh Groq decisions. The native 6,693-byte JSON file was physically saved and verified. A reload during provider waiting followed by restoration recovered the same completed case in the existing session; no new session, plan or provider capture was created for recovery.

The five unique films per profile respected both constraints and equalled the same-input Qloo baseline. This proves the observed technical route, not human satisfaction, improvement over Qloo, reserved provider capacity or physical iOS/Safari behavior. All three recorded repair types also passed six checks each with zero new provider calls. All 792 old ordinary files and the three older repeatable cases/receipts were preserved; 80 old database rows were checked, including six permitted quota/sequence advances. [Exact acceptance evidence](JUDGE-ACCEPTANCE.md).

Earlier on 15 October, runtime `32406c2` completed two consecutive Sade / Nine Inch Nails cases. The first used four fresh Qloo requests and two Groq decisions; the second used four cached Qloo responses and two fresh Groq decisions. Both native downloads and recovery of the first case passed. These retained historical trials are not counted as new executions of `ab32065`.

## Historical walkthrough and provenance

The following dated observations retain their original versions and limits. They do not supersede the current acceptance above.

**Historical walkthrough · 9 October 2026.** Open the [hosted application](https://affinityqa-review.onrender.com), running [UI release 52851c9](https://github.com/seypherWork/affinityqa/commit/52851c98e36c8c8594b5c0a8c7643c03a717000e) (`52851c98e36c8c8594b5c0a8c7643c03a717000e`) with backend modules unchanged from `457fcace665b29a206840cedf24bceac56865b8f`. The 8 October recorded journey passed 54 HTTPS selections and 324 strict checks. A later genuine hosted case on 8 October completed 39 Groq decisions and four Qloo samples, passed all three fault checklists and survived a real service restart. Browser reload restored the saved session/case and all nine fault/repeat views without a new capture. This one-case functional/persistence acceptance leaves sustained judge capacity and independent cultural quality unvalidated.

This guide separates a two-minute recorded walkthrough from the longer genuine new-case path. Recorded replay uses captured model decisions and makes no new model or Qloo calls. A recording is optional and cannot replace the functional application.

## Choose the review path

### Workspace navigation in the 9 October UI release

The refreshed interface opens **Recorded repair** by default. Use the sidebar (top navigation on narrow screens) to switch to **New individual case**. Recorded replay needs no fresh inference; a new case first opens a private session and a reviewed plan. The observed full remote case took about fourteen minutes. Navigation preserves an opened new-case component; switching modes does not automatically start or duplicate execution.

The private workspace separates **Overview**, **Screening**, **Case library** and **Evidence archive**. The library keeps all six historical cases and supports search by case ID or artist name. Narrow tables scroll inside their own region, including with arrow keys when focused. Earlier failures remain in the evidence archive and outside the public capture-details disclosure.

These navigation details describe UI release `52851c98e36c8c8594b5c0a8c7643c03a717000e`, verified on 9 October. [CI run 37861553671](https://github.com/seypherWork/affinityqa/actions/runs/37861553671) passed 295 tests per platform, source allowlist checks and frontend type checking/build; Render `dep-db42qnub7d7c73a5ihkg` was verified LIVE. Review used recorded replay and the existing owned case with zero new provider calls. The 62 retained case files and owner configuration were unchanged. The separate private portable built from this UI release completed real default installation on Windows 11/Python 3.12.14: 20 GET routes, 41 static assets and 54 recorded replays passed. Selected desktop browser checks covered the four workspace views, case search, retained mixed-result losses, skip-link focus and one recorded replay. `Start-Judge.cmd` restarted the installed recorded server with HTTP 200; owned processes and the port were closed afterward. All 2,100 payload and 1,873 environment files stayed unchanged, with zero new provider calls. This does not cover mobile, optional PowerShell, Python 3.13 portable, fresh inference or graceful shutdown of admitted jobs; the 8 October case and restart retain their separate scope.

The hosted recorded reviewer requires no judge provider key, Docker installation or local model. For a private rehearsal, follow [PUBLIC-DEMO-DEPLOYMENT.md](PUBLIC-DEMO-DEPLOYMENT.md) with the owner's matching evidence package.

The source-only distribution contains code and synthetic engineering tests. Without separately supplied evidence it reports UNAVAILABLE. The private local judge archive is a different package with compiled assets, recorded evidence and historical studies; the restricted hosted service does not expose the general local API or raw evidence exports. See [source setup](PUBLIC-CODE-QUICKSTART.md).

## Two-minute recorded-capture demonstration

| Time | Interaction | Suggested narration |
| --- | --- | --- |
| 0:00–0:20 | Identify **Recorded repair** mode and the separate gates. | A personalized agent can return a valid movie list for the wrong taste profile. AffinityQA exposes the profile chain and checks a supported repair. |
| 0:20–0:45 | Select **Mogwai / Kesha**, **Qloo context bound to wrong profile**, and **Repeat 3 · request Kesha**. Choose **Replay this incident**. | Qloo supplied real movie context in the original capture. This controlled fault binds Mogwai's context to a Kesha request. We are replaying that recorded experiment. |
| 0:45–1:05 | In **Detect**, compare **Before repair** and **After repair** profile chains. Choose **Diagnose**. | The trace shows the requested profile, consumed tool context and profile reaching the agent. The supported diagnosis is WRONG_TOOL_PROFILE. |
| 1:05–1:25 | Choose **Repair** and inspect before, after and healthy movie columns. | The workflow applies bind-request-tool and dispatches the repaired path. Four recorded decisions are dispatched here, with no fresh provider call. The repaired top five must match the recorded healthy execution. |
| 1:25–1:45 | Choose **Verify** and inspect the six replay checks. | Replay checks diagnosis, repair, profile integrity, decision dispatch, healthy match and legitimate cache reuse. The original capture covered 18 controlled cases across six artist pairs and three fault types. |
| 1:45–2:00 | Open **Capture details & evidence boundaries** and its protocol/provenance details; inspect retained quality results. | The original capture obtained 234 local-model decisions and 24 Qloo observations: 19 new requests and five reused searches. It observed 54 recoveries across repeats. These are controlled repeats, not independent users. Earlier quality failures remain visible. |

The fault is deliberately injected into a controlled adapter. Describe an integration incident and its supported repair; do not claim an undisclosed production incident or general source-code repair.

## Additional recorded checks

| Incident | Diagnosis | Repair | Recorded decision dispatches |
| --- | --- | --- | --- |
| Profile missing from cache key | CACHE_OMITS_PROFILE | set-profile-cache | 3 |
| Stale profile passed to agent | STALE_PROFILE | restore-request-profile | 4 |
| Qloo context bound to wrong profile | WRONG_TOOL_PROFILE | bind-request-tool | 4 |

Choose any of the six artist pairs and repeats 1, 2 or 3. Repeats 1 and 3 request the second artist after the first; repeat 2 reverses the order. Changing selection clears the prior result, and returned selection must match the request.

The original 18-case denominator is six pairs × three fault types. Each case has three recorded repeats, producing 54 repeat-level recoveries. Replaying a selection does not add another real-provider execution or independent trial to that denominator.

## Read the gates for the selected mode

The original recorded local capture retains its verified causal result. Its replay label does not certify the current remote provider or a new person's movie preferences.

The remote v3 operator separates **integration**, **backend comparability** and **causal attribution**. All three mandatory faults, all nine checks and three repeats remain unchanged. A complete sample requires 39 validated model decisions. Causal PASS requires integration PASS and 39 known identical fingerprints. Integration PASS with varied or absent fingerprints yields causal INCONCLUSIVE; partial samples are NOT_EVALUATED. Fingerprint equality does not attest immutable weights.

The earlier direct run `20261008T182536Z-edb5fd04` completed with 39 valid Groq packets, four Qloo samples, integration PASS 3/3 and nine recoveries. Its verifier and independent audit checked source/plan/admission/process bindings and arithmetic. That direct run reported **27** known fingerprints. The later hosted run `20261008T190353Z-772b6659` separately reported **25** known fingerprints, none absent, with the same integration PASS and nine observed recoveries. Both have backend VARIED and causal INCONCLUSIVE. These known development requests are not unseen-user trials.

**Cultural quality NOT_VALIDATED** and **tested-recommender release BLOCKED** remain separate. The historical 13/14 development and independent 4/6 movie-quality trials retain FAIL and their original thresholds. No verified human preference labels are available; requested ratings from two real people for the twenty-movie catalog remain pending.

These verifiers inspect recorded evidence and protocol bindings. They do not provide external-service cryptographic attestation or an independent human preference study.

## Unavailable, busy and partial states

Absent, altered or mismatched evidence must not produce a verified result. A source preview reporting UNAVAILABLE needs matching owner-supplied evidence. Recheck the public address before a final judge demonstration.

The restricted server admits one recorded replay at a time. If it reports busy, wait for that replay to finish before selecting it again. This ordinary replay interaction does not authorize retrying a failed genuine provider capture. A changed selection must not display the previous selection's result.

For new cases, use the retained status and case controls. A lost start response must be resolved through status without another admission. Preserve failed or partial attempts and their denominators; do not reset cumulative budgets or silently switch model/schema.

## Genuine hosted new-case journey — one case verified

New-case configuration was retained in the LIVE UI release `52851c98e36c8c8594b5c0a8c7643c03a717000e`, verified on 9 October; backend modules remain byte-identical to revision `457fcace665b29a206840cedf24bceac56865b8f`. Hosted job `20261008T190344Z-a49a92a0`, run `20261008T190353Z-772b6659`, completed this journey on 8 October with 39 Groq packets, four Qloo samples, integration PASS and causal INCONCLUSIVE. The following describes that reviewed path. Starting another full case consumes shared provider budget; inspect availability and the plan first.

1. Open the external application in a fresh browser and enter the new-case controls. Confirm the real remote execution label and separate integration, causal, cultural and release results. Opening a page alone must not start provider inference.
2. Open the visitor session explicitly. Select the two artist interests and review the twenty-item catalog, frozen protocol, execution budget and pacing. Private provider configuration belongs to the owner; judges do not supply API keys.
3. Start the reviewed plan once. Follow saved progress and status. Recover a lost response from retained status without starting another provider capture.
4. Wait for all 39 decisions and real Qloo samples. Check all three faults with three repeats and the unchanged nine checks. Show supported diagnosis, repair and verified output; retain failures, partials and any INCONCLUSIVE attribution.
5. Inspect each stage and selected receipt: requested profile, transmitted profile, consumed tool context and output. Do not promote observed recovery to causal PASS when backend fingerprints differ or are absent.
6. Reopen the owned session and retained case. The actual service restart preserved 62 case-file hashes and one consumed cumulative admission; browser reload restored the same session/case. All nine fault/repeat views displayed nine checks each, without triggering another capture. Treat this as one-case retention evidence; any further session-isolation checks must respect the approved plan and unchanged cumulative budgets.

The current minimum interval is **22 seconds**. For 39 model starts, spacing alone has a lower bound of **38 × 22 = 836 seconds**, or **13 minutes 56 seconds (about 13.9 minutes)**. The observed hosted run took **841.627 seconds (14 min 1.627 s)**, from **19:03:53.159 to 19:17:54.786 UTC**. Qloo work, inference, queuing and verification can add time; this observation is not a completion promise for another request.

The hosted case consumed **57,600 tokens**. At the observed shared **200,000-token daily budget**, approximately three comparable full cases fit before other traffic. That estimate is not guaranteed or reserved capacity. The application's configured cumulative limit of 100 executions is separate; the tested restart retained the one admission already consumed. Anonymous sessions do not establish independent real users.

Do not promise a two-minute fresh provider capture. An optional short video can show recorded replay or a clearly labelled time lapse. The live application still needs usable end-to-end review capacity through judging.

## Submission operator checks

The hosted source/UI release verified on 9 October is `52851c98e36c8c8594b5c0a8c7643c03a717000e`. [CI run 37861553671](https://github.com/seypherWork/affinityqa/actions/runs/37861553671) passed 295 source-only tests on Windows/Python 3.13.16 and Ubuntu/Python 3.12.14, source allowlist checks and frontend type checking/build. Backend modules remain byte-identical to `457fcace665b29a206840cedf24bceac56865b8f`, whose retained 8 October [CI run 37824994293](https://github.com/seypherWork/affinityqa/actions/runs/37824994293) also passed 295 tests per platform. Documentation proposals create no new CI or provider observation. Provider and browser evidence remain separate.

On 8 October, before activation, the code's recorded HTTPS journey passed 54 selections and 324 strict controls, private-route/origin guards and busy recovery. The later hosted case completed and retained its evidence/session/admission across a real restart. The selected hosted result was independently checked; a separate supplement reviewed consistency of operator-reported remote retention and browser restoration. Reviewers did not repeat remote UI or private hash actions and provide no external-service attestation. Useful free capacity through judging and independent cultural quality remain unvalidated.

The 8 October review of official Qloo materials supports the project's private caching, attributed contextual results and minimum inference context; application to an external model is an operational interpretation. It identified no additional individual email-approval gate for that scope. Keep raw provider captures and credentials outside public Git and raw download endpoints. The interpretation does not grant raw-corpus redistribution, training or universal provider reuse. [Official caching guidance](https://docs.qloo.com/reference/qloo-llm-hackathon-developer-guide#can-i-cache-qloo-api-responses-in-my-app) · [Safe use](https://github.com/qloo/qloo-hackathon-kit/blob/main/docs/SAFE_USE.md)

Bind final English materials and the selected execution mode to their verified revisions and results. The deadline is 30 October 2026 at 23:45 EDT; judging runs 2–16 November. [Official rules](https://qloo.devpost.com/rules)

See [JUDGE-ACCEPTANCE.md](JUDGE-ACCEPTANCE.md) and [PUBLIC-NEW-CASES.md](PUBLIC-NEW-CASES.md) for exact gates and owner configuration.

## Appendix: retained earlier evidence

- The 7 October hosted source `e08ddf2a7b7751b07b9c0b4635ad838247c44c00` passed 54 HTTPS selections/324 checks and a process restart preserving 382 evidence hashes. Its bounded keyboard, desktop and 390-pixel mobile checks retain that dated scope; they are not a fresh restart/browser test of the enabled deployment.
- Earlier published source `20d6abfe489eff5ae361d8c45a92bf14d4133de9` passed 285 tests per platform. The subsequent User-Agent source `69102a29aa68f4ecea77f7861636ece9a2e7b69f` passed 289 per platform. Those are historical revisions, not current totals.
- The former 65-second pacing example had a 2,470-second spacing lower bound. The reviewed current plan uses 22 seconds; neither example establishes universal quota entitlement or a latency guarantee.
- The private Windows v9 installation and earlier transport/partial captures remain preserved separately. Their existence does not alter cultural FAIL gates or authorize public provider-data redistribution.


</details>

</details>
