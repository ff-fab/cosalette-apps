## Epic Documentation (Zensical / GitHub Pages) Complete: Full Site

Built the complete Zensical documentation site for vito2mqtt covering landing page,
getting started guide, configuration reference, MQTT signal reference, ADR index,
and usage guides with Home Assistant integration.

**Files created/changed:**

- docs/index.md (landing page)
- docs/getting-started/index.md (getting started guide)
- docs/reference/configuration.md (configuration reference)
- docs/reference/signals.md (MQTT signal reference)
- docs/adr/index.md (ADR index)
- docs/guides/index.md (usage guides + Home Assistant)
- zensical.toml (navigation structure)

**Review Status:** APPROVED (after revision — 3 critical fixes applied)

**Critical fixes applied during review:**

- `VITO2MQTT_MQTT__BROKER` → `VITO2MQTT_MQTT__HOST` (field is `mqtt.host`)
- `VITO2MQTT_LOG_LEVEL` → `VITO2MQTT_LOGGING__LEVEL` (nested model)
- "44 writable commands" → "42 writable commands" (correct count)

**Git Commit Message:**

```text
docs: add complete documentation site

- Landing page with project overview and feature highlights
- Getting started guide (prerequisites, installation, first run)
- Configuration reference (all settings with env var names and defaults)
- MQTT signal reference (all 88 signals across 7 groups with type codes)
- ADR index page with status overview of all 7 decisions
- Usage guides (Home Assistant, Docker, recipes, troubleshooting)
- Full navigation structure in zensical.toml
```
