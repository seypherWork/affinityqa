"""Bounded owner-configured jobs. No execution on preview, refresh or restart."""
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from threading import RLock, Thread
from uuid import uuid4

from .agents import strict_json
from .errors import SchemaError
from .evidence import fingerprint, utc_now
from .individual_capture import (execute_capture, execution_lease, prepare_plan,
                                 safe_directory_path, sha, validate_request, validate_capture_paths)
from .individual_verify import inventory, verify_individual, write_receipt

JOB_ID = re.compile(r'^\d{8}T\d{6}Z-[a-f0-9]{8}$')
ACTIVE = {'STARTED', 'VERIFYING'}
TRANSITIONS = {'PLANNED': {'STARTED'}, 'STARTED': {'VERIFYING', 'FAILED', 'ABANDONED'},
               'VERIFYING': {'COMPLETE', 'PARTIAL', 'FAILED', 'ABANDONED'}}


def need(condition, message):
    if not condition:
        raise SchemaError(message)


def read(path):
    safe_directory_path(path)
    need(path.is_file() and path.stat().st_size <= 2_000_000, 'Invalid local job record.')
    return strict_json(path.read_bytes())


def write(path, value):
    safe_directory_path(path)
    data = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    need(path.read_bytes() == data, 'Local job record was not saved completely; inspect before continuing.')


