import {ContextContrast,contrastChecks} from '../lib/context-contrast';
import styles from './qloo-repair-proof.module.css';

export function QlooContextContrast({proof,beforeTool,afterTool}:{proof:ContextContrast;beforeTool:string;afterTool:string}){
  if(proof.status==='NOT_APPLICABLE')return null;
  const available=proof.status==='CONTRAST_AVAILABLE',m=proof.metrics;
  return <section className={styles.root} aria-label="Recorded Qloo context contrast">
    <div className={styles.heading}><div><span className={styles.kicker}>ONE CONTROLLED CONTEXT SWAP</span><h3>WHAT DID QLOO CHANGE?</h3></div><strong data-pass={available}>{available?'INPUTS CONTROLLED':'COMPARISON UNAVAILABLE'}</strong></div>
    {available&&m?<>
      <p>Same interest, task, movies, model and output format. Only the Qloo context changed in the recorded model input.</p>
      <div className={styles.cards}>
        <section><span className={styles.number}>QLOO CONTEXT</span><h4>{beforeTool} → {afterTool}</h4><p>From another interest to the requested interest.</p></section>
        <section><span className={styles.number}>DISPLAYED FILMS</span><h4>{m.changed_top_five} OF 5 CHANGED</h4><p>{m.top_five_order_changed?'The displayed list changed.':'The displayed list stayed the same.'}</p></section>
        <section><span className={styles.number}>RECORDED RECOVERY</span><h4>{m.recovery_verified?'WITHIN HEALTHY RANGE':'OUTSIDE HEALTHY RANGE'}</h4><p>{m.recovery_observed?'The incorrect route was outside that range before correction.':'Recovery is checked separately from whether the context changed the result.'}</p></section>
      </div>
      <h4>{proof.behavioral_effect==='OBSERVED_CHANGE'?'CHANGE ABOVE RECORDED VARIATION':'NO EFFECT ABOVE RECORDED VARIATION'}</h4>
      <p className={styles.boundary}>{proof.behavioral_effect==='OBSERVED_CHANGE'?'This saved comparison shows a response to the Qloo context swap.':'This saved comparison does not establish an effect beyond the original variation.'}</p>
    </>:<p>Another input or a required control differs. No change is attributed to Qloo in this comparison.</p>}
    <details className={styles.details}><summary>INSPECT THE CONTROLLED COMPARISON</summary><ul>{Object.entries(contrastChecks).map(([key,label])=><li key={key}><span>{label}</span><strong data-pass={proof.checks?.[key as keyof typeof contrastChecks]}>{proof.checks?.[key as keyof typeof contrastChecks]?'PASS':'NOT ESTABLISHED'}</strong></li>)}</ul></details>
    <p className={styles.boundary}>Matching versus mismatched Qloo context, using saved decisions. This does not compare Qloo with no Qloo, explain the model’s internal reasoning or validate personal taste. No new provider calls.</p>
  </section>;
}
