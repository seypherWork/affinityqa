# Render recorded replay — hosted acceptance checked

On 7 October 2026 the existing [hosted recorded demo](https://affinityqa-review.onrender.com) passed 54 HTTPS replay selections and 324 strict checks, followed by a tested service-process restart retaining the reviewed evidence. The deployed revision is `e08ddf2a7b7751b07b9c0b4635ad838247c44c00`; the separately published source engineering revision is `20d6abfe489eff5ae361d8c45a92bf14d4133de9`. Automatic deployments remain off. New cloud-case execution and independent cultural acceptance remain pending.

This repository is source only. The source-archive builder generates
PUBLIC-SOURCE-MANIFEST.json for its exact included source, diagrams and hosting
adapters. Verify those file hashes against the extracted archive. The ZIP has
a separate SHA-256 receipt; the manifest cannot bind its own bytes. Historical
deployment manifests from earlier preparations are retained separately and
are not shipped in this source archive. A source manifest or a successful build
does not approve deployment or prove the hosted judge journey.

Use a Python native web service: Python 3.12.14, Node 24.19.0 and pnpm 11.25.0.
The build invokes the exact pnpm package through npx, installs locked dependencies
with install scripts disabled, checks types and builds the static reviewer web.
Build command for both the manual service form and `render.yaml`:

```sh
AFFINITYQA_NODE_EXECUTABLE="$(node -p process.execPath | tail -n 1)" && test -x "$AFFINITYQA_NODE_EXECUTABLE" && PATH="$(dirname "$AFFINITYQA_NODE_EXECUTABLE"):$PATH" python deployment/build_render.py
```

The observed Render console selected Node 24.19.0, while Python subprocess lookup in this service found `/usr/bin/node` version 24.21.0. Resolving the selected executable and prepending its directory to PATH allowed the complete build to pass. The underlying shell mechanism was not established. Keep `deployment/build_render.py`, its strict version checks and every dependency pin unchanged.

This exact command reached BUILD SUCCESS on 4 October 2026 in deployment `dep-db193s60tbcc73a43i1g`, source commit `f929df5763cb8d37c3958c9c6fa9a4b37e469007`. This is build evidence only; a provisioning service is not the judged demo.
Final start command: `python deployment/start_render.py`.

The existing owner-approved service is Starter (0.5 CPU/512 MB), Frankfurt,
one instance, with a 1 GB disk at /var/data. Its recorded demo is live with
maintenance disabled and automatic deployments off. These checks created no
additional paid resource or plan upgrade. For a new deployment, inspect the
actual dashboard price and obtain owner approval before creating a paid service
or changing its plan; no documented price is a spending cap.

The final start refuses missing mode configuration or compiled frontend. For replay, set
AFFINITYQA_RUN_ID and AFFINITYQA_RECEIPT_SHA256 to the owner-reviewed capture;
these are provenance values, not secrets. Origin comes from RENDER_EXTERNAL_URL,
port from PORT. Evidence belongs only in /var/data/affinityqa-evidence, outside
the public repo and build. Replay needs no Qloo key or local model.

Public new cases use the explicit configuration, retained private storage and
lazy private credential paths in [PUBLIC-NEW-CASES.md](../docs/PUBLIC-NEW-CASES.md).
`AFFINITYQA_ENABLE_NEW_CASES=0` is the default and allows plan inspection only.
Case-only mode needs no replay bundle. Enabling real execution is a separate
owner-approved step after provider, transfer, quota and capacity checks. No
credentials or owner configuration are included in the source archive.

The disk is unavailable during build/predeploy and SSH requires a running
instance. For a new service, after service-creation approval, explicitly use the temporary command
`python deployment/provision_only.py`, with maintenance enabled, to prepare the
disk. It serves only liveness /healthz (204); all other GET paths return 503.
It is not a functioning demo. Do not use liveness as evidence approval.

Upload only the separately reviewed minimal capture after Qloo rights and the
exact SSH destination are approved. Verify every remote hash and all 54 replays,
then switch to the strict final start and redeploy manually. Before removing
maintenance, verify external HTTPS, Host/Origin boundaries, limits, restart,
memory, latency, keyboard/mobile behavior and browser console. Keep previous
failed cultural-quality studies visible. Causal PASS is not cultural validation.

The existing native-Linux recorded runtime and external HTTPS flow passed
the October 7 acceptance described above. All 382 evidence hashes, file modes
and receipt bindings survived a tested process restart. Point-in-time memory
observations remained below the 512 MB limit with no observed OOM event; they
do not establish peak usage or a service guarantee. Two concurrent replay
requests produced 200 and 429, then recovery to 200; useful many-user or new-case
capacity remains unverified. Temporary transfer SSH access was revoked. The
scripts do not provide a firewall or make the disk immutable.
No live provider inference, public data transfer or release approval is implied.

Official references: [native runtimes](https://render.com/docs/native-runtimes),
[Node selection](https://render.com/docs/node-version),
[disks](https://render.com/docs/disks), [SSH](https://render.com/docs/ssh),
[pricing](https://render.com/pricing).

## Case-storage continuity and fallback

Source changes use the stopped-store proposal in
[PUBLIC-NEW-CASES.md](../docs/PUBLIC-NEW-CASES.md#continue-the-same-case-storage-across-source-versions).
Keep the same root and admission history; startup never migrates it. Apply only
an exact reviewed proposal after checking actual host space and terminal workers.
Do not restore an older snapshot as active storage to recover budgets.

Full case rollback requires a chain-aware destination that supports every stored
protocol. Rollback adds a new record rather than removing forward history. The
exact older public release is not made compatible by adding metadata. Its
fallback leaves cases unconfigured and serves only a separately verified replay;
`execution_enabled=false` alone still permits session/plan writes. Without that
replay, do not claim restored product behavior. No cloud migration, fallback or
publication is authorized by packaging or passing local engineering tests.
