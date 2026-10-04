"""Allowlisted local incident jobs; no provider calls or arbitrary execution.

The case is already exposed. This cannot consume the untouched reserved set.
One thread executes at a time, at most two saved nine-decision runs across restarts.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from statistics import median
from threading import RLock, Thread

from .errors import SchemaError
from .evidence import Ledger, fingerprint
from .metrics import ndcg_at_k, max_repeat_jitter
from .movie_incident import CachedMovieAgent
from .ollama_agent import OllamaMovieAgent, local_ollama_url
from .regression_pack import export_pack, evaluate_pack


class LiveJobManager:
    def __init__(self, root: Path, ollama_url: str, *, engine_factory=None, out=None):
        self.root=root;self.url=local_ollama_url(ollama_url)
        self.out=out or root/'runs/live-jobs'
        self.engine_factory=engine_factory or (lambda:OllamaMovieAgent(self.url,'qwen38:cyber-32k',timeout=45,max_calls=9))
        self.lock=RLock();self.jobs={};self.created=0;self.latest=None
        self.recovery_error=None
        try:self._restore()
        except (OSError,ValueError,KeyError,TypeError,SchemaError):
            self.recovery_error='Saved local evidence could not be verified. New execution is blocked; original files are preserved.'

    def _read_saved(self,directory,name,sha):
        from .store import RUN_ID
        if (not RUN_ID.fullmatch(directory.name) or directory.is_symlink() or Path(name).name!=name
                or directory.resolve().parent!=self.out.resolve()):
            raise SchemaError('Unsafe saved job location.')
        path=directory/name
        if path.is_symlink() or path.stat().st_size>4_000_000:raise SchemaError('Unsafe saved job artifact.')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=sha:raise SchemaError('Saved job evidence changed.')
        return json.loads(data) if name.endswith('.json') else None

    def _restore(self):
        if not self.out.exists():return
        for directory in sorted(self.out.iterdir()):
            if not directory.is_dir():continue
            path=directory/'job-snapshot.json'
            if not path.exists():continue
            if path.is_symlink() or path.stat().st_size>500_000:raise SchemaError('Unsafe saved job snapshot.')
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved.get('snapshot_sha256')!=fingerprint({k:v for k,v in saved.items() if k!='snapshot_sha256'}):
                raise SchemaError('Saved job snapshot changed.')
            for name,sha in saved['artifact_sha256'].items():self._read_saved(directory,name,sha)
            job=saved['job']
            if job['id']!=directory.name or job['ci_gate']!='NOT_VALIDATED':raise SchemaError('Invalid saved job identity.')
            if job['status'] not in ('COMPLETE','FAILED'):
                job.update(status='FAILED',phase='Interrupted by server restart',
                           error='The previous execution was interrupted. Partial evidence is preserved; no inference was resumed.')
            job['recovered_from_disk']=True
            self.jobs[job['id']]=job
        # Migrate the earlier completed demonstration in memory only; its files
        # remain exactly as captured, verified against the original receipt.
        receipt=self.root/'evidence/AUDIT-BUILD-PHASE5-20261003.json'
        if self.out.resolve()==(self.root/'runs/live-jobs').resolve() and receipt.exists():
            old=json.loads(receipt.read_text(encoding='utf-8'))['live_test']
            if old['run_id'] not in self.jobs:
                directory=self.out/old['run_id']
                values={name:self._read_saved(directory,name,sha) for name,sha in old['run_artifact_sha256'].items()}
                pack=values['regression-pack.json']
                job={'id':old['run_id'],'status':'COMPLETE','phase':'Verified completed execution recovered',
                     'calls':old['actual_model_decisions'],'call_cap':9,'new_qloo_requests':0,
                     'ci_gate':'NOT_VALIDATED','error':None,'fault_declared':True,
                     'profiles':pack['cases'][0]['artists'],'result':values['job-result.json'],
                     'recovered_from_disk':True,'_pack':pack}
                job['before']=self._projection(job,values['before-decisions.json'])
                self.jobs[job['id']]=job
        self.created=len(self.jobs)
        self.latest=max(self.jobs,default=None)

    def _persist(self,job):
        ledger=job.get('_ledger')
        if ledger is None:return
        saved={'schema_version':1,'job':{k:v for k,v in job.items() if not k.startswith('_')},
               'artifact_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in ledger.directory.iterdir() if p.is_file() and p.name not in ('job-snapshot.json','job-snapshot.tmp')}}
        saved['snapshot_sha256']=fingerprint(saved)
        path=ledger.directory/'job-snapshot.json';temporary=ledger.directory/'job-snapshot.tmp'
        if path.is_symlink() or temporary.is_symlink():raise SchemaError('Unsafe job snapshot path.')
        temporary.write_text(json.dumps(saved,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        temporary.replace(path)

    def capabilities(self):
        with self.lock:
            return {'enabled':self.recovery_error is None,'case':'mutation-12','artists':['Sade','Nine Inch Nails'],
                    'model':'qwen38:cyber-32k','max_calls_per_job':9,'remaining_jobs':max(0,2-self.created),
                    'latest_job_id':self.latest,'new_qloo_requests':0,
                    'notice':self.recovery_error or 'Live local model; declared injected cache fault; two saved jobs maximum, including after restart. Previously exposed case.'}

    def start(self):
        with self.lock:
            if self.recovery_error:raise SchemaError(self.recovery_error)
            if any(j['status'] not in ('COMPLETE','FAILED') for j in self.jobs.values()):
                raise SchemaError('A local test is already active. Inspect or repair that test first.')
            if self.created>=2:raise SchemaError('The two-job session budget is exhausted. No inference was started.')
            pack=export_pack(self.root,baseline='candidate',case_ids=['mutation-12'])
            ledger=Ledger(self.out,'qloo-frozen-reference+live-local-llm')
            ledger.write('regression-pack.json',pack)
            ledger.write('job-plan.json',{'case':'mutation-12','model':'qwen38:cyber-32k','inference_cap':9,
                         'qloo_requests':0,'scope':'exposed-regression-demonstration','fault':'declared task-scope cache',
                         'repair':'profile-scope cache with fresh entries','quality_drop_tolerance':0})
            job={'id':ledger.run_id,'status':'STARTING','phase':'Loading the installed model','calls':0,
                 'call_cap':9,'new_qloo_requests':0,'ci_gate':'NOT_VALIDATED','error':None,
                 'fault_declared':True,'profiles':pack['cases'][0]['artists'],'result':None,
                 '_ledger':ledger,'_pack':pack}
            self.jobs[job['id']]=job;self.created+=1;self.latest=job['id']
            self._persist(job)
            Thread(target=self._detect,args=(job,),daemon=True).start()
            return self.view(job['id'])

    def view(self,job_id):
        with self.lock:
            if job_id not in self.jobs:raise SchemaError('Local job not found in this server session.')
            return copy.deepcopy({k:v for k,v in self.jobs[job_id].items() if not k.startswith('_')})

    def _update(self,job,**values):
        with self.lock:
            job.update(values)
            self._persist(job)

    def _requests(self,job):
        case=job['_pack']['cases'][0]
        template={'schema_version':1,'task':'Rank the fixed movie catalog for a discovery feed based on the explicitly declared musical interest.',
                  'top_k':5,'catalog':case['catalog']}
        result={}
        for label in ('A','B'):
            req=copy.deepcopy(template);req['profile']=[{'name':case['artists'][label],'type':'urn:entity:artist'}]
            req['request_id']=fingerprint(req);result[label]=req
        return result

    def _failure(self,job,exc):
        # Do not expose arbitrary transport/exception text or private payloads.
        job['_ledger'].record('job_stopped',{'error_class':type(exc).__name__,'calls':getattr(job.get('_engine'),'calls',0)})
        job['_ledger'].write('job-failed.json',{'status':'FAILED','error_class':type(exc).__name__,'ci_gate':'NOT_VALIDATED'})
        self._update(job,status='FAILED',phase='Execution stopped',error='Local execution did not complete. The partial evidence is preserved; no release decision is available.',calls=getattr(job.get('_engine'),'calls',0))

    def _detect(self,job):
        try:
            engine=self.engine_factory();job['_engine']=engine
            job['_ledger'].write('agent-manifest.json',engine.manifest)
            job['_ledger'].write('model-readiness.json',engine.warmup())
            reqs=self._requests(job);job['_ledger'].write('agent-inputs.json',reqs)
            before={'A':[],'B':[]};traces=[]
            for repeat in range(3):
                agent=CachedMovieAgent(engine,'task',job['_ledger'],'live-declared-fault')
                for label in (('A','B') if repeat%2==0 else ('B','A')):
                    self._update(job,status='DETECTING',phase=f'Testing the changed interest · repeat {repeat+1}',calls=engine.calls)
                    before[label].append(agent.rank(reqs[label]));self._update(job,calls=engine.calls)
                traces+=agent.trace
            collision=all(t['cache_hit'] and t['input_profile_sha256']!=t['cached_profile_sha256'] for t in traces[1::2])
            job['_before']=before
            job['_ledger'].write('before-decisions.json',before)
            job['_ledger'].write('before-cache-trace.json',traces)
            if not collision:raise SchemaError('The declared incident was not observed.')
            self._update(job,status='AWAITING_REPAIR',phase='Cross-profile cache collision observed',
                         diagnosis={'cache_collision':True,'cache_scope':'task','proposed_cache_scope':'profile'},
                         before=self._projection(job,before),calls=engine.calls)
        except Exception as exc:self._failure(job,exc)

    def repair(self,job_id):
        with self.lock:
            if job_id not in self.jobs:raise SchemaError('Local job not found.')
            job=self.jobs[job_id]
            if job['status']!='AWAITING_REPAIR':raise SchemaError('This test is not awaiting the allowlisted cache repair.')
            job['status']='REPAIRING';job['phase']='Clearing the cache and isolating profiles'
            self._persist(job)
            Thread(target=self._repair,args=(job,),daemon=True).start()
            return self.view(job_id)

    def _repair(self,job):
        try:
            engine=job['_engine'];reqs=self._requests(job);after={'A':[],'B':[]};traces=[]
            patch={'cache_scope':{'before':'task','after':'profile'},'old_entries_cleared':True,
                   'prompt_changed':False,'model_changed':False,'reference_sent_to_agent':False}
            job['_ledger'].write('applied-patch.json',patch)
            for repeat in range(3):
                agent=CachedMovieAgent(engine,'profile',job['_ledger'],'live-profile-cache-repair')
                for label in (('A','B') if repeat%2==0 else ('B','A')):
                    self._update(job,phase=f'Recomputing each profile · repeat {repeat+1}',calls=engine.calls)
                    after[label].append(agent.rank(reqs[label]));self._update(job,calls=engine.calls)
                # Test same-profile reuse without consuming an extra inference.
                reused=copy.deepcopy(reqs['A']);reused['request_id']='live-same-profile-repeat-'+str(repeat)
                if agent.rank(reused)!=after['A'][-1]:raise SchemaError('Same-profile reuse changed its decision.')
                traces+=agent.trace
            structural=all(
                not group[0]['cache_hit'] and not group[1]['cache_hit'] and group[2]['cache_hit']
                and group[0]['cache_key_sha256']!=group[1]['cache_key_sha256']
                and all(t['input_profile_sha256']==t['cached_profile_sha256'] for t in group)
                for group in (traces[i:i+3] for i in range(0,9,3)))
            pack=copy.deepcopy(job['_pack']);pack['cases'][0]['baseline']=job['_before']
            pack['pack_sha256']=fingerprint({k:v for k,v in pack.items() if k!='pack_sha256'})
            quality=evaluate_pack(pack,{'mutation-12':after})
            stable=max(max_repeat_jitter(after[p],5) for p in ('A','B'))<=1e-12
            report={'structural_gate':'PASS' if structural else 'FAIL','sample_quality_gate':quality['regression_gate'],
                    'repeat_stability':'PASS' if stable else 'INCONCLUSIVE','quality':quality,'patch':patch,
                    'after':self._projection(job,after),'ci_gate':'NOT_VALIDATED','release_approved':False}
            for name,value in [('after-decisions.json',after),('after-cache-trace.json',traces),
                               ('inference-observations.json',engine.observations),('job-result.json',report)]:
                job['_ledger'].write(name,value)
            self._update(job,status='COMPLETE',phase='Evidence captured · inspect the verdict',calls=engine.calls,result=report)
        except Exception as exc:self._failure(job,exc)

    def _projection(self,job,ranks):
        case=job['_pack']['cases'][0];movies={e['entity_id']:e for e in case['catalog']}
        result=[]
        for repeat in range(3):
            profiles={}
            for label in ('A','B'):
                profiles[label]={'artist':case['artists'][label],
                    'films':[{'id':i,'title':movies[i]['name'],'year':movies[i]['release_year']} for i in ranks[label][repeat][:5]],
                    'agreement':median(ndcg_at_k(ranks[label][repeat],r,5) for r in case['reference'][label])}
            result.append({'repeat':repeat+1,'order':'AB' if repeat%2==0 else 'BA','profiles':profiles})
        return result
