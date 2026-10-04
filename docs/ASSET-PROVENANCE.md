# Interface asset inventory

Reviewed on 4 October 2026. The application uses project-authored vector and CSS artwork rather than downloaded reference-site images. Visual references informed the direction; their logos, photographs and assets are not included in the source archive.

| Material | Project source | Boundary |
|---|---|---|
| AffinityQA mark and UI arrows | `web/components/primitives.tsx` | Inline project SVG; original-code MIT scope |
| Application icon | `web/app/icon.svg` | Project SVG; original-code MIT scope |
| Cinematic projection artwork | `web/components/projection.tsx` | Project SVG gradients and geometry |
| Grain, backgrounds and panel treatments | `web/app/style.css`, `web/app/cinematic.css`, component CSS | Project CSS, including an inline SVG grain filter |
| Framework and dependency material | Dependency locks and `THIRD-PARTY-LICENSES.txt` | Upstream rights and notices retained |
| Artist names, film names and recorded decisions | Separately authorized evidence | Outside the project's MIT grant |

Inspection of `web/app`, `web/components` and `web/lib` found no external image URLs or downloaded raster assets. The package manifest binds the actual source bytes. This inventory is a source inspection, not a trademark-clearance opinion or a certification of every dependency's rights. See [licensing scope](LICENSING.md).
