import {useEffect,useState} from 'react';
import {Arrow,FilmList,Pill} from './primitives';
import {Screening} from './screening';
import {RepairValidation} from './repair-validation';
import {score,signed,type Movie} from '../lib/review';

type Profile={artist:string;films:Movie[];agreement:number};
type Repeat={repeat:number;order:string;profiles:{A:Profile;B:Profile}};
type Job={id:string;status:string;phase:string;calls:number;call_cap:number;error:string|null;before?:Repeat[];
  result?:{structural_gate:string;sample_quality_gate:string;repeat_stability:string;after:Repeat[];release_approved:boolean;
    quality:{cases:{profiles:{A:{min_delta:number};B:{min_delta:number}}}[]}}|null};
type Capabilities={enabled:boolean;notice:string;remaining_jobs?:number;latest_job_id?:string|null};

async function read<T>(path:string,method='GET'):Promise<T>{
  const response=await fetch(path,{method,cache:'no-store',...(method==='POST'?{headers:{'Content-Type':'application/json'},body:'{}'}:{})});
  const body=await response.json();
  if(!response.ok)throw Error(body.error??body.message??'The local operation did not complete.');
  return body;
}

function LiveScreening(){
  const [cap,setCap]=useState<Capabilities|null>(null),[job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[pending,setPending]=useState(false);
  const [profile,setProfile]=useState<'A'|'B'>('B'),[repeat,setRepeat]=useState(0);
  useEffect(()=>{let mounted=true;read<Capabilities>('/api/live/capabilities').then(async c=>{
    if(!mounted)return;setCap(c);if(c.latest_job_id){const j=await read<Job>('/api/live/jobs/'+c.latest_job_id);if(mounted)setJob(j)}
  }).catch(e=>{if(mounted)setError(e.message)});return()=>{mounted=false}},[]);
  useEffect(()=>{
    if(!job||['AWAITING_REPAIR','COMPLETE','FAILED'].includes(job.status))return;
    let mounted=true,reading=false;
    const timer=setInterval(async()=>{if(reading)return;reading=true;try{const j=await read<Job>('/api/live/jobs/'+job.id);if(mounted){setJob(j);setError('')}}catch(e){if(mounted)setError(e instanceof Error?e.message:'Unable to inspect the local job.')}finally{reading=false}},1200);
    return()=>{mounted=false;clearInterval(timer)};
  },[job?.id,job?.status]);
  const act=async(repair=false)=>{setPending(true);setError('');try{
    const j=await read<Job>(repair?'/api/live/jobs/'+job?.id+'/repair':'/api/live/jobs','POST');setJob(j);
    setCap(await read<Capabilities>('/api/live/capabilities'));
  }catch(e){setError(e instanceof Error?e.message:'Local execution did not start.')}finally{setPending(false)}};
  const busy=pending||!!job&&!['AWAITING_REPAIR','COMPLETE','FAILED'].includes(job.status);
  const before=job?.before?.[repeat]?.profiles[profile],after=job?.result?.after?.[repeat]?.profiles[profile];
  const failedQuality=job?.result?.sample_quality_gate==='FAIL';
  return <section className="section-page live-screening"><div className="page-heading"><div><span className="eyebrow">02 / LIVE LOCAL SCREEN TEST</span><h1>Run the agent.<br/><em>Inspect the proof.</em></h1></div><div><p>Change Sade to Nine Inch Nails. Execute the installed model, expose a cache collision, apply the profile-cache patch, and measure the result.</p><Pill tone="plum">Local model · frozen Qloo reference</Pill></div></div>
    <div className="live-contract"><div><span className="eyebrow">A CONTROLLED INCIDENT</span><p>The cache defect is deliberately injected. This previously exposed case is a regression test. The reference is already captured; these actions make no new Qloo calls.</p></div><div><span className="eyebrow">BOUNDED EXECUTION</span><p>Qwen · up to 9 model decisions per run · three repeats · one active run · {cap?.remaining_jobs??'—'} of two saved runs available.</p></div></div>
    {error&&<p role="alert" className="live-error">{error}</p>}
    {!cap?<p className="loading-line">Checking the local runner…</p>:!cap.enabled?<p className="live-error">{cap.notice}</p>:<div className="live-actions"><button className="button primary" disabled={busy||!!job&&job.status==='AWAITING_REPAIR'||cap.remaining_jobs===0} onClick={()=>act()}>Run local evaluation <Arrow/></button>{job?.status==='AWAITING_REPAIR'&&<button className="button primary" disabled={pending} onClick={()=>act(true)}>Apply cache repair & rerun <Arrow/></button>}<span>Consumes local inference only.</span></div>}
    {job&&<div className="live-progress" aria-live="polite" aria-busy={busy}><div><Pill tone={job.status==='FAILED'?'coral':'neutral'}>{job.status.replaceAll('_',' ').toLowerCase()}</Pill><strong>{job.phase}</strong></div><span>{job.calls} / {job.call_cap} model decisions</span><progress max={job.call_cap} value={job.calls}/><small>Run {job.id}</small></div>}
    {job?.error&&<p role="alert" className="live-error">{job.error}</p>}
    {job?.status==='AWAITING_REPAIR'&&<div className="live-diagnosis"><span className="eyebrow">DIAGNOSIS / OBSERVED CACHE COLLISION</span><h2>A new interest.<br/><em>The same cached answer.</em></h2><p>Three executions observed a cross-profile cache hit. The proposed patch includes the profile in the cache key and clears the old entries. The model and prompt stay fixed.</p><code>cache_scope: task → profile</code></div>}
    {job?.result&&<div className="verdict-banner"><div><Pill tone={failedQuality?'coral':'plum'}>{failedQuality?'Regression detected · release blocked':'Sample check complete · release unvalidated'}</Pill><h3>{failedQuality?'A cache fix did not pass the quality check.':'Inspect each gate before a release.'}</h3><p>{failedQuality?'The repaired cache isolates profiles, but reference agreement fell for at least one. AffinityQA keeps the failed test visible.':'These results apply to this exposed sample. This historical sample does not approve a production release. The separate causal recovery study is available in Causal recovery.'}</p></div><dl className="live-gates"><div><dt>Cache isolation</dt><dd>{job.result.structural_gate}</dd></div><div><dt>Sample quality</dt><dd>{job.result.sample_quality_gate}</dd></div><div><dt>Stable repeats</dt><dd>{job.result.repeat_stability}</dd></div></dl></div>}
    {before&&<><div className="comparison-controls"><div className="profile-switch" role="group" aria-label="Live profile">{(['A','B'] as const).map(p=><button key={p} aria-pressed={profile===p} onClick={()=>setProfile(p)}>{p}<span>{p==='A'?'Sade':'Nine Inch Nails'}</span></button>)}</div><label><span>Actual repeat</span><select aria-label="Live repeat" value={repeat} onChange={e=>setRepeat(Number(e.target.value))}>{job?.before?.map((r,i)=><option value={i} key={i}>{r.repeat} · {r.order==='AB'?'A then B':'B then A'}</option>)}</select></label></div><div className="ranking-comparison"><article><div className="rank-label"><span>LIVE AGENT / BEFORE</span><Pill tone="coral">Declared cache fault</Pill></div><h3>{before.artist}</h3><FilmList movies={before.films}/><div className="agreement"><span>Frozen Qloo agreement</span><strong>{score(before.agreement)}</strong></div></article><article className="after-column"><div className="rank-label"><span>LIVE AGENT / AFTER</span><Pill tone={after&&after.agreement<before.agreement?'coral':'neutral'}>{after?'Recomputed':'Awaiting repair'}</Pill></div><h3>{before.artist}</h3>{after?<><FilmList movies={after.films} compare={before.films}/><div className="agreement"><span>Frozen Qloo agreement</span><strong>{score(after.agreement)}<small className={after.agreement<before.agreement?'negative':'positive'}>{signed(after.agreement-before.agreement)}</small></strong></div></>:<p>Apply the proposed cache patch to obtain a new model decision. No repaired ranking is displayed before execution.</p>}</article></div></>}
    <p className="metric-note">Full rankings, cache traces, model observations and the applied patch are saved locally. Agreement with Qloo measures a cultural reference; it is not a satisfaction percentage. No production release is approved here.</p>
  </section>;
}

export function ScreeningSpace({mode,setMode,...props}:Parameters<typeof Screening>[0]&{mode:'repair'|'repair-history'|'recorded'|'live';setMode:(mode:'repair'|'repair-history'|'recorded'|'live')=>void}){
  return <><div className="screening-mode" role="group" aria-label="Screening mode"><button aria-pressed={mode==='repair'} onClick={()=>setMode('repair')}>Causal recovery</button><button aria-pressed={mode==='repair-history'} onClick={()=>setMode('repair-history')}>Historical quality trial</button><button aria-pressed={mode==='recorded'} onClick={()=>setMode('recorded')}>Cache study</button><button aria-pressed={mode==='live'} onClick={()=>setMode('live')}>Live local test <span>↗</span></button></div>{mode==='repair-history'?<RepairValidation/>:mode==='live'?<LiveScreening/>:<Screening {...props}/>}</>;
}
