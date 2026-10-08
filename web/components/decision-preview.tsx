import {useState} from 'react';
import type {ReviewCase} from '../lib/review';
import {score,signed} from '../lib/review';
import {Arrow,Pill} from './primitives';

export function DecisionPreview({item,openCase}:{item:ReviewCase;openCase:(id:string,stage?:number)=>void}){
  const [version,setVersion]=useState<'before'|'after'>('after');
  const p=item.views[0].profiles.B;
  const films=p[version],value=version==='after'?p.after_agreement:p.before_agreement;
  const delta=p.after_agreement-p.before_agreement;
  return <section className="evidence-panel evidence-preview" aria-labelledby="decision-preview-title">
    <header className="evidence-preview-heading"><div><span className="eyebrow">Historical case / Recorded decision</span><h2 id="decision-preview-title">Decision comparison</h2><p>Inspect the original response and the repaired ranking for the same profile.</p></div><button className="text-link" onClick={()=>openCase(item.id,3)}>Inspect case <Arrow diagonal/></button></header>
    <div className="evidence-preview-meta"><div><span>Case</span><strong>{item.id}</strong></div><div><span>Artist interest</span><strong>{p.artist}</strong></div><div><span>Recorded view</span><strong>Repeat 1 · Profile B</strong></div><Pill tone={item.outcome==='MIXED'?'warning':'neutral'}>{item.outcome.replaceAll('_',' ')}</Pill></div>
    <div className="evidence-preview-body">
      <div className="evidence-preview-ranking">
        <div className="evidence-preview-controls"><h3>Agent top five</h3><div className="preview-version" role="group" aria-label="Preview agent version"><button aria-pressed={version==='before'} onClick={()=>setVersion('before')}>Before</button><button aria-pressed={version==='after'} onClick={()=>setVersion('after')}>After repair</button></div></div>
        <p className="evidence-preview-source">{version==='before'?'Original response reused from '+item.artists.A:'Response recomputed for this profile'}</p>
        <ol className="evidence-preview-films">{films.map((film,i)=><li key={film.id}><span className="evidence-preview-rank">{String(i+1).padStart(2,'0')}</span><strong>{film.title}</strong><small>{film.year}</small></li>)}</ol>
      </div>
      <aside className="evidence-preview-score" aria-label="Recorded ranking agreement"><span className="eyebrow">Qloo agreement</span><strong className="evidence-preview-value">{score(value)}</strong>
        {version==='after'?<><span className={delta<0?'evidence-preview-loss':delta>0?'evidence-preview-gain':'evidence-preview-unchanged'}>{signed(delta)} change</span><p>{delta<0?'Agreement fell after repair.':delta>0?'Agreement rose after repair.':'Agreement was unchanged after repair.'}</p></>:<p>The original response used another profile’s cache.</p>}
        <p className="metric-note">Reference agreement is separate from human preferences and satisfaction.</p>
      </aside>
    </div>
    <footer className="evidence-preview-footer"><span>Recorded decisions · no new inference</span><strong>Release not validated</strong></footer>
  </section>;
}