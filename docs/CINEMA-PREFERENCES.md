# Explicit film preferences

The **FILM PREFERENCES** case adds cinema information to the configured remote
operator. Each of two profiles can select up to five favorite movies and up to
fifteen excluded movies from the fixed twenty-movie catalog. Favorites provide
soft evidence about tastes. Excluded movie IDs are mandatory delivery constraints.
Unknown IDs, duplicates, overlapping favorites/exclusions and fewer than five
eligible movies are rejected before credentials or provider requests.

## Reviewer journey

1. Open a review session and choose **FILM PREFERENCES** in New case.
2. Enter two distinct musical interests. Expand each profile's film choices.
3. Mark favorites and movies to avoid, then prepare a new plan.
4. Review the exact named choices, plan fingerprint and declared budget before
   starting that plan. Editing either profile invalidates the selected plan.
5. When artist confirmation is supported, choose **FIND ARTISTS**. This performs
   two searches restricted to artist/person identities, with no model inference.
   Select one returned musical identity for each profile; there is no default
   selection. Check each canonical name and confirm **CONFIRM ARTISTS & START
   REVIEW**. The selected identities must differ. A query spelling is not a
   verified artist identity, and a non-musical person or album cannot be selected.
6. Inspect raw model top five, delivered five and the declared preferences-aware
   baseline. Downloading the selected receipt does not repeat execution.

This separate protocol uses at most **four Qloo attempts and two Groq decisions**,
plus one cached boundary check per profile. It uses the same configured model,
pacing, single shared worker, private credential loaders, session ownership,
CSRF checks and cumulative execution admissions. Failures stop without retry,
fallback or admission refund; available partial results remain visibly partial.
The existing **PROFILE INTEGRITY** case still uses 39 decisions and the three
previously declared faults. Film preferences do not constitute a fourth repair
or change the historical thresholds, scores or datasets.

## Evidence contract

Cinema capture request v3 and plan v4 use `cinema-preferences-v1`. The old artist
request v2 remains supported. A separate prompt/manifest binds the preferences
actually sent to the model. Cache keys include profile, preferences, catalog,
Qloo context and model manifest. Artist hashes remain distinct from preference
and combined-intent hashes: Qloo receives the artist only.

The confirmed-identity workflow uses request v4, plan v5 and
`cinema-confirmed-identity-v1`. It preserves the earlier cinema driver and
verifier. Both phases share one execution admission and one capture directory:
two typed searches, followed only after explicit confirmation by two insights
requests and two model decisions. Opening a case or restarting a server does
not repeat calls. A pending selection survives a normal restart; a crash during
an active phase is marked abandoned. A saved confirmation without its committed
active transition is also abandoned. No retry or automatic resumption is offered.

The verifier binds the chosen IDs to the original candidate responses, the
immutable search-ledger prefix, the saved plan and installed sources. Final
counters include both phases. An identity spelling fix is a functional correction;
it does not prove better taste prediction, alter previous simulation results or
turn fictional profiles into real participants.

The raw twenty-movie model permutation and its original observation hash are
retained. `stable-eligible-first-top-five-v1` then delivers the first five
non-excluded movies, with a separate delivery hash and visible selection-change
indicator. The verifier independently reconstructs the payload, remote envelope,
tool provenance, pacing, cache boundaries, delivery and baseline. It audits file
coherence; it does not externally attest provider weights or service signatures.

The baseline gets the same explicit favorites and exclusions: favorite movies
first, Qloo order as tie breaker, then the same exclusion policy. This is a
declared preferences-aware baseline, not an artist-only Qloo comparison. Matching
or differing from it is not itself proof of higher recommendation quality.

`preference_gate=PASS` means complete delivery conforms to excluded catalog IDs.
Cultural quality stays `NOT_VALIDATED`; causal and integration fault gates are
`NOT_EVALUATED` for this separate case. Human satisfaction is unmeasured. No
real participants, demographic identities or universal accuracy claims are
created by this feature. Genre/theme exclusions are not offered: this version
only enforces exact selected movies, avoiding unverified genre inference.

## Existing public storage

This update changes the source seals of the public controller and manager.
Startup deliberately rejects older seals without an explicit reviewed
continuation. It never erases storage or resets budgets. With the service stopped:

```powershell
python -B scripts/continue_public_policy.py --storage "ABSOLUTE_EXISTING_STORAGE"
```

Review the printed storage inventory and proposal fingerprint. After owner
approval, run the same command with `--execute --expected-proposal-sha256 HASH`.
It appends the next bounded `public-policy-continuation-v2-000001.json` record
and verifies every existing policy, session, ownership, job and capture remains
unchanged. A legacy `public-policy-continuation.json` anchor is retained.
Continuation cannot alter origin, template, cadence, expiry or budgets. The
original sealed records still define admissions. Later source changes and
compatible rollback require another exact reviewed append; startup never
creates one. The driver cannot acquire an active service's storage lock.
See [the continuity and rollback contract](PUBLIC-NEW-CASES.md#continue-the-same-case-storage-across-source-versions)
for limits, staging, failure handling and older-release compatibility.

These commands describe a reviewed deployment step. Creating this source does
not publish it, modify the hosted service or authorize a candidature submission.
