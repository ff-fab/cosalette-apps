## Epic User Documentation: Doc Pages + Nav + Slim README

Created 5 user-facing documentation pages following the User Journey lifecycle model,
updated zensical.toml navigation, and slimmed README to a billboard with link to docs.

**Files created:**
- docs/index.md — Landing page with badges, features, hardware summary, grid cards
- docs/getting-started.md — Prerequisites, wiring, tabbed Docker/manual install, verification
- docs/configuration.md — All settings (MQTT, Logging, I2C, Schmitt, Polling, Temp, Features) with .env example
- docs/mqtt-topics.md — 9+ topics with payload schemas, per-device error note, naming convention
- docs/architecture.md — Mermaid diagrams (component + sequence), layer descriptions, cosalette integration

**Files changed:**
- zensical.toml — Nav updated with 6 entries (Home, Getting Started, Configuration, MQTT Topics, Architecture, ADRs)
- README.md — Slimmed to billboard: kept badges/features/hardware, added docs link, replaced detailed tables with one-liners

**Review Status:** APPROVED after revision (4 blocking issues fixed: added cosalette base MQTT settings, Logging section, synced .env block, removed hardcoded settings count, added per-device error topics note, added Schmitt threshold formula)

**Git Commit Message:**
```
docs: add user documentation site

- Create 5 doc pages: index, getting-started, configuration, mqtt-topics, architecture
- Update zensical.toml navigation with User Journey ordering
- Slim README to billboard with link to docs site
- Document cosalette base settings (MQTT client_id, topic_prefix, logging)
```
