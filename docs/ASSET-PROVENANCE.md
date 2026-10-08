# Interface asset inventory

Reviewed on 9 October 2026. The application uses project-authored vector and CSS artwork rather than downloaded reference-site images. Visual references informed the direction; their logos, photographs and assets are not included in the source archive.

| Material | Project source | Boundary |
|---|---|---|
| AffinityQA mark and UI arrows | `web/components/primitives.tsx` | Original AQ monogram and inline project SVG; original-code MIT scope |
| Workspace shell and navigation icons | `web/components/workspace-shell.tsx` | Original inline SVG; no downloaded icon library |
| Application icon | `web/app/icon.svg` | Project SVG; original-code MIT scope |
| Active workspace palette, panels and responsive layout | `web/app/workspace.css`, `web/app/typography.css`, component CSS | Original graphite, ivory and violet styles |
| Earlier cinematic artwork and treatments | `web/components/projection.tsx`, `web/app/style.css`, `web/app/cinematic.css` | Retained project source; the active layout no longer imports the two earlier global stylesheets |
| Framework and dependency material | Dependency locks and `THIRD-PARTY-LICENSES.txt` | Upstream rights and notices retained |
| Artist names, film names and recorded decisions | Separately authorized evidence | Outside the project's MIT grant |

Inspection of `web/app`, `web/components` and `web/lib` found no external image URLs or downloaded raster assets. The package manifest binds the actual source bytes. This inventory is a source inspection, not a trademark-clearance opinion or a certification of every dependency's rights. See [licensing scope](LICENSING.md).

The interface study used the workspace hierarchy and result navigation in [Linear Insights](https://linear.app/insights) and the summary/table/case workflow documented in [Braintrust](https://www.braintrust.dev/docs/evaluate/interpret-results). These references informed information hierarchy and progressive disclosure; their code and branded assets were not copied. The original documentation illustrations remain distinct from application screenshots and provider evidence.
