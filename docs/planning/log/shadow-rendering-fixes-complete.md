## Epic Shadow Rendering Fixes Complete

Fixed three visual issues identified during the review gate: convergent shadows, buildings
extending past circle, and illuminated-edge thickness.

**Phases Completed:** 4 of 4

1. ✅ Phase 1: Remove `clamp_to_circle` — fix convergent shadows
2. ✅ Phase 2: Auto-scale buildings to fit within circle
3. ✅ Phase 3: Reduce illuminated-edge stroke thickness
4. ✅ Phase 4: Generate preview SVGs for visual verification

**All Files Created/Modified:**

- `apps/suncast/packages/src/suncast/domain/shadow.py`
- `apps/suncast/packages/src/suncast/domain/geometry.py`
- `apps/suncast/packages/src/suncast/renderer.py`
- `apps/suncast/packages/src/suncast/app.py`
- `apps/suncast/packages/tests/unit/test_shadow.py`
- `apps/suncast/packages/tests/unit/test_geometry.py`

**Key Functions/Classes Added:**

- `fit_to_circle()` in geometry.py — uniform scaling toward canvas center

**Key Functions/Classes Removed:**

- `clamp_to_circle()` from shadow.py — radial clamping that distorted shadow edge
  direction

**Test Coverage:**

- Total tests: 191 (net +2: removed 5 clamp tests, added 7 fit_to_circle tests)
- All tests passing: ✅

**Numerical verification:**

- Shadow edge angle spread: 0.30° (was 19-38° before fix, legacy reference: 0.19-0.33°)
- Auto-scaling: vertices exceeding circle boundary now uniformly scaled with 5% padding
- Illuminated-edge: stroke-width reduced from 1.0 to 0.67 (2/3)
