'use client';

import {useEffect,useRef,useState} from 'react';
import styles from './causal-screening.module.css';

type Profile='A'|'B';
type Film={id:string;title:string;year:number};
type Trace={requested_profile_sha256:string;transmitted_profile_sha256:string;tool_profile_sha256:string;output_profile_sha256:string;cache_hit:boolean};
type View={repeat:number;order:Profile[];profile:Profile;healthy:Film[];before:Film[];after:Film[];trace:Trace;repaired_trace:Trace};
type Fault={fault:string;diagnosis:string;repair_operation:string;passing:boolean;checks:Record<string,boolean>;behavior_changed_repeats:number;recovery_max_distance:number;repeat_count:number;views:View[]};
type Pair={pair_id:string;artists:Record<Profile,string>;split:'development'|'validation';tool_signal_distance:number;cases:Fault[]};
type Report={schema_version:1;status:'COMPLETE'|'INCOMPLETE'|'UNAVAILABLE';notice:string;protocol_version?:string;run_id?:string;causal_gate?:string;behavioral_gate?:string;behavioral_recoveries?:number;cultural_gate?:string;release_gate?:string;source?:string;model_calls?:number;qloo_requests?:number;policy_sha256?:string;noise_barrier?:number;denominator?:number;passing?:number;pairs?:Pair[];historical?:{development:{passing:number;denominator:number;status:string};independent:{passing:number;denominator:number;status:string}}};
const stages=['Detect','Diagnose','Repair','Verify'] as const;
const faultNames:Record<string,string>={'cache-omits-profile':'Profile missing from cache key','stale-profile':'Stale profile passed to agent','wrong-tool-profile':'Qloo context bound to wrong profile'};
const readable=(text:string)=>text.replaceAll('_',' ').replaceAll('-',' ');
const decimal=(value:number|undefined)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(6):'Not recorded';

function Films({title,rows,artist}:{title:string;rows:Film[];artist:string}){
  return <section className={styles.films}><span className={styles.label}>{title}</span><h4>{artist}</h4><ol>{rows.slice(0,5).map((film,i)=><li key={`${film.id}-${i}`}><span className={styles.position}>{String(i+1).padStart(2,'0')}</span><span>{film.title}<small>{film.year}</small></span></li>)}</ol>{rows.length===0&&<p>No recorded decision.</p>}</section>;
}
function TraceDetails({trace,title}:{trace:Trace;title:string}){
  const fields:[keyof Trace,string][]=[['requested_profile_sha256','Requested profile'],['transmitted_profile_sha256','Agent received'],['tool_profile_sha256','Qloo context belongs to'],['output_profile_sha256','Output belongs to']];
  return <details className={styles.trace}><summary>{title}<span>Inspect provenance ↗</span></summary><dl>{fields.map(([key,label])=><div key={key}><dt>{label}</dt><dd><details><summary>{typeof trace[key]==='string'?`${String(trace[key]).slice(0,12)}…`:'Not recorded'}</summary><code>{String(trace[key]??'Not recorded')}</code></details></dd></div>)}<div><dt>Cache reused</dt><dd>{trace.cache_hit?'Yes':'No'}</dd></div></dl></details>;
}


type Replay={status:'PASS'|'FAIL';source:'recorded-local-llm-replay';new_model_calls:0;new_qloo_calls:0;recorded_decision_dispatches:number;diagnosis:unknown;repair:unknown;checks:Record<string,boolean>;before:Film[];after:Film[];healthy:Film[];trace:Trace;repaired_trace:Trace;notice:string};
const describe=(value:unknown):string=>typeof value==='string'?value:JSON.stringify(value);
function ReplayControl({runId,pairId,fault,repeat,artist}:{runId:string|undefined;pairId:string;fault:string;repeat:number;artist:string}){
  const [result,setResult]=useState<Replay|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);const active=useRef<AbortController|null>(null);
  useEffect(()=>()=>active.current?.abort(),[]);
  async function run(){
    if(busy)return;const controller=new AbortController();active.current=controller;setBusy(true);setError('');setResult(null);
    try{const response=await fetch('/api/causal-repair/replay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pair_id:pairId,fault,repeat}),signal:controller.signal});const body=await response.json();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Replay could not be verified.');if(!runId||body.run_id!==runId||body.pair_id!==pairId||body.fault!==fault||body.repeat!==repeat||!['PASS','FAIL'].includes(body.status)||body.source!=='recorded-local-llm-replay'||body.new_model_calls!==0||body.new_qloo_calls!==0)throw new Error('Unexpected replay contract. No verified result is shown.');if(!controller.signal.aborted)setResult(body);}
    catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Replay failed.');}finally{if(!controller.signal.aborted)setBusy(false);}
  }
  return <section className={styles.replay} aria-label="Recorded pipeline replay"><span className={styles.label}>EXECUTABLE REVIEW / RECORDED DECISIONS</span><h3>Run the repair path again.</h3><p>Reproduce this incident, diagnosis and repair with the saved local-model decisions. This is a new pipeline execution, not new model inference.</p><button type="button" disabled={busy} onClick={run}>{busy?'Replaying recorded decisions…':'Replay this incident'}</button>{busy&&<p role="status">Verifying the recorded execution…</p>}{error&&<p role="alert" className={styles.warning}>{error}</p>}{result&&<div aria-live="polite"><p><strong>Replay {result.status}</strong> · {result.recorded_decision_dispatches} recorded decision dispatches · {result.new_model_calls} new model calls · {result.new_qloo_calls} new Qloo calls</p><p>{result.notice}</p><p>Diagnosis: {describe(result.diagnosis)}</p><p>Repair: {describe(result.repair)}</p><ul className={styles.checks}>{Object.entries(result.checks).map(([name,passed])=><li key={name}><span>{readable(name)}</span><strong data-pass={passed}>{passed?'PASS':'FAIL'}</strong></li>)}</ul><div className={styles.ranking}><Films title="REPLAY / BEFORE" rows={result.before} artist={artist}/><Films title="REPLAY / AFTER" rows={result.after} artist={artist}/><Films title="REPLAY / HEALTHY" rows={result.healthy} artist={artist}/></div><div className={styles.traces}><TraceDetails title="Replay: before" trace={result.trace}/><TraceDetails title="Replay: after" trace={result.repaired_trace}/></div></div>}</section>;
}

