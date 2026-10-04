export type Movie = {id:string;title:string;year:number};
export type Profile = {artist:string;before:Movie[];reference:Movie[];after:Movie[];before_agreement:number;after_agreement:number};
export type ReviewCase = {id:string;artists:{A:string;B:string};outcome:string;delta:{min:number;median:number;max:number};reference_noise:number;structural_gate:string;reference_hash:string;views:{repeat:number;order:string;profiles:{A:Profile;B:Profile}}[]};
export type Snapshot = {metadata_development?:MetadataStudy;context_extensions?:ExtensionStudy;repair_learning?:LearningStudy;individual_development?:IndividualStudy;ordering_development?:OrderingStudy;mode:string;run_id:string;verified_utc:string;cases:ReviewCase[];counts:Record<string,number>;case_count:number;reference_calls:number;model_calls:number;ci_gate:string;policy_hash:string;model:string;new_live_calls:number;value_study?:{run_id:string;sample_gate:string;passing_cases:number;denominator:number;model_calls:number;reference_calls:number;policy_sha256:string;promotion:string;development_passes:number;development_denominator:number};repair_study?:{run_id:string;sample_gate:string;passing_cases:number;denominator:number;model_calls:number;reference_calls:number;policy_sha256:string;promotion:string};semantic_study?:SemanticStudy;context_study?:{model_calls:number;reference_calls:number;reserved_inputs_executed:number;candidates:{index:number;run_id:string;candidate_gate:string;cases:{pair_id:string;checks:Record<string,boolean>}[]}[]}};
export type Section = 'overview'|'screening'|'library'|'evidence';
export type SemanticStudy={run_id:string;candidate_gate:string;embedding_calls:number;reserved_inputs_executed:number;cases:{pair_id:string;checks:Record<string,boolean>;delta:Record<string,number>}[]};
export const sections: {id:Section;label:string;number:string}[] = [
  {id:'overview',label:'Overview',number:'01'},
  {id:'screening',label:'Screening room',number:'02'},
  {id:'library',label:'Case library',number:'03'},
  {id:'evidence',label:'Evidence archive',number:'04'},
];
export const score = (n:number)=>n.toFixed(3);
export const signed = (n:number)=>(n>=0?'+':'')+n.toFixed(3);
export const serial = (n:number)=>String(n+1).padStart(2,'0');
export const isMixed = (item:ReviewCase)=>item.outcome==='MIXED';
export function readSection():Section {
  const hash=window.location.hash.slice(1);
  if(hash==='suite')return 'library';
  return sections.find(s=>s.id===hash)?.id??'overview';
}

export type OrderingStudy={best_passes:number;denominator:number;discrete_candidates:number;calibration_intervals:number;new_qloo_requests:number;cases:{pair_id:string;artists:{A:string;B:string};passing:boolean;comparisons:{neutral_graph:{A:{min:number};B:{min:number}}};minimum_pair_mean_delta:{neutral_graph:number}}[]};

export type IndividualStudy={best_passes:number;denominator:number;available_projections:number;total_projections:number;candidate_count:number;new_qloo_requests:number;cases:{pair_id:string;artists:{A:string;B:string};passing:boolean;checks:Record<string,boolean>;comparisons:Record<'baseline'|'neutral_graph',Record<'A'|'B',{min:number}>>;minimum_pair_mean_delta:{neutral_graph:number}}[]};

export type LearningStudy={full_fit_passes:number;resampled_passes:number;denominator:number;fits_verified:number;new_qloo_requests:number;cases:Record<'full'|'held',IndividualStudy['cases']>};

export type ExtensionStudy={denominator:number;fits_verified:number;new_qloo_requests:number;new_model_calls:number;new_validation_pairs:number;experiments:{id:string;label:string;full:{passes:number;cases:IndividualStudy["cases"]};held:{passes:number;cases:IndividualStudy["cases"]}|null}[];diagnostic:{rows:{movie:string;reference_position:number;five_movie:number;artist_mean:number;twenty_movie:number}[]}};

export type MetadataStudy={status:string;passes:number|null;denominator:number;verified_outputs:number;new_qloo_requests:number;new_validation_pairs:number;cumulative_model_calls_including_stopped_attempt:number;error:string|null;cases:{pair_id:string;artists:{A:string;B:string};checks:Record<string,boolean>;comparisons:Record<"baseline"|"neutral_graph"|"swapped_graph",Record<"A"|"B",{min:number}>>;minimum_pair_mean_delta:Record<"baseline"|"neutral_graph"|"swapped_graph",number>}[]};
