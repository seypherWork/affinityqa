'use client';
import type {ReactNode} from 'react';
import {Mark} from './primitives';

type IconName='overview'|'screening'|'library'|'evidence'|'new'|'recorded';
type NavItem={id:string;label:string;icon:IconName};
const defaultItems:NavItem[]=[
  {id:'overview',label:'Overview',icon:'overview'},
  {id:'screening',label:'Screening',icon:'screening'},
  {id:'library',label:'Case library',icon:'library'},
  {id:'evidence',label:'Evidence archive',icon:'evidence'},
];
export function WorkspaceIcon({name}:{name:IconName}){
  const paths:Record<IconName,ReactNode>={
    overview:<><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    screening:<><path d="M4 7h16v13H4zM4 7l2-4h16l-2 4M10 3l-2 4m9-4-2 4"/><path d="m10 11 5 3-5 3z"/></>,
    library:<><rect x="4" y="4" width="5" height="16" rx="1"/><rect x="12" y="4" width="5" height="16" rx="1"/><path d="m19 5 2 14M4 9h5m3 0h5"/></>,
    evidence:<><path d="M6 3h9l4 4v14H6zM14 3v5h5M9 12h7m-7 4h7"/></>,
    new:<><rect x="3" y="3" width="18" height="18" rx="4"/><path d="M12 7v10M7 12h10"/></>,
    recorded:<><circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4z"/></>,
  };
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
export function WorkspaceShell({children,active,title,publicMode=false,onNavigate,items=defaultItems,homeId='new',savedCasesTarget='saved-cases'}:{children:ReactNode;active:string;title:string;publicMode?:boolean;onNavigate?:(id:string)=>void;items?:NavItem[];homeId?:string;savedCasesTarget?:string}){
  function showDiscovery(view:'discover'|'history'){
    onNavigate?.(homeId);
    if(homeId==='wide')window.dispatchEvent(new CustomEvent('affinityqa:wide-view',{detail:view}));
    if(view==='history')requestAnimationFrame(()=>document.getElementById(savedCasesTarget)?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'}));
  }
  if(publicMode)return <div className="app public-cinema">
    <a className="skip-link" href="#main-content" onClick={event=>{event.preventDefault();document.getElementById('main-content')?.focus();}}>Skip to content</a>
    <header className="cinema-topbar">
      <a className="cinema-brand" href="#recorded" onClick={onNavigate?event=>{event.preventDefault();onNavigate('recorded');}:undefined} aria-label="AffinityQA home">
        <svg viewBox="0 0 32 32" className="cinema-logo" aria-hidden="true"><path d="m9 23 8-15 10 16M9 23l18 1" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/><circle cx="8" cy="24" r="5" fill="#4a9eff"/><circle cx="18" cy="7" r="5" fill="#659cff"/><circle cx="27" cy="24" r="5" fill="#9b80f9"/></svg>
        <span>Affinity<span>QA</span></span><small className="gemini-brand-tag">AGENT EVALUATION</small>
      </a>
      <nav className="cinema-navigation" aria-label="Main navigation">
        <div className="cinema-primary-navigation">
          <a href="#recorded" aria-label="DIAGNOSIS & EVIDENCE" aria-current={active==='recorded'?'page':undefined} onClick={onNavigate?event=>{event.preventDefault();onNavigate('recorded');}:undefined}>DIAGNOSIS &amp; EVIDENCE</a>
          <a href={'#'+homeId} aria-label={items.find(item=>item.id===homeId)?.label??'Discover'} aria-current={active===homeId?'page':undefined} onClick={event=>{event.preventDefault();showDiscovery('discover');}}>FILM DISCOVERY</a>
          <a href={'#'+homeId} onClick={event=>{event.preventDefault();showDiscovery('history');}}>SAVED</a>
        </div>
        <div className="cinema-legacy-navigation">{items.filter(item=>item.id!==homeId&&item.id!=='recorded').map(item=><a key={item.id} href={'#'+item.id} aria-current={active===item.id?'page':undefined} onClick={onNavigate?event=>{event.preventDefault();onNavigate(item.id);}:undefined}>{item.label}</a>)}</div>
      </nav>
    </header>
    <main id="main-content" className="workspace-main cinema-main" tabIndex={-1} aria-label={title}>{children}</main>
    <footer className="cinema-footer"><p>Qloo context · AI selection · evidence before approval. Card artwork is original and decorative. Independent cultural evaluation remains pending.</p><a href="https://github.com/seypherWork/affinityqa" target="_blank" rel="noreferrer">SOURCE &amp; METHOD ↗</a></footer>
  </div>;
  return <div className="app workspace">
    <a className="skip-link" href="#main-content" onClick={event=>{event.preventDefault();document.getElementById('main-content')?.focus();}}>Skip to content</a>
    <aside className="workspace-rail" aria-label="Workspace">
      <a className="workspace-brand" href={publicMode?'/demo':'#overview'} onClick={onNavigate?event=>{event.preventDefault();onNavigate(items[0].id);}:undefined} aria-label="AffinityQA home"><Mark/><span>Affinity<span>QA</span><small>AGENT EVALUATION STUDIO</small></span></a>
      <div className="workspace-project"><span className="project-avatar">AQ</span><div><strong>Music → movies</strong><small>{publicMode?'Jury workspace':'Local workspace'}</small></div><span className="project-lock" aria-label={publicMode?'Public demo':'Local review'}>{publicMode?'↗':'⌑'}</span></div>
      <span className="rail-label">WORKSPACE</span>
      <nav className="workspace-navigation" aria-label="Main navigation">{items.map(item=><a key={item.id} href={'#'+item.id} aria-current={active===item.id?'page':undefined} onClick={onNavigate?event=>{event.preventDefault();onNavigate(item.id);}:undefined}><WorkspaceIcon name={item.icon}/><span>{item.label}</span>{active===item.id&&<i aria-hidden="true"/>}</a>)}</nav>
      <div className="rail-method"><span className="rail-label">THE REVIEW METHOD</span><ol>{['Detect the fault','Diagnose the cause','Apply the repair','Verify the recovery'].map((step,i)=><li key={step}><span>{i+1}</span>{step}</li>)}</ol><p>Causal integrity and cultural quality are evaluated separately.</p></div>
      <div className="rail-bottom"><span className="rail-provider"><span className="provider-mark">Q</span><div><strong>Qloo reference data</strong><small>Inspect the evidence behind every gate</small></div></span><a href="https://github.com/seypherWork/affinityqa" target="_blank" rel="noreferrer">Source & documentation <span aria-hidden="true">↗</span></a></div>
    </aside>
    <div className="workspace-body"><header className="workspace-topbar"><div className="workspace-breadcrumb"><span>WORKSPACE</span><span aria-hidden="true">/</span><strong>{title}</strong></div><span className="workspace-environment"><i aria-hidden="true"/>{publicMode?'JURY DEMO':'LOCAL REVIEW'}</span></header>
      <main id="main-content" className="workspace-main" tabIndex={-1}>{children}</main>
      <footer className="workspace-footer"><span>AffinityQA · Evidence before approval</span><span>Qloo is a cultural reference, not individual ground truth.</span></footer>
    </div>
  </div>;
}


function ContextGuideIcon({name}:{name:'profile'|'context'|'agent'}){
  const paths:Record<typeof name,ReactNode>={
    profile:<><circle cx="12" cy="7" r="3"/><path d="M5 21v-2a7 7 0 0 1 14 0v2z"/></>,
    context:<><path d="M6 3h8l4 4v14H6zM13 3v5h5M9 12h6m-6 4h6"/></>,
    agent:<><rect x="4" y="7" width="16" height="13" rx="4"/><path d="M12 3v4M9 15h6M1 11v5m22-5v5"/><circle cx="9" cy="11" r=".6"/><circle cx="15" cy="11" r=".6"/></>,
  };
  return <svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function ContextFlowGuide(){
  return <figure className="context-guide" aria-label="Illustrative context-binding diagram, not a case result">
    <figcaption>CONTEXT INTEGRITY <span>ILLUSTRATIVE EXAMPLE</span></figcaption>
    {(['before','after'] as const).map(route=><div className="context-guide-route" data-route={route} key={route}>
      <span>{route==='before'?'BEFORE REPAIR':'AFTER REPAIR'}</span>
      <div className="context-guide-nodes">
        <div className="context-guide-node"><i><ContextGuideIcon name="profile"/></i><div><small>PROFILE</small><strong>USER A</strong></div></div>
        <div className="context-guide-node" data-mismatch={route==='before'} data-repaired={route==='after'}><i><ContextGuideIcon name="context"/></i><div><small>QLOO CONTEXT</small><strong>PROFILE {route==='before'?'B':'A'}</strong></div></div>
        <div className="context-guide-node"><i><ContextGuideIcon name="agent"/></i><div><small>AGENT</small><strong>OUTPUT</strong></div></div>
      </div>
    </div>)}
  </figure>;
}
