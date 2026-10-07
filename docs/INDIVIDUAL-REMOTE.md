# INDIVIDUAL REMOTE CASES — CANDIDATE

This candidate connects a separately versioned Groq operator to new-case capture,
diagnosis, repair, read-only verification and the local panel. It is not yet
accepted against Groq's real service or deployed for unrestricted judging.
No cloud account, key, billing plan or third-party data-transfer permission is
inferred from the existence of this code.

## PREPARE A REQUEST

Create a private JSON request with `schema_version: 2`, two canonical musical
interests in `artists.A` and `artists.B`, exactly twenty actual movie identities
in `catalog`, and `model: {"provider":"groq","name":"openai/gpt-oss-20b"}`.
Each movie contains `entity_id`, `name` and `release_year`. Resolve real identities
before using a template. No fabricated catalog, historical default or local
weights digest is inserted by this operator.

```powershell
python scripts/capture_individual_remote.py --request private/request.json --output private/new-capture
```

Preparing a plan reads source/driver/dependency hashes. It does not read keys,
create the output, call a provider, load a local model or accept terms. Inspect
the returned fixed endpoint, model, options, source hashes and exact plan hash.

An unconfigured plan has `execution_pacing.configured: false` and cannot execute
real inference. Select an interval only after checking the actual organization
limits and sharing with other applications. Zero through 65 seconds is accepted;
zero is an explicit owner choice, not a default capacity guarantee. Set
`$affinityqaReviewedInterval` to the value reviewed for that account, then prepare
the exact plan again:

```powershell
python scripts/capture_individual_remote.py --request private/request.json --output private/new-capture --model-minimum-interval $affinityqaReviewedInterval
```

## EXECUTE ONLY THE REVIEWED PLAN

Keep keys in private files excluded from version control. The Qloo file contains
`QLOO_API_KEY`; the Groq file contains exactly one `GROQ_API_KEY` assignment.
Keys must never appear in the request JSON, command arguments or browser.
The remote credential loader does not discover files or override them from the
process environment. Review the provider account, actual rate limits, costs and
authorization to transfer these interests, movie names and Qloo context first.

```powershell
python scripts/capture_individual_remote.py --request private/request.json --output private/new-capture --model-minimum-interval $affinityqaReviewedInterval --execute --plan-sha256 <reviewed-hash> --env-file private/qloo.env --groq-env-file private/groq.env
```

The output must be new. Four fresh Qloo attempts resolve two exact musical
identities and collect their complete twenty-movie context. Inputs are sealed
before the first model decision. There are at most39 serialized model requests,
zero model metadata requests and zero model loads. The existing causal operator
is unchanged: six healthy decisions, legitimate cache controls, a frozen noise
policy, three repeats for each of three faults, actual repair and new decisions.
Faults are profile omitted from cache keys, stale profile, and wrong tool profile.

There is no retry, automatic model/schema substitution, invented tail ranking,
resume or timeout-driven restart. A failure stops the capture and preserves the
first failed attempt and all committed evidence. HTTP429 may stop a run; this
candidate does not claim that an unverified free account supports39 requests at
the required rate. Prompt usage is checked after each response and is not a
prepaid financial cap or a local tokenizer estimate.

The selected cadence is sealed in the plan and checked before execution. A
single serialized operator records each consumed slot before delegating its
decision. A monotonic clock controls the interval after admission is saved;
slow disk writes cannot shorten the interval between delegated decisions.
Each sleep slice is at most five seconds, with a 70-second scheduled-wait bound.
An interrupted wait admits no further slot; a failed admitted decision stops
the operator without a retry. Pacing records are local observations, not proof
of HTTP timing, billing limits or reserved provider capacity.

At 65 seconds, 38 intervals alone require at least 41 minutes and 10 seconds.
That is a duration implication of the selected policy, not an appropriate
default for judging. A faster reviewed setting needs verified account capacity.
Groq limits are shared at organization level, and a single request or daily
quota can still fail: [official limits](https://console.groq.com/docs/rate-limits).

## VERIFY WITHOUT CREDENTIALS OR NETWORK

```powershell
python scripts/verify_individual_remote.py private/new-capture/<run-id> --receipt private/verification.json
```

The exclusive receipt must be outside the captured directory. The verifier
checks the exact v2 plan and installed sources, Qloo sample/identity/context
bindings, sequential39-packet replay,54 session boundaries, healthy calibration
ordering, unchanged faults, independent score arithmetic and complete/partial
attempt accounting. A local v1 verifier does not silently admit v2, or vice versa.
The remote verifier also checks the independently defined pacing contract,
slot count, input-seal order, slot-before-packet order and recorded intervals.
Rehashing a false quota claim or inventing a faster interval cannot pass these
closed checks. This does not independently certify real dispatch timing.

Every accepted model packet embeds a closed, depurated response envelope: model,
completion ID, timestamp, optional deployment fingerprint, final catalog
permutation and typed usage. It excludes headers, arbitrary response fields,
refusals, private reasoning and both private credentials. Envelope hashes are
recomputed. The full parsed response hash is only a recorded observation; the
full response is deliberately not stored and its hash cannot be recomputed from
the projection. The effective HTTP request body hash is independently rebuilt
without Authorization. Fingerprints must stay identical through every accepted
decision, including presence/absence. All-null fingerprints are explicitly
unattested. Model IDs, optional fingerprints and seed7 do not attest immutable
weights, a provider signature or deterministic generation.

## LOCAL PANEL WITH THE REMOTE OPERATOR

Preparation only:

```powershell
python scripts/affinityqa.py serve --individual-provider groq --individual-template private/request.json --individual-output private/jobs
```

After provider/data-transfer review and deliberate owner configuration:

```powershell
python scripts/affinityqa.py serve --individual-provider groq --individual-template private/request.json --individual-output private/jobs --remote-model-minimum-interval $affinityqaReviewedInterval --individual-remote-enabled --env-file private/qloo.env --groq-env-file private/groq.env
```

The panel remains bound to numeric loopback. The browser supplies only the two
musical interests and then confirms the exact plan hash. It cannot select keys,
provider, model, endpoint, catalog, files or options. Credential loading occurs
only at deliberate execution. Progress counts committed samples/packets, distinct
from attempted requests. Results require a committed verifier receipt; changed
evidence is withheld, partials are visible, and restart never resumes an unfinished
job. Synthetic provenance survives restart even if test adapters are removed.
The interval belongs to the server owner; browser requests cannot choose or
change it. Enabling real remote jobs without that setting fails before loading
credentials or starting the server. Changing the setting after preparation
invalidates the reviewed plan before loading either key.

The storage limits of20 plans and three lifetime admissions are preparation
controls inherited from the local manager, not an unrestricted public judging
policy. Hosted new-case admission, capacity, actual provider limits, HTTPS origin,
judge access and period-long availability still require separate work and tests.
This local panel must not be exposed by simply changing its listening address.

## EVIDENCE BOUNDARIES

Denied-network fixtures establish these code contracts and simulated causal
behavior. They do not establish Groq schema acceptance, actual cultural behavior,
account capacity or external end-to-end availability. An internally passing causal
case is not an independent cultural evaluation: `cultural_gate` remains
`NOT_VALIDATED` and release remains `BLOCKED`. Historical cultural failures and
their thresholds are preserved. MIT covers owned code, not provider data rights.
