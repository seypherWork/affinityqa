# Remote model preparation candidate

This unpublished source derivative adds a Groq ranking adapter and a separately
versioned capture, verifier and panel integration for a future externally usable
demonstration. The original reviewed sources remain in their unchanged trees;
this candidate changes only the integration files and preserves the historical
Qloo/Ollama captures. It does not change their outcome,
noise thresholds, cultural-quality status or license boundary.

## Intended server contract

The reviewed option is `openai/gpt-oss-20b` through the fixed HTTPS Groq chat
completion endpoint. It requires a private server-side Groq credential and an
owner-reviewed account plan. The implementation has no cloud calls at import or
construction, no local Ollama metadata/load calls, and no model download.

The adapter uses the existing musical-profile/movie-catalog/Qloo-context payload
and unchanged causal operator. It requests strict JSON Schema: every one of the
20 catalog positions exactly once. Independent local checks reject missing,
duplicate, Boolean or invented positions, truncated completions, refusals,
unexpected models, invalid usage and changing returned deployment fingerprints.
There is no model switch, schema downgrade, automatic retry or completed tail.

Attempts are serialized and capped at 39. Request and response sizes and timeout
are bounded; rejected remote attempts consume the decision budget. Completion
tokens are capped at 1,024. Prompt usage is checked after the remote response
against 8,192 tokens; this is not a prepaid spending limit or an exact local
tokenizer estimate. Account billing/rate limits must be inspected separately.

The transport restricts credentials to `api.groq.com`, validates TLS and rejects
redirects/proxies. The remote capture passes the Qloo key as an additional
forbidden input secret. Credentials, error bodies and private reasoning
are excluded from model payloads and recorded observations. The original Qloo
response body is not sent: the existing bounded movie context is projected into
the model input.

## Identity and evidence boundary

An API model ID and optional `system_fingerprint` do not attest an immutable
weight revision. The manifest states `model_weights_sha256: null` and revision
attestation false. It never manufactures an Ollama digest. A returned fingerprint
must remain consistent across successful decisions, including its absence.

Test transport injection is labelled `test-double-only`. Offline tests include
the unchanged 39-decision healthy/fault/repair protocol, but do not establish
real Groq schema compatibility, account capacity, performance, cultural quality
or external hosted acceptance. The independent review fixed and reproduced a
reasoning-null/empty compatibility defect; the failed test evidence is retained.

The local v1 capture/verifier still does not admit this adapter. The separately
bound remote v2 flow and explicit owner-selected manager are documented in
[INDIVIDUAL-REMOTE.md](INDIVIDUAL-REMOTE.md). Each accepted response now has an
auditable closed envelope and independently rebuilt effective request hash.
The hosted public demo must not advertise remote inference until actual service
and hosted acceptance are verified. No publication, account signup, terms
acceptance, billing change, provider inference or deployment was performed by
preparing this derivative.

## Official sources consulted 2026-10-06

- [Groq structured outputs](https://console.groq.com/docs/structured-outputs)
- [Groq reasoning controls](https://console.groq.com/docs/reasoning)
- [Groq API reference](https://console.groq.com/docs/api-reference)
- [Supported models](https://console.groq.com/docs/models)
- [Billing FAQ](https://console.groq.com/docs/billing-faqs)
- [Rate limits](https://console.groq.com/docs/rate-limits)

The exact array schema/parameter combination and effective account limits still
require a deliberately budgeted real-provider trial. A key must remain in a
private file or server environment; never paste it into a conversation or repo.
