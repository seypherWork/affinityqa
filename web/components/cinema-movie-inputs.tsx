'use client';
import styles from './individual-screening.module.css';

export type MovieQueryPair={A:string[];B:string[]};
export type MovieInputCandidate={entity_id:string;name:string;release_year:number;type:'urn:entity:movie'};
export type MovieInputCandidates={A:MovieInputCandidate[][];B:MovieInputCandidate[][]};
export type MovieInputSelection={A:string[];B:string[]};
export type ConfirmedMovieInputs={A:MovieInputCandidate[];B:MovieInputCandidate[]};
const profiles=['A','B'] as const;
export const emptyMovieQueries=():MovieQueryPair=>({A:[],B:[]});
export const emptyMovieSelection=():MovieInputSelection=>({A:[],B:[]});
export const movieQueryCount=(queries:MovieQueryPair)=>queries.A.length+queries.B.length;
export const hasConfirmedYear=(movie:MovieInputCandidate)=>Number.isInteger(movie.release_year)&&movie.release_year>=1000&&movie.release_year<=9999;
const shortId=(id:string)=>id.length>16?`${id.slice(0,8)}…${id.slice(-4)}`:id;

export function CinemaMovieQueryEditor({queries,artists,maximum,disabled,onChange}:{queries:MovieQueryPair;artists:{A:string;B:string};maximum:number;disabled:boolean;onChange:(value:MovieQueryPair)=>void}){
  const count=movieQueryCount(queries);
  function update(profile:'A'|'B',index:number,text:string){onChange({...queries,[profile]:queries[profile].map((value,slot)=>slot===index?text:value)})}
  return <section className={styles.preferences} aria-labelledby="movie-input-query-title">
    <div className={styles.sectionHeading}><h2 id="movie-input-query-title">ADD A FILM YOU ALREADY LIKE</h2><span>Optional · {count}/{maximum} searches across both profiles</span></div>
    <p>A film you love is a useful starting point. Enter its title; you’ll confirm the exact film and year before the AI ranks the twenty-film catalog.</p>
    <div className={styles.preferenceProfiles}>{profiles.map(profile=><fieldset className={styles.movieQueryProfile} disabled={disabled} key={profile}>
      <legend>PROFILE {profile} · {artists[profile]||'Choose an artist'}</legend>
      {queries[profile].map((query,index)=><div className={styles.movieQueryRow} key={index}>
        <label>FILM TITLE {index+1}<input required maxLength={400} aria-label={`Profile ${profile} film title ${index+1}`} value={query} placeholder="For example: Gladiator" onChange={event=>update(profile,index,event.target.value)}/></label>
        <button type="button" className={styles.secondaryButton} aria-label={`Remove profile ${profile} film query ${index+1}`} onClick={()=>onChange({...queries,[profile]:queries[profile].filter((_,slot)=>slot!==index)})}>REMOVE</button>
      </div>)}
      {!queries[profile].length&&<p>No extra film selected for this profile.</p>}
      <button type="button" className={styles.secondaryButton} disabled={disabled||count>=maximum} onClick={()=>onChange({...queries,[profile]:[...queries[profile],'']})}>ADD FILM TO PROFILE {profile}</button>
    </fieldset>)}</div>
    <p className={styles.small}>Up to two titles across both tastes. No searches while typing; each title adds at most one Qloo search when you start the reviewed plan.</p>
  </section>;
}

export function CinemaMovieIdentityPicker({queries,candidates,selection,disabled,groupId,onChange}:{queries:MovieQueryPair;candidates:MovieInputCandidates;selection:MovieInputSelection;disabled:boolean;groupId:string;onChange:(profile:'A'|'B',slot:number,entityId:string)=>void}){
  return <section className={styles.identityReview} aria-labelledby={`movie-confirm-title-${groupId}`}>
    <div className={styles.sectionHeading}><h3 id={`movie-confirm-title-${groupId}`}>CONFIRM YOUR FILMS</h3><span>Match the title and year · no automatic selection</span></div>
    <p>Choose the intended film for every query. Only these saved Qloo matches can be confirmed. A title without a verified year cannot be accepted.</p>
    <div className={styles.identityProfiles}>{profiles.flatMap(profile=>queries[profile].map((query,slot)=>{
      const matches=candidates[profile]?.[slot]??[];
      const duplicate=!!selection[profile]?.[slot]&&selection[profile].some((id,index)=>index!==slot&&id===selection[profile][slot]);
      return <fieldset className={styles.identityProfile} disabled={disabled} key={`${profile}-${slot}`}>
        <legend>MOVIE PROFILE {profile} · QUERY {slot+1}</legend>
        <p className={styles.identityQuery}><span>ORIGINAL FILM QUERY</span>{query}</p>
        <div className={styles.identityChoices}>{matches.length?matches.map(movie=><label className={styles.identityChoice} key={movie.entity_id} data-selected={selection[profile]?.[slot]===movie.entity_id}>
          <input type="radio" name={`movie-identity-${groupId}-${profile}-${slot}`} value={movie.entity_id} checked={selection[profile]?.[slot]===movie.entity_id} disabled={!hasConfirmedYear(movie)} onChange={()=>onChange(profile,slot,movie.entity_id)}/>
          <span><strong>{movie.name} ({hasConfirmedYear(movie)?movie.release_year:'Year unverified'})</strong><span className={styles.identityMetadata}><span>Qloo film identity</span><code title={movie.entity_id}>{shortId(movie.entity_id)}</code></span></span>
        </label>):<p role="alert">No film matches were saved for this query. Edit the title above and review a new plan. This case cannot continue without a confirmed film.</p>}</div>
        {duplicate&&<p className={styles.identityConflict} role="alert">Choose distinct films within this profile. The same film cannot fill two query slots.</p>}
      </fieldset>;
    }))}</div>
  </section>;
}

export function CinemaConfirmedMovieInputs({movies}:{movies:ConfirmedMovieInputs}){
  return <section className={styles.identityReview} aria-label="Confirmed film inputs">
    <div className={styles.sectionHeading}><h3>CONFIRMED FILM INPUTS</h3><span>Positive taste signals saved with this case</span></div>
    <div className={styles.identityProfiles}>{profiles.map(profile=><div className={styles.confirmedIdentity} key={profile}>
      <span className={styles.eyebrow}>PROFILE {profile}</span>
      {movies[profile]?.length?movies[profile].map(movie=><div className={styles.confirmedMovie} key={movie.entity_id}><strong>{movie.name} ({movie.release_year})</strong><code title={movie.entity_id}>{shortId(movie.entity_id)}</code></div>):<p>No additional film input for this profile.</p>}
    </div>)}</div>
    <p className={styles.small}>The confirmed identities are supplied to Qloo and the model. Recommendations remain in the reviewed catalog; this does not establish how much you will like them.</p>
  </section>;
}
