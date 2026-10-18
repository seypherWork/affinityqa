'use client';
import styles from './individual-screening.module.css';

export type IdentityCandidate={entity_id:string;name:string;type:string};
export type IdentityPair={A:IdentityCandidate;B:IdentityCandidate};
export type IdentityCandidates={A:IdentityCandidate[];B:IdentityCandidate[]};
export type IdentityQueries={A:string;B:string};
export type IdentitySelection={A:string;B:string};
const profiles=['A','B'] as const;
const profileLabel=(type:string)=>type==='urn:entity:artist'?'MUSIC ARTIST':type==='urn:entity:person'?'PERSON PROFILE':'QLOO PROFILE';

export function CinemaIdentityPicker({candidates,queries,selection,disabled,groupId,onChange}:{candidates:IdentityCandidates;queries:IdentityQueries;selection:IdentitySelection;disabled:boolean;groupId:string;onChange:(profile:'A'|'B',entityId:string)=>void}){
  const sameIdentity=!!selection.A&&selection.A===selection.B;
  return <section className={styles.identityReview} aria-labelledby={`identity-title-${groupId}`}>
    <div className={styles.sectionHeading}><h3 id={`identity-title-${groupId}`}>CONFIRM YOUR ARTISTS</h3><span>Manual selection · one distinct artist per profile</span></div>
    <p>Qloo returned these artist matches for your original queries. Choose the intended artist for each profile. No model request has started.</p>
    <div className={styles.identityProfiles}>{profiles.map(profile=><fieldset className={styles.identityProfile} key={profile} disabled={disabled}>
      <legend>PROFILE {profile}</legend>
      <p className={styles.identityQuery}><span>ORIGINAL QUERY</span>{queries[profile]}</p>
      <div className={styles.identityChoices}>{candidates[profile].length?candidates[profile].map(candidate=><label className={styles.identityChoice} key={candidate.entity_id} data-selected={selection[profile]===candidate.entity_id}>
        <input type="radio" name={`identity-${groupId}-${profile}`} value={candidate.entity_id} checked={selection[profile]===candidate.entity_id} onChange={()=>onChange(profile,candidate.entity_id)}/>
        <span><strong>{candidate.name}</strong><span className={styles.identityMetadata}>{profileLabel(candidate.type)}</span></span>
      </label>):<p>No artist matches were saved for this query. This case cannot continue without two valid artist choices.</p>}</div>
    </fieldset>)}</div>
    {sameIdentity&&<p className={styles.identityConflict} role="alert">Choose two distinct artists. Both profiles currently point to the same Qloo identity.</p>}
    <p className={styles.small}>Nothing is selected automatically. Your confirmation binds these identities to this plan and its saved search receipt.</p>
  </section>;
}

export function CinemaConfirmedIdentities({identities,queries}:{identities:IdentityPair;queries:IdentityQueries}){
  return <section className={styles.identityReview} aria-label="Confirmed artist identities">
    <div className={styles.sectionHeading}><h3>CONFIRMED ARTIST IDENTITIES</h3><span>Saved with this case</span></div>
    <div className={styles.identityProfiles}>{profiles.map(profile=><div className={styles.confirmedIdentity} key={profile}>
      <span className={styles.eyebrow}>PROFILE {profile}</span><strong>{identities[profile].name}</strong>
      <span className={styles.identityMetadata}>{profileLabel(identities[profile].type)}</span>
      <p className={styles.identityQuery}><span>ORIGINAL QUERY</span>{queries[profile]}</p>
    </div>)}</div>
  </section>;
}