export function CausalScreening(){
  const [report,setReport]=useState<Report|null>(null);const [error,setError]=useState('');const [loading,setLoading]=useState(true);const [refresh,setRefresh]=useState(0);
  const [pairIndex,setPairIndex]=useState(0);const [faultIndex,setFaultIndex]=useState(0);const [viewIndex,setViewIndex]=useState(0);const [stage,setStage]=useState<typeof stages[number]>('Detect');
  useEffect(()=>{const controller=new AbortController();setLoading(true);setError('');fetch('/api/causal-repair',{cache:'no-store',signal:controller.signal}).then(async response=>{if(!response.ok)throw new Error(`Recorded evidence could not be loaded (${response.status}).`);const body=await response.json();if(body?.schema_version!==1||!['COMPLETE','INCOMPLETE','UNAVAILABLE'].includes(body.status))throw new Error('The evidence response has an unsupported format.');setReport(body);setPairIndex(0);setFaultIndex(0);setViewIndex(0);}).catch(e=>{if(e.name!=='AbortError'){setError(e.message||'Recorded evidence is unavailable.');setReport(null);}}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();},[refresh]);
  const pair=report?.pairs?.[pairIndex];const fault=pair?.cases?.[faultIndex];const view=fault?.views?.[viewIndex];
  const failures=fault?Object.entries(fault.checks).filter(([,passed])=>!passed):[];
  return <section className={styles.root} aria-labelledby="causal-title">
    <header className={styles.header}><div><span className={styles.label}>NEW PROTOCOL / PROFILE INTEGRITY</span><h2 id="causal-title">Follow the profile.<br/><em>Prove the recovery.</em></h2></div><p>A controlled fault breaks the path from requested taste to agent decision. Inspect the diagnosis, the repair and the recorded rerun. Cultural recommendation quality has a separate gate.</p></header>
    <div className={styles.gates} aria-label="Separate acceptance gates"><div><span>Causal integrity</span><strong data-pass={report?.causal_gate==='PASS'}>{loading?'Loading':report?.causal_gate??'NOT EVALUATED'}</strong></div><div><span>Cultural quality</span><strong>{report?.cultural_gate??'NOT VALIDATED'}</strong></div><div><span>Release approval</span><strong>{report?.release_gate??'BLOCKED'}</strong></div></div>
    {loading&&<p role="status">Loading the saved repair record…</p>}
    {error&&<div className={styles.warning} role="alert"><p>{error}</p><button type="button" onClick={()=>setRefresh(n=>n+1)}>Reload evidence</button></div>}
    {!loading&&report&&<>
      <p className={styles.notice}>{report.notice}</p><div className={styles.context}><strong>Behavioral recovery: {report.behavioral_gate??'NOT EVALUATED'}</strong><span>{report.behavioral_recoveries??'—'} recorded recoveries</span></div>
      {report.status!=='COMPLETE'&&<div className={styles.warning}><strong>{report.status==='UNAVAILABLE'?'No completed record available.':'The recorded run is incomplete.'}</strong><p>There is no complete causal result to approve. Saved partial evidence remains visible where available.</p></div>}
      <div className={styles.totals}><div><strong>{report.passing??'—'} / {report.denominator??'—'}</strong><span>Incident cases pass</span></div><div><strong>{report.model_calls??'—'}</strong><span>Local model decisions</span></div><div><strong>{report.qloo_requests??'—'}</strong><span>Qloo requests in this run</span></div><div><strong>{decimal(report.noise_barrier)}</strong><span>Recorded noise barrier</span></div></div>
      {pair&&<>
        <div className={styles.selectors}><label>Artist pair<select aria-label="Causal artist pair" value={pairIndex} onChange={e=>{setPairIndex(Number(e.target.value));setFaultIndex(0);setViewIndex(0);}}>{report.pairs?.map((p,i)=><option key={p.pair_id} value={i}>{p.artists.A} / {p.artists.B}</option>)}</select></label><label>Injected fault<select aria-label="Causal fault" value={faultIndex} onChange={e=>{setFaultIndex(Number(e.target.value));setViewIndex(0);}}>{pair.cases.map((c,i)=><option key={c.fault} value={i}>{faultNames[c.fault]??readable(c.fault)}</option>)}</select></label><label>Repeat & requested profile<select aria-label="Causal repeat and profile" value={viewIndex} onChange={e=>setViewIndex(Number(e.target.value))}>{fault?.views.map((v,i)=><option key={`${v.repeat}-${v.profile}-${i}`} value={i}>Repeat {v.repeat} · {pair.artists[v.profile]} · {v.order.join(' → ')}</option>)}</select></label></div>
        <div className={styles.context}><span>{pair.split==='validation'?'Reserved validation pair':'Known development pair'}</span><span>Tool signal distance {decimal(pair.tool_signal_distance)}</span></div>
        {fault&&<>
          <nav className={styles.stages} aria-label="Repair investigation stages">{stages.map((name,i)=><button type="button" key={name} aria-pressed={stage===name} className={stage===name?styles.active:''} onClick={()=>setStage(name)}><span>0{i+1}</span>{name}</button>)}</nav>
          <div className={styles.panel} aria-live="polite">
            <span className={styles.label}>{stage.toUpperCase()} / {fault.passing?'CAUSAL CONTROLS PASS':'CAUSAL CONTROLS FAIL'}</span>
            {stage==='Detect'&&<><h3>{faultNames[fault.fault]??readable(fault.fault)}</h3><p>The requested artist remains the same across these comparisons. Before repair records the injected fault; after repair records its rerun.</p></>}
            {stage==='Diagnose'&&<><h3>Find where identity diverged.</h3><p>{fault.diagnosis}</p></>}
            {stage==='Repair'&&<><h3>A recorded change. A real rerun.</h3><p>{fault.repair_operation}</p><p>Restoring profile integrity does not establish better cultural recommendations.</p></>}
            {stage==='Verify'&&<><h3>Recovery must clear every control.</h3><div className={styles.verification}><p><strong>{fault.behavior_changed_repeats} / {fault.repeat_count}</strong> repeats changed behavior</p><p><strong>{decimal(fault.recovery_max_distance)}</strong> maximum distance from healthy behavior</p></div><ul className={styles.checks}>{Object.entries(fault.checks).map(([name,passed])=><li key={name}><span>{readable(name)}</span><strong data-pass={passed}>{passed?'PASS':'FAIL'}</strong></li>)}</ul></>}
            {failures.length>0&&<div className={styles.warning}><strong>Unresolved controls</strong><ul>{failures.map(([name])=><li key={name}>{readable(name)}</li>)}</ul></div>}
          </div>
          {view&&<><ReplayControl key={`${report.run_id}-${pair.pair_id}-${fault.fault}-${view.repeat}-${view.profile}`} runId={report.run_id} pairId={pair.pair_id} fault={fault.fault} repeat={view.repeat} artist={pair.artists[view.profile]}/><div className={styles.ranking}><Films title="BEFORE / FAULT INJECTED" rows={view.before} artist={pair.artists[view.profile]}/><Films title="AFTER / REPAIR RERUN" rows={view.after} artist={pair.artists[view.profile]}/><Films title="HEALTHY / RECOVERY TARGET" rows={view.healthy} artist={pair.artists[view.profile]}/></div><div className={styles.traces}><TraceDetails title="Before repair" trace={view.trace}/><TraceDetails title="After repair" trace={view.repaired_trace}/></div></>}
        </>}
      </>}
      {report.historical&&<aside className={styles.history}><span className={styles.label}>EARLIER QUALITY EXPERIMENTS / PRESERVED</span><p>Development: <strong>{report.historical.development.passing}/{report.historical.development.denominator} · {report.historical.development.status}</strong>. Independent trial: <strong>{report.historical.independent.passing}/{report.historical.independent.denominator} · {report.historical.independent.status}</strong>. This causal protocol does not overturn either quality result.</p></aside>}
      <details className={styles.trace}><summary>Protocol & provenance</summary><dl><div><dt>Run</dt><dd>{report.run_id??'Not recorded'}</dd></div><div><dt>Protocol</dt><dd>{report.protocol_version??'Not recorded'}</dd></div><div><dt>Execution source</dt><dd>{report.source??'Not recorded'}</dd></div><div><dt>Frozen policy</dt><dd><code>{report.policy_sha256??'Not recorded'}</code></dd></div></dl></details>
    </>}
    <footer className={styles.footer}><p>Opening this screen reads saved evidence. Replay re-executes the local pipeline using recorded decisions; it makes no new model or Qloo calls.</p><div><a href="/api/causal-repair" target="_blank" rel="noreferrer">Open source record ↗</a><a href="/api/causal-repair/export" download>Download review pack ↓</a></div></footer>
  </section>;
}
