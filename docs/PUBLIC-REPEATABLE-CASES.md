# Repeatable reviewer access

This version adds an explicit `repeatable-v1` admission mode. It removes the
application's lifetime plan and execution caps for one visitor identity. It
does not remove Qloo or Groq quotas, reserve future capacity, guarantee uptime,
or certify compliance with the organizer's testing requirement. Groq remains
Free and the hosted operator remains `openai/gpt-oss-20b`.

The existing finite-policy store and its consumed admissions remain sealed.
Activation requires a separately reviewed new configuration and separate
persistent directory. Keeping new code in GitHub does not activate this mode
on an existing deployment.

## Reviewer journey

1. Open the demo and choose **OPEN OR RESTORE MY SESSION**. The browser keeps
   an anonymous ownership cookie; this is not a verified human participant.
2. Enter two musical interests and optional known film favorites/exclusions.
   Review the plan before admitting it.
3. Choose artist identities explicitly when search finishes. The queue never
   makes this choice for the reviewer.
4. Inspect queue position, provider-capacity waits and saved progress. A wait
   before dispatch resumes from durable state. Reloading requires the explicit
   restore action and reads saved state; it does not create or execute a case.
5. Inspect the verified result and download its selected verification. Prepare
   another plan in the same session. Earlier cases stay available in history.

If a request has already been sent and no accepted response was persisted,
the case reports **UNKNOWN**. It is never silently resent. A recorded failure,
including HTTP 429, remains visible and consumes its actual attempt. A later
new plan is separate work. An individual request that cannot fit a configured
quota window fails before send instead of waiting indefinitely.

## Separate storage and historical ownership

The new store contains a policy binding, private SQLite ownership/job/provider
ledgers, a private exact-context Qloo cache and immutable capture attempts.
One service runs one capture dispatcher; no paid worker or database is added.

The historical reader never constructs the previous manager. Even its disabled
constructor could write recovery events. Historical jobs remain read-only,
including historical PLANNED jobs. Receipt and artifact fingerprints are
checked when read; completed old cases are not reinterpreted as new captures.
An existing ownership token can open a new ownership record while reading its
old cases, without changing old expiry records or refunding old admissions.
New ownership is valid through **17 November 2026, 04:45 UTC**, the end of the
official judging period. Losing the cookie does not grant access to another
visitor's cases.

## Provider accounting and evidence

Shared durable quota reservations cover conservative rolling minute/day
windows and explicit Qloo windows. Provider headers may impose lower capacity
or a longer wait. Groq request-limit headers refer to requests per day; token
headers refer to tokens per minute. Published defaults do not establish the
owner account's exact entitlement or remaining quota.

The new outer verification separates:

| Mode | Meaning |
| --- | --- |
| Fresh HTTP attempt | A new provider dispatch with an observed response |
| Private Qloo cache | A matching private owner/context entry, with original timestamp and hashes |
| Accepted reconstruction | The exact accepted operation from this job/stage, without a new dispatch |
| Unknown attempt | A dispatched operation with no accepted durable receipt; no automatic retry |

Original capture packets remain byte-bound original observations. New
provenance records outside their strict legacy artifact directories record the
current reuse mode. Outer receipts bind those records cryptographically. No
cached or reconstructed observation is described as a new provider request.
Source/operator bindings are checked before admission and resumed execution.

An observed token count above its reservation creates a durable provider safety
pause. Elapsed time and restarts do not clear it. A local evidence/storage write
failure likewise stops related captures and new admissions while retaining
queued work and readable evidence. These exceptional pauses require owner
inspection; they are different from a scheduled, recoverable quota wait.
Rejected provider envelopes retain only a closed status/error projection,
never an arbitrary provider debug body.

The original per-case two- or 39-decision bounds, explicit identity choice,
favorite/exclusion checks, cultural **NOT_VALIDATED** and zero verified human
participants remain unchanged. Completed synthetic cases verify engineering
behavior; they are not evidence of actual provider availability or film quality.

## Owner configuration

Create this configuration outside the public export. It is a new schema,
not an edit to the historical policy. The original validated `request` catalog
and model declaration must be retained; no credential belongs in this JSON.

```python
from dataclasses import asdict
from affinityqa.repeatable_cases import repeatable_policy
from affinityqa.provider_scheduler import GROQ_FREE_CONSERVATIVE

configuration = {
    "schema_version": 2,
    "admission_mode": "repeatable-v1",
    "request": original_validated_request,
    "policy": repeatable_policy(maximum_queued_jobs=128),
    "minimum_model_interval_seconds": 22,
    "http_limits": {
        "case_session_limit": 12, "case_write_limit": 30,
        "case_read_limit": 240,
    },
    "provider_limits": {
        "groq": [asdict(window) for window in GROQ_FREE_CONSERVATIVE],
        "qloo": owner_reviewed_qloo_windows,
    },
}
```

Qloo windows must be explicit conservative operating bounds or supported
account observations; inventing a Qloo monthly entitlement is not valid.
HTTP safeguards and concurrent queue capacity are independent of lifetime
admissions. A full queue preserves plans for a later admission attempt.

Install the original dependency lock and the separate repeatable lock:

```sh
python -m pip install -r requirements-backend.lock.txt
python -m pip install --require-hashes -r requirements-repeatable.lock.txt
python -B -m unittest discover -s tests -v
```

The new tokenizer asset is pinned and checked offline. Runtime never downloads
it. Token reservations are conservative preflight estimates with a framing
margin and completion allowance, not a claim about Groq's exact billing count.
An absent or changed tokenizer asset must not cause an unbounded request.

## Deployment selection

Keep the existing historical variables, secret-file paths, model, plan and
disk. Add only the new absolute paths after final rollout approval:

```text
AFFINITYQA_REPEATABLE_CASE_CONFIG=/var/data/affinityqa-repeatable-v1/owner-config.json
AFFINITYQA_REPEATABLE_CASE_STORAGE=/var/data/affinityqa-repeatable-v1/cases
```

The existing `AFFINITYQA_PUBLIC_CASE_STORAGE` is then passed only as the
read-only historical store. New and historical roots must be disjoint. Start
in maintenance with `AFFINITYQA_ENABLE_NEW_CASES=0`; inventory old files,
deploy, verify exact preservation and historical receipts, then activate only
after the reviewed checks. Turning execution off preserves read access.

For a local owner-managed preview:

```sh
python scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767 \
  --repeatable-config /absolute/private/owner-repeatable.json \
  --repeatable-storage /absolute/private/repeatable-cases \
  --legacy-cases-storage /absolute/private/sealed-cases
```

This command does not read keys or enable provider calls. Enabled operation
also requires explicit credential-file options and separately authorized
execution. Never transfer keys through a command argument or public source.
Before rollback, disable admissions and retain every new store/file; removing
the new selection variables can restore the old finite-policy runtime after
its source and store bindings have been checked. No rollback deletes history.

## Sources and acceptance boundary

[Groq rate limits](https://console.groq.com/docs/rate-limits) and
[Qloo official rules](https://qloo.devpost.com/rules), checked 14 October 2026.
The rules require free testing access through judging; replacing a one-use
application cap with repeatable admission addresses that technical defect.
Provider scarcity and actual long-term access still need operational evidence.
This document neither grants an organizer exemption nor submits the entry.
