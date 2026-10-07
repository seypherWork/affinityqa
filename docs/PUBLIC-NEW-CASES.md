# Public new-case service and HTTP integration

`affinityqa.public_cases.PublicCaseManager` prepares visitor isolation and shared
admissions for new remote cases. The public app accepts one explicit instance via
`create_public_app(..., case_manager=manager)`. Its owned HTTP routes are mounted
without exposing the local API. The public frontend provides explicit session,
plan, start, status and selected-verification controls. The CLI and Render
entrypoint accept explicit owner configuration; execution is disabled by default.
The recorded replay remains a separate section.

The [event overview](https://qloo.devpost.com/) requires an externally hosted,
working application usable from beginning to end. A completed synthetic service
test is not that acceptance. Account access, approved third-party transfer, real
provider execution and public capacity remain necessary acceptance work.
Independent cultural quality is a separate project evaluation goal; the official
rules do not prescribe our specific cultural gate.

## One operator, explicit retained budgets

The owner supplies the catalog, model, interval, origin and private credential
loaders. No visitor can choose a provider, output path, quota or model option.
One shared manager performs the unchanged 39-decision causal protocol, with at
most four Qloo attempts and a single active capture. Existing local defaults
remain 20 plans and three cumulative execution admissions; the public wrapper
requires its own explicit bounded policy.

The policy and controller/manager hashes are bound in `public-policy.json`.
Changing the policy for the same storage is rejected. A second instance cannot
acquire the worker storage lease. No quota is multiplied by creating an operator
per session. Each STARTED event is flushed, fsynced and read back before worker
launch. This is an observed local persistence boundary, not a guarantee against
all power loss, disk rollback or externally incurred charges.

Failed or abandoned admissions remain consumed. Restart does not resume them;
the retained history reconstructs the cumulative budget. There is no automatic
daily reset, refund, removal of expired sessions or deletion of evidence.
An orphaned plan after an ownership-write failure stops restoration until the
owner inspects it. The same process also blocks subsequent mutations after a
partial session or plan/ownership commit or an admission journal inconsistent with memory.
Existing readable evidence remains available; nothing is silently repaired or
discarded. Invalid visitor inputs are validated before that commit boundary.

## Anonymous ownership

A server-generated 256-bit random bearer token identifies one session. Only its
SHA-256 is persisted. Every case binds to that session hash; status, execution
and selected verification refuse other sessions with the same missing-access
error. There is no global list of visitor interests or cases. Expiry is checked
in server UTC and cannot be renewed by replaying an expired token.

A distinct mutation token is derived from the session bearer. The HTTP integration
checks it before preparing or starting a case and requires the exact configured
Origin. It rejects ambiguous critical headers and cookies, bounds JSON bodies to
4096 bytes with a five-second deadline and four shared body readers, and reserves
separate global session/write/read request slots before body parsing or dispatch.
Default minute limits are 12 session requests, 30 case writes and 240 case reads;
the owner may explicitly select values 1..600. These are request controls, not
execution capacity or provider quotas.

The bearer travels only in `__Host-affinityqa-case`, with HttpOnly, Secure,
SameSite=Strict, Path=/ and no Domain. Explicit HTTP loopback preview uses a
different `affinityqa-loopback-case` cookie without Secure. URLs with case query
parameters are rejected. Neither expired nor invalid cookies are automatically
replaced. Resuming a valid session returns its mutation token without extending
either server or browser expiry. Bearers are never returned in JSON. See
[OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
and [OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

The token identifies a session, not a verified person. Direct clients can create
more sessions; Origin checks do not authenticate humans. The global retained
budget limits admitted work but cannot guarantee jury availability under abuse.
Its actual value must be chosen after checking provider capacity and hosting
storage, with approval before activation or spending.

## Public result boundary

The service returns an allowlisted case view and selected verification summary.
It excludes filesystem paths, complete private inventories, provider envelopes
and raw Qloo responses. A complete simulated case stays SIMULATION_ONLY; a
partial remains partial. Causal, cultural and publication claims stay separate:
the new case never upgrades cultural NOT_VALIDATED or release BLOCKED.

## HTTP contract

| Method | Route under `/api/demo/cases` | Required access |
|---|---|---|
| POST | `/session` | Exact Origin and empty JSON object; existing cookie resumes only |
| GET | `/capabilities` | Valid cookie; only this session's jobs |
| POST | `/plans` | Cookie, CSRF header and exact Origin; strict artists A/B object |
| GET | `/jobs/{id}` | Valid cookie and matching case ownership |
| POST | `/jobs/{id}/execute` | Cookie, CSRF and Origin; exact plan SHA-256; single use |
| GET | `/jobs/{id}/verification` | Valid cookie; selected owned complete/partial summary |

The mutation header is `X-AffinityQA-CSRF`. Missing, unknown and other-session
case access return the same 404. Ambiguous headers/cookies return 400, CSRF/Origin
403, strict body errors 422, already-used/changed plans 409, request/admission
limits 429 and disabled or unverifiable service 503. Error text does not echo
private exceptions. Slash variants never redirect to an HTTP backend origin.
No global private receipt export is registered. Public app shutdown joins any
already admitted worker before releasing its shared lease; browser disconnect
does not cancel or retry a capture. Liveness states configuration and activity
without attesting real provider or cultural readiness.

## Explicit startup

Create an owner-reviewed JSON outside the public web export and repository. Its
exact keys are `schema_version` (integer 1), `request` (the remote v2 request in
[INDIVIDUAL-REMOTE.md](INDIVIDUAL-REMOTE.md)), `policy`,
`minimum_model_interval_seconds` and `http_limits`. `policy` requires the complete
closed object below, generated by `affinityqa.public_cases.public_policy(...)`.
The six configurable bounded integers are `maximum_sessions`, `maximum_plans`,
`maximum_executions`, `plans_per_session`, `executions_per_session`,
`session_hours`; retain every other field exactly. This example is for an isolated
preparation, not an approved production capacity. Its one cumulative
execution does not demonstrate useful judge access through the evaluation
period. Before submission, measure duration and provision approved capacity so
a visitor cannot exhaust the main judge journey. The rules specify free
judge access through evaluation, not a particular attempt count; neither
unlimited access nor eligibility follows from this example:

```json
{
  "schema_version": 1,
  "maximum_sessions": 5,
  "maximum_plans": 5,
  "maximum_executions": 1,
  "plans_per_session": 2,
  "executions_per_session": 1,
  "session_hours": 24,
  "concurrent_captures": 1,
  "maximum_qloo_calls_per_capture": 4,
  "maximum_model_attempts_per_capture": 39,
  "budget_period": "cumulative-for-this-owner-selected-storage",
  "failed_or_abandoned_admissions_refunded": false,
  "automatic_retry_or_resume": false,
  "session_is_a_verified_person": false,
  "provider_quota_or_cost_reserved": false
}
```

`http_limits`
requires `case_session_limit`, `case_write_limit`, `case_read_limit`, each 1..600.
Unknown fields, duplicate JSON keys and implicit defaults are rejected.

Both configuration and retained storage need explicit absolute paths. Preview
with `scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767
--cases-config <ABSOLUTE_OWNER_JSON> --cases-storage <ABSOLUTE_PRIVATE_STORAGE>`.
This enables plan inspection only. For separately authorized real execution,
also supply `--cases-execute --case-qloo-env <ABSOLUTE_QLOO_ENV>
--case-model-env <ABSOLUTE_GROQ_ENV>`. Startup checks file metadata; private
credentials are read only when an execution is admitted. Never place keys in
the command, browser or public source. No model is loaded on the visitor's PC.

Render uses `AFFINITYQA_PUBLIC_CASE_CONFIG`, `AFFINITYQA_PUBLIC_CASE_STORAGE`,
`AFFINITYQA_ENABLE_NEW_CASES` (exactly `0` or `1`, default `0`),
`AFFINITYQA_QLOO_ENV_FILE` and `AFFINITYQA_MODEL_ENV_FILE`. Origin comes from
`RENDER_EXTERNAL_URL`. Case-only startup does not require a recorded replay
bundle; if replay bindings are supplied, its original verification remains
mandatory. Do not activate either mode before owner approval.

## Browser journey and remaining acceptance

Opening the page makes no session mutation. The visitor explicitly opens or
restores the browser session, reviews the exact plan and starts it once. Closing
the browser does not cancel an admitted job. Reopening the session retrieves only
its saved cases. Session restoration does not extend expiry. A lost mutation
response pauses further mutations until the visitor reads current saved status;
the frontend never automatically retries an execution.

The page labels simulated adapters and keeps the previous 13/14 and 4/6 cultural
failures visible even without a replay bundle. The complete real provider case,
hosted HTTPS/browser acceptance, restart capacity and independent cultural
quality still require evidence. Default execution remains disabled. No account
terms, transfer, publication or deployment is authorized by this preparation.

On Windows, choose a short retained storage root. Preparation checks every
fixed capture artifact path in UTF-16 units against conservative legacy Windows
limits, including the longest summary filename, before reading keys or calling
providers. An incompatible root is refused with an instruction to choose a
shorter one; no registry setting or general extended-path support is enabled.
The same preflight protects both local and remote direct capture drivers.
