'use client';
import {useEffect,useState} from 'react';
import {sections,readSection,type Section,type Snapshot} from '../lib/review';
import {Mark,Arrow} from '../components/primitives';
import {Overview} from '../components/overview';
import {ScreeningSpace as Screening} from '../components/live-screening';
import {Library} from '../components/library';
import {Evidence} from '../components/evidence';
import {CausalScreening} from '../components/causal-screening';

export default function AffinityApp(){
  const [data,setData]=useState<Snapshot|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const [section,setSection]=useState<Section>('screening'),[selected,setSelected]=useState('mutation-07'),[stage,setStage]=useState(0);
  const [screeningMode,setScreeningMode]=useState<'repair'|'repair-history'|'recorded'|'live'>('repair');
  useEffect(()=>{const sync=()=>{setSection(window.location.hash?readSection():'screening');window.scrollTo({top:0,behavior:'instant'});};sync();window.addEventListener('hashchange',sync);return()=>window.removeEventListener('hashchange',sync)},[]);
  useEffect(()=>{const controller=new AbortController();setError('');fetch('/api/review',{signal:controller.signal,cache:'no-store'}).then(async response=>{if(!response.ok)throw Error('The recorded evidence could not be verified. No release decision is available.');return response.json();}).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message)});return()=>controller.abort()},[retry]);
  const navigate=(next:Section)=>{if(next==='screening')setScreeningMode('repair');if(window.location.hash==='#'+next){setSection(next);window.scrollTo({top:0,behavior:'instant'});}else window.location.hash=next;};
  const openCase=(id:string,nextStage=0)=>{setScreeningMode('recorded');setSelected(id);setStage(nextStage);navigate('screening');setScreeningMode('recorded')};
  const changeStage=(next:number)=>{setStage(next);requestAnimationFrame(()=>document.querySelector('.step-nav')?.scrollIntoView({block:'start',behavior:'instant'}));};
  const item=data?.cases.find(c=>c.id===selected)??data?.cases[0];
  return <div className="app"><a className="skip-link" href="#main-content" onClick={event=>{event.preventDefault();document.getElementById('main-content')?.focus();}}>Skip to content</a><header className="masthead"><a className="brand" href="#overview" onClick={event=>{event.preventDefault();navigate('overview')}} aria-label="AffinityQA home"><Mark/><span>affinity<span className="brand-qa">QA</span></span></a><nav className="main-nav" aria-label="Main navigation">{sections.map(s=><a key={s.id} href={'#'+s.id} onClick={event=>{event.preventDefault();navigate(s.id)}} aria-current={section===s.id?'page':undefined}><span>{s.label}</span><sup>{s.number}</sup></a>)}</nav><div className="environment-label"><span className="status-dot"/> Local studio</div></header><div className="edition-bar"><span>THE CULTURAL INTELLIGENCE REVIEW</span><span>Qloo references <span className="bar-divider">/</span> Recorded model decisions</span></div><main id="main-content" tabIndex={-1}>
    {section==='screening'&&screeningMode==='repair'?<div className="page-transition"><CausalScreening/><button className="button outline" onClick={()=>setScreeningMode('recorded')}>Inspect earlier screening records <Arrow/></button></div>:error?<section className="load-state"><span className="eyebrow">EVIDENCE UNAVAILABLE</span><h1>A review starts<br/>with <em>proof.</em></h1><p role="alert">{error}</p><button className="button primary" onClick={()=>setRetry(retry+1)}>Check evidence again <Arrow/></button><button className="button outline" onClick={()=>navigate('screening')}>Open causal screening <Arrow/></button></section>:!data||!item?<section className="load-state" aria-busy="true"><span className="eyebrow">PREPARING YOUR REVIEW</span><h1>Setting<br/><em>the scene.</em></h1><p>Checking the recorded evidence before displaying results.</p><span className="loading-line"/></section>:<div className="page-transition" key={section}>{section==='overview'?<Overview data={data} navigate={navigate} openCase={openCase}/>:section==='screening'?<Screening mode={screeningMode} setMode={setScreeningMode} data={data} item={item} stage={stage} setStage={changeStage} onSelect={setSelected} openEvidence={()=>navigate('evidence')}/>:section==='library'?<Library data={data} openCase={openCase}/>:<Evidence data={data} openScreening={()=>navigate('screening')}/>}</div>}
  </main><footer className="site-footer"><a className="footer-brand" href="#overview" onClick={event=>{event.preventDefault();navigate('overview')}}><Mark/>affinityQA</a><p>A little more scrutiny.<br/>A better-informed release.</p><div><span>Recorded evidence, openly inspectable.</span><span>Qloo is a reference, not individual ground truth.</span></div><a href="#evidence">Behind the verdict <Arrow diagonal/></a></footer></div>;
}

