# Search names and partial verification

Wide cinema protocol v11 changes only musical identity eligibility. Every raw
Qloo row is structurally validated before display-name filtering. A musical
alternative whose name is not canonical printable text (NFKC, normalized
spacing, at most 300 characters) is not offered as a choice. Its raw observation
is retained unchanged. Conflicting musical profiles with the same UUID still
stop the search, including conflicts involving an unusable name. Invalid UUIDs,
envelopes, metadata or affinity values are never hidden by this filter.

At least one usable provider identity and the user's explicit confirmation are
required. The search text never becomes a fabricated identity. This is not a
claim of cultural quality or worldwide catalog coverage. The model, its options,
Groq Free scheduling and the two-page Qloo retrieval budget remain unchanged.

Frozen v10 source identities and an independent v10 reader preserve old complete
and partial captures. Historical failures are not rewritten or resumed.

An intact PARTIAL identity-search receipt in request schemas 8 and 9 may predate
final-capture counters. The reader counts its hash-verified immutable sample and
model artifacts. It never equates HTTP attempts with saved responses. Changed
receipts, samples or provenance still block download; full capture counters stay
mandatory. A readable partial receipt is not a successful recommendation.

Reproducible offline checks, from a prepared public-source environment:

```sh
python -B -m unittest discover -s tests -p 'test_partial_identity_projection.py' -v
python -B -m unittest discover -s tests -p 'test_search_name_isolation.py' -v
python -B -m unittest discover -s tests -p 'test_wide_cinema_v10_history.py' -v
node tests/browser/search-name-backend-journey.cjs
node tests/browser/search-name-backend-journey.cjs --mobile
```

Browser checks need the same built web export and existing browser dependencies
as the main workflow. Their provider replies are synthetic; they do not establish a fresh Qloo/Groq
acceptance result. A new real case must have its own recorded consumption budget.
