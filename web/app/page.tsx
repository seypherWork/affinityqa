'use client';
import {useEffect,useState} from 'react';
import {readSection,type Section,type Snapshot} from '../lib/review';
import {Arrow} from '../components/primitives';
import {WorkspaceShell} from '../components/workspace-shell';
import {Overview} from '../components/overview';
import {ScreeningSpace as Screening} from '../components/live-screening';
import {Library} from '../components/library';
import {Evidence} from '../components/evidence';
import {CausalScreening} from '../components/causal-screening';
import {IndividualScreening} from '../components/individual-screening';
import screeningStyles from '../components/screening-mode.module.css';

export default function AffinityApp(){
  const [data,setData]=useState<Snapshot|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  const [section,setSection]=useState<Section>('screening'),[selected,setSelected]=useState('mutation-07'),[stage,setStage]=useState(0);
  const [screeningMode,setScreeningMode]=useState<'repair'|'repair-history'|'recorded'|'live'>('repair');
  const [individual,setIndividual]=useState(false);
  const [individualOpened,setIndividualOpened]=useState(false);
  useEffect(()=>{const sync=()=>{setSection(window.location.hash?readSection():'screening');window.scrollTo({top:0,behavior:'instant'});};sync();window.addEventListener('hashchange',sync);return()=>window.removeEventListener('hashchange',sync)},[]);
  useEffect(()=>{const controller=new AbortController();setError('');fetch('/api/review',{signal:controller.signal,cache:'no-store'}).then(async response=>{if(!response.ok)throw Error('The recorded evidence could not be verified. No release decision is available.');return response.json();}).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message)});return()=>controller.abort()},[retry]);
  const navigate=(next:Section)=>{if(next==='screening'){setScreeningMode('repair');setIndividual(false)}if(window.location.hash==='#'+next){setSection(next);window.scrollTo({top:0,behavior:'instant'});}else window.location.hash=next;};
  const openCase=(id:string,nextStage=0)=>{setScreeningMode('recorded');setSelected(id);setStage(nextStage);navigate('screening');setScreeningMode('recorded')};
  const changeStage=(next:number)=>{setStage(next);requestAnimationFrame(()=>document.querySelector('.step-nav')?.scrollIntoView({block:'start',behavior:'instant'}));};
  const item=data?.cases.find(c=>c.id===selected)??data?.cases[0];
  const titles:Record<Section,string>={overview:'Overview',screening:'Screening',library:'Case library',evidence:'Evidence archive'};
  return <WorkspaceShell active={section} title={titles[section]} onNavigate={id=>navigate(id as Section)}>
    {section==='screening'&&<div className={screeningStyles.tabs} role="group" aria-label="Screening source"><button type="button" aria-pressed={!individual} onClick={()=>setIndividual(false)}>Recorded screening <span>Saved evidence · no new provider calls</span></button><button type="button" aria-pressed={individual} onClick={()=>{setIndividual(true);setIndividualOpened(true);}}>New individual case <span>Fresh execution · plan before running</span></button></div>}
    {individualOpened&&<div hidden={section!=='screening'||!individual}><IndividualScreening/></div>}
    {section==='screening'&&individual?null:section==='screening'&&screeningMode==='repair'?<div className="page-transition"><CausalScreening/><button className="button outline" onClick={()=>setScreeningMode('recorded')}>Inspect historical screening records <Arrow/></button></div>:error?<section className="load-state"><span className="eyebrow">EVIDENCE UNAVAILABLE</span><h1>Evidence could not be verified</h1><p role="alert">{error}</p><div className="hero-actions"><button className="button primary" onClick={()=>setRetry(retry+1)}>Check evidence again <Arrow/></button><button className="button outline" onClick={()=>navigate('screening')}>Open causal screening <Arrow/></button></div></section>:!data||!item?<section className="load-state" aria-busy="true"><span className="eyebrow">PREPARING YOUR REVIEW</span><h1>Verifying the evidence</h1><p>Checking recorded artifacts before displaying results.</p><span className="loading-line"/></section>:<div className="page-transition" key={section}>{section==='overview'?<Overview data={data} navigate={navigate} openCase={openCase}/>:section==='screening'?<Screening mode={screeningMode} setMode={setScreeningMode} data={data} item={item} stage={stage} setStage={changeStage} onSelect={setSelected} openEvidence={()=>navigate('evidence')}/>:section==='library'?<Library data={data} openCase={openCase}/>:<Evidence data={data} openScreening={()=>navigate('screening')}/>}</div>}
  </WorkspaceShell>;
}

