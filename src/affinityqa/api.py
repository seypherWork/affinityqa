from __future__ import annotations

from .access import public_access_state

from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Path as ApiPath, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agents import CONTRACT_VERSION
from .errors import AffinityQAError
from .evaluation import METRIC_VERSION
from .store import RunStore

RunId = Annotated[str, Field(pattern=r"^\d{8}T\d{6}Z-[a-f0-9]{8}$")]
AgentLabel = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^\S(?:.*\S)?$")]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyBody(StrictBody):
    pass


class CausalReplayBody(StrictBody):
    pair_id: Annotated[str, Field(pattern=r'^causal-(development|validation)-\d{2}$')]
    fault: Literal['cache-omits-profile', 'stale-profile', 'wrong-tool-profile']
    repeat: Annotated[int, Field(ge=1, le=3)]


class ControlBody(StrictBody):
    reference_run_id: RunId
    behavior: Literal["taste-aware", "taste-insensitive"]


class Decisions(StrictBody):
    A: Annotated[list[Annotated[str, Field(min_length=1, max_length=120)]], Field(min_length=1, max_length=50)]
    B: Annotated[list[Annotated[str, Field(min_length=1, max_length=120)]], Field(min_length=1, max_length=50)]


class ReplayBody(StrictBody):
    reference_run_id: RunId
    agent_name: AgentLabel
    agent_version: AgentLabel
    cases: Annotated[dict[str, Decisions], Field(min_length=1, max_length=20)]


class ComparisonBody(StrictBody):
    baseline_run_id: RunId
    candidate_run_id: RunId


class LocalRequestGuard:
    """Bound streamed request bodies; reject browser requests from unrelated sites."""
    def __init__(self, app, max_bytes: int = 262144):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope["headers"]}
        origin = headers.get("origin")
        if origin:
            try:
                parsed = urlsplit(origin)
                allowed = parsed.scheme == "http" and parsed.netloc == headers.get("host") and not parsed.path
            except ValueError:
                allowed = False
            if not allowed:
                return await JSONResponse({"error": "Cross-origin access is disabled for the local backend."}, status_code=403)(scope, receive, send)
        if scope["method"] in ("POST", "PUT", "PATCH"):
            if headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                return await JSONResponse({"error": "Use application/json."}, status_code=415)(scope, receive, send)
            chunks, size = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > self.max_bytes:
                    return await JSONResponse({"error": "Request exceeds the local size limit."}, status_code=413)(scope, receive, send)
                chunks.append(chunk)
                if not message.get("more_body"):
                    break
            delivered = False

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                return await receive()

            return await self.app(scope, bounded_receive, send)
        return await self.app(scope, receive, send)


