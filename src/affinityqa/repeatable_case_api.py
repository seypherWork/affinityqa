"""Same-origin owned case HTTP contract for repeatable-v1 and read-only legacy access."""
from datetime import datetime
from typing import Annotated, Literal
import hmac
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from .errors import SchemaError
from .individual_api import JobId, StartBody, StrictBody
from .movie_case_bodies import ConfirmBody, PlanBody, MovieId, MovieQuery
from .public_case_api import EmptyBody, cookie_name
from .public_cases import SHA, TOKEN


class OpenMoviePlanBody(StrictBody):
    movie_query: MovieQuery
    intent_text: Annotated[str, Field(max_length=600)] = ''
    excluded_entity_ids: Annotated[list[MovieId], Field(max_length=15)] = Field(default_factory=list)


class OpenMovieConfirmBody(StartBody):
    identity_receipt_sha256: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
    selected_movie_entity_id: MovieId


class WideCinemaPlanBody(StrictBody):
    mode: Literal['movie','music']
    seed_query: MovieQuery
    favorite_movie_query: MovieQuery | None = None
    intent_text: Annotated[str, Field(max_length=600)] = ''
    excluded_entity_ids: Annotated[list[MovieId], Field(max_length=15)] = Field(default_factory=list)


class WideCinemaConfirmBody(StartBody):
    identity_receipt_sha256: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
    selected_seed_entity_id: MovieId
    selected_favorite_movie_entity_id: MovieId | None = None


