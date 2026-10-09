"""Server-owned anonymous case access and cumulative budgets; no HTTP activation."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from pathlib import Path
import re
import secrets
from threading import RLock

from .evidence import fingerprint
from .errors import SchemaError
from .individual_capture import safe_directory_path, sha, validate_capture_paths
from .individual_jobs import IndividualJobManager, JOB_ID, need, read, write
from .public_demo import canonical_origin

TOKEN=re.compile(r'^[A-Za-z0-9_-]{43}$')
SHA=re.compile(r'^[a-f0-9]{64}$')
VIEW_FIELDS=('job_id','status','created_utc','artists','model','operator_mode','model_load_requests',
             'model_metadata_requests','plan_sha256','catalog_sha256','maximum_qloo_requests',
             'maximum_model_decisions','simulation_only','cultural_gate','release_gate','error_class',
             'saved_provider_samples','saved_model_packets','result','pacing_configured',
             'minimum_model_interval_seconds','receipt_sha256','case_protocol','declared_faults','preferences',
             'identity_candidates','identity_queries','identity_receipt_sha256','chosen_identities')
RESULT_FIELDS=('verification_status','provenance','status','causal_gate','integration_gate','backend_comparability','behavioral_gate','cultural_gate',
               'release_gate','verified_model_packets','verified_provider_samples','model_attempts',
               'qloo_attempts','observed_recoveries_by_fault','summary','external_service_attested','error_class','frames','preference_gate','cinema_results','chosen_identities')


def utc(value):
    need(isinstance(value,str),'Invalid session timestamp.')
    try:result=datetime.fromisoformat(value)
    except ValueError:
        need(False,'Invalid session timestamp.')
    need(result.tzinfo is not None and result.utcoffset()==timedelta(0),'Session timestamps must be UTC.')
    return result


def public_policy(*, maximum_sessions, maximum_plans, maximum_executions,
                  plans_per_session, executions_per_session, session_hours):
    values={'maximum_sessions':maximum_sessions,'maximum_plans':maximum_plans,
            'maximum_executions':maximum_executions,'plans_per_session':plans_per_session,
            'executions_per_session':executions_per_session,'session_hours':session_hours}
    need(all(type(value) is int for value in values.values()),'Public budgets must be explicit integers.')
    need(1<=maximum_sessions<=10000 and 1<=maximum_plans<=2000
         and 0<=maximum_executions<=min(maximum_plans,1000)
         and 1<=plans_per_session<=maximum_plans
         and 0<=executions_per_session<=min(plans_per_session,maximum_executions)
         and 1<=session_hours<=168,'Public budget bounds differ.')
    return {'schema_version':1,**values,'concurrent_captures':1,
            'maximum_qloo_calls_per_capture':4,'maximum_model_attempts_per_capture':39,
            'budget_period':'cumulative-for-this-owner-selected-storage',
            'failed_or_abandoned_admissions_refunded':False,'automatic_retry_or_resume':False,
            'session_is_a_verified_person':False,'provider_quota_or_cost_reserved':False}


class PublicCaseManager:
    """One shared operator; never instantiate an operator per anonymous visitor."""
    def __init__(self,root,template,*,origin,policy,minimum_model_interval_seconds,
                 execution_enabled=False,settings_loader=None,remote_key_loader=None,
                 _test_adapters=None,_test_now=None):
        need(isinstance(policy,dict),'A closed, explicit public admission policy is required.')
        expected=public_policy(**{key:policy[key] for key in (
            'maximum_sessions','maximum_plans','maximum_executions','plans_per_session',
            'executions_per_session','session_hours')})
        need(fingerprint(policy)==fingerprint(expected),'Public admission policy differs.')
        need(type(execution_enabled) is bool,'Execution must be enabled explicitly.')
        need(_test_now is None or _test_adapters is not None,'A simulated clock requires simulated providers.')
        self.root=safe_directory_path(Path(root))
        validate_capture_paths(self.root/'jobs'/('20000101T000000Z-'+'0'*8)/'capture')
        self.origin=canonical_origin(origin)
        self.policy=copy.deepcopy(expected)
        self._clock=_test_now or (lambda:datetime.now(timezone.utc))
        self.lock=RLock()
        self._mutations_blocked=False
        self.sessions=self.root/'sessions';self.owners=self.root/'ownership'
        from .individual_remote_capture import validate_request
        from .remote_pacing import pacing_policy
        self.template=validate_request(template)
        cadence=pacing_policy(minimum_model_interval_seconds)
        need(cadence['configured'],'Public case cadence must be selected before configuration.')
        binding={'schema_version':1,'policy':self.policy,'origin':self.origin,
                 'template_sha256':fingerprint(self.template),'execution_pacing':cadence,
                 'controller_sha256':sha(Path(__file__)),
                 'manager_sha256':sha(Path(__file__).with_name('individual_jobs.py'))}
        binding['policy_sha256']=fingerprint(binding)
        self.binding=binding
        self._binding_hash=fingerprint(binding)
        self.root.mkdir(mode=0o700,parents=False,exist_ok=True)
        for directory in (self.sessions,self.owners):
            safe_directory_path(directory);directory.mkdir(mode=0o700,exist_ok=True)
        path=self.root/'public-policy.json'
        self._continuation_applied = False
        if path.exists():
            previous = read(path)
            if fingerprint(previous) != self._binding_hash:
                from .public_policy_continuation import MARKER, validate_continuation
                need((self.root/MARKER).is_file(), 'Public source seal changed; review and explicitly continue stopped storage without resetting budgets.')
                validate_continuation(previous, binding, read(self.root/MARKER))
                self.binding = previous
                self._binding_hash = fingerprint(previous)
                self._continuation_applied = True
        else:
            need(not (self.root/'jobs').exists() and not list(self.sessions.iterdir())
                 and not list(self.owners.iterdir()),'Storage predates its public policy; retain and inspect it.')
            write(path,binding)
        self.manager=IndividualJobManager(self.root/'jobs',self.template,operator='groq',
            execution_enabled=execution_enabled,settings_loader=settings_loader,remote_key_loader=remote_key_loader,
            remote_minimum_interval_seconds=cadence['minimum_interval_seconds'],_test_adapters=_test_adapters,
            maximum_plans=self.policy['maximum_plans'],maximum_executions=self.policy['maximum_executions'])
        try:self._restore_access()
        except BaseException:
            self.manager.close()
            raise

    def close(self):self.manager.close()

    def _now(self):
        result=self._clock()
        need(isinstance(result,datetime) and result.tzinfo is not None and result.utcoffset()==timedelta(0),
             'Public session clock must be UTC.')
        return result

    def _bound(self):
        need(not self.manager.closed,'The public case service is closed.')
        if self._continuation_applied:
            from .public_policy_continuation import MARKER, validate_continuation
            current = {**self.binding, 'controller_sha256':sha(Path(__file__)),
                       'manager_sha256':sha(Path(__file__).with_name('individual_jobs.py'))}
            current['policy_sha256'] = fingerprint({k:v for k,v in current.items() if k != 'policy_sha256'})
            validate_continuation(self.binding, current, read(self.root/MARKER))
        need(fingerprint(read(self.root/'public-policy.json'))==self._binding_hash
             and fingerprint(self.binding)==self._binding_hash
             and fingerprint(self.binding['policy'])==fingerprint(self.policy),'Public policy changed during service.')

    def _session_record(self,key):
        record=read(self.sessions/(key+'.json'))
        need(set(record)=={'schema_version','session_sha256','created_utc','expires_utc','policy_sha256'}
             and type(record['schema_version']) is int and record['schema_version']==1
             and record['session_sha256']==key and record['policy_sha256']==self.binding['policy_sha256'],
             'Public session binding differs.')
        need(utc(record['expires_utc'])-utc(record['created_utc'])==timedelta(hours=self.policy['session_hours']),
             'Session duration differs from the sealed policy.')
        return record

    def _restore_access(self):
        self._bound()
        entries=list(self.root.iterdir())
        need({path.name for path in entries}==({'public-policy.json','sessions','ownership','jobs'} | ({'public-policy-continuation.json'} if self._continuation_applied else set())),
             'Unknown public storage entry; retain and inspect it.')
        sessions=list(self.sessions.iterdir())
        need(len(sessions)<=self.policy['maximum_sessions'],'Public session storage exceeds its bound.')
        self.session_keys=set()
        for path in sessions:
            need(path.suffix=='.json' and SHA.fullmatch(path.stem),'Invalid session entry.')
            self._session_record(path.stem);self.session_keys.add(path.stem)
        self.job_owners={}
        for path in self.owners.iterdir():
            need(path.suffix=='.json' and JOB_ID.fullmatch(path.stem),'Invalid ownership entry.')
            owner=read(path)
            need(set(owner)=={'schema_version','job_id','session_sha256','policy_sha256'}
                 and type(owner['schema_version']) is int and owner['schema_version']==1
                 and owner['job_id']==path.stem and owner['session_sha256'] in self.session_keys
                 and owner['policy_sha256']==self.binding['policy_sha256'],'Invalid case ownership binding.')
            self.job_owners[path.stem]=owner['session_sha256']
        need(set(self.job_owners)==set(self.manager.jobs),'An orphaned plan or ownership record requires owner inspection.')
        for key in self.session_keys:
            jobs=self._jobs(key)
            need(len(jobs)<=self.policy['plans_per_session']
                 and sum(job['sequence']>0 for job in jobs)<=self.policy['executions_per_session'],
                 'Persisted per-session budgets differ.')

    def _jobs(self,key):return [self.manager.jobs[job] for job,owner in self.job_owners.items() if owner==key]

    def _can_mutate(self):
        self._bound()
        with self.manager.lock:
            if (set(self.manager.jobs)!=set(self.job_owners)
                    or {path.name for path in self.sessions.iterdir()}!={key+'.json' for key in self.session_keys}
                    or any(not self._transition_matches_memory(job_id) for job_id in self.manager.jobs)):
                self._mutations_blocked=True
        need(not self._mutations_blocked,
             'Public admissions are blocked after a partial storage failure; retain all records for owner inspection.')

    def _transition_matches_memory(self,job_id):
        # A failed flush can leave a consumed event on disk while the in-memory
        # count still says PLANNED. Never admit further work on that uncertainty.
        try:
            job=self.manager.jobs[job_id]
            events=sorted((self.manager.root/job_id).glob('event-*.json'))
            if [path.name for path in events]!=[f'event-{i:04d}.json' for i in range(1,job['sequence']+1)]:return False
            if not events:return job['status']=='PLANNED'
            event=read(events[-1])
            return event['status']==job['status'] and event['sequence']==job['sequence']
        except (SchemaError,OSError,KeyError,TypeError,ValueError):return False

    def _identity(self,token):
        self._bound()
        if not isinstance(token,str) or not TOKEN.fullmatch(token):raise FileNotFoundError('Case access unavailable.')
        key=hashlib.sha256(token.encode('ascii')).hexdigest()
        if key not in self.session_keys:raise FileNotFoundError('Case access unavailable.')
        record=self._session_record(key)
        if not utc(record['created_utc'])<=self._now()<utc(record['expires_utc']):
            raise FileNotFoundError('Case access unavailable.')
        return key

    def session(self,token=None):
        with self.lock:
            self._bound()
            if token is not None:
                key=self._identity(token)
            else:
                self._can_mutate()
                need(len(self.session_keys)<self.policy['maximum_sessions'],'Public session capacity reached; retained sessions are not automatically cleared.')
                token=secrets.token_urlsafe(32)
                need(TOKEN.fullmatch(token),'Unexpected session token format.')
                key=hashlib.sha256(token.encode('ascii')).hexdigest()
                now=self._now()
                try:
                    write(self.sessions/(key+'.json'),{'schema_version':1,'session_sha256':key,
                          'created_utc':now.isoformat(),'expires_utc':(now+timedelta(hours=self.policy['session_hours'])).isoformat(),
                          'policy_sha256':self.binding['policy_sha256']})
                    self.session_keys.add(key)
                except BaseException:
                    self._mutations_blocked=True
                    raise
            csrf=hmac.new(token.encode('ascii'),b'affinityqa-public-case-csrf-v1',hashlib.sha256).hexdigest()
            return token,{'schema_version':1,'csrf_token':csrf,'expires_utc':self._session_record(key)['expires_utc']}

    def authorize_mutation(self,token,csrf):
        with self.lock:
            self._identity(token)
            self._can_mutate()
            expected=hmac.new(token.encode('ascii'),b'affinityqa-public-case-csrf-v1',hashlib.sha256).hexdigest()
            need(isinstance(csrf,str) and SHA.fullmatch(csrf) and hmac.compare_digest(csrf,expected),'Session mutation token differs.')

    def _owned(self,key,job_id):
        if not isinstance(job_id,str) or not JOB_ID.fullmatch(job_id) or self.job_owners.get(job_id)!=key:
            raise FileNotFoundError('Case access unavailable.')
        record=read(self.owners/(job_id+'.json'))
        need(record=={'schema_version':1,'job_id':job_id,'session_sha256':key,
                     'policy_sha256':self.binding['policy_sha256']},'Case ownership changed.')

    def capabilities(self,token):
        with self.lock:
            key=self._identity(token);own=self._jobs(key);cap=self.manager.capabilities()
            for job in own:self._owned(key,job['job_id'])
            return {'schema_version':1,'configured':True,'execution_enabled':cap['execution_enabled'] and not self._mutations_blocked,
                'admissions_blocked':self._mutations_blocked,
                'simulation_only':cap['simulation_only'],'operator_mode':'groq','provider':'groq','model':cap['model'],
                'default_artists':copy.deepcopy(cap['default_artists']),'catalog':copy.deepcopy(cap['catalog']),
                'cinema_preferences_supported':cap['cinema_preferences_supported'],
                'cinema_identity_confirmation_supported':cap['cinema_identity_confirmation_supported'],
                'cinema_discoveries_supported':cap['cinema_discoveries_supported'],
                'minimum_model_interval_seconds':self.binding['execution_pacing']['minimum_interval_seconds'],
                'remaining_plans':min(cap['remaining_plans'],self.policy['plans_per_session']-len(own)),
                'remaining_executions':min(cap['remaining_executions'],self.policy['executions_per_session']-sum(j['sequence']>0 for j in own)),
                'jobs':[{'job_id':job['job_id'],'status':job['status'],'artists':copy.deepcopy(job['plan']['request']['artists'])} for job in own],
                'session_is_verified_person':False,'provider_quota_or_cost_reserved':False,
                'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED'}

    def prepare(self,token,artists,preferences=None,confirm_identities=False,discover_new_movies=False):
        with self.lock:
            key=self._identity(token)
            self._can_mutate()
            need(len(self._jobs(key))<self.policy['plans_per_session'],'This session has used its plan admissions.')
            need(self.manager.capabilities()['remaining_plans']>0,'Public plan capacity reached.')
            request=self.manager.request_for(artists,preferences,confirm_identities,discover_new_movies)
            try:
                job=self.manager.prepare(request['artists'],**({'preferences':request['preferences']} if 'preferences' in request else {}),
                    **({'confirm_identities':True} if confirm_identities else {}),
                    **({'discover_new_movies':True} if discover_new_movies else {}))
                write(self.owners/(job['job_id']+'.json'),{'schema_version':1,'job_id':job['job_id'],
                      'session_sha256':key,'policy_sha256':self.binding['policy_sha256']})
                self.job_owners[job['job_id']]=key
            except BaseException:
                self._mutations_blocked=True
                raise
            return self.view(token,job['job_id'])

    def start(self,token,job_id,plan_hash):
        with self.lock:
            key=self._identity(token);self._owned(key,job_id)
            self._can_mutate()
            need(sum(j['sequence']>0 for j in self._jobs(key))<self.policy['executions_per_session'],
                 'This session has used its execution admissions.')
            try:self.manager.start(job_id,plan_hash)
            except BaseException:
                if not self._transition_matches_memory(job_id):self._mutations_blocked=True
                raise
            return self.view(token,job_id)

    def view(self,token,job_id):
        with self.lock:
            key=self._identity(token);self._owned(key,job_id)
            view=self.manager.view(job_id)
            result={name:copy.deepcopy(view[name]) for name in VIEW_FIELDS if name in view}
            if result.get('result') is not None:
                result['result']={name:copy.deepcopy(view['result'][name]) for name in RESULT_FIELDS if name in view['result']}
            return result

    def confirm_identities(self,token,job_id,plan_hash,identity_receipt_hash,selected_entity_ids):
        with self.lock:
            key=self._identity(token);self._owned(key,job_id)
            self._can_mutate()
            # The lookup already consumed this session's one execution admission.
            try:self.manager.confirm_identities(job_id,plan_hash,identity_receipt_hash,selected_entity_ids)
            except BaseException:
                path=self.manager.root/job_id/'identity-confirmation.json'
                if (path.exists() and self.manager.jobs[job_id]['status']=='AWAITING_IDENTITY_CONFIRMATION') or not self._transition_matches_memory(job_id):
                    self._mutations_blocked=True
                raise
            return self.view(token,job_id)

    def verification(self,token,job_id):
        view=self.view(token,job_id)
        need(view['status'] in ('COMPLETE','PARTIAL') and view.get('receipt_sha256'),
             'No verified public receipt is available.')
        return {'schema_version':1,'job_id':job_id,'plan_sha256':view['plan_sha256'],
                'receipt_sha256':view['receipt_sha256'],'result':copy.deepcopy(view['result']),
                'notice':'Selected case summary; private inventory and provider envelopes are excluded. Local integrity is not external or cultural attestation.'}
