/** Original cinematic artwork: two taste signals converge on a screen. */
export function Projection(){
  return <svg className="projection-art" viewBox="0 0 700 580" fill="none" aria-hidden="true">
    <defs>
      <radialGradient id="projection-halo"><stop stopColor="#648c9e" stopOpacity=".7"/><stop offset="1" stopColor="#101014" stopOpacity="0"/></radialGradient>
      <linearGradient id="projection-screen" x1="150" y1="120" x2="550" y2="440" gradientUnits="userSpaceOnUse"><stop stopColor="#eed9e8"/><stop offset=".38" stopColor="#738995"/><stop offset=".65" stopColor="#182e3c"/><stop offset="1" stopColor="#080e13"/></linearGradient>
      <linearGradient id="projection-edge"><stop stopColor="#eed9e8"/><stop offset=".5" stopColor="#89d5db"/><stop offset="1" stopColor="#335163"/></linearGradient>
      <linearGradient id="projection-beam"><stop stopColor="#e8c1d8" stopOpacity="0"/><stop offset="1" stopColor="#ddbccc" stopOpacity=".4"/></linearGradient>
      <filter id="projection-glow"><feGaussianBlur stdDeviation="12"/></filter>
    </defs>
    <ellipse cx="350" cy="300" rx="345" ry="260" fill="url(#projection-halo)"/>
    <path d="M20 140 544 200v198L20 510Z" fill="url(#projection-beam)" opacity=".45"/>
    <g transform="rotate(-13 350 290)"><rect x="173" y="100" width="345" height="376" rx="3" fill="#101e2b" stroke="#476275"/><path d="M191 120h309v335H191Z" stroke="#476275" strokeOpacity=".4"/></g>
    <g transform="rotate(9 350 290)"><rect x="170" y="106" width="345" height="376" rx="3" fill="#1e3849" stroke="#335163"/></g>
    <g transform="rotate(-3 350 290)">
      <rect x="163" y="96" width="368" height="393" rx="3" fill="#080d11" stroke="url(#projection-edge)"/>
      <rect x="178" y="112" width="337" height="328" fill="url(#projection-screen)"/>
      <ellipse cx="341" cy="281" rx="111" ry="122" stroke="#ddd7ed" strokeWidth="10" opacity=".45" filter="url(#projection-glow)"/>
      <ellipse cx="341" cy="281" rx="109" ry="122" fill="#0b1520" fillOpacity=".76" stroke="url(#projection-edge)" strokeWidth="2"/>
      <ellipse cx="341" cy="281" rx="75" ry="121" transform="rotate(44 341 281)" stroke="#9eafbf" strokeOpacity=".65"/>
      <ellipse cx="341" cy="281" rx="75" ry="121" transform="rotate(-44 341 281)" stroke="#e8c4d9" strokeOpacity=".85"/>
      <g transform="translate(307 243) scale(1.45)"><path d="M5 38 20 8h8l15 30H32l-8-18-8 18H5Z" fill="#ebe8f0"/><path d="M9 31h30" stroke="#14212d" strokeWidth="3"/><path d="m26 33 10 10h9L34 32Z" fill="#ddbccf"/></g>
      <path d="M178 408h337" stroke="#dee0f6" strokeOpacity=".25"/><path d="M192 422h140m9 0h22" stroke="#dee0f6" strokeOpacity=".6"/>
      <text x="183" y="466" fill="#ebe8f0" fontFamily="Arial,sans-serif" fontSize="10" letterSpacing="3">THE TASTE / TEST</text><text x="481" y="466" fill="#9ea9b8" fontFamily="Arial,sans-serif" fontSize="10">01</text>
    </g>
    <path d="M72 384C12 471 591 532 635 336c15-67-79-113-105-121" stroke="#ebe8f0" strokeOpacity=".72" strokeWidth="1.5"/>
    <circle cx="622" cy="368" r="5" fill="#ddbccc"/><circle cx="94" cy="436" r="4" fill="#8cbecb"/>
    <path d="M567 110v28m-14-14h28M110 267v16m-8-8h16" stroke="#b7c7d6" strokeOpacity=".6"/>
  </svg>;
}