def routes(manager,*,origin):
    router=APIRouter(prefix='/api/demo/cases');name=cookie_name(origin)
    def response(value,status=200,extra=None):return JSONResponse(value,status_code=status,headers={'Cache-Control':'no-store',**(extra or {})})
    def call(action):
        try:return action()
        except FileNotFoundError:return response({'error':'Case access unavailable.'},404)
        except Denial as exc:return response({'error':exc.message},exc.status)
        except Exception:return response({'error':'Case service unavailable. No result approved.'},503)
    def service():
        if manager is None:raise Denial(503,'New cases are not configured on this server.')
        return manager
    def cookie(request):
        found=None;names=set();raw=request.headers.get('cookie','')
        for part in raw.split(';') if raw else ():
            key,separator,value=part.strip().partition('=')
            if not separator or not key or key in names:raise Denial(400,'Ambiguous session cookie.')
            names.add(key)
            if key==name:
                if not TOKEN.fullmatch(value):raise FileNotFoundError('Case access unavailable.')
                found=value
        return found
    def access(request,mutation=False):
        current=service();token=cookie(request)
        if token is None:raise FileNotFoundError('Case access unavailable.')
        current._identity(token)
        _,info=current.session(token)
        if mutation:
            if request.headers.get('origin')!=origin:raise Denial(403,'This action requires the demo origin.')
            csrf=request.headers.get('x-affinityqa-csrf','')
            if not SHA.fullmatch(csrf) or not hmac.compare_digest(csrf,info['csrf_token']):raise Denial(403,'Session mutation token differs.')
            current.authorize_mutation(token,csrf)
        return current,token

    @router.post('/session')
    def session(request:Request,body:EmptyBody):
        def action():
            current=service()
            if request.headers.get('origin')!=origin:raise Denial(403,'This action requires the demo origin.')
            token,info=current.session(cookie(request));answer=response(info)
            expiry=datetime.fromisoformat(info['expires_utc'])
            seconds=max(1,int((expiry-current._now()).total_seconds()))
            answer.set_cookie(name,token,max_age=seconds,expires=expiry,path='/',secure=urlsplit(origin).scheme=='https',
                              httponly=True,samesite='strict')
            return answer
        return call(action)

    @router.get('/capabilities')
    def capabilities(request:Request):
        return call(lambda:response(service().capabilities(access(request)[1])))

    @router.post('/plans',status_code=201)
    def plan(request:Request,body:PlanBody):
        def action():
            current,token=access(request,True)
            try:
                value=current.prepare(token,body.artists.model_dump(),
                    preferences=body.preferences.model_dump() if body.preferences is not None else None,
                    confirm_identities=body.confirm_identities,discover_new_movies=body.discover_new_movies,
                    **({'movie_queries':body.movie_queries.model_dump()} if body.movie_queries is not None else {}),
                    **({'fast_pair_review':True} if body.fast_pair_review else {}))
            except SchemaError:raise Denial(422,'Use two distinct interests, valid cinema preferences and at most two movie searches per case.') from None
            return response(value,201)
        return call(action)

    @router.get('/jobs/{job_id}')
    def status(request:Request,job_id:JobId):
        def action():
            current,token=access(request);return response(current.view(token,job_id))
        return call(action)

    @router.post('/open-movies/plans',status_code=201)
    def open_movie_plan(request:Request,body:OpenMoviePlanBody):
        def action():
            current,token=access(request,True)
            try:return response(current.prepare_open_movie(token,body.movie_query,body.intent_text,body.excluded_entity_ids),201)
            except SchemaError:raise Denial(422,'Use a film title, a bounded preference and valid film exclusions.') from None
        return call(action)

    @router.get('/open-movies/jobs/older-than/{cursor_job_id}')
    def open_movie_history(request:Request,cursor_job_id:JobId):
        def action():
            current,token=access(request)
            return response(current.open_movie_history(token,cursor_job_id))
        return call(action)

    @router.post('/wide-cinema/plans',status_code=201)
    def wide_cinema_plan(request:Request,body:WideCinemaPlanBody):
        def action():
            current,token=access(request,True)
            try:return response(current.prepare_wide_cinema(token,body.mode,body.seed_query,body.favorite_movie_query,body.intent_text,body.excluded_entity_ids),201)
            except SchemaError:raise Denial(422,'Use one confirmed seed, at most one favorite film in music mode, and valid bounded preferences.') from None
        return call(action)

    @router.get('/wide-cinema/jobs')
    def wide_cinema_first_page(request:Request):
        def action():
            current,token=access(request)
            return response(current.wide_cinema_history(token))
        return call(action)

    @router.get('/wide-cinema/jobs/older-than/{cursor_job_id}')
    def wide_cinema_history(request:Request,cursor_job_id:JobId):
        def action():
            current,token=access(request)
            return response(current.wide_cinema_history(token,cursor_job_id))
        return call(action)

    @router.get('/jobs/older-than/{cursor_job_id}')
    def history(request:Request,cursor_job_id:JobId):
        def action():
            current,token=access(request)
            return response(current.history(token,cursor_job_id))
        return call(action)

    @router.post('/jobs/{job_id}/execute',status_code=202)
    def execute(request:Request,job_id:JobId,body:StartBody):
        def action():
            current,token=access(request,True);view=current.view(token,job_id)
            if view.get('read_only') or view['status']!='PLANNED' or view['plan_sha256']!=body.plan_sha256:
                raise Denial(409,'This reviewed plan cannot be admitted again or with a different fingerprint.')
            if not current.capabilities(token)['execution_enabled']:raise Denial(503,'New execution is disabled; saved evidence remains readable.')
            if current.health()['queued']>=current.policy['maximum_queued_jobs']:raise Denial(429,'The concurrent queue is full. This saved plan can be admitted later.')
            return response(current.start(token,job_id,body.plan_sha256),202)
        return call(action)

    @router.get('/jobs/{job_id}/verification')
    def verification(request:Request,job_id:JobId):
        def action():
            current,token=access(request);view=current.view(token,job_id)
            if view['status'] not in ('COMPLETE','PARTIAL') or not view.get('receipt_sha256'):raise Denial(409,'No verified receipt is available for this case.')
            return response(current.verification(token,job_id),extra={'Content-Disposition':f'attachment; filename=affinityqa-public-{job_id}-verification.json'})
        return call(action)

    @router.post('/jobs/{job_id}/confirm-identities',status_code=202)
    def confirm(request:Request,job_id:JobId,body:ConfirmBody):
        def action():
            current,token=access(request,True);view=current.view(token,job_id)
            if view.get('read_only') or view.get('open_movie_discovery') or view.get('wide_cinema_discovery') or view['status']!='AWAITING_IDENTITY_CONFIRMATION':raise Denial(409,'This saved identity selection cannot be admitted again.')
            if view['plan_sha256']!=body.plan_sha256 or view.get('identity_receipt_sha256')!=body.identity_receipt_sha256:
                raise Denial(409,'The reviewed plan or identity receipt differs.')
            if not current.capabilities(token)['execution_enabled']:raise Denial(503,'Confirmed capture is disabled; saved cases remain readable.')
            if current.health()['queued']>=current.policy['maximum_queued_jobs']:raise Denial(429,'The concurrent queue is full. Your saved selection can be admitted later.')
            try:return response(current.confirm_identities(token,job_id,body.plan_sha256,body.identity_receipt_sha256,body.selected_entity_ids.model_dump(),
                **({'selected_movie_entity_ids':body.selected_movie_entity_ids.model_dump()} if body.selected_movie_entity_ids is not None else {})),202)
            except SchemaError:raise Denial(409,'The saved identity choices or evidence no longer match this plan.') from None
        return call(action)

    @router.post('/jobs/{job_id}/confirm-movie',status_code=202)
    def confirm_movie(request:Request,job_id:JobId,body:OpenMovieConfirmBody):
        def action():
            current,token=access(request,True);view=current.view(token,job_id)
            if view.get('read_only') or not view.get('open_movie_discovery') or view['status']!='AWAITING_IDENTITY_CONFIRMATION':
                raise Denial(409,'This saved movie selection cannot be admitted again.')
            if view['plan_sha256']!=body.plan_sha256 or view.get('identity_receipt_sha256')!=body.identity_receipt_sha256:
                raise Denial(409,'The reviewed plan or movie receipt differs.')
            if not current.capabilities(token)['execution_enabled']:raise Denial(503,'Confirmed capture is disabled; saved cases remain readable.')
            if current.health()['queued']>=current.policy['maximum_queued_jobs']:raise Denial(429,'The concurrent queue is full. Your saved selection can be admitted later.')
            try:return response(current.confirm_movie(token,job_id,body.plan_sha256,body.identity_receipt_sha256,body.selected_movie_entity_id),202)
            except SchemaError:raise Denial(409,'The saved film choice or evidence no longer matches this plan.') from None
        return call(action)
    @router.post('/jobs/{job_id}/confirm-wide',status_code=202)
    def confirm_wide(request:Request,job_id:JobId,body:WideCinemaConfirmBody):
        def action():
            current,token=access(request,True);view=current.view(token,job_id)
            if view.get('read_only') or not view.get('wide_cinema_discovery') or view['status'] != 'AWAITING_IDENTITY_CONFIRMATION':
                raise Denial(409,'This saved wide selection cannot be admitted again.')
            if view['plan_sha256'] != body.plan_sha256 or view.get('identity_receipt_sha256') != body.identity_receipt_sha256:
                raise Denial(409,'The reviewed wide plan or identity receipt differs.')
            if not current.capabilities(token)['execution_enabled']:raise Denial(503,'Capture is disabled; saved evidence remains readable.')
            if current.health()['queued'] >= current.policy['maximum_queued_jobs']:raise Denial(429,'The queue is full; the saved choice can be admitted later.')
            try:return response(current.confirm_wide(token,job_id,body.plan_sha256,body.identity_receipt_sha256,
                body.selected_seed_entity_id,body.selected_favorite_movie_entity_id),202)
            except SchemaError:raise Denial(409,'The saved choices or their evidence no longer match this wide plan.') from None
        return call(action)
    return router


class Denial(Exception):
    def __init__(self,status,message):self.status,self.message=status,message
