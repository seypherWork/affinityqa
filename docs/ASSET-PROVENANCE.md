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

The following paragraph records the earlier, superseded wide-cinema image
policy. That route used actual image URLs observed in Qloo film metadata and
permitted direct
browser loads from `images.qloo.com` only, with identity binding and a missing
image fallback. No standalone poster asset or application screenshot containing
third-party film images is bundled into this source package. No URL is
synthesized and no third-party film image is included in the project's MIT grant.
The CDN receives ordinary image requests; `no-referrer` does not conceal the visitor's
network address. Image-specific unrestricted rights have not been established.
The retained original abstract artwork continues to be decorative rather than
an official film poster. Observed film images are not automatically classified
as official posters. [New route and boundaries](WIDE-CINEMA-DISCOVERY.md).

## Local application evidence — 18 October 2026

Two existing local screenshots of the accepted v10 result and retained Fighting
display were visually inspected. They contain Qloo/provider-derived metadata
and third-party film images. They remain private and are omitted from the source
package; no screenshot or standalone poster collection is being licensed as
original project artwork.

Contextual image display in the running application does not establish an
unrestricted repository redistribution right. That right has not been confirmed,
and no new permission is inferred here. The public documentation instead keeps
the project-authored SVG illustrations and a
[dated acceptance summary](LOCAL-ACCEPTANCE-20261018.md). The package excludes raw
provider captures, private stores, credentials and a Qloo corpus. See
[licensing scope](LICENSING.md). Acceptance records and their local images are
not automatically public judge evidence or permission to publish.

The interface study used the workspace hierarchy and result navigation in [Linear Insights](https://linear.app/insights) and the summary/table/case workflow documented in [Braintrust](https://www.braintrust.dev/docs/evaluate/interpret-results). These references informed information hierarchy and progressive disclosure; their code and branded assets were not copied. The original documentation illustrations remain distinct from application screenshots and provider evidence.

The 16 October discovery study additionally used [Seerr's official repository](https://github.com/seerr-team/seerr), [Letterboxd's description](https://letterboxd.com/about/what-is-letterboxd/) and [MUBI's presentation](https://mubi.com/en/about). Their discovery, title/year confirmation and editorial hierarchy informed the original implementation. No third-party UI code, film artwork or branded asset was copied. Film titles and years come from the existing catalog and confirmed inputs; decorative art does not assert additional film metadata.

## Original-only card presentation — 20 October 2026 local candidate

This policy supersedes the earlier wide-discovery image rendering above. All
five cards now reuse `FilmAbstractArtwork` from `web/components/cinema-art.tsx`,
the project-authored abstract SVG already used in the earlier comparison view.
No downloaded image, new asset provider or new dependency is introduced. The
art is decorative and labelled ORIGINAL ILLUSTRATION; it does not depict or
assert facts about a film. It is original project code under the existing MIT
scope, not a licence to any title, metadata, trademark or third-party image.

The UI no longer consumes external image URLs and the HTTP content policy no
longer permits the Qloo image CDN. Valid, missing, stale and unsafe historical
image metadata all receive original artwork without changing film identities,
ranking or source descriptions. Archived case/verification bytes are retained.
Earlier dated CDN tests remain historical observations, not current behavior.
Promotional materials can use original workflow illustrations without depending
on permission to reproduce posters; screenshots still require checking for
provider-derived text and personal information before publication.

## Interface screenshots — 22 October 2026

- `jury-diagnosis-20261022.png`: actual local interface executing the existing original recorded capture; saved decisions, zero new provider calls. The context diagram is labelled illustrative.
- `jury-discovery-20261022.png`: actual local Daft Punk / Tron: Legacy (2010) trial using real Qloo/Groq and expressly synthetic operator preferences. Original abstract film-card SVGs render in the screenshot; no external posters. Recommendation completion is not a claim that this trial's automated download/restoration passed.

These screenshots are presentation records of this project's own interface, not redistributed raw provider captures, human preference-study results or licensed film-poster artwork. Earlier assets and their dated provenance remain intact.
