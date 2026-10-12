# Diagnose a retained identity-search failure

Use this operator tool when a saved case stopped during artist search with a
generic `SchemaError`. It reads the **original capture run directory**, not the
selected public verification download or the parent job directory. It makes
no Qloo or model calls, selects no identity, and writes no capture artifacts.

```text
python -B scripts/diagnose_identity_search.py /absolute/private/capture/run-directory
```

Use the project's installed Python interpreter. Capture artifacts must remain
in their original declared location where required by the protocol, and the
capture/verifier source files must match the sealed source revision. A renamed
or copied folder is not a substitute for that binding. Do not edit a plan or
receipt to make it pass. Locate the owner's retained capture directory using
the job/capture index, then run the diagnostic on the owner's server or other
environment that preserves the exact bindings.

The tool supports original identity-v1, discovery-v2 and discovery-v3 searches before
confirmation. It runs the existing independent file verifier first, including
sample hashes, request bindings, ledger ordering and source checks. It then
replays candidate validation on the recorded responses and checks the file
inventory again. A later confirmed capture must use its full existing verifier.

| Output | Meaning |
| --- | --- |
| `RECORDED_RESPONSE_REJECTION_REPRODUCED` | Current source matching the sealed revision rejects at least one immutable recorded search response. Inspect the fixed reason code per profile. |
| `STOP_CAUSE_NOT_REPRODUCED` | The retained response passes candidate validation; a storage or other boundary may have stopped. The tool does not invent an original exception cause. |
| `SEARCH_COMPLETE` | Candidate search completed and awaits selection. This does not approve recommendations, release or cultural quality. |
| `EVIDENCE_REJECTED` with exit code 1 | The original evidence, location, supported phase or source binding could not be verified. No diagnostic verdict is issued. |

Reason codes distinguish malformed envelopes, missing types, invalid UUIDs,
duplicate IDs, result-bound violations, noncanonical names, no verified musical
candidates, transport failures and HTTP failures. They contain no provider
names, IDs, artist queries, response bodies, credential values, paths or original
exception text. Do not paste or publish the private input artifacts merely to
share the diagnosis. The output retains `NOT_VALIDATED` and `BLOCKED` gates.

The retained 13 October case `20261012T230633Z-8a5793a9` was subsequently inspected read-only on Render. Its original source-bound verifier passed and candidate validation reproduced `DUPLICATE_ENTITY_IDS` for B. Both responses had five raw rows; B had four unique IDs, with one repeated musical/nonmusical variant. The proposed pure v3 projection returned A=5/B=4 musical choices without altering any file or making a new call. The original receipt remains `VERIFIED_PARTIAL`; the case is not retried, relabelled or culturally validated. See `DISCOVERY-V3-SEARCH.md`.

The official [Qloo entity-search reference](https://github.com/qloo/docs-public/blob/d4a0eb978518f7fb404993d1509d11b21239ada6/reference/get-search.md)
documents `types` and `take` as search parameters. The code's `take=5` is
therefore supported by the inspected reference; it was not changed to a
speculative `limit` parameter. Documentation review is not live-provider
acceptance. No parser rule or capture threshold is relaxed by this diagnostic.
