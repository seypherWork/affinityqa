import type {Snapshot} from '../lib/review';
import {Arrow,Pill} from './primitives';
import {OrderingDevelopment} from './ordering-development';
import {IndividualDevelopment} from './individual-development';
import {RepairLearning} from './repair-learning';
import {ContextExtensions} from './context-extensions';
import {MetadataDevelopment} from './metadata-development';

const contextCheckNames:Record<string,string>={
  reference_informative:'Informative reference',
  no_profile_loss:'No profile loss',
  benefit_beyond_instructions:'Benefit beyond instructions',
  beats_swapped_context:'Better than swapped context',
  stable:'Stable repeats',
};

export function Evidence({data,openScreening}:{data:Snapshot;openScreening:()=>void}){
  return <section className="section-page evidence-page">
    <header className="evidence-header"><div><span className="eyebrow">04 / Verified records and preserved experiments</span><h1>Evidence archive</h1><p>Inspect recorded inputs, acceptance checks and outcomes, including every rejected candidate.</p></div><a className="button outline" href="/api/review" target="_blank" rel="noreferrer">Open review data <Arrow diagonal/></a></header>

    <section className="evidence-panel evidence-current" aria-labelledby="evidence-current-title">
      <div className="evidence-panel-heading"><div><span className="eyebrow">Current / Causal profile integrity</span><h2 id="evidence-current-title">Faults, repairs and verification</h2><p>Inspect the observed fault, supported repair and the verifier’s result.</p></div><div className="evidence-actions"><button className="button primary" onClick={openScreening}>Open current screening <Arrow/></button><a className="text-link" href="/api/causal-repair" target="_blank" rel="noreferrer">Current evidence <Arrow diagonal/></a></div></div>
      <p className="metric-note">The historical experiments below retain their original quality failures. A current causal result does not change those outcomes.</p>
    </section>

    <section className="evidence-panel evidence-historical" aria-labelledby="evidence-historical-title">
      <div className="evidence-panel-heading"><div><span className="eyebrow">Historical / Complete denominator</span><h2 id="evidence-historical-title">Quality results remain visible</h2><p>Preserved experiments are separate from the current profile-integrity protocol.</p></div><Pill tone="warning">Release not validated</Pill></div>
      {(data.repair_study||data.value_study)&&<div className="evidence-table-wrap"><table className="evidence-table"><thead><tr><th scope="col">Historical experiment</th><th scope="col">All-control passes</th><th scope="col">Sample gate</th><th scope="col">Recorded run</th></tr></thead><tbody>
        {data.repair_study&&<tr><th scope="row">Multiview validation</th><td>{data.repair_study.passing_cases} / {data.repair_study.denominator}</td><td><Pill tone={data.repair_study.sample_gate==='PASS'?'pass':'fail'}>{data.repair_study.sample_gate}</Pill></td><td className="evidence-id">{data.repair_study.run_id}</td></tr>}
        {data.value_study&&<tr><th scope="row">Affinity-aware repair</th><td>{data.value_study.passing_cases} / {data.value_study.denominator}</td><td><Pill tone={data.value_study.sample_gate==='PASS'?'pass':'fail'}>{data.value_study.sample_gate}</Pill></td><td className="evidence-id">{data.value_study.run_id}</td></tr>}
      </tbody></table></div>}
    </section>

    <div className="evidence-grid">
      <section className="evidence-panel" aria-labelledby="experiment-record-title">
        <div className="evidence-panel-heading"><div><span className="eyebrow">Earlier / Cache-isolation study</span><h2 id="experiment-record-title">Experiment record</h2></div><span className="evidence-record-index">001</span></div>
        <p>Local model decisions were sealed before capturing the Qloo references. All {data.case_count} reserved cases remain in the record.</p>
        <dl className="evidence-record">
          <div><dt>Agent model</dt><dd>{data.model}</dd></div>
          <div><dt>Fixed evaluation catalog</dt><dd>20 movies</dd></div>
          <div><dt>Reserved pairs</dt><dd>{data.case_count} · three repeats each</dd></div>
          <div><dt>Qloo requests</dt><dd>{data.reference_calls} · no retry</dd></div>
          <div><dt>Local model decisions</dt><dd>{data.model_calls} · development, controls and reserved</dd></div>
          <div><dt>Recorded verification</dt><dd>{new Date(data.verified_utc).toLocaleString('en-GB',{timeZone:'Europe/Brussels'})} · Brussels</dd></div>
        </dl>
      </section>
      <section className="evidence-panel" aria-labelledby="evidence-boundaries-title">
        <div className="evidence-panel-heading"><div><span className="eyebrow">Interpretation</span><h2 id="evidence-boundaries-title">Evidence boundaries</h2></div></div>
        <ul className="evidence-boundaries">
          <li><strong>Qloo is a cultural reference.</strong><span>Agreement does not establish an individual’s preferences or satisfaction.</span></li>
          <li><strong>Repeated observations are paired.</strong><span>The 27 combinations per case are not 27 independent trials.</span></li>
          <li><strong>The defect was deliberately injected.</strong><span>Cache isolation is verified separately from recommendation quality.</span></li>
          <li><strong>A release threshold remains pending.</strong><span>These recorded outcomes do not certify a production release.</span></li>
        </ul>
      </section>
    </div>

    <details className="evidence-panel evidence-disclosure">
      <summary><div><span className="eyebrow">Operational disclosure</span><strong>Review mode and evidence handling</strong></div><span className="detail-toggle" aria-hidden="true">+</span></summary>
      <dl className="evidence-record"><div><dt>Review mode</dt><dd>{data.mode.replaceAll('_',' ')}</dd></div><div><dt>New live calls in this review</dt><dd>{data.new_live_calls}</dd></div></dl>
      <p>Historical outcomes are replayed from recorded artifacts. Replaying a result is separate from executing a new provider-backed case.</p>
      <p className="metric-note">Evaluator-only reference data must remain outside agent inputs. An artifact fingerprint identifies recorded bytes; it does not establish human preference quality.</p>
    </details>

    <div className="evidence-development-stack">
      {data.metadata_development&&<MetadataDevelopment study={data.metadata_development}/>}
      {data.context_extensions&&<ContextExtensions study={data.context_extensions}/>}
      {data.repair_learning&&<RepairLearning study={data.repair_learning}/>}
      {data.individual_development&&<IndividualDevelopment study={data.individual_development}/>}
      {data.ordering_development&&<OrderingDevelopment study={data.ordering_development}/>}
    </div>

    {data.context_study&&<section className="evidence-panel evidence-section" aria-labelledby="context-study-title">
      <div className="evidence-panel-heading"><div><span className="eyebrow">Rejected / Context experiments</span><h2 id="context-study-title">Additional context did not pass</h2></div><Pill tone="fail">Development rejected</Pill></div>
      <p>Five Qloo examples per profile, all outside the evaluation catalog. Four conditions: original, instructions alone, correct context and swapped context.</p>
      <div className="evidence-candidates">{data.context_study.candidates.map(c=><article className="evidence-candidate" key={c.index}>
        <div className="evidence-candidate-heading"><div><span className="eyebrow">Development candidate / 0{c.index}</span><h3>{c.index===1?'Context-guided ranking':'Conservative ranking review'}</h3></div><Pill tone={c.candidate_gate==='REJECTED_DEVELOPMENT_CANDIDATE'?'fail':'warning'}>{c.candidate_gate==='REJECTED_DEVELOPMENT_CANDIDATE'?'Rejected':'Needs review'}</Pill></div>
        <p>{c.index===1?'Improved one development pair but reduced agreement for Björk. A gain elsewhere did not excuse the profile loss.':'Kept the original top-five decisions. No measured benefit beyond instructions alone or swapped context.'}</p>
        <details className="evidence-checks"><summary>Acceptance checks <span aria-hidden="true">+</span></summary>{c.cases.map(item=><div className="evidence-check-group" key={item.pair_id}><h4>{item.pair_id==='mutation-01'?'Brian Eno / Bad Bunny':'Björk / Taylor Swift'}</h4><table className="evidence-check-table"><thead><tr><th scope="col">Check</th><th scope="col">Result</th></tr></thead><tbody>{Object.entries(item.checks).map(([key,passed])=><tr key={key}><th scope="row">{contextCheckNames[key]??key}</th><td className={passed?'check-pass':'check-fail'}>{passed?'Met':'Not met'}</td></tr>)}</tbody></table></div>)}</details>
      </article>)}</div>
      <div className="context-totals"><span><strong>{data.context_study.reference_calls}</strong> Qloo requests</span><span><strong>{data.context_study.model_calls}</strong> Local decisions</span><span><strong>{data.context_study.reserved_inputs_executed}</strong> New reserved profiles executed</span></div>
      <p className="metric-note">The two-attempt development study is closed. Neither candidate changed the cache repair. The later multiview repair subsequently executed the six new pairs; they are now exposed.</p>
    </section>}

    {data.semantic_study&&<section className="evidence-panel evidence-section" aria-labelledby="semantic-study-title">
      <div className="evidence-panel-heading"><div><span className="eyebrow">Rejected / Alternative repair mechanism</span><h2 id="semantic-study-title">Semantic transfer</h2></div><Pill tone="fail">Rejected</Pill></div>
      <p>Recorded film descriptions, local embeddings and fixed rank fusion. One candidate, with neutral and swapped-context controls.</p>
      <div className="evidence-alert"><strong>Profile loss prevented acceptance.</strong><p>Brian Eno / Bad Bunny gained 0.026 in mean agreement. Björk lost 0.099 despite a positive pair average. The candidate failed its predeclared checks.</p></div>
      <details className="evidence-checks"><summary>Semantic acceptance checks <span aria-hidden="true">+</span></summary>{data.semantic_study.cases.map(c=><div className="evidence-check-group" key={c.pair_id}><h4>{c.pair_id==='mutation-01'?'Brian Eno / Bad Bunny':'Björk / Taylor Swift'}</h4><table className="evidence-check-table"><thead><tr><th scope="col">Check</th><th scope="col">Result</th></tr></thead><tbody>{Object.entries(c.checks).map(([key,passed])=><tr key={key}><th scope="row">{key.replaceAll('_',' ')}</th><td className={passed?'check-pass':'check-fail'}>{passed?'Met':'Not met'}</td></tr>)}</tbody></table></div>)}</details>
      <div className="context-totals"><span><strong>{data.semantic_study.embedding_calls}</strong> Local embedding batches</span><span><strong>0</strong> New Qloo requests</span><span><strong>{data.semantic_study.reserved_inputs_executed}</strong> Reserved profiles executed</span></div>
      <p className="metric-note">At the time of this rejected semantic study, the six new pairs were unused. They were subsequently tested once after the multiview policy was frozen.</p>
    </section>}

    {data.repair_study&&<section className="evidence-panel evidence-section" aria-labelledby="multiview-study-title">
      <div className="evidence-panel-heading"><div><span className="eyebrow">Historical / Multiview validation</span><h2 id="multiview-study-title">Multiview repair remains blocked</h2></div><Pill tone={data.repair_study.sample_gate==='PASS'?'pass':'fail'}>{data.repair_study.sample_gate}</Pill></div>
      <p>Six new artist pairs, one frozen global policy, indirect movie and artist context. Direct references were requested only after all candidate rankings were sealed.</p>
      <div className="context-totals"><span><strong>{data.repair_study.passing_cases} / {data.repair_study.denominator}</strong> All-control passes</span><span><strong>{data.repair_study.model_calls}</strong> Model decisions</span><span><strong>{data.repair_study.reference_calls}</strong> Qloo requests</span></div>
      <div className="evidence-alert"><strong>All cases remain in the denominator.</strong><p>Ryuichi Sakamoto / Doja Cat missed the pooled-context benefit threshold. Massive Attack / Shakira failed profile-loss and pooled-context checks. The overall candidate is rejected.</p></div>
      <p className="metric-note">These inputs are now exposed. This original rejection is preserved. Integrity correction: Ryuichi Sakamoto also appeared as 坂本龍一 under a second ID in the artist context. This historical study does not establish fully disjoint context. Subsequent development is separate from the newer reserved trial.</p>
      <a className="button outline" href="#screening" onClick={event=>{event.preventDefault();openScreening()}}>Open screening <Arrow/></a>
    </section>}

    {data.value_study&&<section className="evidence-panel evidence-section" aria-labelledby="affinity-study-title">
      <div className="evidence-panel-heading"><div><span className="eyebrow">Historical / Affinity-aware repair</span><h2 id="affinity-study-title">Identity-amended frozen sample</h2></div><Pill tone={data.value_study.sample_gate==='PASS'?'pass':'fail'}>{data.value_study.sample_gate}</Pill></div>
      <p>Thirty bounded development candidates, eight exposed pairs. One policy passed every development check and was frozen before six new pairs.</p>
      <div className="context-totals"><span><strong>{data.value_study.development_passes} / {data.value_study.development_denominator}</strong> Development cases passed</span><span><strong>{data.value_study.passing_cases} / {data.value_study.denominator}</strong> New validation cases passed</span><span><strong>{data.value_study.model_calls}</strong> Local decisions</span><span><strong>{data.value_study.reference_calls}</strong> Qloo requests</span></div>
      <p className="metric-note">The same no-loss, benefit and stability thresholds apply. The repair uses affinity strength from disjoint movie context; it receives no direct evaluation answers. All six new outcomes remain included. Before evaluation, Selena Gomez was explicitly mapped to her Qloo person record with a singer-songwriter occupation; the original interrupted trial and sealed decisions remain preserved. No production release is approved.</p>
      <button className="button outline" onClick={openScreening}>Open current screening <Arrow/></button>
    </section>}

    <section className="evidence-panel evidence-section" aria-labelledby="regression-record-title">
      <div className="evidence-panel-heading"><div><span className="eyebrow">Reusable / Regression record</span><h2 id="regression-record-title">Preserved regression check</h2></div><a className="button outline" href="/api/regression-pack" target="_blank" rel="noreferrer">Open regression pack <Arrow diagonal/></a></div>
      <p>The Sade / Nine Inch Nails pack preserves the full catalog, three reference repeats per profile and the recorded baseline. Missing cases, partial rankings or changed packs stop evaluation.</p>
      <p className="metric-note">Evaluator-only reference data. Keep it out of agent inputs; export requires approval.</p>
    </section>

    <details className="evidence-panel evidence-provenance">
      <summary><div><span className="eyebrow">Provenance</span><strong>Record identifiers and integrity</strong></div><span className="detail-toggle" aria-hidden="true">+</span></summary>
      <p>The server checks recorded artifact fingerprints before serving this review. A changed artifact makes the review unavailable.</p>
      <div className="evidence-table-wrap"><table className="evidence-table"><thead><tr><th scope="col">Record</th><th scope="col">Identifier or fingerprint</th></tr></thead><tbody><tr><th scope="row">Run</th><td className="evidence-hash">{data.run_id}</td></tr><tr><th scope="row">Policy fingerprint</th><td className="evidence-hash">{data.policy_hash}</td></tr>{data.cases.map(c=><tr key={c.id}><th scope="row">{c.artists.A} / {c.artists.B}</th><td className="evidence-hash">{c.reference_hash}</td></tr>)}</tbody></table></div>
      <a className="text-link" href="/api/review" target="_blank" rel="noreferrer">Open verified projection <Arrow diagonal/></a>
    </details>
  </section>;
}