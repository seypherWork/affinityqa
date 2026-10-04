import {useState} from 'react';
import type {ExtensionStudy} from '../lib/review';
import {Arrow,Pill} from './primitives';
import styles from './context-extensions.module.css';

const signed=(v:number)=>(v>=0?'+':'')+v.toFixed(6);
export function ContextExtensions({study}:{study:ExtensionStudy}){
  const [selected,setSelected]=useState('interaction-1');
  const [view,setView]=useState<'held'|'full'>('held');
  const experiment=study.experiments.find(e=>e.id===selected)??study.experiments[0];
  const result=view==='held'&&experiment.held?experiment.held:experiment.full;
  return <section className="context-archive" aria-label="Latest context experiments">
    <div className="archive-section-title"><div><span className="eyebrow">LATEST / TWO CLOSED EXPERIMENTS</span><h2>A wider signal.<br/><em>The same hard checks.</em></h2></div><p>Twenty external films per profile and a separate nonlinear combination of the original signals were tested. Neither improves on the earlier 13 / 14 development result. The repair remains blocked.</p></div>
    <div className="context-totals"><span><strong>{study.new_qloo_requests}</strong> New Qloo requests</span><span><strong>{study.fits_verified}</strong> Fits independently checked</span><span><strong>{study.new_model_calls}</strong> New model calls</span><span><strong>{study.new_validation_pairs}</strong> New validation pairs</span></div>
    <Pill tone="coral">Both approaches rejected · no repair deployed</Pill>
    <div className={styles.tableWrap}><table className={styles.table}><caption>Every declared candidate · all {study.denominator} known pairs</caption><thead><tr><th scope="col">Candidate</th><th scope="col">Full fit</th><th scope="col">Excluded pair</th></tr></thead><tbody>{study.experiments.map(e=><tr key={e.id}><th scope="row">{e.label}</th><td>{e.full.passes} / {study.denominator}</td><td>{e.held?`${e.held.passes} / ${study.denominator}`:'Not refitted'}</td></tr>)}</tbody></table></div>
    <details className="integrity-details"><summary><span className="eyebrow">CASE REVIEW</span><strong>Inspect every candidate and failure.</strong></summary>
      <div className="study-selector"><label><span className="eyebrow">CANDIDATE</span><select aria-label="Extension candidate" value={selected} onChange={e=>setSelected(e.target.value)}>{study.experiments.map(e=><option value={e.id} key={e.id}>{e.label}</option>)}</select></label><label><span className="eyebrow">COMPARISON</span><select aria-label="Extension comparison" value={experiment.held?view:'full'} onChange={e=>setView(e.target.value as 'held'|'full')} disabled={!experiment.held}><option value="held">Exclude each pair from its own fit</option><option value="full">Fit using all known pairs</option></select></label></div>
      <p>{result.passes} / {study.denominator} pairs pass every unchanged check. Training used exposed reference labels. Excluded-pair checks remain internal development, not an independent trial.</p>
      {result.cases.filter(c=>!c.passing).map(c=><div className="repair-reasons" key={c.pair_id}><span className="eyebrow">FAIL / {c.artists.A} + {c.artists.B}</span>{(['baseline','neutral_graph'] as const).map(control=>(['A','B'] as const).filter(p=>c.comparisons[control][p].min < -1e-12).map(p=><p key={control+p}>{c.artists[p]}: <strong>{signed(c.comparisons[control][p].min)}</strong> against {control==='baseline'?'the original ranking':'pooled context'}.</p>))}{!c.checks.benefit_beyond_neutral&&<p>Pair gain over pooled context: <strong>{signed(c.minimum_pair_mean_delta.neutral_graph)}</strong>; required +0.020000.</p>}</div>)}
      {result.cases.map(c=><div className="candidate-checks" key={c.pair_id}><strong>{c.artists.A} / {c.artists.B}</strong><Pill tone={c.passing?'neutral':'coral'}>{c.passing?'PASS':'FAIL'}</Pill></div>)}
    </details>
    <details className="integrity-details"><summary><span className="eyebrow">SIGNAL DIAGNOSIS / PATTI SMITH</span><strong>Where the indirect views disagree.</strong></summary><p>The reference puts Moonlight first and The Florida Project third. Both indirect views rank them lower. More context and nonlinear fitting have not repaired that gap; this is a diagnosis of a known case.</p><div className={styles.tableWrap}><table className={styles.table}><caption>Position within the same 20-film catalog · lower is earlier</caption><thead><tr><th scope="col">Film</th><th scope="col">Reference</th><th scope="col">5-film context</th><th scope="col">Related artists</th><th scope="col">20-film context</th></tr></thead><tbody>{study.diagnostic.rows.map(r=><tr key={r.movie}><th scope="row">{r.movie}</th><td>{r.reference_position}</td><td>{r.five_movie}</td><td>{r.artist_mean}</td><td>{r.twenty_movie}</td></tr>)}</tbody></table></div></details>
    <p className="metric-note">All fourteen pairs had already been exposed. Wider context uses one new snapshot against older frozen references; provider stability was not retested. Acceptance thresholds and historical outcomes are unchanged. Latest independent movie-only validation: 4 / 6, FAIL.</p>
    <a className="button outline" href="/api/context-extensions" target="_blank" rel="noreferrer">Open verified experiment record <Arrow diagonal/></a>
  </section>;
}
