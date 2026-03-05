---
title: Architecture Decision Records
---

# Architecture Decision Records

Architecture Decision Records (ADRs) document the significant technical decisions
made during vito2mqtt's development. Each ADR captures the context, decision, and
consequences so that future maintainers understand **why** something was built the
way it was — not just *what* was built.

ADRs follow the format described by Michael Nygard in
[Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

---

## Status Overview

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [ADR-001](ADR-001-framework-choice.md) | Framework Choice — cosalette | Accepted | 2026-02-27 |
| [ADR-002](ADR-002-mqtt-topic-layout.md) | MQTT Topic Layout — Domain-Grouped | Accepted | 2026-02-27 |
| [ADR-003](ADR-003-hardware-abstraction.md) | Hardware Abstraction — Hexagonal Architecture | Accepted | 2026-02-27 |
| [ADR-004](ADR-004-optolink-protocol-design.md) | Optolink Protocol Design | Accepted | 2026-02-27 |
| [ADR-005](ADR-005-configuration-settings.md) | Configuration and Settings | Accepted | 2026-02-27 |
| [ADR-006](ADR-006-configurable-signal-language.md) | Configurable Signal Language (DE/EN) | Accepted | 2026-02-28 |
| [ADR-007](ADR-007-telemetry-coalescing-groups.md) | Telemetry Coalescing Groups | Accepted | 2026-03-03 |

---

## Summary

### ADR-001: Framework Choice — cosalette

Chose [cosalette](https://github.com/ff-fab/cosalette) as the application framework.
cosalette provides MQTT lifecycle management, telemetry scheduling, command handling,
and pydantic-settings integration out of the box — letting vito2mqtt focus on
Optolink protocol and device logic.

### ADR-002: MQTT Topic Layout — Domain-Grouped

Topics use a domain-grouped structure:
`vito2mqtt/{device_id}/{group}/state` for telemetry and
`vito2mqtt/{device_id}/{group}/set` for commands. Groups are semantic domains
(outdoor, hot_water, burner, etc.) rather than flat signal lists or deep hierarchies.

### ADR-003: Hardware Abstraction — Hexagonal Architecture

The Optolink serial interface is abstracted behind a port protocol
(`OptolinkPort`), enabling a fake adapter for testing and dry-run mode.
Follows hexagonal (ports & adapters) architecture.

### ADR-004: Optolink Protocol Design

Documents the P300 protocol implementation: telegram structure, byte framing,
address mapping, codec type system (11 type codes), and the command registry.

### ADR-005: Configuration and Settings

All settings use environment variables with the `VITO2MQTT_` prefix. Per-domain
polling intervals are configurable. Validated at startup via pydantic-settings.

### ADR-006: Configurable Signal Language (DE/EN)

Enum-type signals (BA, USV, ES) support bilingual labels — German and English.
Controlled by `VITO2MQTT_SIGNAL_LANGUAGE`. Numeric types are language-neutral.

### ADR-007: Telemetry Coalescing Groups

Telemetry handlers sharing the `"optolink"` coalescing group have their ticks
aligned by cosalette, so signals due at the same time are batched into a single
serial session — reducing Optolink bus occupancy and improving throughput.
