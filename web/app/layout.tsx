import './style.css';
import './cinematic.css';
import './typography.css';
export const metadata = {title:'AffinityQA · The cultural intelligence review',description:'Taste is personal. Proof is everything. Inspect personalization failures, recorded repairs and the evidence behind your agent’s recommendations.'};
export default function Layout({children}:{children:React.ReactNode}) {
  return <html lang="en"><body>{children}</body></html>;
}
