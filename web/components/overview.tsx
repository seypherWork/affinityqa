import type {Snapshot,Section} from '../lib/review';
import {Arrow,Pill} from './primitives';
import {DecisionPreview} from './decision-preview';
import {useEffect,useState} from 'react';

export function Overview({data,navigate,openCase}:{data:Snapshot;navigate:(s:Section)=>void;openCase:(id:string,stage?:number)=>void}){
  const [causal,setCausal]=useState<{passing:number;denominator:number;causal_gate:string;mode:string;behavioral_recoveries:number;model_calls:number;latest_attempt?:{status:string;error?:string}}|null>(null);
  const [causalError,setCausalError]=useState(false);
  useEffect(()=>{const controller=new AbortController();fetch('/api/causal-repair',{cache:'no-store',signal:controller.signal}).then(async response=>{if(!response.ok)throw Error('Unavailable');return response.json()}).then(value=>{if(value.status==='COMPLETE')setCausal(value);else setCausalError(true)}).catch(e=>{if(e.name!=='AbortError')setCausalError(true)});return()=>controller.abort()},[]);
  const first=data.cases[0],mixed=data.cases.find(c=>c.outcome==='MIXED');
  const latest=data.value_study??data.repair_study;
  const date=new Date(data.verified_utc).toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'Europe/Brussels'});
  return <section className="overview-page" aria-labelledby="overview-title">
    <header className="overview-header">
      <div><span className="eyebrow">01 / Review workspace</span><h1 id="overview-title">Review overview</h1><p>Profile integrity, recorded repairs and the limits of the evidence.</p></div>
      <div className="overview-header-actions"><button className="button primary" onClick={()=>navigate('screening')}>Open screening <Arrow/></button><button className="button outline" onClick={()=>navigate('library')}>Case library <Arrow diagonal/></button></div>
    </header>

    <section className="overview-panel overview-causal" aria-labelledby="overview-causal-title">
      <div className="overview-panel-heading"><div><span className="eyebrow">Current / Profile integrity {causal?.mode?.toUpperCase()}</span><h2 id="overview-causal-title">Causal integrity</h2></div><Pill tone={causal?.causal_gate==='PASS'?'pass':causal?.causal_gate==='FAIL'?'fail':'warning'}>{causal?.causal_gate??'NOT EVALUATED'}</Pill></div>
      <div className="overview-causal-summary"><p>{causal?'Incident checks and observed recoveries are reported separately from the causal gate.':causalError?'Causal evidence unavailable.':'Checking causal evidence…'}</p><button className="text-link" onClick={()=>navigate('screening')}>Inspect the repair path <Arrow diagonal/></button></div>
      <div className="overview-metric-grid" aria-label="Current recorded causal study">
        <article className="overview-metric"><span>Incident cases passing</span><strong>{causal?<>{causal.passing}<small> / {causal.denominator}</small></>:'—'}</strong><p>Wrong cache · stale profile · wrong tool</p></article>
        <article className="overview-metric"><span>Captured model decisions</span><strong>{causal?.model_calls??'—'}</strong><p>Recorded execution evidence</p></article>
        <article className="overview-metric"><span>Behavioral recoveries</span><strong>{causal?.behavioral_recoveries??'—'}</strong><p>Observed in the captured run</p></article>
        <article className="overview-metric"><span>Calls needed to replay</span><strong>{causal?'0':'—'}</strong><p>Replay uses recorded evidence</p></article>
      </div>
    </section>

    {causal?.latest_attempt?.status==='INCOMPLETE'&&<section className="overview-alert" role="status"><div><span className="eyebrow">Newer validation / Incomplete</span><p>{causal.latest_attempt.error??'The latest attempt has not completed. The result above remains the earlier verified capture.'}</p></div><button className="button outline" onClick={()=>navigate('screening')}>Inspect attempt <Arrow/></button></section>}

    <section className="overview-panel overview-history" aria-labelledby="overview-history-title">
      <div className="overview-panel-heading"><div><span className="eyebrow">Historical / Preserved results</span><h2 id="overview-history-title">Recommendation quality</h2></div><button className="text-link" onClick={()=>navigate('evidence')}>Evidence archive <Arrow diagonal/></button></div>
      {latest&&<div className="overview-quality-result"><div><strong>{latest.passing_cases} / {latest.denominator}</strong><span>Cases meeting all quality controls</span></div><Pill tone={latest.sample_gate==='PASS'?'pass':'fail'}>{latest.sample_gate} · historical quality</Pill></div>}
      <div className="overview-history-metrics" aria-label="Earlier cache-isolation study">
        <div><span>Cache isolation repaired</span><strong>{data.cases.filter(c=>c.structural_gate==='PASS').length} / {data.case_count}</strong></div>
        <div><span>Consistent agreement gains</span><strong>{data.counts.OBSERVED_AGREEMENT_IMPROVEMENT??0} / {data.case_count}</strong></div>
        <div><span>Mixed outcomes preserved</span><strong>{data.counts.MIXED??0} / {data.case_count}</strong></div>
      </div>
      <p className="metric-note">These earlier quality outcomes remain unchanged by the current causal protocol. Agreement with Qloo does not measure human satisfaction.</p>
    </section>

    <section className="overview-panel overview-workflow" aria-labelledby="overview-workflow-title">
      <div className="overview-panel-heading"><div><span className="eyebrow">Recorded workflow</span><h2 id="overview-workflow-title">Detect · Diagnose · Repair · Verify</h2></div><span className="overview-workflow-case">Case {first.id}</span></div>
      <div className="overview-workflow-steps">{[['01','Detect','Observe an unchanged response after the taste changes.'],['02','Diagnose','Inspect the profile missing from the cache.'],['03','Repair','Give each profile its own cache entry.'],['04','Verify','Check the agreement gain and any regression.']].map(([n,title,body],i)=><button key={n} onClick={()=>openCase(first.id,i)}><span className="overview-step-index">{n}</span><div><strong>{title}</strong><p>{body}</p></div><Arrow diagonal/></button>)}</div>
    </section>

    <DecisionPreview item={mixed??first} openCase={openCase}/>
    {mixed&&<section className="overview-alert"><div><span className="eyebrow">Historical / Mixed outcome</span><h3>Profile loss remains visible</h3><p>The {mixed.artists.A} / {mixed.artists.B} case exposes a quality regression for one profile. The release remains under review.</p></div><button className="button outline" onClick={()=>openCase(mixed.id)}>Inspect mixed case <Arrow/></button></section>}
    <footer className="overview-footer"><span>Reference: <strong>Qloo</strong></span><span>Historical verification: {date} · Brussels</span><span>Release status: <strong>not validated</strong></span></footer>
  </section>;
}