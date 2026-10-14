// Optional additions to the public case contract; finite legacy responses stay valid.
export type ProviderUsage={http_attempts:number;cache_hits:number;reconstructed_steps:number;unknown_attempts:number};
export type ProviderStats={qloo:ProviderUsage;groq:ProviderUsage};
export function safeProviderStats(value:unknown):ProviderStats|null{
  if(!value||typeof value!=='object'||Array.isArray(value))return null;
  const fields=Object.keys(value);if(fields.length!==2||!fields.includes('qloo')||!fields.includes('groq'))return null;
  const raw=value as Record<string,unknown>,parsed={} as ProviderStats;
  const counters=['http_attempts','cache_hits','reconstructed_steps','unknown_attempts'] as const;
  for(const provider of ['qloo','groq'] as const){
    const row=raw[provider];if(!row||typeof row!=='object'||Array.isArray(row))return null;
    const names=Object.keys(row);if(names.length!==counters.length||!counters.every(name=>names.includes(name)))return null;
    const data=row as Record<string,unknown>,counts={} as ProviderUsage;
    for(const name of counters){const number=data[name];if(typeof number!=='number'||!Number.isSafeInteger(number)||number<0)return null;counts[name]=number;}
    parsed[provider]=counts;
  }
  return parsed;
}
export type CaseAccess={admission_mode?:string;legacy_case?:boolean;read_only?:boolean};
export type CaseQueue={queue_status?:string|null;queue_position?:number|null;not_before?:string|null};
export type RequestDiagnostic={provider:string;window:string;required:number;capacity:number;dispatch_started:boolean;automatic_retry?:boolean};
const activeStates=new Set(['STARTED','STARTED_IDENTITY_SEARCH','STARTED_CONFIRMED_CAPTURE','RUNNING','VERIFYING','QUEUED','WAITING_PROVIDER_CAPACITY']);
const queueStates=new Set(['QUEUED','WAITING_PROVIDER_CAPACITY']);
export function queueState(job:({status:string}&CaseQueue)|null){
  if(!job)return null;
  return queueStates.has(job.status)?job.status:activeStates.has(job.status)&&job.queue_status&&queueStates.has(job.queue_status)?job.queue_status:null;
}
export function caseIsBusy(job:({status:string}&CaseQueue&CaseAccess)|null){
  return !!job&&!job.read_only&&(activeStates.has(job.status)||!!queueState(job));
}
export function eligibilityTime(value?:string|null){
  if(!value)return null;
  const parsed=Date.parse(value);
  return Number.isFinite(parsed)?new Date(parsed).toUTCString():null;
}
export function pollingDelay(job:({status:string}&CaseQueue)|null,publicMode:boolean){
  if(!queueState(job))return publicMode?3000:1500;
  const parsed=job?.not_before?Date.parse(job.not_before):NaN;
  return Number.isFinite(parsed)?Math.max(3000,Math.min(30000,parsed-Date.now())):10000;
}
export function executionCapacity(value:number|null|undefined,publicMode:boolean,repeatable:boolean){
  if(repeatable&&value===null)return 'No lifetime execution count cap; provider capacity and storage still apply.';
  if(typeof value!=='number')return 'Execution availability has not been reported.';
  return `${value} ${publicMode?'execution admissions available to this review session':'execution admissions remaining in this storage'}.`;
}
export function safePreDispatchDiagnostic(value?:RequestDiagnostic){
  return value?.dispatch_started===false&&['qloo','groq'].includes(value.provider)&&typeof value.window==='string'&&/^[a-z][a-z0-9_-]{0,63}$/.test(value.window)&&Number.isSafeInteger(value.required)&&Number.isSafeInteger(value.capacity)&&value.capacity>0&&value.required>value.capacity?value:null;
}
