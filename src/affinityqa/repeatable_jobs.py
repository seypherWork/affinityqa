"""Durable single-service FIFO stages; a wait before dispatch is recoverable."""
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import Condition, RLock, Thread
from uuid import uuid4

from .evidence import fingerprint, utc_now
from .errors import SchemaError
import builtins
from .individual_capture import safe_directory_path, execution_lease, sha
from .individual_jobs import JOB_ID, IndividualJobManager, need, read, write
from .individual_verify import inventory
from .repeatable_capture import request_for, open_movie_request, prepare_protocol, execute_stage, outer_receipt, protocol

ACTIVE = ('QUEUED','WAITING_PROVIDER_CAPACITY','RUNNING','VERIFYING')
HELPERS = ('repeatable_cases.py','repeatable_jobs.py','repeatable_capture.py',
           'repeatable_case_config.py','repeatable_case_api.py','provider_runtime.py',
           'provider_scheduler.py','qloo_cache.py','movie_case_bodies.py')


def open_movie_confirmation(receipt, selected_movie_entity_id):
    """A title/year selection must resolve to exactly one verified search candidate."""
    from .cinema_movie_inputs import movie_identity
    need(receipt.get('verification_status') == 'VERIFIED_IDENTITY_SEARCH', 'Verified movie search required.')
    candidates = receipt.get('movie_candidates')
    need(isinstance(candidates, list) and 1 <= len(candidates) <= 5, 'Bounded movie candidates required.')
    chosen = [movie_identity(candidate) for candidate in candidates
              if candidate.get('entity_id') == selected_movie_entity_id]
    need(len(chosen) == 1, 'Choose one verified title and year.')
    return chosen[0]


def validate_open_movie_confirmation(receipt, choice):
    need(set(choice) == {'schema_version', 'identity_receipt_sha256', 'identity_receipt',
                        'selected_movie_entity_id', 'chosen_movie_input'}
         and type(choice['schema_version']) is int and choice['schema_version'] == 3,
         'Closed open-movie confirmation version3 required.')
    need(choice['chosen_movie_input'] == open_movie_confirmation(receipt, choice['selected_movie_entity_id']),
         'Saved movie selection differs from verified title and year.')


def movie_confirmation(request, receipt, selected_movie_entity_ids):
    """Resolve only server-verified choices; posted names and years are never accepted."""
    if request['schema_version'] in (6,7):
        if request['schema_version'] == 7:
            from .fast_pair_verify import selection_movies
        else:
            from .cinema_discovery_v4_verify import selection_movies
        need(selected_movie_entity_ids is not None, 'Every movie search requires an explicit selection.')
        return selection_movies(receipt, selected_movie_entity_ids)
    need(selected_movie_entity_ids is None, 'This historical request has no movie searches.')
    return None


def validate_movie_confirmation(request, receipt, choice):
    if request['schema_version'] in (6,7):
        need(set(choice) == {'schema_version','identity_receipt_sha256','identity_receipt',
                            'selected_entity_ids','chosen_identities','selected_movie_entity_ids','chosen_movie_inputs'}
             and type(choice['schema_version']) is int and choice['schema_version'] == 2,
             'Closed movie confirmation version2 required.')
        need(choice['chosen_movie_inputs'] == movie_confirmation(request, receipt, choice['selected_movie_entity_ids']),
             'Saved movie selection differs from its verified search slots.')
    else:
        need('selected_movie_entity_ids' not in choice and 'chosen_movie_inputs' not in choice,
             'Historical confirmations cannot add movie inputs.')


def helper_bindings():
    source=Path(__file__).resolve().parent
    result={name:sha(source/name) for name in HELPERS}
    result['requirements-backend.lock.txt']=sha(source.parents[1]/'requirements-backend.lock.txt')
    for relative in ('requirements-repeatable.lock.txt','assets/tokenizers/o200k_base.tiktoken'):
        path=source.parents[1]/relative
        if path.is_file():result[relative]=sha(path)
    # The transport may supply separately inspected tokenizer assets; no
    # unverified model-specific estimator is silently admitted by this manager.
    from . import provider_runtime
    getter=getattr(provider_runtime,'runtime_source_bindings',None)
    if callable(getter):
        result['transport_assets']=getter()
    return result


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def timestamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


