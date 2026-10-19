import type {CaseAccess,CaseQueue} from './individual-case';

export const WIDE_BASE='/api/demo/cases';
export const SHA256=/^[a-f0-9]{64}$/;
export const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
export const CASE_ID=/^[a-zA-Z0-9_-]{1,160}$/;
export type DiscoveryMode='movie'|'music';
export type Movie={entity_id:string;name:string;release_year:number};
export type Identity={entity_id:string;name:string;type:string;release_year?:number|null};
export type PresentationAsset={entity_id:string;identity_sha256:string;url:string;source:'QLOO_OBSERVED';sample_sha256:string};
export type DiscoveryResults={mode:DiscoveryMode;seed_identity:Identity;known_favorite_movie:Identity|null;candidate_catalog:Movie[];candidate_count:number;raw_selection:string[];delivered:string[];baseline_delivered:string[];reasons:{catalog_index:number;entity_id:string;text:string;kind:string;verification:string;provider_cause_verified:boolean}[];intent_text:string;information_policy?:unknown;boundaries?:unknown;provider_rows_count:number;rejected_rows_count:number;deduplicated_rows_count:number;presentation_assets:PresentationAsset[]};
export type SavedCase=CaseAccess&CaseQueue&{job_id:string;status:string;wide_cinema_discovery:true;discovery_mode:DiscoveryMode;seed_query:string;favorite_movie_query:string|null;intent_text:string};
export type Capability=CaseAccess&{configured:boolean;execution_enabled:boolean;wide_cinema_discovery_supported?:boolean;simulation_only?:boolean;admissions_blocked?:boolean;remaining_plans?:number|null;remaining_executions?:number|null;wide_cinema_jobs?:SavedCase[];wide_cinema_jobs_truncated?:boolean;wide_cinema_next_cursor_job_id?:string|null};
export type CaseResult={verification_status?:string;provenance?:string;qloo_attempts?:number;model_attempts?:number;wide_cinema_results?:DiscoveryResults};
export type DiscoveryJob=SavedCase&{plan_sha256:string;identity_receipt_sha256?:string;seed_candidates?:Identity[];favorite_movie_candidates?:Identity[];maximum_qloo_requests:number;maximum_model_decisions:number;saved_provider_samples:number;saved_model_packets:number;simulation_only?:boolean;error_class?:string|null;receipt_sha256?:string;result?:CaseResult|null;wide_cinema_display?:unknown};
export type MovieChoice={job_id:string;identity_receipt_sha256:string;selected_seed_entity_id:string;selected_favorite_movie_entity_id:string|null};
export const isRecord=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
export function hasMovieYear(value:Identity):boolean{return Number.isInteger(value.release_year)&&(value.release_year??0)>=1888&&(value.release_year??0)<=2100}
export function isIdentity(value:unknown):value is Identity{return isRecord(value)&&typeof value.entity_id==='string'&&UUID.test(value.entity_id)&&typeof value.name==='string'&&value.name.trim().length>0&&typeof value.type==='string'&&(value.release_year===undefined||value.release_year===null||typeof value.release_year==='number'&&Number.isInteger(value.release_year))}
export function isMovie(value:unknown):value is Movie{return isRecord(value)&&typeof value.entity_id==='string'&&UUID.test(value.entity_id)&&typeof value.name==='string'&&value.name.trim().length>0&&typeof value.release_year==='number'&&Number.isInteger(value.release_year)&&value.release_year>=1888&&value.release_year<=2100}
export function checkedDiscoveryJob(value:unknown):DiscoveryJob{if(!isRecord(value)||value.wide_cinema_discovery!==true||typeof value.job_id!=='string'||!CASE_ID.test(value.job_id)||typeof value.status!=='string'||!['movie','music'].includes(value.discovery_mode as string)||typeof value.seed_query!=='string'||typeof value.intent_text!=='string'||!(value.favorite_movie_query===null||typeof value.favorite_movie_query==='string')||typeof value.plan_sha256!=='string'||!SHA256.test(value.plan_sha256))throw Error('The saved response is not a wide-catalog discovery. Open Previous Comparisons for earlier cases.');return value as DiscoveryJob}
export function validDiscoveryResults(value:unknown):value is DiscoveryResults{
  if(!isRecord(value)||!['movie','music'].includes(value.mode as string)||!isIdentity(value.seed_identity)||!(value.known_favorite_movie===null||isIdentity(value.known_favorite_movie)&&hasMovieYear(value.known_favorite_movie))||!Array.isArray(value.candidate_catalog)||value.candidate_catalog.length<5||value.candidate_catalog.length>100||!value.candidate_catalog.every(isMovie)||value.candidate_count!==value.candidate_catalog.length||typeof value.intent_text!=='string'||!Array.isArray(value.reasons))return false;
  const catalog=value.candidate_catalog,ids=new Set(catalog.map(row=>row.entity_id));if(ids.size!==catalog.length||value.mode==='movie'&&(!hasMovieYear(value.seed_identity)||value.seed_identity.type!=='urn:entity:movie'||value.known_favorite_movie!==null)||value.mode==='music'&&!['urn:entity:artist','urn:entity:person'].includes(value.seed_identity.type))return false;
  for(const key of ['provider_rows_count','rejected_rows_count','deduplicated_rows_count'])if(!Number.isSafeInteger(value[key])||(value[key] as number)<0)return false;
  const known=new Set([value.mode==='movie'?value.seed_identity.entity_id:null,value.known_favorite_movie?.entity_id]);
  for(const key of ['raw_selection','delivered','baseline_delivered']){const rows=value[key];if(!Array.isArray(rows)||rows.length!==5||rows.some(id=>typeof id!=='string'||!ids.has(id))||new Set(rows).size!==5)return false;}
  if((value.delivered as string[]).some(id=>known.has(id)))return false;
  // Historical prose stays in the original receipt. Cards never consume it.
  return true;
}
export const SOURCE_FALLBACK='Seleccionada por IA entre las películas obtenidas para esta búsqueda. No hay una descripción breve vinculada disponible.';
export type GroundedReason={catalog_index:number;entity_id:string;kind:'SOURCE_EXTRACT'|'RETRIEVAL_CONTEXT';verification:'SOURCE_BOUND_NOT_FACT_CHECKED';text:string;provider_cause_verified:false;evidence:Record<string,unknown>};
export type CinemaDisplay={schema_version:1;renderer_version:string;receipt_sha256:string;protocol_version:string;delivered:string[];reasons:GroundedReason[];legacy_original_archived:boolean;notice:string;integrity:'SOURCE_BOUND';binding_sha256:string};
const closed=(value:Record<string,unknown>,keys:string[])=>Object.keys(value).sort().join('|')===[...keys].sort().join('|');
const canonical=(value:unknown):string=>JSON.stringify(value,(_key,member)=>isRecord(member)?Object.fromEntries(Object.keys(member).sort().map(key=>[key,member[key]])):member);
async function textSha(value:string){const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value));return Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('')}
export async function checkedCinemaDisplay(value:unknown,results:DiscoveryResults,receiptSha:unknown):Promise<CinemaDisplay|null>{
  try{
    if(!isRecord(value)||!closed(value,['schema_version','renderer_version','receipt_sha256','protocol_version','delivered','reasons','legacy_original_archived','notice','integrity','binding_sha256'])||value.schema_version!==1||value.renderer_version!=='qloo-grounded-display-v1'||typeof receiptSha!=='string'||!SHA256.test(receiptSha)||value.receipt_sha256!==receiptSha||typeof value.protocol_version!=='string'||!/^qloo-wide-cinema-discovery-v(?:[3-9]|10)$/.test(value.protocol_version)||value.integrity!=='SOURCE_BOUND'||typeof value.legacy_original_archived!=='boolean'||value.legacy_original_archived!==(!['qloo-wide-cinema-discovery-v9','qloo-wide-cinema-discovery-v10'].includes(value.protocol_version))||typeof value.notice!=='string'||!Array.isArray(value.delivered)||JSON.stringify(value.delivered)!==JSON.stringify(results.delivered)||!Array.isArray(value.reasons)||value.reasons.length!==5||typeof value.binding_sha256!=='string'||!SHA256.test(value.binding_sha256))return null;
    for(let position=0;position<5;position++){
      const row=value.reasons[position];if(!isRecord(row)||!closed(row,['catalog_index','entity_id','kind','verification','text','provider_cause_verified','evidence'])||!Number.isInteger(row.catalog_index)||typeof row.catalog_index!=='number'||row.catalog_index<0||row.catalog_index>=results.candidate_catalog.length||row.entity_id!==results.delivered[position]||row.entity_id!==results.candidate_catalog[row.catalog_index].entity_id||row.verification!=='SOURCE_BOUND_NOT_FACT_CHECKED'||row.provider_cause_verified!==false||typeof row.text!=='string'||Array.from(row.text).length<40||Array.from(row.text).length>240||row.text!==row.text.trim().replace(/\s+/gu,' ')||/\p{C}/u.test(row.text)||!isRecord(row.evidence))return null;
      const e=row.evidence,movie=results.candidate_catalog[row.catalog_index];if(!closed(e,['schema_version','renderer','source','language','catalog_index','entity_id','title','release_year','page','position','sample_sha256','response_sha256','value_pointer','languages_pointer','value_sha256','fallback_reason'])||e.schema_version!==1||e.renderer!=='qloo-short-description-v1'||e.catalog_index!==row.catalog_index||e.entity_id!==movie.entity_id||e.title!==movie.name||e.release_year!==movie.release_year||!Number.isInteger(e.page)||![1,2].includes(e.page as number)||!Number.isInteger(e.position)||(e.position as number)<0||(e.position as number)>49||typeof e.sample_sha256!=='string'||!SHA256.test(e.sample_sha256)||typeof e.response_sha256!=='string'||!SHA256.test(e.response_sha256))return null;
      if(row.kind==='SOURCE_EXTRACT'){
        if(e.source!=='QLOO_OBSERVED'||!['es','en'].includes(e.language as string)||e.fallback_reason!==null||e.value_sha256!==await textSha(row.text)||typeof e.value_pointer!=='string'||!new RegExp(`^/response/results/entities/${e.position}/properties/short_descriptions/(0|[1-9][0-9]?)/value$`).test(e.value_pointer)||e.languages_pointer!==e.value_pointer.slice(0,-5)+'languages')return null;
      }else if(row.kind!=='RETRIEVAL_CONTEXT'||row.text!==SOURCE_FALLBACK||e.source!=='RETRIEVAL_CONTEXT'||e.language!==null||e.value_pointer!==null||e.languages_pointer!==null||e.value_sha256!==null||!['MISSING','MALFORMED','AMBIGUOUS','UNSAFE'].includes(e.fallback_reason as string))return null;
    }
    const {binding_sha256,...body}=value;if(await textSha(canonical(body))!==binding_sha256)return null;
    return value as unknown as CinemaDisplay;
  }catch{return null;}
}
export function approvedImageUrl(value:unknown,entityId:string):string|null{
  if(typeof value!=='string'||!UUID.test(entityId)||value.length>2048||value.trim()!==value||/[\s\\]/u.test(value))return null;
  try{const url=new URL(value);if(url.href!==value||url.origin!=='https://images.qloo.com'||url.protocol!=='https:'||url.hostname!=='images.qloo.com'||url.port||url.username||url.password||url.search||url.hash)return null;const match=url.pathname.match(/^\/i\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-[1-9][0-9]{0,3}x-(?:auto|[1-9][0-9]{0,3})\.(?:jpg|jpeg|png|webp)$/i);return match?.[1].toLowerCase()===entityId?value:null;}catch{return null;}
}
export async function movieIdentitySha(movie:Movie):Promise<string>{const bytes=new TextEncoder().encode(JSON.stringify({entity_id:movie.entity_id,name:movie.name,release_year:movie.release_year}));const digest=await crypto.subtle.digest('SHA-256',bytes);return Array.from(new Uint8Array(digest),value=>value.toString(16).padStart(2,'0')).join('')}
export function identityTitle(value:Identity|Movie){return `${value.name}${typeof value.release_year==='number'?` (${value.release_year})`:''}`}
export function artistChoiceGroups(rows:Identity[],query:string){
  const normalized=(value:string)=>value.normalize('NFKC').trim().replace(/\s+/gu,' ').toLowerCase();
  const searched=normalized(query);
  const exact=(row:Identity)=>!!searched&&row.type==='urn:entity:artist'&&normalized(row.name)===searched;
  return {exactArtists:rows.filter(exact),alternatives:rows.filter(row=>!exact(row))};
}
export function mergeWideCases(first:SavedCase[],second:SavedCase[]){const rows=new Map(first.filter(value=>value.wide_cinema_discovery===true).map(value=>[value.job_id,value]));for(const value of second)if(value.wide_cinema_discovery===true&&!rows.has(value.job_id))rows.set(value.job_id,value);return [...rows.values()]}

// An older page refreshes loaded rows in place and appends only unseen IDs.
export function mergeEarlierWideCases(loaded:SavedCase[],fresh:SavedCase[]){
  const updates=new Map(fresh.filter(row=>row.wide_cinema_discovery===true).map(row=>[row.job_id,row]));
  return mergeWideCases(loaded.map(row=>updates.get(row.job_id)??row),fresh);
}
export function refreshWideCaseStatus(rows:SavedCase[],job:Pick<SavedCase,'job_id'|'status'>){
  return rows.map(row=>row.job_id===job.job_id?{...row,status:job.status}:row);
}
// Distinct provider records must not masquerade as one unambiguous film choice.
export function ambiguousMovieIds(rows:Identity[]){
  const groups=new Map<string,Set<string>>();
  for(const row of rows){
    if(row.type!=='urn:entity:movie'||!hasMovieYear(row))continue;
    const title=row.name.normalize('NFKC').trim().replace(/\s+/gu,' ').toLowerCase();
    const key=JSON.stringify([title,row.release_year]);
    const ids=groups.get(key)??new Set<string>();ids.add(row.entity_id);groups.set(key,ids);
  }
  return new Set([...groups.values()].filter(ids=>ids.size>1).flatMap(ids=>[...ids]));
}
