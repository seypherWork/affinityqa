# Interface asset inventory

Reviewed on 16 October 2026 for the local experience candidate. The application uses project-authored vector and CSS artwork rather than downloaded reference-site images. Visual references informed the direction; their logos, photographs and assets are not included in the source archive. This source inventory does not assert deployment of the candidate.

| Material | Project source | Boundary |
|---|---|---|
| AffinityQA mark and UI arrows | `web/components/primitives.tsx` | Original AQ monogram and inline project SVG; original-code MIT scope |
| Workspace shell and navigation icons | `web/components/workspace-shell.tsx` | Original inline SVG; no downloaded icon library |
| Application icon | `web/app/icon.svg` | Project SVG; original-code MIT scope |
| Discovery palette, panels and responsive layout | `web/app/experience.css`, `web/app/workspace.css`, `web/app/typography.css`, component CSS | Original warm dark, cream and amber styles; earlier workspace rules remain as underlying source |
| Record-to-screen hero and film-card illustrations | `web/components/cinema-art.tsx` | Original abstract inline SVG; film-card art is not an official movie poster |
| Earlier cinematic artwork and treatments | `web/components/projection.tsx`, `web/app/style.css`, `web/app/cinematic.css` | Retained project source; the active layout no longer imports the two earlier global stylesheets |
| Framework and dependency material | Dependency locks and `THIRD-PARTY-LICENSES.txt` | Upstream rights and notices retained |
| Offline OpenAI token vocabulary | `assets/tokenizers/o200k_base.tiktoken` | Official OpenAI encoding asset; SHA-256 `446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d`; upstream material |
| Tokenizer and copied encoding pattern | `requirements-repeatable.lock.txt`, `licenses/tiktoken-MIT.txt` | OpenAI tiktoken 0.14.0, pinned release wheel hashes; MIT notice retained |
| Artist names, film names and recorded decisions | Separately authorized evidence | Outside the project's MIT grant |

Inspection of `web/app`, `web/components` and `web/lib` found no external image URLs or downloaded raster assets. The package manifest binds the actual source bytes. This inventory is a source inspection, not a trademark-clearance opinion or a certification of every dependency's rights. See [licensing scope](LICENSING.md).

The interface study used the workspace hierarchy and result navigation in [Linear Insights](https://linear.app/insights) and the summary/table/case workflow documented in [Braintrust](https://www.braintrust.dev/docs/evaluate/interpret-results). These references informed information hierarchy and progressive disclosure; their code and branded assets were not copied. The original documentation illustrations remain distinct from application screenshots and provider evidence.

The 16 October discovery study additionally used [Seerr's official repository](https://github.com/seerr-team/seerr), [Letterboxd's description](https://letterboxd.com/about/what-is-letterboxd/) and [MUBI's presentation](https://mubi.com/en/about). Their discovery, title/year confirmation and editorial hierarchy informed the original implementation. No third-party UI code, film artwork or branded asset was copied. Film titles and years come from the existing catalog and confirmed inputs; decorative art does not assert additional film metadata.
