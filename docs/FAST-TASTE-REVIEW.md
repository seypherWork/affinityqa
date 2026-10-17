# Taste discovery and the shared model pass

This page describes the retained musical-comparison protocol. The additive
[open film-discovery protocol](OPEN-FILM-DISCOVERY.md) retrieves a new pool per
confirmed film; it does not change the historical fixed-catalog experiment.

The cinematic discovery interface and additive paired-ranking protocol are deployed
as `1bb98f8`, verified 17 October 2026. Two real cases completed with native
downloads and same-session restoration: 6 Qloo + 1 Groq and 4 Qloo + 1 Groq.
Their confirmation-admission-to-COMPLETE server intervals were 9.030 and 6.492
seconds without provider-capacity waiting. These exclude human selection, page
loads and browser observation delays; they are not a future latency guarantee.
See [dated acceptance and boundaries](JUDGE-ACCEPTANCE.md).

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

Groq stays on the free plan. No new model, subscription, server or credential was
introduced by this protocol. Offline synthetic tests prove contracts and failure
handling; the two separately documented hosted trials supply bounded real-provider
evidence. Neither establishes future availability or recommendation quality. All
four delivered lists matched their same-input Qloo baselines. Cultural quality
remains `NOT_VALIDATED`, with zero verified human participants.

## Observed abbreviated-query check

On 17 October, an additional identity-only case searched **Matrix** and
returned **The Matrix (1999)** as its first candidate, with the same canonical
Qloo ID as the previous full-title search. Three fresh Qloo requests covered
two artists and that film; zero Groq requests ran. No identity was selected
automatically. The retained case stops at AWAITING_IDENTITY_CONFIRMATION,
rather than representing another completed recommendation. This establishes
that specific missing-article example, not general spelling, translation or
partial-title coverage.

## Visual references and assets

The information hierarchy was informed by [Seerr](https://github.com/seerr-team/seerr),
[Letterboxd](https://letterboxd.com/about/what-is-letterboxd/) and
[MUBI](https://mubi.com/en/about). These are references for discovery, clear film
identities and editorial presentation. AffinityQA's warm dark palette, amber
accents and abstract SVG illustrations are original. The cards contain real
catalog titles and years; the abstract artwork is not an official movie poster.
No film ratings, genres, synopses, streaming availability or human validation are
invented. See [asset provenance](ASSET-PROVENANCE.md).
