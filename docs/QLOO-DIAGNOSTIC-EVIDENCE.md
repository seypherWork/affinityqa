# Qloo-bound diagnosis and repair

This extension checks the meaning of a selected, already verified capture before
allowing one of the existing three repairs. It independently reconstructs the
expected Qloo movie context from the saved raw response, reconstructs the model
input, checks the observed decision and permits only the corresponding single
adapter change. It checks both restored profiles and valid same-profile cache
reuse afterwards. It has no provider transport and sends no Qloo or model calls.

The original capture modules, capture driver, receipt formats, stored files,
session ownership and quotas remain unchanged. The new semantic checker is not
a signature or external-service attestation: callers must first pin the original
receipt and artifact bytes. A live_network_request flag in a fixture is not
proof of a network send. Cultural recommendation quality remains NOT_VALIDATED.

## Contracts

The public replay adds schema version2 and a closed diagnostic_evidence object
with eight strict boolean controls. Original six recovery controls remain.
The frontend accepts legacy version1 when the summary does not advertise v2;
an advertised v2 cannot downgrade or omit the new proof. Raw provider rows,
model packets and private filesystem paths are excluded from the new projection.
The normal proof cards use verified artist names and fixed explanations, with
technical inspection kept separate. The checker rejects unsupported/multiple
fault settings and cannot approve an arbitrary code repair.

## Reproduce without providers

After preparing the locked backend and web environment described in
[the source quickstart](PUBLIC-CODE-QUICKSTART.md), run from the source root:

```text
python -B -m unittest discover -s tests -p test_causal_evidence*.py -v
python -B -m unittest discover -s tests -v
```

Build the frontend using the existing web commands, then from web/:

```text
pnpm test:diagnostic-evidence
pnpm test:diagnostic-evidence --mobile
```

These are SYNTHETIC local tests. They create a fresh fabricated capture and run
the actual verifier, replay, public API and browser over it. They cover all three
faults and three repeats, both profile orders, healthy recovery, valid cache reuse,
rehashed corruption, privacy projection, missing/truthy proof, downgrade, keyboard,
mobile layout and busy/unavailable responses. The browser uses an isolated profile.
Its localhost fixture host displays a SYNTHETIC banner and sends zero real calls.
Never install the fixture in a real service or count it as cultural/user evidence.

For a visible local walkthrough, after building, run from the source root:

```text
python -B tests/browser/serve_diagnostic_synthetic.py --exit-after-seconds 0
```

Open the printed ready_origin followed by /demo#recorded. This is a local
synthetic preview and needs the host PC running. Stop that process with Ctrl+C.
Each start creates a new fixture; it does not read existing cases or credentials.

A separately authorized, read-only compatibility replay of the original private
capture is a distinct acceptance step. Synthetic PASS does not establish that
the private bundle passes, does not renew a provider budget, and does not grant
publication or deployment approval. CI on Windows/Linux must run for the final
published revision; earlier green runs are not results for this extension.
