import {useState} from 'react';
import type {Snapshot} from '../lib/review';
import {isMixed,score,signed,serial} from '../lib/review';
import {Arrow,Pill} from './primitives';

export function Library({data,openCase}:{data:Snapshot;openCase:(id:string)=>void}){
  const [query,setQuery]=useState(''),[filter,setFilter]=useState('all');
  const cases=data.cases.filter(c=>(filter==='all'||(filter==='mixed'?isMixed(c):!isMixed(c)))&&[c.id,c.artists.A,c.artists.B].join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <section className="section-page library-page">
    <header className="library-header"><div><span className="eyebrow">03 / Historical cache-isolation study</span><h1>Case library</h1><p>All {data.case_count} recorded pairs and every outcome. Current profile-integrity cases remain in the Screening room.</p></div><Pill tone="neutral">Recorded evidence</Pill></header>
    <div className="library-toolbar">
      <div className="filter-group" role="group" aria-label="Filter cases">{[['all','All cases',data.case_count],['gain','Consistent gain',data.counts.OBSERVED_AGREEMENT_IMPROVEMENT??0],['mixed','Mixed result',data.counts.MIXED??0]].map(([id,label,count])=><button key={id} aria-pressed={filter===id} onClick={()=>setFilter(String(id))}>{label}<span>{count}</span></button>)}</div>
      <label className="search-field"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="6" stroke="currentColor" strokeWidth="1.5"/><path d="m15 15 5 5" stroke="currentColor" strokeWidth="1.5"/></svg><input type="search" aria-label="Search case IDs or artist names" placeholder="Search cases or artists…" value={query} onChange={e=>setQuery(e.target.value)}/></label>
    </div>
    <div className="library-results"><span role="status">{cases.length} of {data.case_count} cases</span><span>Qloo-reference agreement · recorded paired comparisons</span></div>
    <div className="library-table-wrap" tabIndex={0} role="region" aria-label="Historical cases; scroll horizontally to inspect every column"><table className="library-table">
      <caption className="library-table-caption">Historical cases and observed outcomes</caption>
      <thead><tr><th scope="col">Case</th><th scope="col">Artist profiles</th><th scope="col">Paired agreement change</th><th scope="col">Reference noise</th><th scope="col">Cache isolation</th><th scope="col">Outcome</th><th scope="col"><span className="library-action-label">Review</span></th></tr></thead>
      <tbody>{cases.map(item=>{const index=data.cases.indexOf(item);return <tr key={item.id}>
        <td><span className="library-case-number">{serial(index)}</span><strong className="library-case-id">{item.id}</strong></td>
        <td><div className="library-profiles"><strong>{item.artists.A}</strong><span aria-hidden="true">→</span><strong>{item.artists.B}</strong></div></td>
        <td><strong className="library-metric-value">{signed(item.delta.median)}</strong><span className="library-cell-detail">Range {signed(item.delta.min)} to {signed(item.delta.max)}</span></td>
        <td><span className="library-metric-value">{score(item.reference_noise)}</span></td>
        <td><Pill tone={item.structural_gate==='PASS'?'pass':'fail'}>{item.structural_gate}</Pill></td>
        <td><span title={item.outcome}><Pill tone={isMixed(item)?'warning':'neutral'}>{item.outcome==='OBSERVED_AGREEMENT_IMPROVEMENT'?'Consistent gain':item.outcome==='MIXED'?'Mixed result':item.outcome.replaceAll('_',' ')}</Pill></span></td>
        <td><button className="library-review-action text-link" onClick={()=>openCase(item.id)} aria-label={'Review '+item.id+': '+item.artists.A+' and '+item.artists.B}>Review <Arrow diagonal/></button></td>
      </tr>})}</tbody>
    </table></div>
    {cases.length===0&&<div className="empty-state"><h2>No matching cases</h2><p>Try another case ID or artist, or reset the filters.</p><button className="button outline" onClick={()=>{setQuery('');setFilter('all')}}>Show all {data.case_count} cases <Arrow/></button></div>}
    <p className="library-footnote">The full denominator stays visible. Paired changes compare the mean agreement of two profiles. They are not satisfaction percentages or independent user trials.</p>
  </section>;
}
