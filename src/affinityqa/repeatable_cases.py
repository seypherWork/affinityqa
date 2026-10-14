"""Public repeatable-v1 ownership with sealed legacy evidence kept read-only."""
import copy
from datetime import datetime, timezone
import hashlib
import hmac
from pathlib import Path
import secrets
import sqlite3
import json
from threading import RLock

from .evidence import fingerprint
from .individual_capture import safe_directory_path, sha, validate_capture_paths
from .individual_jobs import IndividualJobManager, JOB_ID, TRANSITIONS, need, read, write
from .public_cases import TOKEN, SHA, utc
from .public_demo import canonical_origin
from .repeatable_jobs import DurableStore, RepeatableJobManager

JUDGING_END = '2026-11-17T04:45:00+00:00'
HISTORY_PAGE_SIZE=200


def repeatable_policy(*, access_until_utc=JUDGING_END, maximum_queued_jobs=128):
    need(access_until_utc==JUDGING_END,'Use the verified judging-period access horizon.')
    need(type(maximum_queued_jobs) is int and 1<=maximum_queued_jobs<=2000,'Explicit bounded concurrent queue capacity required.')
    return {'schema_version':1,'admission_mode':'repeatable-v1','access_until_utc':access_until_utc,
            'maximum_queued_jobs':maximum_queued_jobs,'lifetime_session_limit':None,
            'lifetime_plan_limit':None,'lifetime_execution_limit':None,
            'per_session_plan_limit':None,'per_session_execution_limit':None,
            'session_is_a_verified_person':False,'automatic_pruning':False,
            'automatic_failed_or_unknown_send_retry':False,'concurrent_captures':1}


class LegacyCaseReader:
    """Never initialize legacy managers: even disabled constructors may write events."""
    def __init__(self,root):
        self.root=safe_directory_path(Path(root))
        self.binding=read(self.root/'public-policy.json')
        self.binding_sha=sha(self.root/'public-policy.json')
        self.sessions=self.root/'sessions';self.owners=self.root/'ownership'
        need(self.sessions.is_dir() and self.owners.is_dir() and (self.root/'jobs').is_dir(),
             'Legacy storage directories unavailable.')
        manager=IndividualJobManager.__new__(IndividualJobManager)
        manager.root=self.root/'jobs';manager.lock=RLock();manager.jobs={};manager.operator='groq'
        manager.adapters=None;manager.enabled=False;manager.closed=False;manager.worker=None
        self.manager=manager

    def _bound(self):
        need(sha(self.root/'public-policy.json')==self.binding_sha,'Legacy seal changed.')

    def recognizes(self,key):
        self._bound();path=self.sessions/(key+'.json')
        if not path.is_file():return False
        value=read(path)
        need(value['session_sha256']==key and value['policy_sha256']==self.binding['policy_sha256'],
             'Legacy ownership identity differs.')
        utc(value['created_utc']);utc(value['expires_utc'])
        return True

    def owner(self,job_id):
        self._bound()
        if not isinstance(job_id,str) or not JOB_ID.fullmatch(job_id):return None
        path=self.owners/(job_id+'.json')
        if not path.is_file():return None
        value=read(path)
        need(value['job_id']==job_id and value['policy_sha256']==self.binding['policy_sha256']
             and isinstance(value['session_sha256'],str) and SHA.fullmatch(value['session_sha256']),
             'Legacy case ownership differs.')
        return value['session_sha256']

    def _restore_job(self,job_id):
        envelope=read(self.manager.root/job_id/'job-plan.json')
        need(envelope['job_id']==job_id and envelope['plan']['plan_sha256']==fingerprint(
             {k:v for k,v in envelope['plan'].items() if k!='plan_sha256'}),'Legacy plan binding differs.')
        status='PLANNED';sequence=0;receipt_hash=None;error=None
        for path in sorted((self.manager.root/job_id).glob('event-*.json')):
            event=read(path);sequence+=1
            need(path.name==f'event-{sequence:04d}.json' and event['job_id']==job_id
                 and event['sequence']==sequence and event['status'] in TRANSITIONS.get(status,set()),
                 'Legacy transition history differs.')
            status,receipt_hash,error=event['status'],event['receipt_sha256'],event['error_class']
        self.manager.jobs[job_id]={**envelope,'status':status,'sequence':sequence,
                                  'receipt_sha256':receipt_hash,'error_class':error}

    def view(self,key,job_id):
        if self.owner(job_id)!=key:raise FileNotFoundError('Case access unavailable.')
        with self.manager.lock:
            self._restore_job(job_id)
            result=self.manager.view(job_id)
        result.update(legacy_case=True,read_only=True,admission_mode='legacy-sealed-v1',
                      queue_status=None,queue_position=None,not_before=None)
        return result

    def receipt(self,key,job_id):
        if self.owner(job_id)!=key:raise FileNotFoundError('Case access unavailable.')
        with self.manager.lock:
            self._restore_job(job_id)
            return self.manager.receipt(job_id)

    def jobs(self,key):
        self._bound();result=[]
        for path in self.owners.glob('*.json'):
            if self.owner(path.stem)==key:
                view=self.view(key,path.stem)
                result.append({k:view[k] for k in ('job_id','status','artists','legacy_case','read_only')})
        return result


