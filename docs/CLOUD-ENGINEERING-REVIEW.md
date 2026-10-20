# Cloud engineering review — 13 October 2026

> **Human testing update — 20 October 2026:** Three real people (the creator and two friends) are reported to have tested the application, with positive qualitative feedback. See [current human testing evidence](DEMO-GUIDE.md#informal-human-testing). Earlier technical records below did not collect structured human preference labels; they are not a current count of everyone who used the app.

## Outcome and scope

Review started from `250aac1258535db593db644747a5659003fced82` on
`seypherWork/affinityqa`. A reproducible frontend recovery defect was corrected:
after a progress request failed, **CHECK CURRENT STATUS** could read the same
running case but leave automatic polling permanently stopped. The observer now
restarts after an explicit successful refresh, including when the job ID and
status have not changed.

A second defect was diagnosed on the original retained Render capture: discovery v2 rejected duplicate UUIDs across musical and nonmusical search variants before eligibility filtering. New discovery v3 plans validate every raw row, filter musical eligibility, then require unique, consistent selectable profiles. All raw samples and original v2 source files remain unchanged. See `DISCOVERY-V3-SEARCH.md` for the frozen contract and deployment continuity.

The frontend repair only affects reading progress and capabilities. It does not restart
a capture, refund an admission, change the experiment, or alter acceptance
thresholds. Existing abort-controller cleanup prevents old observer requests
from surviving a restarted polling effect.

## Verification

| Check | Observation | Boundary |
| --- | --- | --- |
| Baseline Linux Python environment | All 461 tests passed in 116.767 seconds with the locked dependencies | Synthetic/source tests, Python 3.12.14 |
| Final Linux Python suite | All 479 tests passed in 119.181 seconds, including source-bound v3 and diagnostic regressions | Locked dependencies; zero real provider calls |
| Frontend typecheck and production export | Passed on the final v3 frontend and recovery patch | Node 24.19.0, pnpm 11.25.0, locked dependencies |
| Browser reproduction on unchanged baseline assets | Failed waiting for COMPLETE after successful same-status recovery | This established the defect before editing the component |
| Desktop recovery after one interruption | PASS, four job GETs and one session POST | Built assets, synthetic responses, zero provider calls |
| Mobile recovery after two interruptions | PASS, five job GETs and one session POST; 390 × 844 viewport fits without horizontal overflow | Built assets, synthetic responses; viewport coverage is not physical iOS/Safari acceptance |
| Complete new-case browser journey | PASS: actual frontend, FastAPI and case store; search variants, explicit selection, result, verification HTTP response, reload/session restoration; exactly one execution admission | Four fake Qloo calls and two fake model calls; zero real provider calls |
| Original retained search diagnosis | Independent original-source verifier passed; B rejected duplicate UUIDs, five raw rows/four unique IDs; proposed pure projection produced A=5/B=4 musical choices | Read-only server inspection; original artifact inventory unchanged; no new provider/model calls |
| Public health and recorded summary | Both returned HTTP 200; new cases configured, capture inactive; recorded summary COMPLETE, causal PASS, cultural NOT_VALIDATED, release BLOCKED | Read-only observation on 13 October; health is not provider readiness or sustained capacity |

The recovery browser harness fails closed on unexpected API routes and external browser
requests. It runs against exported frontend files served by a temporary loopback
server and intercepts all synthetic API responses. Apart from its one simulated
session POST, no case is prepared, executed, or confirmed during recovery.

The runtime's default Playwright browser download was unavailable in this
environment. Local browser checks used Playwright 1.62.1 with Chromium
153.0.8010.0 supplied separately by `@sparticuz/chromium` 153.0.0. That browser
binary is not included in the project or source archive. CI installs its normal
Playwright Chromium on Linux; CI results must be checked separately.

## Reproduce the browser regression

After installing the locked web dependencies and building the frontend:

```text
cd web
npx --yes pnpm@11.25.0 exec playwright install chromium
npx --yes pnpm@11.25.0 test:recovery
npx --yes pnpm@11.25.0 test:case-journey
```

Linux hosts missing browser system libraries can use Playwright's
`install --with-deps chromium` command. An already-installed compatible Chromium
may be selected with `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`. Playwright is a pinned
development dependency; it is not imported by the product frontend. The public
source builder includes the regression harness and this review.

## Remaining acceptance work

| Item | Current evidence | What closes it |
| --- | --- | --- |
| Actual new-case hosted browser journey | Retained live v2 trial stopped PARTIAL; original response diagnosis and counterfactual v3 projection now complete; full v3 browser journey passes with fake providers | Observe a complete new owned case after a reviewed v3 deployment on the exact runtime; do not repeat or relabel the admitted partial case |
| Sustained judge capacity | A liveness/summary read succeeded; internal admissions do not reserve Groq quota | Verify the account's provider allowance, hosting persistence and usable access over the judging period |
| Remote causal attribution | Prior genuine runs retain varied fingerprints and INCONCLUSIVE attribution | Comparable controlled observations under the frozen causal protocol; no relabelling of those prior runs |
| Cultural recommendation quality | NOT_VALIDATED; the dated technical acceptance contains no structured human preference ratings | Independent real-person labels and the existing evaluation protocol |

The scoped technical patch can be reviewed without claiming full jury
acceptance. Local checks made no provider calls. The separate authorized live
browser trial below made two Qloo requests and no model calls. No paid service
change, deployment, or competition submission was performed. Render confirmed the current live deploy is `250aac1258535db593db644747a5659003fced82` with auto-deploy disabled. The current
hosted application is separate from the proposed source changes until deployed.

## Separate live browser trial — retained failure

On 13 October (Europe/Brussels), one new technical test session and one plan
were created through the hosted browser UI. The explicit test interests were
Sade and Nine Inch Nails, with one favorite and one exclusion per profile;
these are engineering inputs, not human-participant preferences. The reviewed
plan allowed four Qloo requests and two model decisions, with explicit artist
confirmation required between search and inference.

Job `20261012T230633Z-8a5793a9` stopped after the identity-search phase. The UI
showed **PARTIAL**, two of four provider samples saved, zero of two model
packets saved, and `SchemaError`. The selected downloadable verification
confirmed `VERIFIED_PARTIAL`, `INCOMPLETE`, two provider attempts, zero model
attempts, cultural `NOT_VALIDATED`, and release `BLOCKED`. Plan SHA-256:
`6a9892646e70bea1644e37102a3e7fb34ec0de7a5b2a693f2076756994b1a806`;
receipt SHA-256:
`3cb4fac52d4eb581456e5f6a5d60416e22b9d3d316bd2288e5174d7bb145e0c6`.

No identity was confirmed, no model inference started, and the admitted case
was not repeated. The safe public receipt does not contain the failing provider
body or a detailed exception cause. Read-only access to the original capture directory on Render subsequently passed the independent v2 source-bound file verifier and reproduced `DUPLICATE_ENTITY_IDS` in profile B. Both searches returned HTTP 200 and five raw rows; B contained four unique UUIDs. A repeated UUID had one musical and one nonmusical variant with differing types/metadata. The proposed search-only policy returned A=5/B=4 musical candidates from those same verified samples. Original file inventories remained unchanged, with zero new Qloo or model calls. This establishes the response-validation stop and supports the new projection; it does not claim a newly completed live capture. The retained receipt and admission remain partial and consumed. Private response bodies, identities, paths and credentials were not published.

## Delivery state

The reviewed changes are on `work/cloud-review-20261013`. Earlier GitHub writes returned HTTP 403 because no connector installation was available. The owner enabled the installation on 13 October, and remote branch creation succeeded. The final pull request and its exact CI status are the review entry point; local checks above are separately recorded. Neither main nor the hosted application is changed by creating the review branch.

The handoff includes an applicable patch, validation log, sanitized retained-case diagnosis and continuation instructions. Deploying the new manager over an existing public store requires the explicit stopped-store source continuation in `PUBLIC-NEW-CASES.md`; no policy/admission reset or automatic migration is included.