class IndividualJobManager:
    """Server-owned catalog/model, client supplies only two canonical interests."""
    def __init__(self, root, template, url=None, *, execution_enabled=False,
                 settings_loader=None, _test_adapters=None, operator='local', remote_key_loader=None,
                 remote_minimum_interval_seconds=None, maximum_plans=20, maximum_executions=3):
        need(type(maximum_plans) is int and 1<=maximum_plans<=2000
             and type(maximum_executions) is int and 0<=maximum_executions<=min(maximum_plans,1000),
             'Explicit job budgets must be bounded integers.')
        self.maximum_plans,self.maximum_executions=maximum_plans,maximum_executions
        self._sealed_limits=(maximum_plans,maximum_executions)
        need(operator in ('local', 'groq'), 'Use an explicitly reviewed individual operator.')
        self.operator = operator
        self.remote_minimum_interval_seconds=remote_minimum_interval_seconds
        if operator == 'groq':
            from .individual_remote_capture import prepare_plan as remote_plan, validate_request as remote_request
            from .individual_remote_verify import verify_individual_remote
            need(url is None, 'The remote operator does not accept an Ollama URL.')
            self._validate_request = remote_request
            from .remote_pacing import pacing_policy
            pacing_policy(remote_minimum_interval_seconds)
            need(execution_enabled is not True or _test_adapters is not None or remote_minimum_interval_seconds is not None,
                 'Real remote execution requires an explicitly reviewed model interval.')
            self._prepare_plan = lambda request, output: remote_plan(request, output,
                minimum_model_interval_seconds=self.remote_minimum_interval_seconds)
            self._verify = verify_individual_remote
        else:
            need(remote_minimum_interval_seconds is None,'Local execution does not accept remote pacing configuration.')
            self._validate_request = validate_request
            self._prepare_plan = lambda request, output: prepare_plan(request, output, self.url)
            self._verify = verify_individual
        self.root = safe_directory_path(Path(root))
        validate_capture_paths(self.root/('20000101T000000Z-'+'0'*8)/'capture')
        self.template = self._validate_request(template)
        self.url = url
        self.enabled = execution_enabled is True
        need(not self.enabled or callable(settings_loader), 'An explicit local credential loader is required.')
        need(operator != 'groq' or not self.enabled or callable(remote_key_loader), 'An explicit private remote credential loader is required.')
        self.settings_loader = settings_loader
        self.remote_key_loader = remote_key_loader
        self.adapters = _test_adapters
        self.lock, self.jobs, self.worker = RLock(), {}, None
        self.closed = False
        self.root.mkdir(mode=0o700, parents=False, exist_ok=True)
        self._prepare_plan(self.template, self.root/'preflight-not-created')
        # This lease serializes panel managers using this storage root, not unrelated GPU clients.
        self.lease = execution_lease(self.root)
        self.lease.__enter__()
        try:
            self._restore()
        except BaseException:
            self.lease.__exit__(None, None, None)
            raise

    def close(self):
        # Do not release the process lease while an already admitted capture is still running.
        with self.lock:
            if self.closed:
                return
            self.closed = True
            thread = self.worker
        if thread:
            thread.join()
        with self.lock:
            self.lease.__exit__(None, None, None)

    def _restore(self):
        dirs = sorted(p for p in self.root.iterdir() if p.name != '.affinityqa-individual.lock')
        need(len(dirs) <= self.maximum_plans, 'Local plan storage exceeds its declared bound.')
        for path in dirs:
            safe_directory_path(path)
            need(path.is_dir() and JOB_ID.fullmatch(path.name), 'Unknown local job entry; retain and inspect it.')
            envelope = read(path/'job-plan.json')
            need(isinstance(envelope, dict) and set(envelope) == {'job_id', 'created_utc', 'manager_sha256', 'plan'},
                 'Invalid persisted plan envelope.')
            plan = envelope['plan']
            need(envelope['job_id'] == path.name and isinstance(plan, dict)
                 and plan.get('plan_sha256') == fingerprint({k:v for k,v in plan.items() if k != 'plan_sha256'})
                 and plan.get('output_directory') == str(path/'capture'), 'Persisted plan binding differs.')
            self._validate_request(plan['request'])
            status, sequence, receipt_hash, error = 'PLANNED', 0, None, None
            entries = sorted(path.glob('event-*.json'))
            need(len(entries) <= 8, 'Too many local job transitions.')
            for item in entries:
                sequence += 1
                event = read(item)
                need(item.name == f'event-{sequence:04d}.json' and isinstance(event, dict)
                     and set(event) == {'sequence','job_id','utc','status','error_class','receipt_sha256'}
                     and type(event['sequence']) is int and event['sequence'] == sequence
                     and event['job_id'] == path.name and event['status'] in TRANSITIONS.get(status, set()),
                     'Invalid local transition history; no automatic resumption.')
                status, receipt_hash, error = event['status'], event['receipt_sha256'], event['error_class']
            self.jobs[path.name] = {**envelope, 'status':status, 'sequence':sequence,
                                    'receipt_sha256':receipt_hash, 'error_class':error}
            if status in ACTIVE:
                self._event(path.name, 'ABANDONED', error='ServerRestart')
        need(sum(j['sequence']>0 for j in self.jobs.values())<=self.maximum_executions,
             'Persisted admissions exceed the configured execution budget.')

    def _check_limits(self):
        need((self.maximum_plans,self.maximum_executions)==self._sealed_limits
             and type(self.maximum_plans) is int and type(self.maximum_executions) is int,
             'The configured job budgets changed; retain storage and review before restart.')

    def capabilities(self):
        with self.lock:
            self._check_limits()
            return {'configured':True, 'execution_enabled':self.enabled and not self.closed,
                'simulation_only':self.adapters is not None, 'default_artists':self.template['artists'],
                'operator_mode':self.operator, 'provider':'groq' if self.operator=='groq' else 'ollama-local',
                'model':self.template['model']['name'], 'catalog':self.template['catalog'],
                'catalog_sha256':fingerprint(self.template['catalog']),
                'maximum_qloo_requests':4, 'maximum_model_decisions':39,
                'maximum_plans':self.maximum_plans, 'remaining_plans':self.maximum_plans-len(self.jobs),
                'remaining_executions':self.maximum_executions-sum(j['sequence']>0 for j in self.jobs.values()),
                'jobs':[{'job_id':k,'status':v['status'],'artists':v['plan']['request']['artists']} for k,v in self.jobs.items()],
                'cultural_gate':'NOT_VALIDATED', 'release_gate':'BLOCKED'}

    def prepare(self, artists):
        with self.lock:
            self._check_limits()
            need(not self.closed, 'The local manager is closed.')
            need(len(self.jobs) < self.maximum_plans, 'This local storage has reached its plan limit; retain it and review the owner-selected budget.')
            request = {**copy.deepcopy(self.template), 'artists':artists}
            self._validate_request(request)
            job_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]
            path = self.root/job_id
            # Parent for the actual output exists only after a validated, deliberately prepared plan.
            path.mkdir(mode=0o700)
            plan = self._prepare_plan(request, path/'capture')
            envelope = {'job_id':job_id,'created_utc':utc_now(), 'manager_sha256':sha(Path(__file__)), 'plan':plan}
            write(path/'job-plan.json', envelope)
            self.jobs[job_id] = {**envelope, 'status':'PLANNED', 'sequence':0,
                                 'receipt_sha256':None, 'error_class':None}
            return self.view(job_id)

    def _job(self, job_id):
        need(isinstance(job_id, str) and JOB_ID.fullmatch(job_id), 'Invalid local job identifier.')
        if job_id not in self.jobs:
            raise FileNotFoundError(job_id)
        return self.jobs[job_id]

    def _event(self, job_id, status, *, error=None, receipt_hash=None):
        job = self._job(job_id)
        need(status in TRANSITIONS.get(job['status'], set()), 'This job transition is not permitted.')
        sequence = job['sequence']+1
        event = {'sequence':sequence,'job_id':job_id,'utc':utc_now(),'status':status,
                 'error_class':error,'receipt_sha256':receipt_hash}
        write(self.root/job_id/f'event-{sequence:04d}.json', event)
        job.update(status=status, sequence=sequence, receipt_sha256=receipt_hash, error_class=error)

    def start(self, job_id, plan_hash):
        with self.lock:
            self._check_limits()
            job = self._job(job_id)
            need(self.enabled and not self.closed, 'New local execution is disabled. Preview and existing evidence remain available.')
            need(job['status'] == 'PLANNED', 'A job is single use; partial or restarted work is never retried automatically.')
            need(not (self.worker and self.worker.is_alive()), 'Another local capture is active.')
            need(sum(j['sequence']>0 for j in self.jobs.values()) < self.maximum_executions,
                 'This local storage has used its configured execution admissions.')
            plan = job['plan']
            need(plan_hash == plan['plan_sha256'] and job['manager_sha256'] == sha(Path(__file__)), 'The reviewed plan or manager changed.')
            need(read(self.root/job_id/'job-plan.json') == {k:job[k] for k in ('job_id','created_utc','manager_sha256','plan')},
                 'The saved plan changed; retain and inspect it.')
            now = self._prepare_plan(plan['request'], self.root/job_id/'capture')
            need(now['plan_sha256'] == plan_hash, 'Request, model, dependency or capture source changed before admission.')
            # Credential loading is delayed until explicit admission, never echoed or stored in jobs.
            settings = self.settings_loader()
            from .evidence import redact
            need(isinstance(settings.api_key,str) and bool(settings.api_key.strip())
                 and redact(plan['request'], (settings.api_key,)) == plan['request'], 'Local credential configuration or capture inputs are invalid.')
            remote_key = None
            if self.operator == 'groq':
                from .groq_agent import contains_secret
                remote_key = self.remote_key_loader()
                need(isinstance(remote_key,str) and re.fullmatch(r'[!-~]{20,512}',remote_key)
                     and not contains_secret(plan,(settings.api_key,remote_key)), 'Private remote configuration or capture inputs are invalid.')
            self._event(job_id, 'STARTED')
            self.worker = Thread(target=self._run, args=(job_id, settings, remote_key), daemon=False, name='affinityqa-individual')
            try:
                self.worker.start()
            except BaseException as exc:
                self._event(job_id, 'FAILED', error=type(exc).__name__)
                self.worker = None
                raise
            return self.view(job_id)

    def _capture_dir(self, job_id):
        parent = safe_directory_path(self.root/job_id/'capture')
        if not parent.is_dir():
            return None
        dirs = [p for p in parent.iterdir() if p.is_dir()]
        if not dirs and self.jobs[job_id]['status'] in ACTIVE:
            return None
        need(len(dirs) == 1 and JOB_ID.fullmatch(dirs[0].name), 'Unrecognized capture directory.')
        return safe_directory_path(dirs[0])

    def _run(self, job_id, settings, remote_key=None):
        try:
            plan = self.jobs[job_id]['plan']
            if self.operator == 'groq':
                from .individual_remote_capture import execute_capture as remote_capture
                remote_capture(plan['request'], self.root/job_id/'capture', plan['plan_sha256'],
                               settings, remote_key, _test_adapters=self.adapters,
                               minimum_model_interval_seconds=plan['execution_pacing']['minimum_interval_seconds'])
            else:
                execute_capture(plan['request'], self.root/job_id/'capture', self.url,
                                plan['plan_sha256'], settings, _test_adapters=self.adapters)
            with self.lock:
                self._event(job_id, 'VERIFYING')
            directory = self._capture_dir(job_id)
            receipt = self._verify(directory)
            destination = self.root/job_id/'verification.json'
            write_receipt(receipt, destination, directory)
            with self.lock:
                self._event(job_id, 'COMPLETE' if receipt['verification_status']=='VERIFIED_COMPLETE' else 'PARTIAL',
                            receipt_hash=sha(destination), error=receipt['error_class'])
        except BaseException as exc:
            with self.lock:
                self._event(job_id, 'FAILED', error=type(exc).__name__)

    def receipt(self, job_id):
        with self.lock:
            job = self._job(job_id)
            need(job['status'] in {'COMPLETE','PARTIAL'}, 'No verified receipt is available for this job.')
            path = self.root/job_id/'verification.json'
            need(sha(path) == job['receipt_sha256'], 'The verification receipt changed; no result is admitted.')
            result = read(path)
            need(inventory(self._capture_dir(job_id)) == result['artifact_sha256'], 'Captured evidence changed after verification; no result is admitted.')
            return result

    def view(self, job_id):
        with self.lock:
            job = self._job(job_id)
            plan = job['plan']
            result = {'job_id':job_id,'status':job['status'],'created_utc':job['created_utc'],
                'artists':plan['request']['artists'],'model':plan['request']['model']['name'],
                'operator_mode':self.operator, 'model_load_requests':plan['model_load_requests'],
                'model_metadata_requests':plan['new_model_metadata_requests'],
                'plan_sha256':plan['plan_sha256'],'catalog_sha256':fingerprint(plan['request']['catalog']),
                'maximum_qloo_requests':4,'maximum_model_decisions':39,'simulation_only':self.adapters is not None,
                'cultural_gate':'NOT_VALIDATED','release_gate':'BLOCKED','error_class':job['error_class'],
                'saved_provider_samples':0,'saved_model_packets':0, 'result':None}
            if self.operator=='groq':
                result['pacing_configured']=plan['execution_pacing']['configured']
                result['minimum_model_interval_seconds']=plan['execution_pacing']['minimum_interval_seconds']
            directory = self._capture_dir(job_id)
            if directory:
                # Saved-file progress is deliberately distinct from actual attempted requests.
                ledger = directory/'ledger.jsonl'
                events = []
                if ledger.is_file() and ledger.stat().st_size <= 2_000_000:
                    raw = ledger.read_bytes()
                    for line in raw.splitlines(keepends=True):
                        if not line.endswith(b'\n'):
                            break
                        try:
                            event = strict_json(line)
                            if not isinstance(event, dict):
                                break
                            events.append(event)
                        except (SchemaError,ValueError,UnicodeError):
                            break
                result.update(saved_provider_samples=min(4,sum(e.get('kind')=='tool_call' for e in events)),
                              saved_model_packets=min(39,sum(e.get('kind')=='observed_model_execution' for e in events)))
            if job['status'] in {'COMPLETE','PARTIAL'}:
                try:
                    receipt = self.receipt(job_id)
                    fields = ('verification_status','provenance','status','causal_gate','behavioral_gate','cultural_gate',
                              'release_gate','verified_model_packets','verified_provider_samples','model_attempts','qloo_attempts',
                              'observed_recoveries_by_fault','summary','external_service_attested','error_class')
                    result['result'] = {k:receipt[k] for k in fields if k in receipt}
                    if receipt['verification_status']=='VERIFIED_COMPLETE':
                        record = read(directory/f"causal-pair-individual-{receipt['run_id']}.json")
                        names = {r['entity_id']:r['name'] for r in record['catalog']}
                        frames = []
                        for case in record['cases']:
                            repeats = []
                            for repeat in case['repeats']:
                                victim = repeat['order'][1]
                                repeats.append({'victim':victim,
                                    'before':[names[i] for i in repeat['before'][victim]['ranking'][:5]],
                                    'after':[names[i] for i in repeat['after'][victim]['ranking'][:5]],
                                    'healthy':[names[i] for i in record['healthy'][victim][0]['ranking'][:5]],
                                    'diagnosis':repeat['diagnosis'],
                                    'before_trace':repeat['before'][victim]['trace'],
                                    'after_trace':repeat['after'][victim]['trace']})
                            frames.append({'fault':case['fault'],'repeats':repeats})
                        need(inventory(directory)==receipt['artifact_sha256'], 'Evidence changed while preparing the display.')
                        result['result']['frames'] = frames
                    result['simulation_only'] = receipt['provenance']=='SIMULATION_ONLY'
                    result['error_class'] = receipt['error_class']
                    result['receipt_sha256'] = job['receipt_sha256']
                except (SchemaError,OSError,KeyError,TypeError):
                    result.update(status='EVIDENCE_CHANGED', error_class='EvidenceIntegrityFailure', result=None)
                    result.pop('receipt_sha256',None)
            return result
