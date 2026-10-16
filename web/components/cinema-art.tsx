// Original geometric artwork. It does not reproduce film posters or imply film imagery.
export function CinemaSignalArtwork(){
  return <div className="cinema-signal-art" aria-hidden="true"><svg viewBox="0 0 520 380" fill="none">
    <defs><linearGradient id="signal-light" x1="55" y1="80" x2="465" y2="335" gradientUnits="userSpaceOnUse"><stop stopColor="#edc27b"/><stop offset="1" stopColor="#794a2f"/></linearGradient><radialGradient id="signal-glow"><stop stopColor="#e7ba73" stopOpacity=".24"/><stop offset="1" stopColor="#e7ba73" stopOpacity="0"/></radialGradient></defs>
    <circle cx="280" cy="190" r="190" fill="url(#signal-glow)"/><path d="M20 299H500M20 75H500" stroke="#e5c69b" strokeOpacity=".13"/>
    <g transform="translate(68 87) rotate(-9 112 112)"><rect width="224" height="224" rx="9" fill="#191c1c" stroke="#d7b179" strokeOpacity=".5"/><circle cx="112" cy="112" r="86" fill="#0b0e0e" stroke="#d7b179" strokeOpacity=".5"/>{[58,67,76].map(r=><circle key={r} cx="112" cy="112" r={r} stroke="#d7b179" strokeOpacity=".18"/>)}<circle cx="112" cy="112" r="31" fill="#d5a75f"/><circle cx="112" cy="112" r="5" fill="#101313"/><path d="M21 22H80M21 33H55" stroke="#e8c696" strokeWidth="2" strokeOpacity=".55"/></g>
    <g transform="translate(283 58) rotate(10 90 134)"><rect width="180" height="268" rx="8" fill="#161d1c" stroke="#d7b179" strokeOpacity=".6"/><rect x="15" y="15" width="150" height="196" fill="url(#signal-light)"/><path d="M15 174 105 65 165 133V211H15Z" fill="#233c35"/><circle cx="120" cy="66" r="26" fill="#f1dcad"/><path d="m15 211 63-95 39 95" fill="#101a18"/><path d="M20 233H103M20 246H72" stroke="#d7b179" strokeWidth="3" strokeOpacity=".55"/><circle cx="151" cy="239" r="8" stroke="#d7b179"/></g>
    <g transform="translate(246 179)"><circle r="28" fill="#e8bd76"/><path d="M-12 0H12M6-6l6 6-6 6" stroke="#1a211d" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></g>
    <path d="m450 27 3 10 10 3-10 3-3 10-3-10-10-3 10-3Z" fill="#e6c28c"/><path d="m43 324 2 7 7 2-7 2-2 7-2-7-7-2 7-2Z" fill="#e6c28c"/>
  </svg><span className="signal-art-caption">FROM THE RECORD TO THE SCREEN</span></div>;
}

export function FilmAbstractArtwork({seed,index}:{seed:string;index:number}){
  const value=Array.from(seed).reduce((total,char)=>(total*31+char.codePointAt(0)!)>>>0,17);
  const palettes=[['#bd815b','#e5c89c','#293d38'],['#466b67','#dfc694','#162b31'],['#825a54','#e3bfa3','#2c292e'],['#6c7958','#dcd0ae','#28352d'],['#687990','#c9c4b2','#262f42']];
  const [base,light,shade]=palettes[value%palettes.length];
  return <svg className="film-abstract-art" viewBox="0 0 220 280" fill="none" aria-hidden="true"><rect width="220" height="280" fill={base}/><rect x="13" y="13" width="194" height="254" stroke={light} strokeOpacity=".5"/><circle cx={75+value%70} cy={71+value%50} r={40+value%20} fill={light}/><path d={`M0 ${190+value%30} 109 ${76+value%70} 220 211V280H0Z`} fill={shade}/><path d="M-5 263 88 167 140 280H-5Z" fill="#0f1715" fillOpacity=".65"/><path d="M24 239H89M24 247H65" stroke={light} strokeOpacity=".7" strokeWidth="2"/><text x="182" y="248" fill={light} fontSize="13" fontFamily="ui-monospace,monospace" textAnchor="end">{String(index+1).padStart(2,'0')}</text></svg>;
}
