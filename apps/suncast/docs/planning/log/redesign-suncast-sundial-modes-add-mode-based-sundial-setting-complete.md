## Epic Redesign Suncast Sundial Modes Complete: Add Mode-Based Sundial Setting

Replaced the old boolean sundial toggle with the new `sundial_mode` setting,
threaded that mode through the pipeline, and reduced the sun marker diameter by
10 percent. Focused unit coverage confirms the new configuration path and the
marker size regression point.

**Files created/changed:**
- apps/suncast/packages/src/suncast/settings.py
- apps/suncast/packages/src/suncast/app.py
- apps/suncast/packages/src/suncast/renderer.py
- apps/suncast/packages/tests/unit/test_settings.py
- apps/suncast/packages/tests/unit/test_app.py
- apps/suncast/packages/tests/unit/test_renderer.py
- apps/suncast/docs/_scripts/pre_build.py

**Functions created/changed:**
- SundialMode
- RenderSettings
- _build_pipeline()
- ShadowRenderer.render()
- generate_config_comparison()

**Tests created/changed:**
- TestDefaults.test_rendering_colors
- TestCustomValues.test_rendering_overrides
- TestCustomValues.test_sundial_mode_accepts_supported_values
- TestValidation.test_sundial_mode_rejects_unknown_value
- TestBuildPipeline.test_render_settings_propagated
- TestShadowRenderer.test_sundial_mode_off_hides_ring
- TestShadowRenderer.test_sun_position_marker_uses_reduced_diameter

**Review Status:** APPROVED

**Git Commit Message:**
feat(suncast): add mode-based sundial setting

- replace the boolean sundial toggle with a three-mode setting
- wire the new mode through render settings and app pipeline
- reduce the sun marker diameter by 10 percent and cover it in tests
