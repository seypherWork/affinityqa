# New individual cases in the local panel

The public source includes a separate **NEW INDIVIDUAL CASE** screen. It works without historical review files. The existing recorded screen and frozen captures remain separate.

## Configure, review, execute

Supply an explicit local JSON request template following [Individual capture](INDIVIDUAL-CAPTURE.md): schema version 1, two initial musical interests, exactly 20 Qloo movie UUID/name/year records, and the name plus full digest of a model already installed in local Ollama. No catalog is guessed or loaded from historical runs. The browser can change the two interests; catalog, model, destination and credential configuration belong to the server owner. Do not paste credentials into the browser or chat.

From an installed backend environment, preparation only:

```powershell
python -m affinityqa serve --port 8794 --individual-template C:\path\request.json --individual-output C:\path\new-job-storage --ollama-url http://127.0.0.1:11434
```

The storage parent must already exist. Open `http://127.0.0.1:8794/#screening`, select **NEW INDIVIDUAL CASE**, choose the interests, and select **REVIEW A NEW PLAN**. This writes a private plan, with no credential loading, Qloo requests, model queries or inference. A template does not enable execution.

When the owner is ready to use Qloo and the local model, explicitly enable execution:

```powershell
python -m affinityqa serve --port 8794 --individual-template C:\path\request.json --individual-output C:\path\new-job-storage --ollama-url http://127.0.0.1:11434 --individual-local-enabled --env-file C:\path\.env
```

Inspect the budget and fingerprints, then select **START THIS REVIEWED LOCAL PLAN**. The exact request, capture source, dependency lock, output and manager must still match the plan. Credentials are loaded locally at admission. The limit per job is four Qloo attempts and 39 fresh ranking decisions, with the previously declared metadata checks and one model load. One capture is active per manager storage; storage is limited to 20 prepared plans and three execution admissions, including failed or interrupted admissions. Use a new owner-selected storage root after inspecting old evidence; there is no automatic cleanup, retry, quota reset or resume. These limits do not control unrelated GPU clients or separately configured storage roots.

## Progress and evidence

- Closing or navigating away from the screen does not cancel the server job. Reopen it through **RECENT LOCAL JOBS**.
- Progress counts committed sample/model events. Counts of saved observations are distinct from attempted requests.
- A completed capture must pass the separate recorded-file verifier before results are displayed. A coherent interrupted capture is **PARTIAL**, with no completed repair claim. A complete causal **FAIL** is displayed as a failure.
- The results expose each fault, all three repeats, diagnosis, repair, top-five before/after/healthy rankings, causal checks and the profile trace. Downloading the receipt makes no provider calls.
- A process restart marks unfinished admissions **ABANDONED** and preserves all files. It never resumes them. Shutdown waits for an admitted worker to finish; this is not a cancellation mechanism.
- Any changed evidence or receipt hides the admitted result. There is no arbitrary filesystem path, command, model URL, credential or capture-adapter field in HTTP requests.
- Simulation adapters are an internal test seam. They remain **SIMULATION ONLY**, including after restart without those adapters. HTTP cannot select them.

Verification is recorded-file consistency, sequential replay and independent score arithmetic. It is not cryptographic provider attestation, population reliability or cultural validation. Cultural quality remains **NOT VALIDATED** and release **BLOCKED**. The existing hosted restricted recorded demo exposes none of these new local-execution routes.

## Publication and execution boundary

The published source tree contains 183 files, including the local capture command, verifier, job manager and interface. The source manifest hashes 182 files and excludes itself. The Ubuntu 24.04 engineering job passed 285 synthetic tests, source packaging checks, frontend type checking and build in [the October 7 run](https://github.com/seypherWork/affinityqa/actions/runs/37668343600); that run failed Windows setup before testing because its Python artifact was unavailable. The hosted recorded demo has separate acceptance evidence and exposes no local execution routes. Source publication and synthetic tests do not prove a new real Qloo/Ollama journey. Retain historical manifests and evidence; independently verify any new provider capture before making an acceptance claim.
