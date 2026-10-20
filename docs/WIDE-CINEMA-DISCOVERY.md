# Film discovery from a confirmed starting point

The versioned `qloo-wide-cinema-discovery-v10` protocol retrieves films for a
confirmed movie or artist, with an optional known favorite film in music mode.
The visitor explicitly chooses the starting identity. Two Qloo Insights pages
of up to fifty films form the actual candidate pool. No fixed output catalog
or `filter.results.entities` list is sent. Deduplication, observed integer
years and input exclusions determine eligibility; at least five films must
remain. All retrieved observations and partial failures stay preserved.

## AI selection and source descriptions

One Groq Free decision on `openai/gpt-oss-20b` ranks five distinct eligible
identities. Its input retains the complete named candidate rows, their original
indices, titles, years, observed affinities and provider order, plus the
confirmed starting point and the visitor's direction. Descriptive metadata
stays on the server and does not expand the model request. Free taste text is
sent to the model, not to Qloo as an undocumented Insights parameter.

The model must return one closed JSON object with only
`ordered_catalog_indices`: an ordered array of exactly five closed objects,
each containing only `catalog_index`. Every index must be a strictly typed
integer, unique and eligible. Titles, years, UUIDs, text, explanations,
`reason_refs` and all other extra fields are rejected. JSON remains locally
strict, including duplicate keys, nonfinite values and surrounding prose.
The captured provider envelope and `selected_catalog_indices` observation
contain only the actual index objects. The server reconstructs canonical
UUIDs, titles and years from the sealed candidate catalog at those indices,
preserving their order. These derived identities and source descriptions are
never inserted into the model envelope or represented as Groq's words.

After selection, the server displays a literal `properties.short_descriptions`
value from the same first eligible captured row that supports that film's
UUID, exact title and year. A unique Spanish value is preferred; if Spanish is
absent, a unique English value is allowed and labelled English. Identical values
are deduplicated. Conflicting Spanish values, an unsafe Spanish value or any
malformed description item cause a closed fallback, rather than a convenient
English or later-page replacement.

A source extract must be the complete literal value, forty to 240 characters,
with canonical whitespace and no nonprintable controls or credential markers.
Its Unicode characters are not NFKC-normalized, translated, paraphrased,
truncated or padded. HTML-looking metadata is escaped plain text in the browser.
Missing, ambiguous, malformed or unsafe metadata produces the fixed notice:

> Seleccionada por IA entre las películas obtenidas para esta búsqueda. No hay una descripción breve vinculada disponible.

The title and year remain separate visible identity fields. Missing description
coverage never removes a film from the candidate pool. No genre inference,
generated plot detail or additional metadata request fills a gap.

## Evidence and independent verification

The private `wide-context.json` contains the complete server-only grounding
registry and its hash. Each explanation binds the catalog index, UUID, title,
year, original page and row, raw sample and response hashes, language, JSON
pointers and literal UTF-8 value hash. Source extracts use `SOURCE_EXTRACT`;
closed notices use `RETRIEVAL_CONTEXT`. Both use
`SOURCE_BOUND_NOT_FACT_CHECKED` and explicitly deny provider-cause verification.
These labels establish fidelity to an observed source, not independent truth
of Qloo metadata, internal ranking reasons, cultural quality or satisfaction.

The separate verifier rebuilds the registry and displayed text directly from
the preserved raw pages using its own extraction implementation. It does not
call the producer's registry function or trust the stored registry. It checks
the context, decision, actual indices, independently derived identities,
server result and all source bindings.

Transport remains explicit text mode with a 2,048-token completion cap, an
8,000-token total reservation limit and the unchanged 1,024-token input framing
guard. `WideHarmonyTokenEstimator` counts the full exact wire. Both the agent
and normal service factory use it; the independent verifier recalculates the
same reservation. A request above the limit stops before dispatch, without
reducing the pool, changing providers or retrying a sent decision. Text mode
does not remotely guarantee JSON or local acceptance.

## Saved cases and the current display

Read-only v3 through v9 decoders retain their original four source snapshots
and original shared source bindings. Earlier complete and partial outcomes,
model envelopes, explanations, receipts, charges and files are not rewritten
or regraded. Old pending plans cannot execute through the new protocol.
Explicit relocation is available only to the historical v3 pure verifier.
The earlier v9 echoed-title contract stays strict in its decoder. A retained
title-echo rejection remains partial; the new contract never normalizes an old
title, salvages its indices or promotes that failed attempt into a success.

Owned completed wide cases receive a derived `wide_cinema_display` at the top
level of their read response. It is outside the historical `result` and is
bound to the original receipt and the same captured source pages. Cards use
only this checked display, never archived model prose. A brief notice identifies
free model explanation as archived for v3 through v8. Source-grounded v9 and
v10 displays remain current. Invalid or unavailable display evidence
leaves a fixed no-plot notice; it cannot rescue the original prose.

The original verification download continues to serialize the original result,
without this display overlay. Reading history, restoring a session, refreshing
or downloading evidence does not create a new recommendation or provider send.
Ownership, CSRF, queues, provider quotas and failed/unknown-send controls remain
unchanged. The maximum for a film or artist alone is three Qloo requests and
one model decision; an artist with a favorite film may use four Qloo requests.
Native caching may reduce new sends without bypassing evidence accounting.

## Presentation and limits

The existing local design, manual artist/film choices, saved cases and five-card
layout remain. The interface states that AI selects and Qloo supplies the source
description. Source and language are accessible beside each extract. Each card
uses project-authored abstract SVG artwork labelled ORIGINAL ILLUSTRATION. It
is decorative, not a poster or a depiction of a film, cast, plot or genre. No
third-party image loads, including for historical cases. The server's image
policy permits only same-origin/data images. Selection and source binding are
unchanged; original image metadata stays in archived verifications.

Provider metadata and images are outside the original-code MIT grant; raw
provider captures, personal case stores and image binaries are not included
in the public source package. See [asset provenance](ASSET-PROVENANCE.md) and
[licensing scope](LICENSING.md).

Source builds and synthetic engineering tests do not prove actual provider
acceptance or cultural quality. A local source correction does not identify
the unique cause of earlier HTTP 400 responses or guarantee future completion.
Current real-service acceptance, hosted deployment, public CI and publication
require their own evidence and approval. Cultural quality remains
`NOT_VALIDATED`; technical completion and source fidelity are limited claims.
