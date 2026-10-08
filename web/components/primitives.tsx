import type {Movie,ReviewCase} from '../lib/review';

export function Arrow({diagonal=false}:{diagonal?:boolean}){
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d={diagonal?'M6 18 18 6M6 6h12v12':'M4 12h15m-6-6 6 6-6 6'} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}
export function Mark(){
  return <svg className="brand-mark" width="36" height="36" viewBox="0 0 40 40" fill="none" aria-hidden="true"><rect width="40" height="40" rx="11" fill="currentColor"/><path d="m8 28 9-17h5l7 13M13 22h13" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/><circle cx="27" cy="27" r="6" fill="currentColor" stroke="white" strokeWidth="2"/><path d="m30 31 3 3" stroke="white" strokeWidth="2.5" strokeLinecap="round"/></svg>;
}
export function Pill({children,tone='neutral'}:{children:React.ReactNode;tone?:string}){
  return <span className={'pill '+tone}><i aria-hidden="true"/>{children}</span>;
}
export function PairArtwork({item,index=0,large=false}:{item:ReviewCase;index?:number;large?:boolean}){
  return <div className={'pair-art palette-'+index%6+(large?' large':'')} aria-hidden="true"><div className="poster-light"/><div className="poster-orbit orbit-one"/><div className="poster-orbit orbit-two"/><div className="poster-frame"/><div className="poster-initials"><span>{item.artists.A.slice(0,1)}</span><span>{item.artists.B.slice(0,1)}</span></div><div className="grooves"/><span className="art-caption">TWO TASTES. ONE SCREEN TEST.</span><span className="art-number">{String(index+1).padStart(2,'0')}</span></div>;
}
export function FilmList({movies,compare}:{movies:Movie[];compare?:Movie[]}){
  return <ol className="film-list">{movies.map((film,i)=>{
    const previous=compare?.findIndex(m=>m.id===film.id);
    const movement=previous===undefined?null:previous===-1?'New':previous===i?'—':previous>i?'↑ '+(previous-i):'↓ '+(i-previous);
    return <li key={film.id}><span className="film-position">{String(i+1).padStart(2,'0')}</span><div><strong>{film.title}</strong><span>{film.year}</span></div>{movement!==null&&<small className={previous===-1?'new-entry':''} aria-label={previous===-1?'New in the top five':'Rank movement '+movement}>{movement}</small>}</li>;
  })}</ol>;
}