def create_app(project_root: Path, *, store_root: Path | None = None, live_manager=None) -> FastAPI:
    store = RunStore(store_root or project_root / "runs/backend", project_root / "evals/qloo.json", project_root / "fixtures/synthetic.json")
    app = FastAPI(title="AffinityQA local backend", version="0.2.0", description="Local engineering preview. No live Qloo calls or external agent execution through HTTP.")
    app.state.store = store
    app.add_middleware(LocalRequestGuard)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Default validation errors echo input values; never return submitted keys or reasoning.
        return JSONResponse({"error": "Invalid request schema.", "issue_types": sorted({error["type"] for error in exc.errors()})}, status_code=422)

    @app.exception_handler(AffinityQAError)
    async def safe_error(request: Request, exc: AffinityQAError):
        return JSONResponse({"error": str(exc), "ci_gate": "NOT_VALIDATED"}, status_code=422)

    @app.exception_handler(FileNotFoundError)
    async def missing(request: Request, exc: FileNotFoundError):
        return JSONResponse({"error": "Local run or artifact not found."}, status_code=404)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        return JSONResponse({"error": "Local artifact or execution failed. No quality gate passed.", "ci_gate": "NOT_VALIDATED"}, status_code=500)

    @app.get("/api/status")
    def status():
        return {"project": "AffinityQA", "backend": "ready", "preview_mode": "local", **public_access_state(project_root / "runs"),
                "live_qloo_enabled": False, "http_agent_execution": "synthetic-controls-only",
                "agent_contract": CONTRACT_VERSION, "metric_version": METRIC_VERSION, "metrics_status": "PROVISIONAL"}

    @app.get("/api/review")
    def review():
        from .review import review_snapshot
        return JSONResponse(review_snapshot(project_root), headers={"Cache-Control":"no-store"})

    @app.get('/api/causal-repair')
    def causal_repair():
        from .causal_review import causal_snapshot
        return JSONResponse(causal_snapshot(project_root), headers={'Cache-Control': 'no-store'})

    @app.get('/api/causal-repair/export')
    def causal_export():
        from .causal_review import export_causal
        return JSONResponse(export_causal(project_root), headers={'Cache-Control': 'no-store',
                            'Content-Disposition': 'attachment; filename=affinityqa-causal-review.json'})

    @app.post('/api/causal-repair/replay')
    def causal_replay(body: CausalReplayBody, request: Request):
        if request.headers.get('origin') != str(request.base_url).rstrip('/'):
            return JSONResponse({'error': 'Replay requires this application\'s own origin.'}, status_code=403)
        from .causal_review import replay_causal
        return JSONResponse(replay_causal(project_root, body.pair_id, body.fault, body.repeat),
                            headers={'Cache-Control': 'no-store'})

    @app.get("/api/regression-pack")
    def regression_pack():
        from .regression_pack import export_pack
        return JSONResponse(export_pack(project_root,baseline='candidate',case_ids=['mutation-12']),headers={"Cache-Control":"no-store"})

    @app.get("/api/repair-validation")
    def repair_validation():
        from .repair_gate import validation_snapshot
        result=validation_snapshot(project_root)
        if (project_root/'evidence/INDIVIDUAL-CONTEXT-20261004.json').exists():
            from .individual_review import historical_qualification
            result['integrity_qualification']=historical_qualification(project_root)
        return JSONResponse(result,headers={"Cache-Control":"no-store"})

    @app.get("/api/repair-contract")
    def repair_contract():
        from .repair_gate import load_recorded_validation
        contract,_,_,_=load_recorded_validation(project_root)
        return JSONResponse(contract,headers={"Cache-Control":"no-store",
                            "Content-Disposition":"attachment; filename=affinityqa-repair-contract.json"})

    @app.get("/api/repair-decisions")
    def repair_decisions():
        from .repair_gate import load_recorded_validation
        _,decisions,_,_=load_recorded_validation(project_root)
        return JSONResponse(decisions,headers={"Cache-Control":"no-store",
                            "Content-Disposition":"attachment; filename=affinityqa-candidate-decisions.json"})

    @app.get("/api/value-validation")
    def value_validation():
        from .value_review import value_snapshot
        return JSONResponse(value_snapshot(project_root),headers={"Cache-Control":"no-store"})

    @app.get("/api/ordering-development")
    def ordering_development():
        from .ordering_review import ordering_snapshot
        result=ordering_snapshot(project_root)
        if (project_root/'evidence/INDIVIDUAL-CONTEXT-20261004.json').exists():
            from .individual_review import historical_qualification
            result['integrity_qualification']=historical_qualification(project_root)
        return JSONResponse(result,headers={"Cache-Control":"no-store"})

    @app.get("/api/individual-context")
    def individual_context():
        from .individual_review import individual_snapshot
        return JSONResponse(individual_snapshot(project_root),headers={"Cache-Control":"no-store"})

    @app.get("/api/repair-learning")
    def repair_learning():
        from .learning_review import learning_snapshot
        return JSONResponse(learning_snapshot(project_root),headers={"Cache-Control":"no-store"})

    @app.get("/api/context-extensions")
    def context_extensions():
        from .extension_review import extension_snapshot
        return JSONResponse(extension_snapshot(project_root),headers={"Cache-Control":"no-store"})

    @app.get("/api/metadata-development")
    def metadata_development():
        from .metadata_review import metadata_snapshot
        return JSONResponse(metadata_snapshot(project_root),headers={"Cache-Control":"no-store"})

    @app.get("/api/value-contract")
    def value_contract():
        from .value_review import load_recorded_value
        contract,_,_,_=load_recorded_value(project_root)
        return JSONResponse(contract,headers={"Cache-Control":"no-store",
                            "Content-Disposition":"attachment; filename=affinityqa-value-contract.json"})

    @app.get("/api/value-decisions")
    def value_decisions():
        from .value_review import load_recorded_value
        _,decisions,_,_=load_recorded_value(project_root)
        return JSONResponse(decisions,headers={"Cache-Control":"no-store",
                            "Content-Disposition":"attachment; filename=affinityqa-value-decisions.json"})

    @app.get("/api/live/capabilities")
    def live_capabilities():
        return JSONResponse(live_manager.capabilities() if live_manager else {
            "enabled":False,"notice":"Start the local server with its explicit live-model option."},headers={"Cache-Control":"no-store"})

    def check_live(request):
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            return JSONResponse({"error":"Local model execution requires this application's own origin."},status_code=403)
        if live_manager is None:
            return JSONResponse({"error":"Live local execution is disabled."},status_code=503)
        return None

    @app.post("/api/live/jobs",status_code=202)
    def start_live(request: Request, body: EmptyBody):
        denied=check_live(request)
        return denied if denied is not None else live_manager.start()

    @app.get("/api/live/jobs/{job_id}")
    def inspect_live(job_id: Annotated[str, ApiPath(pattern=r"^\d{8}T\d{6}Z-[a-f0-9]{8}$")]):
        if live_manager is None:return JSONResponse({"error":"Live local execution is disabled."},status_code=503)
        return JSONResponse(live_manager.view(job_id),headers={"Cache-Control":"no-store"})

    @app.post("/api/live/jobs/{job_id}/repair",status_code=202)
    def repair_live(request: Request, job_id: Annotated[str, ApiPath(pattern=r"^\d{8}T\d{6}Z-[a-f0-9]{8}$")], body: EmptyBody):
        denied=check_live(request)
        return denied if denied is not None else live_manager.repair(job_id)

    @app.get("/api/runs")
    def runs():
        return {"runs": store.list_runs()}

    @app.get("/api/runs/{run_id}")
    def run(run_id: Annotated[str, ApiPath(pattern=r"^\d{8}T\d{6}Z-[a-f0-9]{8}$")]):
        return store.read(run_id, "manifest.json")

    @app.get("/api/runs/{run_id}/artifacts/{artifact}")
    def artifact(run_id: str, artifact: str):
        return store.read(run_id, artifact)

    @app.get("/api/runs/{run_id}/ledger")
    def ledger(run_id: str):
        return {"events": store.ledger(run_id)}

    @app.post("/api/references/synthetic", status_code=201)
    def synthetic(body: EmptyBody):
        return store.synthetic_reference()

    @app.post("/api/agents/control", status_code=201)
    def control(body: ControlBody):
        return store.control(body.reference_run_id, body.behavior)

    @app.post("/api/agents/replay", status_code=201)
    def replay(body: ReplayBody):
        return store.replay(body.reference_run_id, body.agent_name, body.agent_version,
                            {key: value.model_dump() for key, value in body.cases.items()})

    @app.post("/api/comparisons", status_code=201)
    def comparison(body: ComparisonBody):
        return store.compare(body.baseline_run_id, body.candidate_run_id)

    web_root = project_root / "web/out"
    if (web_root / "index.html").is_file() and not web_root.is_symlink():
        @app.api_route("/api/{unknown:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"], include_in_schema=False)
        def unknown_api(unknown: str):
            return JSONResponse({"error": "Unknown local API route."}, status_code=404)

        app.mount("/", StaticFiles(directory=web_root, html=True), name="review-ui")
    return app
