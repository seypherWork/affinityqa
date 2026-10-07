# Verify individual captures

This preparation candidate adds read-only verification to the individual capture command. It does not change the frozen historical experiments or admit new records to the existing panel. The earlier `INDIVIDUAL-CAPTURE.md` describes the preceding preparation stage; its pending-verifier item is addressed by this candidate only.

Use the virtual-environment interpreter from the main installation guide. Supply the actual run directory containing `individual-plan.json` and `individual-report.json`:

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_individual_capture.py "C:\PRIVATE\captures\new-pair\<RUN_ID>"
```

Verification reads recorded files and installed source. It uses no credential, makes no provider or model request, loads no model and creates no file by default. Windows simulation tests cover this command; Linux acceptance and actual provider captures remain pending. The original output path in a plan is provenance, not an instruction to read or write that location. A copied run can be verified at its current location with the exact matching source and dependency lock.

To preserve a new private receipt outside the captured artifact directory, explicitly select an existing parent and a new filename:

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_individual_capture.py "C:\PRIVATE\captures\new-pair\<RUN_ID>" --receipt "C:\PRIVATE\receipts\<RUN_ID>.json"
```

The receipt is created exclusively and existing files are retained. It binds the artifact inventory, capture sources, capture driver, dependency lock and verifier. Linked paths, unexpected artifacts, changed files and inconsistent records are rejected. Ordinary concurrent changes are checked before returning and again before writing a receipt; this is not a filesystem lock or an external-service signature.

The verifier checks four exact Qloo observations and 39 sequential decision packets for a complete capture. It reconstructs identities and complete movie contexts, replays the session protocol using recorded decisions in their original order, verifies all 54 boundary observations, and checks the policy was frozen after six healthy decisions and before incidents. Independent arithmetic recomputes healthy noise and recovery distances. A protocol replay shares the installed operator; the arithmetic audit does not use its metric implementation.

A coherent incomplete run can receive `VERIFIED_PARTIAL`, retaining its original error and `NOT_EVALUATED` result. Failed attempts may exceed saved successful observations. Uncommitted or malformed artifacts are refused and retained for inspection; verification does not repair them, retry a request or invent missing results.

Exit zero means the recorded evidence is internally consistent, including a valid partial run or a complete causal failure. It does not mean causal PASS, cultural quality, external-service attestation or release approval. Read the reported status and separate gates. `test-double-only` remains `SIMULATION_ONLY`, even when a synthetic HTTP sample has a live-request-shaped field. Production-labeled records remain `RECORDED_PROVIDER_OBSERVATIONS`, without a cryptographic attestation from the provider.

Individual calibration uses this pair's healthy repetitions and is not a reserved population evaluation. Model metadata request counts describe planned budgets; the existing adapter does not record those requests individually. Cultural quality stays `NOT_VALIDATED`, release stays `BLOCKED`, and the original report's `independent_verification` stays unchanged. The separate receipt records this audit.

UI admission, a bounded local job manager, real Qloo/Ollama acceptance, Linux acceptance and a new reviewed distribution manifest are still required. The existing release manifests describe the 147-file public baseline. Neither the preceding individual-capture additions nor these verifier additions are included in those manifests or published.
