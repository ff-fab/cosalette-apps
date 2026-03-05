## Epic Foundation & Architecture Decisions Complete: ADRs

Created 4 Architecture Decision Records documenting the foundational design choices
for jeelink2mqtt: application framework (cosalette), sensor ID management (hybrid
auto-adopt + raw diagnostic), hardware abstraction (hexagonal port/adapter for
pylacrosse), and persistence (cosalette JsonFileStore with SaveOnChange).

**Files created/changed:**
- docs/adr/ADR-001-application-framework.md
- docs/adr/ADR-002-sensor-id-management-strategy.md
- docs/adr/ADR-003-hardware-abstraction.md
- docs/adr/ADR-004-sensor-registry-and-persistence.md

**Functions created/changed:**
- N/A (documentation only)

**Tests created/changed:**
- N/A (documentation only)

**Review Status:** APPROVED (ADR-002 revised to remove specific platform references)

**Git Commit Message:**
docs: add foundational architecture decision records

- ADR-001: Choose cosalette as the application framework
- ADR-002: Hybrid sensor ID management with auto-adopt and diagnostic channel
- ADR-003: Hexagonal port/adapter wrapping pylacrosse for hardware abstraction
- ADR-004: cosalette JsonFileStore with SaveOnChange for sensor registry persistence
