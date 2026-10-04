import type {Snapshot,Section} from '../lib/review';
import {Arrow,Pill} from './primitives';
import {DecisionPreview} from './decision-preview';
import {Projection} from './projection';
import {useEffect,useState} from 'react';

export function Overview({data,navigate,openCase}:{data:Snapshot;navigate:(s:Section)=>void;openCase:(id:string,stage?:number)=>void}){
  const [causal,setCausal]=useState<{passing:number;denominator:number;causal_gate:string;mode:string;behavioral_recoveries:number;model_calls:number;latest_attempt?:{status:string;error?:string}}|null>(null);
  const [causalError,setCausalError]=useState(false);
  useEffect(()=>{const controller=new AbortController();fetch('/api/causal-repair',{cache:'no-store',signal:controller.signal}).then(async response=>{if(!response.ok)throw Error('Unavailable');return response.json()}).then(value=>{if(value.status==='COMPLETE')setCausal(value);else setCausalError(true)}).catch(e=>{if(e.name!=='AbortError')setCausalError(true)});return()=>controller.abort()},[]);
  const first=data.cases[0],mixed=data.cases.find(c=>c.outcome==='MIXED');
  const latest=data.value_study??data.repair_study;
  const date=new Date(data.verified_utc).toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'Europe/Brussels'});
  return <>
    <section className="cinema-hero" aria-labelledby="hero-title">
      <div className="hero-kicker"><span>INDEPENDENT TASTE. ACCOUNTABLE AI.</span><span>MUSIC → MOVIES / VOL. 01</span></div>
      <div className="hero-wordmark" aria-hidden="true">affinity<span>QA</span><i>↗</i></div>
      <div className="cinema-composition">
        <div className="cinema-copy"><span className="eyebrow">THE CULTURAL INTELLIGENCE REVIEW</span><h1 id="hero-title">Taste is personal.<br/><em>Proof is everything.</em></h1><p>Change the music. Challenge the movies.<br/>See whether your agent truly follows the person behind the prompt.</p><div className="hero-actions"><button className="button primary" onClick={()=>navigate('screening')}>Enter the screening room <Arrow diagonal/></button><button className="text-link" onClick={()=>navigate('library')}>Explore the cases <span>06</span></button></div><div className="hero-note"><span className="status-dot"/> Real Qloo references. Recorded local AI decisions.</div></div>
        <div className="cinema-art"><Projection/><div className="art-side-label">A NEW PERSPECTIVE ON PERSONALIZATION</div><div className="art-foot-label"><span>ORIGINAL SIGNAL → CULTURAL REFERENCE</span><span>{date.toUpperCase()}</span></div></div>
      </div>
      <div className="hero-bottom-line"><span>01 — EXPLORE THE EXPERIMENT</span><span>SCROLL TO LOOK CLOSER ↓</span></div>
    </section>
    <section className="current-study"><div><span className="eyebrow">CURRENT / PROFILE INTEGRITY {causal?.mode?.toUpperCase()}</span><p>{causal?<><strong>{causal.passing} / {causal.denominator}</strong> incident cases pass</>:causalError?'Causal evidence unavailable.':'Checking causal evidence…'}</p></div><Pill tone={causal?.causal_gate==='PASS'?'plum':'coral'}>{causal?.causal_gate??'NOT EVALUATED'} · causal integrity</Pill><button className="text-link" onClick={()=>navigate('screening')}>Replay the repair path <Arrow diagonal/></button></section>
    {causal?.latest_attempt?.status==='INCOMPLETE'&&<section className="editor-note"><div className="note-index">!</div><div><span className="eyebrow">NEWER VALIDATION / INCOMPLETE</span><p>{causal.latest_attempt.error??'The latest attempt has not completed. The result above remains the earlier verified capture.'}</p></div><button className="button outline" onClick={()=>navigate('screening')}>Inspect the attempt <Arrow/></button></section>}
    {causal&&<section className="study-line" aria-label="Current causal study results"><div className="study-caption"><span className="eyebrow">OBSERVED BOUNDARIES / THREE INCIDENTS</span><p>Wrong cache.<br/>Stale profile. Wrong tool.</p></div><div><strong>{causal.model_calls}</strong><p>Real captured model decisions</p></div><div><strong>{causal.behavioral_recoveries}</strong><p>Observed behavioral recoveries</p></div><div className="study-mixed"><strong>0</strong><p>New API calls needed to replay</p></div></section>}
    {latest&&<section className="current-study"><div><span className="eyebrow">HISTORICAL / INDEPENDENT QUALITY EXPERIMENT</span><p><strong>{latest.passing_cases} / {latest.denominator}</strong> cases pass all quality controls</p></div><Pill tone={latest.sample_gate==='PASS'?'plum':'coral'}>{latest.sample_gate} · preserved quality result</Pill><button className="text-link" onClick={()=>navigate('evidence')}>Inspect the earlier study <Arrow diagonal/></button></section>}
    <section className="study-line" aria-label="Recorded study results"><div className="study-caption"><span className="eyebrow">EARLIER / CACHE ISOLATION STUDY</span><p>A fixed catalog.<br/>Six changes in taste.</p></div><div><strong>{data.cases.filter(c=>c.structural_gate==='PASS').length}<span> / 6</span></strong><p>Cache isolation repaired</p></div><div><strong>{data.counts.OBSERVED_AGREEMENT_IMPROVEMENT??0}<span> / 6</span></strong><p>Consistent agreement gains</p></div><div className="study-mixed"><strong>{data.counts.MIXED??0}<span> / 6</span></strong><p>Mixed outcome. Kept visible.</p></div></section>
    <DecisionPreview item={mixed??first} openCase={openCase}/>
    <section className="overview-bottom"><div className="journey-intro"><span className="eyebrow">FROM A SIGNAL TO A DECISION</span><h2>Give your agent<br/>a proper <em>screen test.</em></h2><p>Follow the observed failure, inspect the repair, and decide what the evidence actually supports.</p></div><div className="journey-list">{[['01','Detect','A new taste. An unchanged response.'],['02','Diagnose','Find the profile missing from the cache.'],['03','Repair','Give each profile its own entry.'],['04','Verify','Check the gain—and the regression.']].map(([n,title,body],i)=><button key={n} onClick={()=>openCase(first.id,i)}><span>{n}</span><div><strong>{title}</strong><p>{body}</p></div><Arrow diagonal/></button>)}</div></section>
    {mixed&&<section className="editor-note"><div className="note-index">!</div><div><span className="eyebrow">THE RESULT THAT MATTERS MOST</span><h3>A fixed cache isn’t the whole story.</h3><p>The {mixed.artists.A} / {mixed.artists.B} case exposes a quality regression for one profile. The release remains under review.</p></div><button className="button outline" onClick={()=>openCase(mixed.id)}>Inspect the mixed case <Arrow/></button></section>}
    <div className="overview-colophon"><Pill tone="plum">Reference: Qloo</Pill><span>Observed ranking agreement · not a measure of human satisfaction</span><span>Release status: <strong>not validated</strong></span></div>
  </>;
}

