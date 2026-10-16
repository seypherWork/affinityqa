# Taste discovery and the shared model pass

This source candidate introduces a cinematic discovery interface and an additive
paired-ranking protocol. It is not a claim that this candidate is deployed, that
a fresh hosted trial has passed, or that the model responds instantly. Historical
acceptance remains dated in [the acceptance record](JUDGE-ACCEPTANCE.md).

## Reviewer journey

1. **Your tastes.** Open or restore your private visitor session. Enter two musical
   interests. Optionally add up to two films you already like across the two taste
   scenarios. The twenty-film output catalog is disclosed before you start;
   additional favorites and exclusions are available under its optional controls.
2. **Exact identities.** Review the displayed request budget. Search once, then
   explicitly choose the artists and each film's title and year. Typing makes no
   provider requests. Ambiguous matches are not silently guessed and unverified
   years cannot be confirmed.
3. **Five films.** Confirm to start ranking. Each taste scenario receives five
   eligible films from the disclosed catalog. Open the evidence details to inspect
   the raw ranking, same-input Qloo baseline and constraints. Download the selected
   verification; restoring the case reads its saved state rather than rerunning it.

Both scenarios may be tastes entered by one person. They are not a human study,
independent participants or a guarantee of cultural satisfaction. External film
inputs are positive seeds, not an expansion of the twenty-film output universe.

## One shared request, with a separate contract

When the server advertises `fast_pair_review_supported`, the discovery interface
requests `fast_pair_review: true`. This creates request schema 7 and protocol
`cinema-paired-discovery-v1`. A single bounded Groq response ranks both scenarios
using a shared catalog and separate taste inputs. They are correlated projections
of one shared model observation, not two independent model decisions.

The joint identity, film inputs, preferences, provider contexts, catalog and
protocol version must remain bound through the request, cache, capture and
verification. An invalid shared response stops the shared review. There is no
silent fallback to two new provider calls or a previously saved successful list.

The default API behavior remains unchanged when the flag is absent or false.
Existing two-decision cases retain their own protocol and budgets. The full
39-decision integration experiment remains an explicitly acknowledged advanced
option, with its own waiting time and historical evidence contract. Existing and
running cases are retained when switching between discovery and recorded repair.

## Waiting and free capacity

One shared request removes the second model request from this particular ranking
path. It does not remove the organization's shared free quota, preceding jobs,
provider latency, storage safeguards or uncertain outcomes. The application must
reserve the complete conservative input/output token budget before dispatch and
must not assume a prompt-cache hit. Fresh work may queue. Saved cases remain saved
cases and recorded repairs remain recorded repairs.

Groq stays on the free plan. No new model, subscription, server or credential is
introduced by this source change. Offline synthetic tests prove contracts and
failure handling; they do not prove live provider compatibility, latency or
recommendation quality. Cultural quality remains `NOT_VALIDATED`.

## Visual references and assets

The information hierarchy was informed by [Seerr](https://github.com/seerr-team/seerr),
[Letterboxd](https://letterboxd.com/about/what-is-letterboxd/) and
[MUBI](https://mubi.com/en/about). These are references for discovery, clear film
identities and editorial presentation. AffinityQA's warm dark palette, amber
accents and abstract SVG illustrations are original. The cards contain real
catalog titles and years; the abstract artwork is not an official movie poster.
No film ratings, genres, synopses, streaming availability or human validation are
invented. See [asset provenance](ASSET-PROVENANCE.md).
