# Individual local capture — preparation candidate

This new command prepares and executes one explicit pair through the existing causal operator. It has no dependency on historical private run files. The historical development/validation drivers, their budgets, receipts and operators remain unchanged. This candidate is not published, part of the hosted demo, independently verified, or approved for submission.

## Explicit inputs

Create a private UTF-8 JSON request with exactly these four keys:

| Field | Required value |
| --- | --- |
| `schema_version` | Integer `1` |
| `artists` | Object with `A` and `B`: two different explicit musical interests, as canonical printable names |
| `catalog` | Exactly 20 distinct movies, each containing only `entity_id` (canonical Qloo UUID), `name`, and integer `release_year` |
| `model` | Object with `name` and full SHA-256 `digest` of an already installed local Ollama model |

Use movie inputs you are authorized to use. The request holds the same catalog fixed throughout this individual capture. Live Insights must confirm every movie's identity, title and year; missing coverage stops the run. The command does not invent a catalog or fill missing results.

Ollama's local `/api/tags` response supplies full model digests. This command never installs a model or selects a cloud model. The model needs to support the existing structured-ranking adapter; passing an installed-model check does not establish recommendation quality.

Keep credentials outside the request, source repository and chat. The Qloo key is read only for explicit execution from the process environment or the optional private `--env-file`. The key is restricted to the existing hackathon API transport and excluded from model inputs and recorded evidence. Planning prints the supplied request, so the request must contain no secrets.

## Plan without execution

Use the virtual-environment Python interpreter from the main setup guide. Choose a new output directory under an existing private parent. On Windows:

```powershell
.\.venv\Scripts\python.exe -B scripts/capture_individual_pair.py --request "C:\PRIVATE\request.json" --output "C:\PRIVATE\captures\new-pair"
```

On Linux, substitute `.venv/bin/python` and native absolute paths. Linux behavior has not been verified for this new command.

Planning validates the request, hashes the implementation, driver and dependency lock, and prints `plan_sha256`. It creates no output, reads no credential file and contacts neither Ollama nor Qloo. The default model URL is the local loopback `http://127.0.0.1:11434`; other loopback ports can be supplied explicitly.

## Explicit execution

Inspect the printed plan and its full fingerprint before executing. After configuring the credential locally and making the selected installed model available:

```powershell
.\.venv\Scripts\python.exe -B scripts/capture_individual_pair.py --request "C:\PRIVATE\request.json" --output "C:\PRIVATE\captures\new-pair" --execute --plan-sha256 "<EXACT_REVIEWED_FINGERPRINT>" --env-file "C:\PRIVATE\qloo.env"
```

This command performs real requests and can load the local GPU model. The fingerprint is a consistency check, not permission from this application or the contest organizer. Any changed input, destination, operator, driver or model plan requires a new plan. Do not execute while another workload needs the GPU.

The fixed limits are four Qloo attempts (two exact identity searches and two complete movie-context calls), one attempt per request, and 39 ranking decisions. Three model metadata requests (two at startup and one after loading) and one model-loading request are separate from the decision budget. Request timeouts are bounded by the existing adapters; elapsed execution time depends on the model and hardware.

One OS-backed lease admits only one individual capture using the same output parent. It does not block unrelated Ollama applications or captures in another parent. The marker file is retained; the operating system releases the active lease when the process exits. Existing outputs and unrelated marker files are never overwritten.

Both identities and complete tool contexts are collected before ranking inference. All three faults are tested with healthy, faulty and repaired executions. The individual noise barrier is measured from that pair's three healthy decisions per profile, then frozen before incidents. This is an individual demonstration, not another reserved independent-validation sample.

## Results and current limits

Evidence is saved under a unique run directory inside the new output. Interrupted or invalid runs retain plans, available HTTP samples, packets and an incomplete report. There is no automatic retry, resume, replacement of missing decisions or deletion of partial evidence.

`causal_gate` assesses the unchanged causal checks. `behavioral_gate` is `OBSERVED_RECOVERY` only when every declared fault has at least one observed recovery repeat; a repair with no observable output effect stays `INCONCLUSIVE`. Exit zero requires completion, causal PASS and that behavioral result. The command never turns cultural quality or release approval into PASS.

The report's model-attempt counter covers ranking decisions; loading is recorded separately. Reports explicitly label test-adapter runs `test-double-only`. Offline tests do not establish external-provider behavior.

An independent verifier for this new individual format, user-interface integration, actual provider execution and Linux acceptance remain pending. Existing reviewer services do not automatically admit these new artifacts or expose a new execution endpoint. Existing package manifests describe only the unchanged baseline; the candidate requires a new reviewed manifest before distribution.
