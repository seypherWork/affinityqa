"""Same-origin owned case HTTP contract for repeatable-v1 and read-only legacy access."""
from datetime import datetime
import hmac
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .errors import SchemaError
from .individual_api import ConfirmBody, JobId, PlanBody, StartBody
from .public_case_api import EmptyBody, cookie_name
from .public_cases import SHA, TOKEN


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
                    confirm_identities=body.confirm_identities,discover_new_movies=body.discover_new_movies)
            except SchemaError:raise Denial(422,'Use two distinct interests and valid, disjoint cinema preferences from this catalog.') from None
            return response(value,201)
        return call(action)

    @router.get('/jobs/{job_id}')
    def status(request:Request,job_id:JobId):
        def action():
            current,token=access(request);return response(current.view(token,job_id))
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
            if view.get('read_only') or view['status']!='AWAITING_IDENTITY_CONFIRMATION':raise Denial(409,'This saved identity selection cannot be admitted again.')
            if view['plan_sha256']!=body.plan_sha256 or view.get('identity_receipt_sha256')!=body.identity_receipt_sha256:
                raise Denial(409,'The reviewed plan or identity receipt differs.')
            if not current.capabilities(token)['execution_enabled']:raise Denial(503,'Confirmed capture is disabled; saved cases remain readable.')
            if current.health()['queued']>=current.policy['maximum_queued_jobs']:raise Denial(429,'The concurrent queue is full. Your saved selection can be admitted later.')
            try:return response(current.confirm_identities(token,job_id,body.plan_sha256,body.identity_receipt_sha256,body.selected_entity_ids.model_dump()),202)
            except SchemaError:raise Denial(409,'The saved identity choices or evidence no longer match this plan.') from None
        return call(action)
    return router


class Denial(Exception):
    def __init__(self,status,message):self.status,self.message=status,message
