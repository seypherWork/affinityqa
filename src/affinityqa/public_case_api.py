"""Owned public case routes. No private job lists, provider bodies or bearer JSON."""
from datetime import datetime
import hmac
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .errors import SchemaError
from .individual_api import ConfirmBody, JobId, PlanBody, StartBody, StrictBody
from .public_cases import SHA, TOKEN


class EmptyBody(StrictBody):
    pass


class _Denial(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def cookie_name(origin):
    return '__Host-affinityqa-case' if urlsplit(origin).scheme == 'https' else 'affinityqa-loopback-case'


def routes(manager, *, origin):
    router = APIRouter(prefix='/api/demo/cases')
    name = cookie_name(origin)

    def response(value, status=200, extra=None):
        return JSONResponse(value, status_code=status, headers={
            'Cache-Control': 'no-store', **(extra or {})})

    def call(action):
        try:
            return action()
        except _Denial as error:
            return response({'error': error.message}, error.status)
        except FileNotFoundError:
            return response({'error': 'Case access unavailable.'}, 404)
        except Exception:
            # Never echo exception text, a token, a key, paths or provider bodies.
            return response({'error': 'Case service unavailable. No result approved.'}, 503)

    def service():
        if manager is None:
            raise _Denial(503, 'New cases are not configured on this server.')
        return manager

    def cookie(request):
        found = None
        names = set()
        raw = request.headers.get('cookie', '')
        for part in raw.split(';') if raw else ():
            key, separator, value = part.strip().partition('=')
            if not separator or not key or key in names:
                raise _Denial(400, 'Ambiguous session cookie.')
            names.add(key)
            if key == name:
                if not TOKEN.fullmatch(value):
                    raise FileNotFoundError('Case access unavailable.')
                found = value
        return found

    def access(request, *, mutation=False):
        current = service()
        token = cookie(request)
        if token is None:
            raise FileNotFoundError('Case access unavailable.')
        _, info = current.session(token)
        if mutation:
            if request.headers.get('origin') != origin:
                raise _Denial(403, 'This action requires the demo origin.')
            csrf = request.headers.get('x-affinityqa-csrf', '')
            if not SHA.fullmatch(csrf) or not hmac.compare_digest(csrf, info['csrf_token']):
                raise _Denial(403, 'Session mutation token differs.')
            current.authorize_mutation(token, csrf)
        return current, token

    @router.post('/session')
    def session(request: Request, body: EmptyBody):
        def action():
            current = service()
            if request.headers.get('origin') != origin:
                raise _Denial(403, 'This action requires the demo origin.')
            with current.lock:
                try:
                    previous = cookie(request)
                    if previous is None and len(current.session_keys) >= current.policy['maximum_sessions']:
                        raise _Denial(429, 'Public session capacity reached.')
                    token, info = current.session(previous)
                except FileNotFoundError:
                    # Discard only an unusable browser credential after explicit
                    # same-origin access. Retain server records and every budget;
                    # a new session needs a separate deliberate request.
                    rejected = response({'error': 'Your previous review session is unavailable. Its browser cookie has been cleared. Open a new session to continue; saved cases are retained and no execution has been repeated.'}, 404)
                    rejected.delete_cookie(name, path='/', secure=urlsplit(origin).scheme == 'https',
                                           httponly=True, samesite='strict')
                    return rejected
                answer = response(info)
                if previous is None:
                    expiry = datetime.fromisoformat(info['expires_utc'])
                    seconds = max(1, int((expiry - current._now()).total_seconds()))
                    answer.set_cookie(name, token, max_age=seconds, expires=expiry, path='/',
                                      secure=urlsplit(origin).scheme == 'https',
                                      httponly=True, samesite='strict')
                # An existing session keeps its original server and browser expiry.
                return answer
        return call(action)

    @router.get('/capabilities')
    def capabilities(request: Request):
        return call(lambda: response(service().capabilities(access(request)[1])))

    @router.post('/plans', status_code=201)
    def plan(request: Request, body: PlanBody):
        def action():
            current, token = access(request, mutation=True)
            with current.lock:
                if current.capabilities(token)['remaining_plans'] <= 0:
                    raise _Denial(429, 'Public plan admissions exhausted.')
                try:
                    current.manager.request_for(body.artists.model_dump(), body.preferences.model_dump() if body.preferences is not None else None,
                        **({'confirm_identities':True} if body.confirm_identities else {}),
                        **({'discover_new_movies':True} if body.discover_new_movies else {}))
                except SchemaError:
                    raise _Denial(422, 'Use two distinct interests and valid, disjoint cinema preferences from this catalog.') from None
                return response(current.prepare(token, body.artists.model_dump(),
                    **({'preferences':body.preferences.model_dump()} if body.preferences is not None else {}),
                    **({'confirm_identities':True} if body.confirm_identities else {}),
                    **({'discover_new_movies':True} if body.discover_new_movies else {})), 201)
        return call(action)

    @router.get('/jobs/{job_id}')
    def status(request: Request, job_id: JobId):
        def action():
            current, token = access(request)
            return response(current.view(token, job_id))
        return call(action)

    @router.post('/jobs/{job_id}/execute', status_code=202)
    def execute(request: Request, job_id: JobId, body: StartBody):
        def action():
            current, token = access(request, mutation=True)
            with current.lock:
                view = current.view(token, job_id)
                if view['status'] != 'PLANNED' or view['plan_sha256'] != body.plan_sha256:
                    raise _Denial(409, 'This reviewed plan cannot be admitted again or with a different fingerprint.')
                cap = current.capabilities(token)
                if not cap['execution_enabled']:
                    raise _Denial(503, 'New execution is disabled; saved evidence remains readable.')
                if cap['remaining_executions'] <= 0:
                    raise _Denial(429, 'Public execution admissions exhausted.')
                worker = current.manager.worker
                if worker and worker.is_alive():
                    raise _Denial(429, 'Another public capture is active.')
                return response(current.start(token, job_id, body.plan_sha256), 202)
        return call(action)

    @router.get('/jobs/{job_id}/verification')
    def verification(request: Request, job_id: JobId):
        def action():
            current, token = access(request)
            view = current.view(token, job_id)
            if view['status'] not in ('COMPLETE', 'PARTIAL') or not view.get('receipt_sha256'):
                raise _Denial(409, 'No verified receipt is available for this case.')
            return response(current.verification(token, job_id), extra={
                'Content-Disposition': f'attachment; filename=affinityqa-public-{job_id}-verification.json'})
        return call(action)

    @router.post('/jobs/{job_id}/confirm-identities', status_code=202)
    def confirm(request: Request, job_id: JobId, body: ConfirmBody):
        def action():
            current, token = access(request, mutation=True)
            with current.lock:
                view = current.view(token, job_id)
                if view['status'] != 'AWAITING_IDENTITY_CONFIRMATION' or view['case_protocol'] not in ('cinema-confirmed-identity-v1', 'cinema-confirmed-discovery-v2'):
                    raise _Denial(409, 'This saved identity selection cannot be admitted again.')
                if view['plan_sha256'] != body.plan_sha256 or view.get('identity_receipt_sha256') != body.identity_receipt_sha256:
                    raise _Denial(409, 'The reviewed plan or identity receipt differs.')
                if not current.capabilities(token)['execution_enabled']:
                    raise _Denial(503, 'Confirmed capture is disabled; saved cases remain readable.')
                worker = current.manager.worker
                if worker and worker.is_alive():
                    raise _Denial(429, 'Another public capture is active.')
                try:
                    return response(current.confirm_identities(token, job_id, body.plan_sha256,
                        body.identity_receipt_sha256, body.selected_entity_ids.model_dump()), 202)
                except SchemaError:
                    raise _Denial(409, 'The saved identity choices or evidence no longer match this plan.') from None
        return call(action)

    return router
