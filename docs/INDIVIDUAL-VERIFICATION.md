# Verify individual captures

The public source includes read-only verification for individual captures. It does not change frozen historical experiments or automatically admit new records to an existing panel. See [Individual capture](INDIVIDUAL-CAPTURE.md) for the corresponding command and [Local panel](INDIVIDUAL-PANEL.md) for explicit admission.

Use the virtual-environment interpreter from the main installation guide. Supply the actual run directory containing `individual-plan.json` and `individual-report.json`:

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_individual_capture.py "C:\PRIVATE\captures\new-pair\<RUN_ID>"
```

Verification reads recorded files and installed source. It uses no credential, makes no provider or model request, loads no model and creates no file by default. Windows simulation tests cover this command. The published source also passed 285 synthetic tests on Ubuntu 24.04 in [the October 7 engineering run](https://github.com/seypherWork/affinityqa/actions/runs/37668343600). Actual new provider captures remain unverified. The original output path in a plan is provenance, not an instruction to read or write that location. A copied run can be verified at its current location with the exact matching source and dependency lock.

To preserve a new private receipt outside the captured artifact directory, explicitly select an existing parent and a new filename:

```powershell
.\.venv\Scripts\python.exe -B scripts/verify_individual_capture.py "C:\PRIVATE\captures\new-pair\<RUN_ID>" --receipt "C:\PRIVATE\receipts\<RUN_ID>.json"
```

The receipt is created exclusively and existing files are retained. It binds the artifact inventory, capture sources, capture driver, dependency lock and verifier. Linked paths, unexpected artifacts, changed files and inconsistent records are rejected. Ordinary concurrent changes are checked before returning and again before writing a receipt; this is not a filesystem lock or an external-service signature.

The verifier checks four exact Qloo observations and 39 sequential decision packets for a complete capture. It reconstructs identities and complete movie contexts, replays the session protocol using recorded decisions in their original order, verifies all 54 boundary observations, and checks the policy was frozen after six healthy decisions and before incidents. Independent arithmetic recomputes healthy noise and recovery distances. A protocol replay shares the installed operator; the arithmetic audit does not use its metric implementation.

A coherent incomplete run can receive `VERIFIED_PARTIAL`, retaining its original error and `NOT_EVALUATED` result. Failed attempts may exceed saved successful observations. Uncommitted or malformed artifacts are refused and retained for inspection; verification does not repair them, retry a request or invent missing results.

Exit zero means the recorded evidence is internally consistent, including a valid partial run or a complete causal failure. It does not mean causal PASS, cultural quality, external-service attestation or release approval. Read the reported status and separate gates. `test-double-only` remains `SIMULATION_ONLY`, even when a synthetic HTTP sample has a live-request-shaped field. Production-labeled records remain `RECORDED_PROVIDER_OBSERVATIONS`, without a cryptographic attestation from the provider.

Individual calibration uses this pair's healthy repetitions and is not a reserved population evaluation. Model metadata request counts describe planned budgets; the existing adapter does not record those requests individually. Cultural quality stays `NOT_VALIDATED`, release stays `BLOCKED`, and the original report's `independent_verification` stays unchanged. The separate receipt records this audit.

UI admission and a bounded local job manager are included in the 183-file public source tree. The source manifest hashes 182 files and excludes itself. A new real Qloo/Ollama capture and its end-to-end acceptance remain pending. The hosted restricted recorded demo exposes no local execution routes. Passing synthetic engineering checks or publishing source does not close the cultural or full submission gates.
