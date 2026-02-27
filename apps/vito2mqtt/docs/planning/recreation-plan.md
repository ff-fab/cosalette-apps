# vito2mqtt Recreation Plan

## Business Logic Summary (from Legacy Analysis)

### What the Legacy System Does

The legacy project (`pyvcontrol` + `vcontrol_mqtt`) is an **IoT-to-MQTT bridge**
for a **Viessmann Vitodens 200-W** domestic gas condensing boiler. It:

1. **Communicates with the boiler** via the **Optolink serial interface** using
   the **P300 protocol** (4800 baud, 8E2 serial config)
2. **Publishes sensor readings** to an MQTT broker at different polling intervals
3. **Accepts commands** via MQTT to change boiler parameters (setpoints,
   operation modes, timers)

### Architecture Layers

| Layer | Legacy Module | Responsibility |
|-------|--------------|----------------|
| **Serial transport** | `viSerial` (in `viControl.py`) | Raw serial I/O with thread-safe locking, connect/disconnect/send/read |
| **Protocol framing** | `viTelegram.py` | P300 telegram framing: start byte `0x41`, header (type, mode), command, payload, checksum |
| **Command registry** | `viCommand.py` | Maps human-readable command names → memory addresses, data lengths, units, access modes |
| **Data type codec** | `viData.py` | Encodes/decodes typed values (temperatures, timers, error codes, operating modes, etc.) |
| **Session control** | `viControl.py` | Handshake/init sequence (reset → sync → ack), read/write command execution |
| **MQTT bridge** | `vcontrol_mqtt.py` | Signal mapping, polling schedules, MQTT pub/sub, command dispatch |

### Signal Groups (Polling Schedule)

The bridge reads ~100 data points from the boiler organised by polling frequency:

| Group | Interval | Count | Examples |
|-------|----------|-------|----------|
| **5-minute** | 300 s | ~23 | Outside temp, hot water temp, burner power, flow temps, pump states |
| **1-hour** | 3600 s | ~8 | Burner starts, operating hours, operation modes |
| **4-hour** | 14400 s | ~2 | Frost warnings |
| **On-demand (read)** | Manual trigger via MQTT | ~40+ | Setpoints, heating curve params, timers (M1/M2/WW/ZP), error registers, system time |
| **On-demand (write)** | Command via MQTT | ~30+ | Same as on-demand read where access_mode='write' |

### Writable Parameters

The system supports MQTT-driven writes for:
- **Temperature setpoints**: hot water target, room temperatures (normal, saving, party)
- **Heating curve tuning**: gradient and level for circuits M1 and M2
- **Timer schedules**: weekly timers for heating M1, M2, hot water, and circulation pump (4 time slots per day)
- **Operation modes**: normal, saving, party for M1 and M2
- **System time**: sync boiler clock

### Data Types (Vitodens 200-W Specific)

The codec layer handles these data types (used by the Vitodens 200-W command set):

| Unit Code | Description | Encoding |
|-----------|-------------|----------|
| `IS10` | Signed int ÷ 10 | Fixed-point temperatures (e.g., 239 → 23.9°C) |
| `IUNON` | Unsigned int, no scale | Raw integer values |
| `IU3600` | Unsigned int ÷ 3600 | Seconds → hours conversion |
| `BA` | Betriebsart (operating mode) | Enum: aus/Red./Normal/Heizen&WW/... |
| `RT` | Return status | Enum: 0/1/2/Not OK |
| `CT` | Cycle time (timer) | 4 time slot pairs, bit-packed hours/minutes |
| `ES` | Error set | Error code byte + 8-byte timestamp |
| `TI` | System time | 8-byte BCD datetime |
| `PR2` | Second-byte int | Pump speed extraction |
| `PR3` | First-byte int ÷ 2 | Power percentage |
| `USV` | Umschaltventil | Enum: UNDEF/Heizen/Mittelstellung/Warmwasser |

### P300 Protocol Summary

- **Telegram format**: `0x41 | length | type | mode | address(2) | data_length | [payload] | checksum`
- **Types**: Request (`0x00`), Response (`0x01`), Error (`0x03`)
- **Modes**: Read (`0x01`), Write (`0x02`), Function Call (`0x07`)
- **Checksum**: Sum of all bytes after start byte, modulo 256
- **Init sequence**: Send reset (`0x04`) → wait for not_init (`0x05`) → send sync (`0x16 0x00 0x00`) → expect ack (`0x06`)
- **Serial config**: 4800 baud, 8 data bits, even parity, 2 stop bits

---

