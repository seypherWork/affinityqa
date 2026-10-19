import {DiagnosticEvidence,evidenceChecks,repairCopy} from '../lib/diagnostic-evidence';
import styles from './qloo-repair-proof.module.css';

export function QlooRepairProof({proof,requested,beforeTool,afterTool}:{proof:DiagnosticEvidence;requested:string;beforeTool:string;afterTool:string}){
  const copy=repairCopy[proof.diagnosis];
  return <section className={styles.root} aria-label="Verified Qloo diagnosis and repair">
    <div className={styles.heading}><div><span className={styles.kicker}>QLOO CONTEXT · OBSERVED REPAIR</span><h3>WHAT FAILED. WHAT CHANGED.</h3></div><strong data-pass={proof.status==='VERIFIED'}>{proof.status==='VERIFIED'?'EVIDENCE CHECKED':'VERIFICATION INCOMPLETE'}</strong></div>
    <div className={styles.cards}>
      <section><span className={styles.number}>01 / BEFORE</span><h4>TRACE THE INPUT</h4><p>{copy.reason}</p><dl><div><dt>Requested interest</dt><dd>{requested}</dd></div><div><dt>Observed Qloo context</dt><dd>{beforeTool}</dd></div></dl></section>
      <section><span className={styles.number}>02 / CORRECTION</span><h4>CHANGE ONE SETTING</h4><p>{copy.action}</p><p className={styles.note}>The repair is approved only after the saved response, agent input and decision agree.</p></section>
      <section><span className={styles.number}>03 / AFTER</span><h4>CHECK THE RECOVERY</h4><p>{proof.checks.requested_context_restored?'Each profile now uses its own Qloo context.':'Profile recovery has not been verified.'}</p><dl><div><dt>Requested interest</dt><dd>{requested}</dd></div><div><dt>Repaired Qloo context</dt><dd>{afterTool}</dd></div></dl><p className={styles.note}>A valid cached decision must still work for the same profile.</p></section>
    </div>
    <details className={styles.details}><summary>INSPECT THE EIGHT EVIDENCE CHECKS</summary><ul>{Object.entries(evidenceChecks).map(([key,label])=><li key={key}><span>{label}</span><strong data-pass={proof.checks[key as keyof typeof evidenceChecks]}>{proof.checks[key as keyof typeof evidenceChecks]?'PASS':'FAIL'}</strong></li>)}</ul></details>
    <p className={styles.boundary}>Runs now with saved decisions. No new Qloo or model calls. These checks establish input integrity and recovery; cultural recommendation quality remains unvalidated.</p>
  </section>;
}
