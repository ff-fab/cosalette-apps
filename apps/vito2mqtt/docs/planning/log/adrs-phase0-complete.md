## Epic Architectural Decision Records Complete: Phase 0 ADRs

All 5 foundational Architecture Decision Records written, reviewed, and cross-referenced.
ADRs establish the greenfield architectural foundation for vito2mqtt: framework choice,
MQTT topic layout, hardware abstraction, protocol design, and configuration management.

**Files created/changed:**

- docs/adr/ADR-001-framework-choice.md
- docs/adr/ADR-002-mqtt-topic-layout.md
- docs/adr/ADR-003-hardware-abstraction.md
- docs/adr/ADR-004-optolink-protocol-design.md
- docs/adr/ADR-005-configuration-settings.md
- docs/adr/.gitkeep (removed)

**Functions created/changed:**

- N/A (documentation only)

**Tests created/changed:**

- N/A (documentation only)

**Review Status:** APPROVED with cross-reference improvements applied

**Git Commit Message:**

```
docs: add 5 foundational ADRs for vito2mqtt architecture

- ADR-001: Choose cosalette as application framework
- ADR-002: Define domain-grouped MQTT topic layout
- ADR-003: Establish hexagonal architecture with PEP 544 ports
- ADR-004: Design layered Optolink P300 protocol sub-package
- ADR-005: Configure settings via cosalette.Settings subclass
```
