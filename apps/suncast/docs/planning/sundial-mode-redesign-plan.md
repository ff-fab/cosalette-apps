# Suncast Sundial Mode Redesign Plan

## Goal

Refine the suncast dial so the current sun marker is slightly smaller and the
sundial can operate in three explicit visual modes.

## Selected Design

Use a mode-based rendering setting named `sundial_mode` with these values:

- `ring`: render the existing outer 24-segment sundial ring
- `compact`: hide the outer ring and render the hour segments on the inner sun
  circle instead
- `off`: hide the sundial hour segments entirely

In `compact` mode, the renderer should merge the hour dial and solar path into a
single circle:

- Hour segments move from the outer ring onto the inner circle perimeter.
- The day path is rendered as an overlay on top of the hour segments.
- The night path is not rendered.
- The current sun marker diameter is reduced by 10 percent.

## Why This Approach

- An explicit mode is clearer than separate booleans once there are three valid
  sundial states.
- The renderer can preserve the existing `ring` appearance while making the new
  merged dial a first-class visual mode.
- The data model remains simple: one setting selects one rendering strategy.

## Implementation Phases

### Phase 1: Introduce mode-based configuration

- Replace the boolean sundial setting with `sundial_mode` in settings,
  pipeline wiring, and default tests.
- Keep the render settings API aligned with the new enum-based model.
- Reduce the current sun marker diameter by 10 percent.

### Phase 2: Implement compact merged dial rendering

- Move the hour-segment arcs onto the inner circle when `sundial_mode` is
  `compact`.
- Render the day path as a partial overlay above those segments.
- Suppress the night path in `compact` mode.
- Keep sunrise, sunset, noon, and midnight markers visually coherent with the
  merged dial.

### Phase 3: Refresh verification and documentation assets

- Extend renderer and settings tests to cover all three modes.
- Update generated documentation images to include the compact mode.
- Update the suncast configuration docs to describe `sundial_mode` in its final
  form.

## Likely Files

- `apps/suncast/packages/src/suncast/settings.py`
- `apps/suncast/packages/src/suncast/app.py`
- `apps/suncast/packages/src/suncast/renderer.py`
- `apps/suncast/packages/tests/unit/test_settings.py`
- `apps/suncast/packages/tests/unit/test_app.py`
- `apps/suncast/packages/tests/unit/test_renderer.py`
- `apps/suncast/docs/_scripts/pre_build.py`
- `apps/suncast/docs/configuration.md`
