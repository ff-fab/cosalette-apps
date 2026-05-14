# ADR-004: Sensor Registry and Persistence

## Status

Accepted **Date:** 2026-03-04 | Amended **Date:** 2026-05-14

## Context

The sensor ID→name mapping (ADR-002) must survive application restarts. Battery
replacements happen months apart, so losing the mapping on every restart would force
unnecessary operator intervention to re-establish sensor identities.

Beyond the mapping itself, the application tracks per-sensor metadata:

- **Last-seen timestamp** — when the sensor last transmitted a reading
- **Staleness state** — whether the sensor has exceeded the configurable timeout
- **Battery-changed timestamp** — when the current mapping was created (proxy for
  last battery replacement)
- **Calibration offsets** — optional per-sensor temperature/humidity corrections

This data must be persisted atomically to avoid corruption from unexpected shutdowns
(power loss, OOM kill, SIGKILL).

## Decision

Use **cosalette's JsonFileStore** with SaveOnChange policy to persist the sensor
registry. The mapping table and metadata are stored as a single key, serialized to a
human-readable JSON file on every mapping change.

## Decision Drivers

- Simplicity (minimal moving parts)
- Reliability across restarts (data survives daemon restart and host reboot)
- Framework integration (no additional dependencies)
- Atomic writes (corruption resistance on unexpected shutdown)
- Operator readability (human-inspectable for debugging)
- Multi-sensor failure recovery (persistent state aids disambiguation)

## Considered Options

1. **cosalette JsonFileStore** — use the framework's built-in persistence with a JSON
   file backend. Store the mapping table and metadata as a single key. Use SaveOnChange
   policy for immediate persistence on mapping updates.

2. **SQLite** — store mappings and metadata in an SQLite database with WAL mode for
   concurrent read/write safety.

3. **MQTT retained messages** — store the mapping as a retained message on a dedicated
   MQTT topic. Read it back on startup by subscribing and waiting for the retained
   message.

4. **External config file** — store mappings in a separate YAML/JSON config file that
   the operator maintains manually.

## Decision Matrix

| Criterion              | JsonFileStore | SQLite | MQTT retained | External config |
| ---------------------- | ------------- | ------ | ------------- | --------------- |
| Simplicity             | 5             | 3      | 3             | 4               |
| Restart reliability    | 5             | 5      | 3             | 5               |
| Framework integration  | 5             | 2      | 3             | 1               |
| Atomic writes          | 5             | 5      | 2             | 2               |
| Operator readability   | 5             | 2      | 2             | 5               |
| No extra dependencies  | 5             | 4      | 5             | 5               |
| Recovery support       | 4             | 5      | 2             | 3               |
| **Total**              | **34**        | **26** | **20**        | **25**          |

_Scale: 1 (poor) to 5 (excellent)_

## SensorRegistry Design

The `SensorRegistry` is the central domain object managing sensor identity:

### Core Data

```
mapping: dict[int, str]          # sensor_id → sensor_name
```

### Per-Sensor Metadata

```
last_seen: datetime              # timestamp of most recent reading
battery_changed: datetime        # when this mapping was created
calibration: CalibrationOffset   # optional temp/humidity corrections
```

### Behaviour

- **Staleness timeout**: configurable, default 600 seconds (10 minutes). A sensor
  exceeding this threshold is considered stale and eligible for auto-adopt (ADR-002).
- **Shared state adapter**: registered with cosalette and injected into both the
  receiver device (to resolve IDs to names) and the mapping command handler (to accept
  manual overrides).
- **Persistence trigger**: serialized to JsonFileStore on every mapping change
  (SaveOnChange). Metadata updates (last_seen) are persisted periodically, not on every
  reading, to avoid excessive I/O.

## Consequences

### Positive

- Zero additional dependencies — uses framework-provided persistence
- Human-readable JSON file aids debugging — operators can inspect and even hand-edit
  the mapping if needed
- Atomic writes (rename-based) protect against corruption from unexpected shutdown
- SaveOnChange ensures mapping changes are persisted immediately — no data loss window
- Framework integration means the store participates in cosalette's lifecycle
  (clean shutdown flushes pending writes)

### Negative

- JSON file is not suitable for high-frequency writes — mitigated by only persisting
  mapping changes immediately and batching metadata updates
- No query capability (unlike SQLite) — acceptable since the dataset is small (typically
  fewer than 20 sensors)
- Single-file storage has no built-in history — mapping changes are logged to MQTT
  (ADR-002) for auditability, but the file itself only holds current state
- Manual edits to the JSON file risk introducing invalid state if the operator makes a
  mistake

## Amendment (2026-05-14) — Corrective

**Rationale:** The original decision described a SaveOnChange policy that no longer matches the implementation. Writes are now application-managed: the on_registry_events reactor handles immediate persistence on mapping changes, and persist_registry_if_due handles periodic last-seen metadata updates.

> **Justification for amendment (not supersession):** The storage backend (JsonFileStore) is unchanged and the decision to use it is still valid. Only the persistence trigger mechanism differs from the original write-up; no downstream code depends on the SaveOnChange description. The cost of updating the wording here is negligible and corrective amendment is appropriate.

### Revised Decision

Use cosalette's JsonFileStore to persist the sensor registry. The mapping table and metadata are stored as a single key, serialized to a human-readable JSON file. Writes are application-managed: mapping-change events trigger immediate persistence via the `on_registry_events` reactor; last-seen metadata is persisted periodically via `persist_registry_if_due` to avoid excessive I/O.

!!! note "Editorial note (2026-05-14)"
    The `on_registry_events` reactor (registered with `@app.react`) immediately serializes the registry snapshot to JsonFileStore on every mapping-change event.

!!! note "Editorial note (2026-05-14)"
    `persist_registry_if_due` handles periodic background persistence for last-seen metadata, called from the main receiver loop after each frame, defaulting to a 60-second interval.
