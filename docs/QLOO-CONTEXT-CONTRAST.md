# Controlled Qloo context contrast

The recorded `wrong-tool-profile` incident isolates one consumed model input:
`provider_movie_context`. The request profile, task, ordered movie catalog,
output schema, tool notice and recorded model manifest must stay fixed. Before
and after are distinct fresh saved decisions. Transport nonces are not model
inputs. The other two supported incidents do not isolate Qloo context and do
not display this comparison.

Thirteen controls bind both decisions to saved execution packets, reconstruct
their Qloo context independently, check fixed inputs and three distinct healthy
controls, and reject ambiguous displayed title/year identities. The plan,
frozen policy and execution manifest must agree. The comparison never creates
a model or provider request and never changes saved artifacts or old receipts.

The ordinal ranking distance is compared with the original frozen repeat-noise
barrier (epsilon 1e-12). An observed change above that barrier is separate from
recovery: all three after-to-healthy distances must be within the bound. An
observed recovery also requires the before ranking to be outside every healthy
reference. The displayed number of replaced films and changed top-five order
are independently checked against their title/year rows.

Results can be `OBSERVED_CHANGE`, `NO_OBSERVED_EFFECT`, or `CONFOUNDED`.
Confounding suppresses all metrics and positive attribution. Invalid or unbound
evidence fails closed. No effect is a valid negative result, not an error.

Public replay schema v3 adds one closed `context_contrast` v1 projection to the
existing semantic diagnosis and six recovery checks. Explicit v1/v2 readers
remain, but a v3 summary cannot silently downgrade the replay. No new source
packets, entity IDs, credentials or filesystem paths are exposed.

This contrasts matching and mismatched Qloo context in a saved experiment. It
does not compare Qloo against no Qloo, establish model internal reasoning,
measure general recommendation quality, or validate personal/cultural taste.
Synthetic local fixtures establish the engineering controls only. An authorized
read-only replay of a previous real-service capture is a separate evidence tier.
Human taste validation remains `NOT_VALIDATED` until separately measured.

Local checks: `python -B -m unittest discover -s tests -v`, the existing locked
frontend build, and `node tests/browser/diagnostic-evidence-journey.cjs` (also
`--mobile`, with the documented isolated synthetic host/runtime environment).
These commands require no Qloo or Groq keys. Preserve Groq Free and all cases.
