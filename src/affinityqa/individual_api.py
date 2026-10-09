"""Routes for the explicitly configured loopback panel, never the public demo."""
from typing import Annotated
from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Artists(StrictBody):
    A: Annotated[str, Field(min_length=1, max_length=300)]
    B: Annotated[str, Field(min_length=1, max_length=300)]


class FilmPreferences(StrictBody):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    favorite_entity_ids: Annotated[list[str], Field(max_length=5)]
    excluded_entity_ids: Annotated[list[str], Field(max_length=15)]


class PreferencePair(StrictBody):
    A: FilmPreferences
    B: FilmPreferences


class PlanBody(StrictBody):
    artists: Artists
    preferences: PreferencePair | None = None
    confirm_identities: bool = False
    discover_new_movies: bool = False


class StartBody(StrictBody):
    plan_sha256: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class SelectedEntityIds(StrictBody):
    A: Annotated[str, Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')]
    B: Annotated[str, Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')]


class ConfirmBody(StrictBody):
    plan_sha256: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
    identity_receipt_sha256: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
    selected_entity_ids: SelectedEntityIds


JobId = Annotated[str, Path(pattern=r'^\d{8}T\d{6}Z-[a-f0-9]{8}$')]


def routes(manager):
    router = APIRouter(prefix='/api/individual')
    def response(value, code=200, extra=None):
        return JSONResponse(value, status_code=code, headers={'Cache-Control':'no-store', **(extra or {})})

    def denial(request):
        if request.headers.get('origin') != str(request.base_url).rstrip('/'):
            return response({'error':'Use this local application\'s own origin.'}, 403)
        if manager is None:
            return response({'error':'New individual cases are not configured on this server.'}, 503)
        return None

    @router.get('/capabilities')
    def capabilities():
        return response(manager.capabilities() if manager else {
            'configured':False,'execution_enabled':False,'simulation_only':False,'jobs':[],
            'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'})

    @router.post('/plans', status_code=201)
    def plan(request: Request, body: PlanBody):
        denied = denial(request)
        return denied if denied is not None else response(manager.prepare(body.artists.model_dump(),
            **({'preferences':body.preferences.model_dump()} if body.preferences is not None else {}),
            **({'confirm_identities':True} if body.confirm_identities else {}),
            **({'discover_new_movies':True} if body.discover_new_movies else {})), 201)

    @router.get('/jobs/{job_id}')
    def status(job_id: JobId):
        if manager is None:
            return response({'error':'New individual cases are not configured on this server.'}, 503)
        return response(manager.view(job_id))

    @router.post('/jobs/{job_id}/execute', status_code=202)
    def execute(request: Request, job_id: JobId, body: StartBody):
        denied = denial(request)
        return denied if denied is not None else response(manager.start(job_id, body.plan_sha256), 202)

    @router.post('/jobs/{job_id}/confirm-identities', status_code=202)
    def confirm(request: Request, job_id: JobId, body: ConfirmBody):
        denied = denial(request)
        if denied is not None:
            return denied
        from .errors import SchemaError
        try:
            return response(manager.confirm_identities(job_id, body.plan_sha256,
                body.identity_receipt_sha256, body.selected_entity_ids.model_dump()), 202)
        except SchemaError:
            return response({'error':'This saved identity selection cannot be confirmed.'}, 409)

    @router.get('/jobs/{job_id}/verification')
    def verification(job_id: JobId):
        if manager is None:
            return response({'error':'New individual cases are not configured on this server.'}, 503)
        return response(manager.receipt(job_id), extra={
            'Content-Disposition':f'attachment; filename=affinityqa-individual-{job_id}-verification.json'})

    return router
