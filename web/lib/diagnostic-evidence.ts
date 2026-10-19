export const evidenceChecks = {
  raw_qloo_request_bound:'Interest and movie catalog match the Qloo request',
  raw_qloo_response_bound:'Saved response content is intact',
  context_projection_bound:'Agent context matches the saved Qloo response',
  model_payload_bound:'Model input contains that exact context',
  observed_trace_bound:'Decision and observed trace match the execution',
  supported_transition_verified:'Only the supported adapter setting changed',
  requested_context_restored:'Both profiles use their own Qloo context after repair',
  legitimate_cache_bound:'Valid cache reuse remains bound to its profile',
} as const;
export const repairCopy = {
  CACHE_OMITS_PROFILE:{operation:'set-profile-cache',reason:'A cached decision was reused for a different musical interest.',action:'Include the musical profile in the cache key, then clear the affected cache.'},
  STALE_PROFILE:{operation:'restore-request-profile',reason:'The model received the previous musical profile and its Qloo context.',action:'Pass the current requested profile and its matching Qloo context.'},
  WRONG_TOOL_PROFILE:{operation:'bind-request-tool',reason:'The current musical profile received another profile’s Qloo context.',action:'Bind the Qloo context to the current requested profile.'},
} as const;
export type Diagnosis = keyof typeof repairCopy;
export type DiagnosticEvidence = {schema_version:1;source:'saved-qloo-semantic-check';status:'VERIFIED'|'NOT_VERIFIED';diagnosis:Diagnosis;operation:string;checks:Record<keyof typeof evidenceChecks,boolean>};
type ReplayProof = {schema_version?:number;diagnosis:string;repair:string;fault:string;status:string;diagnostic_evidence?:DiagnosticEvidence};
const faults:Record<string,Diagnosis> = {'cache-omits-profile':'CACHE_OMITS_PROFILE','stale-profile':'STALE_PROFILE','wrong-tool-profile':'WRONG_TOOL_PROFILE'};
export function acceptsDiagnosticEvidence(value:ReplayProof, requiredVersion?:number):boolean {
  // A backend advertising v2 cannot silently downgrade its semantic evidence.
  if(value.schema_version===1)return requiredVersion!==2 && !('diagnostic_evidence' in value);
  if(value.schema_version!==2 || !value.diagnostic_evidence)return false;
  const proof=value.diagnostic_evidence;
  const keys=['schema_version','source','status','diagnosis','operation','checks'];
  if(typeof proof!=='object'||Object.keys(proof).length!==keys.length||keys.some(key=>!(key in proof))
    ||proof.schema_version!==1||proof.source!=='saved-qloo-semantic-check'
    ||!Object.hasOwn(repairCopy,proof.diagnosis)||faults[value.fault]!==proof.diagnosis
    ||proof.diagnosis!==value.diagnosis||proof.operation!==value.repair
    ||proof.operation!==repairCopy[proof.diagnosis].operation
    ||typeof proof.checks!=='object'||proof.checks===null
    ||Object.keys(proof.checks).length!==Object.keys(evidenceChecks).length
    ||Object.keys(evidenceChecks).some(key=>typeof proof.checks[key as keyof typeof evidenceChecks]!=='boolean'))return false;
  const verified=Object.values(proof.checks).every(pass=>pass===true);
  return proof.status===(verified?'VERIFIED':'NOT_VERIFIED') && (value.status!=='PASS'||verified);
}
