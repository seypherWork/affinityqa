export const contrastChecks = {
  saved_decisions_bound:'Both decisions match the saved executions',
  requested_profile_fixed:'Requested interest stayed the same',
  consumed_profile_fixed:'The model received the same interest',
  task_fixed:'Task stayed the same',
  catalog_fixed:'Ordered movie catalog stayed the same',
  output_schema_fixed:'Output format stayed the same',
  tool_notice_fixed:'Tool instructions stayed the same',
  model_manifest_fixed:'Recorded model configuration stayed the same',
  fresh_decisions:'Both routes dispatched separate recorded decisions',
  only_qloo_context_changed:'Only the Qloo context changed in the model input',
  healthy_reference_fixed:'Three recorded healthy controls match the repaired input',
  healthy_variation_within_frozen_noise:'Healthy controls stay within the original variation',
  display_identities_unique:'Displayed titles and years identify distinct catalog films',
} as const;
type Checks=Record<keyof typeof contrastChecks,boolean>;
export type ContrastMetrics={ranking_distance:number;recorded_noise_barrier:number;maximum_after_healthy_distance:number;minimum_before_healthy_distance:number;changed_top_five:number;top_five_order_changed:boolean;recovery_verified:boolean;recovery_observed:boolean};
export type ContextContrast={schema_version:1;source:'saved-qloo-context-contrast';status:'CONTRAST_AVAILABLE'|'CONFOUNDED'|'NOT_APPLICABLE';behavioral_effect:'OBSERVED_CHANGE'|'NO_OBSERVED_EFFECT'|'NOT_EVALUATED';checks:Checks|null;metrics:ContrastMetrics|null};
type Film={position:number;title:string;year:number};
const exact=(value:unknown,keys:string[]):value is Record<string,unknown>=>typeof value==='object'&&value!==null&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
const finite=(value:unknown):value is number=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1;
export function acceptsContextContrast(value:unknown,fault:string,before:Film[],after:Film[]):value is ContextContrast {
  if(!exact(value,['schema_version','source','status','behavioral_effect','checks','metrics'])||value.schema_version!==1||value.source!=='saved-qloo-context-contrast')return false;
  if(fault!=='wrong-tool-profile')return value.status==='NOT_APPLICABLE'&&value.behavioral_effect==='NOT_EVALUATED'&&value.checks===null&&value.metrics===null;
  if(!exact(value.checks,Object.keys(contrastChecks))||Object.values(value.checks).some(check=>typeof check!=='boolean'))return false;
  const all=Object.values(value.checks).every(check=>check===true);
  if(value.status==='CONFOUNDED')return !all&&value.behavioral_effect==='NOT_EVALUATED'&&value.metrics===null;
  if(value.status!=='CONTRAST_AVAILABLE'||!all||!exact(value.metrics,['ranking_distance','recorded_noise_barrier','maximum_after_healthy_distance','minimum_before_healthy_distance','changed_top_five','top_five_order_changed','recovery_verified','recovery_observed']))return false;
  const m=value.metrics;
  if(!finite(m.ranking_distance)||!finite(m.recorded_noise_barrier)||!finite(m.maximum_after_healthy_distance)||!finite(m.minimum_before_healthy_distance)||typeof m.changed_top_five!=='number'||!Number.isInteger(m.changed_top_five)||Number(m.changed_top_five)<0||Number(m.changed_top_five)>5||['top_five_order_changed','recovery_verified','recovery_observed'].some(key=>typeof m[key]!=='boolean'))return false;
  if(!Array.isArray(before)||!Array.isArray(after)||before.length!==5||after.length!==5)return false;
  const identities=(rows:Film[])=>rows.map((film,index)=>typeof film==='object'&&film!==null&&film.position===index+1&&typeof film.title==='string'&&film.title.trim()&&Number.isInteger(film.year)?JSON.stringify([film.title,film.year]):null);
  const left=identities(before),right=identities(after);
  if(left.some(key=>key===null)||right.some(key=>key===null)||new Set(left).size!==5||new Set(right).size!==5)return false;
  const count=5-left.filter(key=>right.includes(key)).length,order=left.some((key,index)=>key!==right[index]);
  if(m.changed_top_five!==count||m.top_five_order_changed!==order||(count>0&&!order)||(order!==(m.ranking_distance>0)))return false;
  const threshold=m.recorded_noise_barrier+1e-12,observed=m.ranking_distance>threshold,recovered=m.maximum_after_healthy_distance<=threshold;
  return value.behavioral_effect===(observed?'OBSERVED_CHANGE':'NO_OBSERVED_EFFECT')&&m.recovery_verified===recovered&&m.recovery_observed===(observed&&recovered&&m.minimum_before_healthy_distance>threshold);
}
