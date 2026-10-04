# Restricted reviewer demo — prepared, not deployed

The public entry point is a separate application, `affinityqa.public_demo.create_public_app`. It does not enable the local backend, RunStore writes, live model jobs, raw run downloads, full manifests or provider-response exports. Do not expose `scripts/affinityqa.py serve` through a public tunnel.

## Review before publication

The intended demo displays an explicitly selected recorded incident and its top-five movie decisions. Even these limited displays contain provider-derived material. Obtain the applicable Qloo permission and approve the exact hosting destination before publication. Original code is MIT, as approved by the owner; that license does not grant rights to provider outputs. The code package contains no evidence; it is not a substitute for the verified recorded demonstration.

The fixed real capture already exists privately. Choose the owner-provided review package, run ID and independent receipt fingerprint. Extract that package into a separate read-only directory; do not copy raw data into the public repository or into a container build context. Keep its matching eight frozen operator source files and exact capture driver intact. The public server checks both the mounted sources and its actual installed operators against the receipt.

## Local rehearsal

Build the interface from the source directory (`pnpm install --frozen-lockfile --ignore-scripts`, then `pnpm build` in `web`) and install `requirements-backend.lock.txt` into a virtual environment. Run:

```powershell
python scripts/serve_public_demo.py --origin http://127.0.0.1:8767 --port 8767 --evidence-root "<absolute authorized review-package root>" --run-id "<owner-provided run ID>" --receipt-sha256 "<independent receipt SHA-256>"
```

Open `http://127.0.0.1:8767/`. Select a pair, incident and repeat, then execute **Replay this incident**. Inspect Detect, Diagnose, Repair and Verify and compare the top-five results. Each replay executes the real routing/diagnosis/repair pipeline using recorded model decisions; it generates no new inference and calls no provider. An unavailable or altered capture cannot return a verified result. Earlier 13/14 development and 4/6 independent quality failures remain explicit and do not become PASS.

Without the run and receipt arguments, the same command runs a source preview whose evidence status is UNAVAILABLE. It never substitutes fabricated data for a real capture.

Run the bounded in-process verifier against the authorized package:

```powershell
python scripts/verify_public_demo.py --evidence-root "<absolute authorized review-package root>" --run-id "<owner-provided run ID>" --receipt-sha256 "<independent receipt SHA-256>"
```

This verifier exercises all recorded combinations and tests HTTPS Host/Origin semantics. It does not certify a real TLS endpoint or an external deployment.

## HTTPS deployment contract

Use an approved host with a TLS ingress or reverse proxy. Configure one exact `--origin https://<approved-hostname>` and a read-only authorized evidence directory. `--listen-internal` explicitly changes the bind address to `0.0.0.0` for the private ingress interface. It is for the approved hosted process, not a request to expose the user's PC. The ingress must preserve the configured Host and the browser's Origin and terminate TLS; do not rewrite arbitrary origins into the allowed value. Forwarded headers are ignored by the runner. Configure public request limits at the ingress as well as in the application. The runtime should permit no outbound network and no evidence writes.

Allowed routes are GET `/`, `/demo`, `/demo/`, `/_next/static/<built asset>`, `/healthz`, `/api/demo/summary` and POST `/api/demo/replay`. The JSON summary contains counts, named pairs and provenance hashes, with no rankings or raw contexts. A replay returns only the selected top-five display, six checks, four profile hashes and their verified artist names. Entity UUIDs, model payloads, source execution packets and bulk exports are omitted. POST requires the exact configured origin and JSON no larger than 4096 bytes, with a five-second total body-reading deadline and at most four active body readers. Requests reserve quota before reading their body. The application admits one active replay and at most 60 replay requests per minute per process. The summary has a separate 120/minute limit; unsupported methods do not consume replay quota. `/healthz` is inexpensive process liveness, not evidence readiness or an approval: it stays available when the summary is rate limited. The application disables automatic API documentation and rejects unknown local-backend routes.

Noncanonical routes such as `/healthz/`, `/api/demo/summary/` and `/api/demo/replay/` return 404 without a Location header. Implicit slash redirects are disabled so the HTTP backend cannot emit a redirect that downgrades the public HTTPS scheme. `/demo` and `/demo/` are both explicit allowed routes. This behavior does not require trusting caller-supplied forwarded headers.

After publication is separately approved, verify the actual external HTTPS address from a fresh browser: all six pairs, three incident types, repeats, provenance, mobile layout, keyboard use, console, unavailable-data behavior and rate-limit messaging. Confirm response headers and that local/private routes remain inaccessible. Keep this check distinct from local or in-process verification. No external URL is claimed by this document.

This deployment approach follows FastAPI's guidance on [containers](https://fastapi.tiangolo.com/deployment/docker/) and [TLS proxies](https://fastapi.tiangolo.com/advanced/behind-a-proxy/). A container recipe or installed Docker client alone is not proof that a container has built or run; Docker verification is currently outside the evidence recorded here.
