## Epic Redesign Suncast Sundial Modes Complete: Implement Compact Merged Sundial

Implemented the compact sundial mode so the hourly dial can collapse onto the
inner circle and merge with the solar path. The renderer now keeps `ring` and
`off` behavior intact while compact mode overlays a 30 percent daylight arc on
top of the inner-circle hour segments and suppresses the night path.

**Files created/changed:**
- apps/suncast/packages/src/suncast/renderer.py
- apps/suncast/packages/tests/unit/test_renderer.py

**Functions created/changed:**
- ShadowRenderer.render()
- append_sundial_arcs()
- append_hour_bar()

**Tests created/changed:**
- TestShadowRenderer.test_sundial_mode_ring_keeps_hour_segments_on_outer_ring
- TestShadowRenderer.test_sundial_mode_compact_merges_segments_and_day_overlay
- TestShadowRenderer.test_sundial_mode_compact_layers_day_overlay_above_hour_segments
- TestShadowRenderer.test_sundial_mode_off_hides_ring

**Review Status:** APPROVED

**Git Commit Message:**
feat(suncast): add compact sundial rendering

- move hourly sundial segments onto the inner circle in compact mode
- overlay the daylight path at 30 percent opacity and hide the night path
- extend renderer tests for ring, compact, and off dial behavior