class DurableStore:
    def __init__(self, path):
        self.path = safe_directory_path(Path(path))
        self.lock = RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS sessions(owner TEXT PRIMARY KEY, created TEXT NOT NULL,
            expires TEXT NOT NULL, legacy INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES sessions(owner),
            created TEXT NOT NULL, plan_json TEXT NOT NULL, envelope_sha TEXT NOT NULL,
            status TEXT NOT NULL, phase TEXT, not_before REAL, attempts INTEGER NOT NULL DEFAULT 0,
            directory TEXT, receipt_json TEXT, receipt_sha TEXT, error_class TEXT,
            confirmation_json TEXT, provider_stats TEXT NOT NULL DEFAULT '{}', diagnostic TEXT NOT NULL DEFAULT '{}');
          CREATE TABLE IF NOT EXISTS queue(seq INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT UNIQUE NOT NULL REFERENCES jobs(job_id), phase TEXT NOT NULL, eligible REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(job_id), utc TEXT NOT NULL, status TEXT NOT NULL,
            details TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS queue_eligible ON queue(eligible,seq);
          CREATE INDEX IF NOT EXISTS owner_jobs ON jobs(owner,created,job_id);
        ''')

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
            else:
                self.db.execute('COMMIT')

    def rows(self, sql, args=()):
        with self.lock:
            return [dict(row) for row in self.db.execute(sql,args).fetchall()]

    def one(self, sql, args=()):
        values=self.rows(sql,args)
        return values[0] if values else None

    def event(self, db, job_id, status, details=None):
        db.execute('INSERT INTO events(job_id,utc,status,details) VALUES(?,?,?,?)',
                   (job_id,utc_now(),status,encoded(details or {})))

    def close(self):
        with self.lock:
            self.db.close()


class RepeatableJobManager:
    def __init__(self, root, template, *, store, execution_enabled=False, settings_loader=None,
                 remote_key_loader=None, minimum_model_interval_seconds=0.0, scheduler=None,
                 qloo_cache=None, token_estimator=None, _test_adapters=None, _test_now=None, _test_autostart=True):
        from .individual_remote_capture import validate_request
        from .remote_pacing import pacing_policy
        self.root=safe_directory_path(Path(root))
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.store=store
        self.template=validate_request(template)
        self.interval=pacing_policy(minimum_model_interval_seconds)['minimum_interval_seconds']
        need(self.interval is not None,'Explicit provider cadence required.')
        need(type(execution_enabled) is bool,'Explicit execution boolean required.')
        self.enabled=execution_enabled
        need(not self.enabled or (callable(settings_loader) and callable(remote_key_loader)),
             'Explicit private credential loaders required.')
        self.settings_loader,self.remote_key_loader=settings_loader,remote_key_loader
        self.adapters=_test_adapters
        self.scheduler,self.qloo_cache=scheduler,qloo_cache
        self.token_estimator=token_estimator
        need(not self.enabled or _test_adapters is not None or (scheduler is not None and token_estimator is not None),
             'Real repeatable execution requires the durable dispatcher and reviewed token estimator.')
        self._clock=_test_now or (lambda:datetime.now(timezone.utc))
        self.lock=RLock();self.condition=Condition(self.lock)
        self.closed=False;self.worker=None;self._active=None;self._storage_failed=False
        self.autostart=_test_autostart
        self.lease=execution_lease(self.root);self.lease.__enter__()
        try:
            self._restore()
            if self.enabled and self.autostart:
                self._ensure_worker()
        except BaseException:
            self.lease.__exit__(None,None,None)
            raise

    def _epoch(self):
        value=self._clock()
        need(isinstance(value,datetime) and value.utcoffset() is not None and value.utcoffset().total_seconds()==0,
             'UTC clock required.')
        return value.timestamp()

    def _restore(self):
        blocked=self.store.one("SELECT value FROM metadata WHERE key='storage_blocked'")
        if blocked is not None or (self.root/'.repeatable-storage-blocked.json').exists():
            self._storage_failed=True
        # A process died while reconstructing. ProviderScheduler independently
        # fences every SENT record to UNKNOWN before a new operation can dispatch.
        if not self._admissions_blocked():
            with self.store.transaction() as db:
                for row in db.execute("SELECT job_id,phase FROM jobs WHERE status IN ('RUNNING','VERIFYING')").fetchall():
                    db.execute("UPDATE jobs SET status='QUEUED',not_before=? WHERE job_id=?",(self._epoch(),row['job_id']))
                    db.execute('INSERT OR IGNORE INTO queue(job_id,phase,eligible) VALUES(?,?,?)',
                               (row['job_id'],row['phase'],self._epoch()))
                    self.store.event(db,row['job_id'],'QUEUED',{'restart_before_next_dispatch':True})
        stored_ids=set()
        for row in self.store.rows('SELECT job_id,owner,envelope_sha,plan_json FROM jobs'):
            stored_ids.add(row['job_id'])
            need(JOB_ID.fullmatch(row['job_id']), 'Invalid durable job ID.')
            path=self.root/row['job_id']/'job-plan.json'
            need(path.is_file() and sha(path)==row['envelope_sha']
                 and read(path)['plan']==json.loads(row['plan_json'])
                 and read(path)['owner_sha256']==row['owner'], 'Saved repeatable plan changed.')
        actual_ids=set()
        for path in self.root.iterdir():
            if path.name=='.affinityqa-individual.lock':continue
            safe_directory_path(path)
            if not path.is_dir() or not JOB_ID.fullmatch(path.name):
                self._storage_failed=True
            else:actual_ids.add(path.name)
        if actual_ids!=stored_ids:self._storage_failed=True
        # A saved explicit choice is a safe pre-dispatch checkpoint in this NEW
        # contract. Validate it before committing the stage after a write/commit
        # interruption; no old admission is ever restarted this way.
        for row in self.store.rows("SELECT job_id FROM jobs WHERE status='AWAITING_IDENTITY_CONFIRMATION' AND confirmation_json IS NULL"):
            if self._admissions_blocked():break
            path=self.root/row['job_id']/'identity-confirmation.json'
            if not path.exists():continue
            job=self._job(row['job_id']);choice=read(path);receipt=self._receipt(job)
            need(choice['identity_receipt_sha256']==job['receipt_sha'] and choice['identity_receipt']==receipt,
                 'Uncommitted identity selection differs from saved evidence.')
            if job['plan']['request']['schema_version'] == 8:
                validate_open_movie_confirmation(receipt, choice)
            else:
                from .cinema_identity_verify import selection_profiles
                need(choice['chosen_identities']==selection_profiles(receipt,choice['selected_entity_ids']),
                     'Uncommitted artist selection differs from saved evidence.')
                validate_movie_confirmation(job['plan']['request'],receipt,choice)
            now=self._epoch()
            with self.store.transaction() as db:
                db.execute("UPDATE jobs SET status='QUEUED',phase='capture',not_before=?,confirmation_json=? WHERE job_id=?",
                           (now,encoded(choice),job['job_id']))
                db.execute("INSERT INTO queue(job_id,phase,eligible) VALUES(?,'capture',?)",(job['job_id'],now))
                self.store.event(db,job['job_id'],'QUEUED',{'recovered_explicit_pre_dispatch_confirmation':True})
        self.reconcile_terminal_reservations()

    def reconcile_terminal_reservations(self):
        """Finish interrupted terminal cleanup before enabling a dispatcher.

        Job status and provider reservations live in separate durable stores.
        A process can stop between committing a terminal job and releasing its
        unsent work. Such a PENDING row must not remain an eligible FIFO head.
        Sent/unknown/accepted observations and case artifacts are never changed.
        """
        with self.lock:
            if self.scheduler is None or self._admissions_blocked():return
            for row in self.store.rows("SELECT job_id,owner,status FROM jobs WHERE status IN ('COMPLETE','PARTIAL','FAILED','UNKNOWN')"):
                cancelled=self.scheduler.abandon_pending(row['job_id'],row['owner'])
                if cancelled:
                    with self.store.transaction() as db:
                        self.store.event(db,row['job_id'],row['status'],{
                            'reconciled_terminal_unsent_reservations':cancelled,
                            'automatic_retry':False})

    def request_for(self,artists,preferences=None,confirm_identities=False,discover_new_movies=False,movie_queries=None,fast_pair_review=False):
        return request_for(self.template,artists,preferences,confirm_identities,discover_new_movies,movie_queries,fast_pair_review)

    def prepare(self,owner,artists,preferences=None,confirm_identities=False,discover_new_movies=False,movie_queries=None,fast_pair_review=False):
        request=self.request_for(artists,preferences,confirm_identities,discover_new_movies,movie_queries,fast_pair_review)
        return self._prepare_request(owner, request)

    def prepare_open_movie(self, owner, movie_query, intent_text='', excluded_entity_ids=None):
        return self._prepare_request(owner, open_movie_request(self.template, movie_query, intent_text, excluded_entity_ids))

    def _prepare_request(self, owner, request):
        with self.lock:
            need(not self.closed and not self._admissions_blocked(),'Repeatable admissions are suspended; owner inspection required.')
            job_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
            parent=self.root/job_id;parent.mkdir(mode=0o700)
            attempts=parent/'attempts';attempts.mkdir(mode=0o700)
            first=attempts/'attempt-000001';first.mkdir(mode=0o700)
            protocol_plan=prepare_protocol(request,first/'capture',self.interval)
            plan={'schema_version':1,'admission_mode':'repeatable-v1','request':request,
                  'protocol_plan':protocol_plan,'source_sha256':sha(Path(__file__)),
                  'capture_source_sha256':sha(Path(__file__).with_name('repeatable_capture.py')),
                  'helper_bindings':helper_bindings(),
                  'token_estimation':copy.deepcopy(self.token_estimator.manifest) if self.token_estimator else
                      {'method':'conservative-byte-upper-bound-v1'},
                  'maximum_model_decisions':protocol_plan['maximum_model_decisions'],
                  'maximum_qloo_requests':protocol_plan['maximum_qloo_requests'],
                  'automatic_failed_or_unknown_send_retry':False}
            plan['plan_sha256']=fingerprint(plan)
            created=utc_now();envelope={'schema_version':1,'job_id':job_id,'owner_sha256':owner,'created_utc':created,'plan':plan}
            write(parent/'job-plan.json',envelope)
            with self.store.transaction() as db:
                db.execute('INSERT INTO jobs(job_id,owner,created,plan_json,envelope_sha,status) VALUES(?,?,?,?,?,?)',
                           (job_id,owner,created,encoded(plan),sha(parent/'job-plan.json'),'PLANNED'))
                self.store.event(db,job_id,'PLANNED')
            return self.view(job_id)

    def _job(self,job_id):
        need(isinstance(job_id,str) and JOB_ID.fullmatch(job_id),'Invalid repeatable job ID.')
        row=self.store.one('SELECT * FROM jobs WHERE job_id=?',(job_id,))
        if row is None:raise FileNotFoundError('Case access unavailable.')
        path=self.root/job_id/'job-plan.json'
        need(sha(path)==row['envelope_sha'],'Saved repeatable plan changed.')
        need(read(path)['owner_sha256']==row['owner'],'Saved repeatable case ownership changed.')
        row['plan']=json.loads(row.pop('plan_json'))
        need(row['plan']['plan_sha256']==fingerprint({k:v for k,v in row['plan'].items() if k!='plan_sha256'}),
             'Repeatable plan binding changed.')
        return row

    def start(self,job_id,plan_hash):
        with self.condition:
            job=self._job(job_id)
            need(self.enabled and not self.closed and not self._admissions_blocked(),'New execution is suspended; owner inspection required.')
            need(job['status']=='PLANNED' and job['plan']['plan_sha256']==plan_hash,'Reviewed plan is single use.')
            self._validate_sources(job)
            need(job['plan']['source_sha256']==sha(Path(__file__))
                 and job['plan']['capture_source_sha256']==sha(Path(__file__).with_name('repeatable_capture.py')),
                 'Repeatable execution source changed.')
            phase='identity-search' if job['plan']['request']['schema_version'] in (4,5,6,7,8) else 'capture'
            now=self._epoch()
            with self.store.transaction() as db:
                db.execute("UPDATE jobs SET status='QUEUED',phase=?,not_before=? WHERE job_id=?",(phase,now,job_id))
                db.execute('INSERT INTO queue(job_id,phase,eligible) VALUES(?,?,?)',(job_id,phase,now))
                self.store.event(db,job_id,'QUEUED')
            if self.autostart:self._ensure_worker()
            self.condition.notify_all()
            return self.view(job_id)

    def _validate_sources(self,job):
        need(job['plan']['helper_bindings']==helper_bindings(),
             'Repeatable helper source or tokenizer assets changed before the next dispatch.')
        current=copy.deepcopy(self.token_estimator.manifest) if self.token_estimator else {'method':'conservative-byte-upper-bound-v1'}
        need(job['plan']['token_estimation']==current,'Reviewed token estimation method changed before the next dispatch.')

    def current_execution_bindings(self):
        return {'helper_bindings':helper_bindings(),
                'token_estimation':copy.deepcopy(self.token_estimator.manifest) if self.token_estimator else
                    {'method':'conservative-byte-upper-bound-v1'}}

    def execution_source_compatible(self,plan,current=None):
        current=self.current_execution_bindings() if current is None else current
        return all(plan.get(key)==value for key,value in current.items())

    def _ensure_worker(self):
        with self.condition:
            if self.closed or (self.worker and self.worker.is_alive()):return
            self.worker=Thread(target=self._loop,daemon=False,name='affinityqa-repeatable-dispatcher')
            self.worker.start()

    def _loop(self):
        while True:
            with self.condition:
                if self.closed or self._admissions_blocked():return
            try:
                advanced=self.run_once()
            except BaseException as exc:
                # Do not dispatch unrelated queued work after partial storage
                # failure. Saved records remain readable for inspection.
                self.block_storage(type(exc).__name__)
                return
            if not advanced:
                with self.condition:
                    if self.closed:return
                    self.condition.wait(timeout=1.0)

    def run_once(self):
        """Only due stages are claimed; a waiting head never blocks another eligible case."""
        with self.lock:
            if self.closed or not self.enabled or self._admissions_blocked() or self._active is not None:return False
            now=self._epoch()
            with self.store.transaction() as db:
                row=db.execute('SELECT * FROM queue WHERE eligible<=? ORDER BY seq LIMIT 1',(now,)).fetchone()
                if row is None:return False
                job_id,phase=row['job_id'],row['phase']
                db.execute('DELETE FROM queue WHERE job_id=?',(job_id,))
                db.execute("UPDATE jobs SET status='RUNNING',phase=?,not_before=NULL,attempts=attempts+1 WHERE job_id=?",(phase,job_id))
                self.store.event(db,job_id,'RUNNING',{'phase':phase})
            self._active=job_id
        try:self._execute(job_id,phase)
        finally:
            with self.lock:self._active=None
        return True

    def _runtime(self,job):
        if self.scheduler is None:return None
        from .provider_runtime import ProviderRuntime
        manager=self
        class StorageGuardedRuntime(ProviderRuntime):
            def qloo_get(self,*args,**kwargs):
                manager._check_dispatch_storage()
                return super().qloo_get(*args,**kwargs)
            def model_rank(self,*args,**kwargs):
                manager._check_dispatch_storage()
                return super().model_rank(*args,**kwargs)
        request=job['plan']['request']
        if request['schema_version'] == 8:
            confirmation=json.loads(job['confirmation_json']) if job['confirmation_json'] else None
            scope={'movie_query':request['movie_query'],'intent_text':request['intent_text'],
                   'excluded_entity_ids':request['excluded_entity_ids'],
                   'selected_movie_entity_id':confirmation['selected_movie_entity_id'] if confirmation else None,
                   'source_namespace':fingerprint(job['plan']['protocol_plan']['source_sha256'])}
            # The musical/fixed-catalog cache has a different validation contract.
            # Accepted operations still reconstruct through the shared durable dispatcher.
            return StorageGuardedRuntime(self.scheduler,job_id=job['job_id'],owner_id=job['owner'],qloo_cache=None,
                cache_scope=scope,token_estimator=self.token_estimator,
                namespace={'request_sha256':fingerprint(request),
                           'source_sha256':fingerprint(job['plan']['protocol_plan']['source_sha256'])})
        selected=json.loads(job['confirmation_json'])['selected_entity_ids'] if job['confirmation_json'] else None
        scope={'identity':{'queries':request['artists'],'selected_entity_ids':selected},
               'profile':request['artists'],'catalog':request['catalog'],
               'preferences':request.get('preferences'),
               'source_namespace':fingerprint(job['plan']['protocol_plan']['source_sha256'])}
        candidate_contract=job['plan']['protocol_plan'].get('identity_candidate_contract')
        if candidate_contract is not None:
            scope['identity_candidate_contract']=candidate_contract
        movie_contract=job['plan']['protocol_plan'].get('movie_candidate_contract')
        if movie_contract is not None:
            scope['movie_candidate_contract']=movie_contract
            scope['movie_queries']=copy.deepcopy(request['movie_queries'])
            scope['selected_movie_entity_ids']=(json.loads(job['confirmation_json'])['selected_movie_entity_ids']
                                                 if job['confirmation_json'] else None)
        return StorageGuardedRuntime(self.scheduler,job_id=job['job_id'],owner_id=job['owner'],qloo_cache=self.qloo_cache,
            cache_scope=scope,token_estimator=self.token_estimator,
            namespace={'request_sha256':fingerprint(job['plan']['request']),
                       'catalog_sha256':fingerprint(job['plan']['request']['catalog']),
                       'source_sha256':fingerprint(job['plan']['protocol_plan']['source_sha256'])})

    def _check_dispatch_storage(self):
        with self.lock:
            if self._admissions_blocked():
                raise RuntimeError('Provider dispatch suspended after a storage or quota-accounting failure; owner inspection required.')

    def _paused_providers(self):
        getter=getattr(self.scheduler,'paused_providers',None)
        return getter() if callable(getter) else []

    def _admissions_blocked(self):
        return self._storage_failed or bool(self._paused_providers())

    def block_storage(self,error_class):
        """Retain an explicit block across restart; no automatic repair or clearing."""
        with self.condition:
            self._storage_failed=True
            self.condition.notify_all()
        value={'schema_version':1,'admission_mode':'repeatable-v1','error_class':error_class,
               'manual_owner_inspection_required':True,'automatic_clear':False}
        # Either independently durable record suffices; failure of both still
        # halts this process and leaves its uncertain records for inspection.
        try:
            with self.store.transaction() as db:
                db.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES('storage_blocked',?)",(encoded(value),))
        except (OSError,sqlite3.Error):pass
        marker=self.root/'.repeatable-storage-blocked.json'
        try:
            if not marker.exists():write(marker,value)
        except OSError:pass

    def _stats(self,job_id):
        default={p:{'http_attempts':0,'cache_hits':0,'reconstructed_steps':0,'unknown_attempts':0} for p in ('qloo','groq')}
        if self.scheduler is not None and callable(getattr(self.scheduler,'job_stats',None)):
            values=self.scheduler.job_stats(job_id)
            if isinstance(values,dict):
                for provider in default:
                    default[provider].update({key:values.get(provider,{}).get(key,0) for key in default[provider]})
        return default

    def _provenance(self,job_id,parent):
        artifacts={}
        job_root=self.root/job_id
        for path in sorted((job_root/'attempts').glob('attempt-*/*/*-provider-receipts.jsonl')):
            safe_directory_path(path)
            need(path.is_file(),'Provider provenance is not a regular file.')
            artifacts[str(path.relative_to(job_root)).replace('\\','/')]=sha(path)
        value={'schema_version':1,'contract':'repeatable-provider-provenance-v1',
               'job_id':job_id,'provider_stats':self._stats(job_id),'artifact_sha256':artifacts}
        if self.scheduler is not None and callable(getattr(self.scheduler,'job_receipts',None)):
            value['receipts']=self.scheduler.job_receipts(job_id)
        destination=parent/'provider-provenance.json'
        write(destination,value)
        return {'path':str(destination.relative_to(job_root)).replace('\\','/'),'sha256':sha(destination),
                'artifact_sha256':artifacts,'receipt_set_sha256':fingerprint(value.get('receipts',[]))}

    def _execute(self,job_id,phase):
        job=self._job(job_id);runtime=self._runtime(job)
        parent=self.root/job_id/'attempts'/f"attempt-{job['attempts']:06d}"
        output=parent/'capture'
        try:
            parent.mkdir(mode=0o700,exist_ok=True)
            self._validate_sources(job)
            request=job['plan']['request']
            confirmation=json.loads(job['confirmation_json']) if job['confirmation_json'] else None
            if request['schema_version'] == 8 and phase != 'identity-search':
                need(confirmation is not None and read(self.root/job_id/'identity-confirmation.json') == confirmation,
                     'Saved movie confirmation differs from its durable checkpoint.')
                need(confirmation['identity_receipt_sha256'] == job['receipt_sha']
                     and confirmation['identity_receipt'] == json.loads(job['receipt_json']),
                     'Saved movie confirmation no longer matches the original search receipt.')
                validate_open_movie_confirmation(confirmation['identity_receipt'], confirmation)
            if request['schema_version'] in (6,7) and phase != 'identity-search':
                need(confirmation is not None and read(self.root/job_id/'identity-confirmation.json') == confirmation,
                     'Saved movie confirmation differs from its durable checkpoint.')
                need(confirmation['identity_receipt_sha256'] == job['receipt_sha']
                     and confirmation['identity_receipt'] == json.loads(job['receipt_json']),
                     'Saved movie confirmation no longer matches the original search receipt.')
                from .cinema_identity_verify import selection_profiles
                need(confirmation['chosen_identities'] == selection_profiles(confirmation['identity_receipt'],confirmation['selected_entity_ids']),
                     'Saved artist selection differs from the confirmed movie case.')
                validate_movie_confirmation(request,confirmation['identity_receipt'],confirmation)
            settings=self.settings_loader()
            from .groq_agent import contains_secret
            need(isinstance(settings.api_key,str) and settings.api_key.strip()
                 and not contains_secret(job['plan'],(settings.api_key,)),'Private Qloo configuration invalid.')
            key=None
            if phase!='identity-search':
                key=self.remote_key_loader()
                import re
                need(isinstance(key,str) and re.fullmatch(r'[!-~]{20,512}',key)
                     and not contains_secret(job['plan'],(settings.api_key,key)),'Private model configuration invalid.')
            directory,receipt=execute_stage(request,output,settings,key,stage=phase,interval=self.interval,
                adapters=self.adapters,runtime=runtime,confirmation=confirmation,
                reviewed_protocol_plan=job['plan']['protocol_plan'])
            failure_type=getattr(builtins,receipt.get('error_class') or '',None)
            if isinstance(failure_type,type) and issubclass(failure_type,OSError):
                raise OSError('The capture reported a local storage failure; owner inspection required.')
            provider_stats=self._stats(job_id)
            receipt=outer_receipt(receipt,plan_hash=job['plan']['plan_sha256'],provider_stats=provider_stats,
                                  attempts=job['attempts'],confirmation=confirmation)
            receipt['repeatable_contract']['provider_provenance']=self._provenance(job_id,parent)
            name='identity-verification.json' if phase=='identity-search' else 'verification.json'
            write(parent/name,receipt)
            status=('AWAITING_IDENTITY_CONFIRMATION' if receipt['verification_status']=='VERIFIED_IDENTITY_SEARCH'
                    else 'COMPLETE' if receipt['verification_status']=='VERIFIED_COMPLETE' else 'PARTIAL')
            with self.store.transaction() as db:
                db.execute('UPDATE jobs SET status=?,directory=?,receipt_json=?,receipt_sha=?,error_class=?,provider_stats=? WHERE job_id=?',
                    (status,str(directory),encoded(receipt),sha(parent/name),receipt.get('error_class'),encoded(provider_stats),job_id))
                self.store.event(db,job_id,status,{'receipt_sha256':sha(parent/name)})
            if status in ('COMPLETE','PARTIAL') and callable(getattr(self.scheduler,'abandon_pending',None)):
                self.scheduler.abandon_pending(job_id,job['owner'])
        except BaseException as exc:
            from .provider_scheduler import ProviderDeferred, ProviderUncertain, ProviderRecordedFailure, ProviderRequestTooLarge
            status='FAILED';not_before=None
            diagnostic={}
            if isinstance(exc,(OSError,sqlite3.Error)):
                self.block_storage(type(exc).__name__)
            if isinstance(exc,ProviderDeferred):
                status='WAITING_PROVIDER_CAPACITY'
                not_before=getattr(exc,'next_eligible_at',getattr(exc,'not_before',None))
                need(type(not_before) in (int,float) and not_before>self._epoch(),'Provider wait metadata invalid.')
            elif isinstance(exc,ProviderUncertain):status='UNKNOWN'
            elif isinstance(exc,ProviderRequestTooLarge):
                diagnostic={'provider':exc.provider,'window':exc.window,'required':exc.required,'capacity':exc.capacity,
                            'dispatch_started':False,'automatic_retry':False}
            provider_stats=self._stats(job_id)
            directory=None
            if output.is_dir():
                captures=[p for p in output.iterdir() if p.is_dir() and JOB_ID.fullmatch(p.name)]
                if len(captures)==1:directory=str(captures[0])
            if isinstance(exc,ProviderRecordedFailure) and directory is not None:
                # A known sent failure is final, and a valid strict partial
                # receipt keeps accepted earlier observations reviewable.
                partial=None
                try:
                    functions=protocol(job['plan']['request'])
                    verifier=functions[4] if phase=='identity-search' else functions[2]
                    partial=verifier(Path(directory))
                    need(partial['verification_status']=='VERIFIED_PARTIAL','Failure did not produce a strict partial prefix.')
                except (SchemaError,OSError,ValueError,KeyError,TypeError):partial=None
                if partial is not None:
                    confirmation=json.loads(job['confirmation_json']) if job['confirmation_json'] else None
                    partial=outer_receipt(partial,plan_hash=job['plan']['plan_sha256'],provider_stats=provider_stats,
                                          attempts=job['attempts'],confirmation=confirmation)
                    partial['repeatable_contract']['provider_provenance']=self._provenance(job_id,parent)
                    write(parent/'verification.json',partial)
                    with self.store.transaction() as db:
                        db.execute("UPDATE jobs SET status='PARTIAL',directory=?,receipt_json=?,receipt_sha=?,error_class=?,provider_stats=? WHERE job_id=?",
                            (directory,encoded(partial),sha(parent/'verification.json'),type(exc).__name__,encoded(provider_stats),job_id))
                        self.store.event(db,job_id,'PARTIAL',{'sent_failure':True})
                    if callable(getattr(self.scheduler,'abandon_pending',None)):self.scheduler.abandon_pending(job_id,job['owner'])
                    return
            with self.store.transaction() as db:
                db.execute('UPDATE jobs SET status=?,not_before=?,error_class=?,directory=COALESCE(?,directory),provider_stats=?,diagnostic=? WHERE job_id=?',
                           (status,not_before,type(exc).__name__,directory,encoded(provider_stats),encoded(diagnostic),job_id))
                if status=='WAITING_PROVIDER_CAPACITY':
                    db.execute('INSERT INTO queue(job_id,phase,eligible) VALUES(?,?,?)',(job_id,phase,not_before))
                self.store.event(db,job_id,status,{'error_class':type(exc).__name__,'not_before':not_before})
            if status in ('FAILED','UNKNOWN') and callable(getattr(self.scheduler,'abandon_pending',None)):
                self.scheduler.abandon_pending(job_id,job['owner'])

    def identity_receipt(self,job_id):
        job=self._job(job_id)
        need(job['status']=='AWAITING_IDENTITY_CONFIRMATION','No pending identity selection.')
        return self._receipt(job)

    def confirm_identities(self,job_id,plan_hash,identity_receipt_hash,selected_entity_ids,selected_movie_entity_ids=None):
        with self.condition:
            job=self._job(job_id)
            need(job['plan']['request']['schema_version'] != 8, 'Use the explicit single-movie confirmation contract.')
            need(self.enabled and not self.closed and not self._admissions_blocked() and job['status']=='AWAITING_IDENTITY_CONFIRMATION',
                 'Identity confirmation is single use.')
            self._validate_sources(job)
            need(job['plan']['plan_sha256']==plan_hash and job['receipt_sha']==identity_receipt_hash,
                 'Reviewed identity receipt differs.')
            receipt=self.identity_receipt(job_id)
            from .cinema_identity_verify import selection_profiles
            profiles=selection_profiles(receipt,selected_entity_ids)
            confirmation={'schema_version':1,'identity_receipt_sha256':identity_receipt_hash,
                          'identity_receipt':receipt,'selected_entity_ids':copy.deepcopy(selected_entity_ids),
                          'chosen_identities':profiles}
            movies=movie_confirmation(job['plan']['request'],receipt,selected_movie_entity_ids)
            if movies is not None:
                confirmation.update(schema_version=2,selected_movie_entity_ids=copy.deepcopy(selected_movie_entity_ids),
                                    chosen_movie_inputs=movies)
            validate_movie_confirmation(job['plan']['request'],receipt,confirmation)
            write(self.root/job_id/'identity-confirmation.json',confirmation)
            now=self._epoch()
            with self.store.transaction() as db:
                db.execute("UPDATE jobs SET status='QUEUED',phase='capture',not_before=?,confirmation_json=? WHERE job_id=?",
                           (now,encoded(confirmation),job_id))
                db.execute("INSERT INTO queue(job_id,phase,eligible) VALUES(?,'capture',?)",(job_id,now))
                self.store.event(db,job_id,'QUEUED',{'explicit_identity_confirmation':True})
            if self.autostart:self._ensure_worker()
            self.condition.notify_all()
            return self.view(job_id)

    def confirm_movie(self, job_id, plan_hash, identity_receipt_hash, selected_movie_entity_id):
        with self.condition:
            job=self._job(job_id)
            need(job['plan']['request']['schema_version'] == 8 and self.enabled and not self.closed
                 and not self._admissions_blocked() and job['status']=='AWAITING_IDENTITY_CONFIRMATION',
                 'Movie confirmation is single use.')
            self._validate_sources(job)
            need(job['plan']['plan_sha256']==plan_hash and job['receipt_sha']==identity_receipt_hash,
                 'Reviewed movie receipt differs.')
            receipt=self.identity_receipt(job_id)
            confirmation={'schema_version':3,'identity_receipt_sha256':identity_receipt_hash,
                          'identity_receipt':receipt,'selected_movie_entity_id':selected_movie_entity_id,
                          'chosen_movie_input':open_movie_confirmation(receipt,selected_movie_entity_id)}
            validate_open_movie_confirmation(receipt,confirmation)
            write(self.root/job_id/'identity-confirmation.json',confirmation)
            now=self._epoch()
            with self.store.transaction() as db:
                db.execute("UPDATE jobs SET status='QUEUED',phase='capture',not_before=?,confirmation_json=? WHERE job_id=?",
                           (now,encoded(confirmation),job_id))
                db.execute("INSERT INTO queue(job_id,phase,eligible) VALUES(?,'capture',?)",(job_id,now))
                self.store.event(db,job_id,'QUEUED',{'explicit_movie_confirmation':True})
            if self.autostart:self._ensure_worker()
            self.condition.notify_all()
            return self.view(job_id)

    def _receipt(self,job):
        receipt=json.loads(job['receipt_json'])
        directory=Path(job['directory'])
        parent=directory.parent.parent
        names=('identity-verification.json',) if job['status']=='AWAITING_IDENTITY_CONFIRMATION' else ('verification.json',)
        if job['status']=='PARTIAL' and job['phase']=='identity-search':
            # Both historical stop paths are immutable: a returned partial used
            # the identity name; a recorded provider failure used the final name.
            # Resolve only this closed pair, refusing missing or ambiguous files.
            names=('identity-verification.json','verification.json')
        paths=[safe_directory_path(parent/name) for name in names]
        existing=[path for path in paths if path.exists()]
        need(len(existing)==1 and existing[0].is_file(),'Missing or ambiguous captured receipt.')
        path=existing[0]
        need(sha(path)==job['receipt_sha'] and read(path)==receipt
             and inventory(directory)==receipt['artifact_sha256'],'Captured evidence changed.')
        provenance=receipt['repeatable_contract'].get('provider_provenance')
        if provenance:
            job_root=self.root/job['job_id']
            need(sha(safe_directory_path(job_root/provenance['path']))==provenance['sha256'],
                 'Provider provenance summary changed.')
            for relative,digest in provenance['artifact_sha256'].items():
                need(sha(safe_directory_path(job_root/relative))==digest,'Provider provenance sidecar changed.')
        return receipt

    def receipt(self,job_id):
        job=self._job(job_id)
        need(job['status'] in ('COMPLETE','PARTIAL'),'No verified receipt available.')
        return self._receipt(job)

    def view(self,job_id):
        with self.lock:
            job=self._job(job_id);plan=job['plan'];protocol=plan['protocol_plan'];request=plan['request']
            provider_stats=self._stats(job_id)
            # Public DTOs always contain both providers and all counter fields.
            # Active work uses its current durable transport observations;
            # completed/failed evidence retains its committed counters even when
            # a preview-only reader has no scheduler attached.
            if job['status'] not in ACTIVE:
                persisted=json.loads(job['provider_stats'])
                for provider,counters in provider_stats.items():
                    saved=persisted.get(provider,{})
                    for field in counters:
                        value=saved.get(field)
                        if type(value) is int and value>=0:counters[field]=value
            queue=self.store.one('SELECT seq FROM queue WHERE job_id=?',(job_id,))
            position=None
            if queue:
                position=self.store.one('SELECT COUNT(*) AS n FROM queue WHERE seq<=?',(queue['seq'],))['n']
            value={'job_id':job_id,'status':job['status'],'created_utc':job['created'],
                'preferences':copy.deepcopy(request.get('preferences')),
                'model':request['model']['name'],'operator_mode':'groq','model_load_requests':0,'model_metadata_requests':0,
                'plan_sha256':plan['plan_sha256'],
                'maximum_qloo_requests':protocol['maximum_qloo_requests'],'maximum_model_decisions':protocol['maximum_model_decisions'],
                'case_protocol':protocol['protocol_version'],'declared_faults':len(protocol['faults']),
                'simulation_only':self.adapters is not None,'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED',
                'pacing_configured':True,'minimum_model_interval_seconds':self.interval,'error_class':job['error_class'],
                'saved_provider_samples':0,'saved_model_packets':0,'result':None,
                'admission_mode':'repeatable-v1','queue_status':job['status'] if job['status'] in ACTIVE else None,
                'queue_position':position,'not_before':timestamp(job['not_before']) if job['not_before'] else None,
                'provider_stats':provider_stats,'read_only':False,'legacy_case':False}
            if request['schema_version'] == 8:
                value.update(open_movie_discovery=True,movie_query=request['movie_query'],intent_text=request['intent_text'],
                             decision_scope='one-confirmed-film-one-candidate-pool-one-model-call')
            else:
                value.update(artists=copy.deepcopy(request['artists']),catalog_sha256=fingerprint(request['catalog']))
            if job['status'] in ('PLANNED','AWAITING_IDENTITY_CONFIRMATION') and not self.execution_source_compatible(plan):
                value.update(read_only=True,continuity_reason='EXECUTION_SOURCE_CHANGED',
                    continuity_notice='This retained plan belongs to an earlier execution source. Its evidence is readable; prepare a new plan to execute the current version.')
            if request['schema_version'] in (6,7):
                value['movie_queries']=copy.deepcopy(request['movie_queries'])
            if request['schema_version'] == 7:
                value.update(fast_pair_review=True,minimum_model_interval_seconds=0,decision_scope='one-shared-call-two-correlated-projections')
            if job['diagnostic']!='{}':value['request_diagnostic']=json.loads(job['diagnostic'])
            if job['directory'] and Path(job['directory']).is_dir():
                directory=Path(job['directory'])
                value['saved_provider_samples']=len(list(directory.glob('http-*.json')))
                value['saved_model_packets']=sum(len(list(directory.glob(pattern))) for pattern in (
                    'causal-execution-*.json','discovery-execution-*.json','pair-execution-*.json','open-movie-execution-*.json'))
                if job['status']=='WAITING_PROVIDER_CAPACITY' and (directory/'individual-report.json').is_file():
                    report=read(directory/'individual-report.json')
                    value['progress']={'verification_status':'PENDING','cultural_gate':'NOT_VALIDATED',
                        'provenance':'SIMULATION_ONLY' if report.get('source')=='test-double-only' else 'ORIGINAL_PROVIDER_OBSERVATIONS',
                        'successful_profiles':sorted(report.get('cinema_results',{})),
                        'cinema_results':copy.deepcopy(report.get('cinema_results',{}))}
            if job['status'] in ('COMPLETE','PARTIAL','AWAITING_IDENTITY_CONFIRMATION'):
                try:
                    receipt=self._receipt(job)
                    value['simulation_only']=receipt.get('provenance')=='SIMULATION_ONLY'
                    if job['status']=='AWAITING_IDENTITY_CONFIRMATION':
                        value['identity_receipt_sha256']=job['receipt_sha']
                        if request['schema_version'] == 8:
                            value.update(movie_candidates=copy.deepcopy(receipt['movie_candidates']),movie_query=receipt['movie_query'])
                        else:
                            value.update(identity_candidates=receipt['identity_candidates'],identity_queries=receipt['identity_queries'])
                        if request['schema_version'] in (6,7):
                            value['movie_candidates']=copy.deepcopy(receipt['movie_candidates'])
                    else:
                        fields=('verification_status','provenance','status','causal_gate','integration_gate','backend_comparability',
                          'behavioral_gate','cultural_gate','release_gate','verified_model_packets','verified_provider_samples',
                          'model_attempts','qloo_attempts','observed_recoveries_by_fault','summary','external_service_attested',
                          'error_class','preference_gate','cinema_results','chosen_identities','repeatable_contract',
                          'chosen_movie_inputs','movie_queries','movie_input_gate','shared_model_calls','correlated_projections',
                           'independent_model_decisions','decision_scope','open_movie_results','chosen_movie_input',
                           'movie_query','intent_text')
                        value['result']={k:copy.deepcopy(receipt[k]) for k in fields if k in receipt}
                        value.update(receipt_sha256=job['receipt_sha'],saved_provider_samples=receipt['verified_provider_samples'],
                                     saved_model_packets=receipt['verified_model_packets'])
                        if 'chosen_identities' in receipt:value['chosen_identities']=copy.deepcopy(receipt['chosen_identities'])
                        if 'chosen_movie_inputs' in receipt:value['chosen_movie_inputs']=copy.deepcopy(receipt['chosen_movie_inputs'])
                        if request['schema_version']==2 and receipt['verification_status']=='VERIFIED_COMPLETE':
                            value['result']['frames']=frames(Path(job['directory']),receipt)
                except (OSError,KeyError,ValueError,TypeError) as exc:
                    value.update(status='EVIDENCE_CHANGED',error_class='EvidenceIntegrityFailure',result=None)
                except Exception:
                    value.update(status='EVIDENCE_CHANGED',error_class='EvidenceIntegrityFailure',result=None)
            return value

    def health(self):
        return {'capture_active':self._active is not None,'queued':self.store.one('SELECT COUNT(*) AS n FROM queue')['n'],
                'execution_enabled':self.enabled and not self.closed and not self._admissions_blocked(),
                'admissions_blocked':self._admissions_blocked(),'paused_providers':self._paused_providers(),
                'admission_mode':'repeatable-v1'}

    def close(self):
        with self.condition:
            if self.closed:return
            self.closed=True;self.condition.notify_all();thread=self.worker
        if thread:thread.join()
        self.lease.__exit__(None,None,None)


def frames(directory,receipt):
    record=read(directory/f"causal-pair-individual-{receipt['run_id']}.json")
    names={r['entity_id']:r['name'] for r in record['catalog']}
    result=[]
    for case in record['cases']:
        repeats=[]
        for repeat in case['repeats']:
            victim=repeat['order'][1]
            repeats.append({'victim':victim,'before':[names[i] for i in repeat['before'][victim]['ranking'][:5]],
                'after':[names[i] for i in repeat['after'][victim]['ranking'][:5]],
                'healthy':[names[i] for i in record['healthy'][victim][0]['ranking'][:5]],
                'diagnosis':repeat['diagnosis'],'before_trace':repeat['before'][victim]['trace'],
                'after_trace':repeat['after'][victim]['trace']})
        result.append({'fault':case['fault'],'repeats':repeats})
    need(inventory(directory)==receipt['artifact_sha256'],'Evidence changed while preparing display.')
    return result

