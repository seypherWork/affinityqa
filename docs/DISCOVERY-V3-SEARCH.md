# Discovery v3: musical identity search variants

The hosted engineering case `20261012T230633Z-8a5793a9` stopped in discovery v2
after two successful HTTP searches. Read-only verification of its original
private capture on Render reproduced `DUPLICATE_ENTITY_IDS` for profile B.
That response had five raw rows and four unique UUIDs. Two rows shared a UUID
and name but differed in types and metadata; only one passed the existing
musical eligibility rules. The original receipt remains `VERIFIED_PARTIAL`.

V2 parsed the complete search response as a unique-ID ranking before filtering
musical eligibility. V3 validates each individual row, applies the same musical
eligibility rules, then enforces uniqueness among selectable profiles. An
identical selectable profile (UUID, canonical name, type) is one choice.
Different musical profiles sharing a UUID stop with `SchemaError`. Invalid
nonmusical rows still stop; they are not hidden by filtering. The five-row
raw bound applies before any projection. All original response rows remain
in the immutable HTTP sample and its hashes.

The proposed pure projection was evaluated on the verified retained responses
without any new provider/model call or file change. It produced five musical
choices for A and four for B. This counterfactual check does not create a new
capture, authorize selection, refund admission or relabel the failed case.

New plans use `cinema-confirmed-discovery-v3`, plan/report schema 7 and the
source-bound `qloo-search-musical-profile-uniqueness-v1` candidate contract.
The explicit input request remains schema 5. Movie discovery, model prompt,
delivery and pacing contracts retain their v2 semantics. Artist choice remains
explicit. Total budgets remain four Qloo requests and two model attempts,
with one admission and no retry. Cultural/release gates remain
`NOT_VALIDATED` / `BLOCKED`.

The v3 capture and independent file verifier are separate source files because
existing evidence seals the exact bytes of the v2 capture/verifier and all
their dependencies. Refactoring or editing those originals would invalidate
the historical source binding. V3 seals the legacy dependencies plus its new
projection, capture and verifier. Its verifier independently reconstructs the
candidate projection from the original rows. Existing v2 plans dispatch to
their original capture/verifier; source-manager changes do not silently grant
permission to continue a plan frozen under a different manager hash.

## Validation and deployment

Run the locked Python suite, web typecheck/export and both browser commands:

```text
python -B -m unittest discover -s tests
cd web
npx --yes pnpm@11.25.0 typecheck
npx --yes pnpm@11.25.0 build
npx --yes pnpm@11.25.0 exec playwright install --with-deps chromium
npx --yes pnpm@11.25.0 test:recovery
npx --yes pnpm@11.25.0 test:case-journey
```

The full browser journey uses the actual frontend, FastAPI and persistent case
manager with explicitly fake providers, including the nonmusical repeated-UUID
shape. It checks no automatic choice, one admission, exact 4/2 provider/model
counts, exclusion/favorite guards, verification download and session restoration.
It does not certify live-provider capacity or physical iOS/Safari behavior.

Before deploying over an existing public store, follow
`docs/PUBLIC-NEW-CASES.md`: the installed manager source hash changes.
Review the exact stopped-store proposal and use its exact hash for the
append-only continuation. Do not clear sessions, jobs, receipts, policy files
or admission counts, and do not add automatic startup migration. Existing
source-bound capture artifacts must remain in their original locations.
Simply deploying a different manager over the current store will fail its
policy binding until the explicit continuation is completed.

The current hosted revision is `250aac1258535db593db644747a5659003fced82`.
This source review does not deploy v3. A complete live v3 browser observation
remains a separate acceptance check after a reviewed deployment.