class RepeatableCaseManager:
    def __init__(self,root,template,*,origin,minimum_model_interval_seconds,execution_enabled=False,
                 settings_loader=None,remote_key_loader=None,legacy_root=None,policy=None,
                 scheduler=None,qloo_cache=None,token_estimator=None,_test_adapters=None,_test_now=None,_test_autostart=True):
        need(_test_now is None or _test_adapters is not None,'Simulated clock requires simulated providers.')
        self.root=safe_directory_path(Path(root));self.origin=canonical_origin(origin)
        need(self.root.is_absolute(),'Absolute repeatable storage root required.')
        validate_capture_paths(self.root/'jobs'/('20000101T000000Z-'+'0'*8)/'attempts'/'attempt-999999'/'capture')
        self.policy=repeatable_policy() if policy is None else copy.deepcopy(policy)
        need(self.policy==repeatable_policy(**{k:self.policy[k] for k in ('access_until_utc','maximum_queued_jobs')}),
             'Closed repeatable admission policy required.')
        if legacy_root is not None:
            previous=safe_directory_path(Path(legacy_root))
            need(previous!=self.root and previous not in self.root.parents and self.root not in previous.parents,
                 'Repeatable store must be separate from sealed legacy storage.')
            self.legacy=LegacyCaseReader(previous)
            need(self.legacy.binding['origin']==self.origin,'Legacy origin differs from new public ownership origin.')
        else:self.legacy=None
        self._clock=_test_now or (lambda:datetime.now(timezone.utc));self.lock=RLock();self._mutations_blocked=False
        self.root.mkdir(mode=0o700,parents=False,exist_ok=True)
        from .individual_remote_capture import validate_request
        template=validate_request(template)
        binding={'schema_version':1,'admission_mode':'repeatable-v1','origin':self.origin,'policy':self.policy,
                 'minimum_model_interval_seconds':float(minimum_model_interval_seconds),
                 'template_sha256':fingerprint(template),'legacy_policy_sha256':self.legacy.binding_sha if self.legacy else None}
        binding['binding_sha256']=fingerprint(binding)
        path=self.root/'repeatable-policy.json'
        if path.exists():need(read(path)==binding,'Repeatable store binding differs; retain and inspect it.')
        else:
            need(not list(self.root.iterdir()),'Choose a new versioned repeatable store.')
            write(path,binding)
        self.binding=binding;self._binding_file_sha=sha(path)
        self.store=DurableStore(self.root/'repeatable-state.sqlite3')
        self.manager=RepeatableJobManager(self.root/'jobs',template,store=self.store,
            execution_enabled=execution_enabled,settings_loader=settings_loader,remote_key_loader=remote_key_loader,
            minimum_model_interval_seconds=minimum_model_interval_seconds,scheduler=scheduler,qloo_cache=qloo_cache,
            token_estimator=token_estimator,
            _test_adapters=_test_adapters,_test_now=_test_now,_test_autostart=_test_autostart)

    def _now(self):return self._clock()

    def _bound(self):
        need(not self.manager.closed and sha(self.root/'repeatable-policy.json')==self._binding_file_sha
             and read(self.root/'repeatable-policy.json')==self.binding,'Repeatable public seal changed.')

    def _identity(self,token):
        self._bound()
        if not isinstance(token,str) or not TOKEN.fullmatch(token):raise FileNotFoundError('Case access unavailable.')
        key=hashlib.sha256(token.encode('ascii')).hexdigest()
        record=self.store.one('SELECT * FROM sessions WHERE owner=?',(key,))
        if record is None:raise FileNotFoundError('Case access unavailable.')
        need(record['owner']==key and record['expires']==self.policy['access_until_utc'],
             'Repeatable ownership/session horizon changed.')
        if not utc(record['created'])<=self._now()<utc(record['expires']):raise FileNotFoundError('Case access unavailable.')
        return key

    def _can_mutate(self):
        self._bound();need(not self._mutations_blocked and not self.manager._admissions_blocked(),
                           'Repeatable admissions blocked after a storage failure.')

    def session(self,token=None):
        with self.lock:
            self._bound()
            now=self._now();need(now<utc(self.policy['access_until_utc']),'Judging-period access has ended.')
            legacy=False
            if token is None:
                self._can_mutate()
                token=secrets.token_urlsafe(32)
                key=hashlib.sha256(token.encode('ascii')).hexdigest()
            else:
                if not isinstance(token,str) or not TOKEN.fullmatch(token):raise FileNotFoundError('Case access unavailable.')
                key=hashlib.sha256(token.encode('ascii')).hexdigest()
                existing=self.store.one('SELECT * FROM sessions WHERE owner=?',(key,))
                if existing:self._identity(token)
                else:
                    if not self.legacy or not self.legacy.recognizes(key):raise FileNotFoundError('Case access unavailable.')
                    self._can_mutate()
                    legacy=True
            if self.store.one('SELECT owner FROM sessions WHERE owner=?',(key,)) is None:
                try:
                    with self.store.transaction() as db:
                        db.execute('INSERT INTO sessions(owner,created,expires,legacy) VALUES(?,?,?,?)',
                                   (key,now.isoformat(),self.policy['access_until_utc'],int(legacy)))
                except (OSError,sqlite3.Error):
                    self._mutations_blocked=True;self.manager.block_storage('StorageFailure');raise
            csrf=hmac.new(token.encode('ascii'),b'affinityqa-public-case-csrf-v1',hashlib.sha256).hexdigest()
            return token,{'schema_version':1,'csrf_token':csrf,'expires_utc':self.policy['access_until_utc'],
                          'admission_mode':'repeatable-v1','ownership_preserved':True}

    def authorize_mutation(self,token,csrf):
        with self.lock:
            self._identity(token);self._can_mutate()
            expected=hmac.new(token.encode('ascii'),b'affinityqa-public-case-csrf-v1',hashlib.sha256).hexdigest()
            need(isinstance(csrf,str) and SHA.fullmatch(csrf) and hmac.compare_digest(csrf,expected),'Session mutation token differs.')

    def _owned(self,key,job_id):
        if not isinstance(job_id,str) or not JOB_ID.fullmatch(job_id):raise FileNotFoundError('Case access unavailable.')
        row=self.store.one('SELECT owner FROM jobs WHERE job_id=?',(job_id,))
        if row is not None:
            if row['owner']!=key:raise FileNotFoundError('Case access unavailable.')
            return True
        if self.legacy and self.legacy.owner(job_id)==key:return False
        raise FileNotFoundError('Case access unavailable.')

    def capabilities(self,token):
        with self.lock:
            key=self._identity(token);template=self.manager.template
            page=self._history_page(key)
            jobs=page['jobs']
            if self.legacy:jobs+=self.legacy.jobs(key)
            health=self.health()
            return {'schema_version':1,'configured':True,'execution_enabled':health['execution_enabled'] and not self._mutations_blocked,
                'admissions_blocked':health['admissions_blocked'],'simulation_only':self.manager.adapters is not None,
                'operator_mode':'groq','provider':'groq','model':template['model']['name'],
                'default_artists':copy.deepcopy(template['artists']),'catalog':copy.deepcopy(template['catalog']),
                'catalog_sha256':fingerprint(template['catalog']),'cinema_preferences_supported':True,
                'cinema_identity_confirmation_supported':True,'cinema_discoveries_supported':True,
                'minimum_model_interval_seconds':self.manager.interval,'remaining_plans':None,'remaining_executions':None,
                'admission_mode':'repeatable-v1','jobs':jobs,'jobs_truncated':page['jobs_truncated'],
                'next_cursor_job_id':page['next_cursor_job_id'],
                'session_is_verified_person':False,'provider_quota_or_cost_reserved':False,
                'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED','queue_length':health['queued']}

    def _history_page(self,key,cursor_job_id=None):
        args=[key];seek=''
        if cursor_job_id is not None:
            if not isinstance(cursor_job_id,str) or not JOB_ID.fullmatch(cursor_job_id):
                raise FileNotFoundError('Case access unavailable.')
            cursor=self.store.one('SELECT created,job_id FROM jobs WHERE owner=? AND job_id=?',(key,cursor_job_id))
            if cursor is None:raise FileNotFoundError('Case access unavailable.')
            seek=' AND (created<? OR (created=? AND job_id<?))'
            args.extend((cursor['created'],cursor['created'],cursor['job_id']))
        rows=self.store.rows('SELECT job_id,status,plan_json FROM jobs WHERE owner=?'+seek+
            ' ORDER BY created DESC,job_id DESC LIMIT ?',(*args,HISTORY_PAGE_SIZE+1))
        more=len(rows)>HISTORY_PAGE_SIZE
        displayed=rows[:HISTORY_PAGE_SIZE]
        jobs=[{'job_id':row['job_id'],'status':row['status'],
               'artists':copy.deepcopy(json.loads(row['plan_json'])['request']['artists']),
               'legacy_case':False,'read_only':False} for row in displayed]
        return {'schema_version':1,'jobs':jobs,'jobs_truncated':more,
                'next_cursor_job_id':displayed[-1]['job_id'] if more else None}

    def history(self,token,cursor_job_id):
        """Seek an owner-bound retained page without admitting or touching a job."""
        with self.lock:
            key=self._identity(token)
            return self._history_page(key,cursor_job_id)

    def prepare(self,token,artists,preferences=None,confirm_identities=False,discover_new_movies=False):
        with self.lock:
            key=self._identity(token);self._can_mutate()
            try:
                return self.manager.prepare(key,artists,preferences,confirm_identities,discover_new_movies)
            except (OSError,sqlite3.Error):
                self._mutations_blocked=True;self.manager.block_storage('StorageFailure');raise

    def _queue_capacity(self):
        need(self.manager.health()['queued']<self.policy['maximum_queued_jobs'],
             'Concurrent queue is full; saved plans and evidence are retained.')

    def start(self,token,job_id,plan_hash):
        with self.lock:
            key=self._identity(token);new=self._owned(key,job_id);self._can_mutate()
            need(new,'Historical sealed cases are read-only; prepare a new repeatable case.')
            self._queue_capacity()
            try:return self.manager.start(job_id,plan_hash)
            except (OSError,sqlite3.Error):
                self._mutations_blocked=True;self.manager.block_storage('StorageFailure');raise

    def confirm_identities(self,token,job_id,plan_hash,identity_receipt_hash,selected_entity_ids):
        with self.lock:
            key=self._identity(token);new=self._owned(key,job_id);self._can_mutate()
            need(new,'Historical sealed cases are read-only.')
            self._queue_capacity()
            try:return self.manager.confirm_identities(job_id,plan_hash,identity_receipt_hash,selected_entity_ids)
            except (OSError,sqlite3.Error):
                self._mutations_blocked=True;self.manager.block_storage('StorageFailure');raise

    def view(self,token,job_id):
        with self.lock:
            key=self._identity(token);new=self._owned(key,job_id)
            result=self.manager.view(job_id) if new else self.legacy.view(key,job_id)
            contract=(result.get('result') or {}).get('repeatable_contract')
            if contract is not None:
                safe_fields=('schema_version','admission_mode','reviewed_plan_sha256','capture_plan_sha256',
                    'provider_stats','capture_attempts','accepted_operation_reconstruction_is_new_dispatch',
                    'legacy_packets_are_original_dispatch_observations','automatic_failed_or_unknown_send_retry',
                    'verified_human_participants','cultural_quality','original_identity_receipt_sha256',
                    'explicit_selection_sha256')
                selected={k:copy.deepcopy(contract[k]) for k in safe_fields if k in contract}
                provenance=contract.get('provider_provenance')
                if provenance:
                    selected.update(provider_provenance_sha256=provenance['sha256'],
                                    provider_receipt_set_sha256=provenance['receipt_set_sha256'])
                result['result']['repeatable_contract']=selected
            return result

    def verification(self,token,job_id):
        with self.lock:
            view=self.view(token,job_id)
            need(view['status'] in ('COMPLETE','PARTIAL') and view.get('receipt_sha256'),
                 'No verified public receipt is available.')
            return {'schema_version':1,'job_id':job_id,'plan_sha256':view['plan_sha256'],
                    'receipt_sha256':view['receipt_sha256'],'result':copy.deepcopy(view['result']),
                    'notice':'Selected case summary; private inventory and provider envelopes are excluded. Local integrity is not external or cultural attestation.'}

    def health(self):return {**self.manager.health(),'admissions_blocked':self._mutations_blocked or self.manager._admissions_blocked()}

    def close(self):
        self.manager.close();self.store.close()
