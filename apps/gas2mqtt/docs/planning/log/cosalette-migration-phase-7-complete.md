## Epic Cosalette Migration Complete: Documentation + Deployment

Production documentation and Docker deployment for gas2mqtt. Comprehensive README with hardware, configuration, MQTT topics, and architecture. Migration ADR documenting the legacy→cosalette decision. Docker stack with Mosquitto.

**Files created/changed:**

- `README.md` — Full rewrite with features, hardware, quick start, config table, MQTT topics, architecture
- `CONTRIBUTING.md` — Updated project structure tree
- `docs/adr/ADR-001-cosalette-migration.md` — Migration ADR with decision matrix
- `docs/planning/framework-opportunities.md` — Future cosalette opportunities
- `Dockerfile` — Production image (python:3.14-slim + uv, non-root)
- `docker-compose.yml` — gas2mqtt + Mosquitto, I2C passthrough, group_add i2c
- `mosquitto.conf` — Minimal config for Mosquitto 2.x (listener + anonymous)
- `.dockerignore` — Excludes tests, docs, .git from build context

**Review Status:** APPROVED after revision (fixed Mosquitto 2.x config, I2C group permissions, MQTT host override, pinned uv version)

**Git Commit Message:**

```
docs: add README, ADR, Dockerfile, and deployment config

- Rewrite README with features, hardware, config, MQTT topics
- Add ADR-001 documenting legacy-to-cosalette migration decision
- Add production Dockerfile with non-root user and uv
- Add docker-compose.yml with Mosquitto and I2C passthrough
- Add framework-opportunities.md for future enhancements
```
