## Shadow Algorithm & Renderer Fixes Complete

Rewrote the shadow projection algorithm from naive vertex projection to silhouette
detection via angle extrema, and fixed two renderer issues from the gap analysis.

**Files created/changed:**

- apps/suncast/packages/src/suncast/domain/shadow.py
- apps/suncast/packages/src/suncast/renderer.py
- apps/suncast/packages/tests/unit/test_shadow.py
- apps/suncast/packages/tests/unit/test_renderer.py

**Functions created/changed:**

- `compute_shadow_polygon()` — rewritten with silhouette-based algorithm
- `ShadowResult` — added `sun_facing_edges` field
- `_render_buildings()` — fill-only, no stroke, home vs other color distinction
- `_render_sundial()` — removed hourly center-to-edge lines

**Tests created/changed:**

- `test_elevation_45_shadow_falls_opposite_sun`
- `test_rectangle_shadow_structure`
- `test_sun_facing_edges_populated`
- `test_convex_shadow_non_self_intersecting`
- `test_concave_l_shape_silhouette`
- Updated renderer tests for fill-only buildings and sundial changes

**Review Status:** APPROVED

**Git Commit Message:**

```
feat(suncast): rewrite shadow algorithm and fix renderer

- Rewrite shadow projection using silhouette detection via angle extrema
- Add sun_facing_edges field to ShadowResult for future outline rendering
- Fix building rendering: fill-only, no stroke; home vs other colors
- Remove hourly center-to-edge sundial lines, keep markers
```