## Recreation Plan: cosalette-Based Architecture

### High-Level Mapping

| Legacy Concept | cosalette Concept |
|---------------|-------------------|
| `vcontrol_mqtt.py` main loop | `cosalette.App` composition root + `@app.device` |
| 5min/1hr/4hr polling | `@app.telemetry` devices with different intervals |
| MQTT set/# handlers | `@app.command` handlers |
| `viControl` + `viSerial` | `OptolinkPort` protocol + `OptolinkAdapter` |
| `viTelegram` | Part of adapter internals (protocol framing) |
| `viCommand` / `viData` | Part of adapter internals (command registry + codec) |
| Hardcoded MQTT config | `cosalette.Settings` subclass with env vars |
| `paho-mqtt` manual mgmt | cosalette framework MQTT lifecycle |

### Proposed Project Structure

```
packages/src/vito2mqtt/
├── __init__.py
├── _version.py
├── app.py                 # cosalette App assembly + device registrations
├── settings.py            # Vito2MqttSettings (cosalette.Settings subclass)
├── ports.py               # OptolinkPort protocol (PEP 544)
├── errors.py              # Domain exceptions
├── adapters/
│   ├── __init__.py
│   ├── optolink.py        # Real serial Optolink adapter
│   └── fake_optolink.py   # Fake adapter for dry-run + testing
└── optolink/              # Clean-room P300 protocol implementation
    ├── __init__.py
    ├── commands.py         # Vitodens 200-W command registry
    ├── codec.py            # Data type encoder/decoder
    ├── telegram.py         # P300 telegram framing
    └── transport.py        # Serial transport layer
```

### Architectural Decisions (Confirmed)

**Device Architecture: Option B — Multiple `@app.telemetry` + `@app.command`**
- Most idiomatic cosalette approach
- One `@app.telemetry` per domain entity, `@app.command` for writable params
- Serial port access coordinated via single shared adapter with async locking

**Topic Layout: Group by Domain Entity**

| Device | Type | Key Signals |
|--------|------|-------------|
| `outdoor` | telemetry | Outside temperature |
| `hot_water` | telemetry + command | WW temp, outlet, boiler, setpoint, pump lag, circ pump, charging pump, timers |
| `burner` | telemetry | Boiler temp, setpoint, exhaust temp, power %, starts, operating hours |
| `heating_radiator` | telemetry + command | M1: flow temps, pump, op mode, heating curve, room temps, frost, timers |
| `heating_floor` | telemetry + command | M2: mirrors M1 for floor heating circuit |
| `system` | telemetry + command | Internal pump, switch valve, system time |
| `diagnosis` | telemetry | Error state, error registers 1–9 |

**Protocol Package: Internal sub-package** (`vito2mqtt.optolink`)

**Signal Names: English throughout** — consistent English in code, topics, docs

**Polling Intervals: Configurable via settings** with sensible defaults matching
legacy intervals (300s, 3600s, 14400s)

**Connection Strategy: Connect per polling cycle** — legacy-proven, simpler fault
tolerance. Serial connection opened/closed per-read, not persistent.

### Clean-Room Approach for pyvcontrol

The P300 protocol layer (`optolink/` package) must follow strict clean-room TDD:

1. **Spec Agent**: Reads legacy code, extracts behavioral specifications and
   writes tests based on observed behavior (input → expected output)
2. **Impl Agent**: Receives only the specs/tests, implements without viewing
   legacy code
3. **Boundary**: The `OptolinkPort` protocol interface is the clean-room boundary

### Implementation Phases

#### Phase 0: Foundation
- ADRs for key architectural decisions
- Add `cosalette` dependency
- Project structure setup

#### Phase 1: Protocol Layer (Clean-Room TDD)
- P300 telegram framing (encode/decode)
- Data type codec (all Vitodens 200-W types)
- Command registry (Vitodens 200-W addresses)
- Serial transport abstraction

#### Phase 2: Adapter Layer
- `OptolinkPort` protocol definition
- `OptolinkAdapter` (real serial)
- `FakeOptolinkAdapter` (dry-run / testing)

#### Phase 3: Application Layer
- `Vito2MqttSettings` configuration
- Telemetry devices (polling groups)
- Command handlers (writable parameters)
- App assembly (`app.py`)
- Lifespan (serial connection management)
- Domain error types

#### Phase 4: Documentation
- Zensical-based user-journey docs
- GitHub Pages deployment
- ADR index in docs site

#### Phase 5: Integration & Polish
- Integration tests with `AppHarness`
- Docker deployment config
- CI pipeline integration
