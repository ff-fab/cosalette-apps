# Getting Started

Get jeelink2mqtt running and see sensor readings flowing to your MQTT broker.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Python 3.14+** | `python3 --version` to verify |
| **MQTT broker** | [Mosquitto](https://mosquitto.org/) or any MQTT 3.1.1+ broker |
| **JeeLink USB receiver** | Or skip hardware entirely with `--dry-run` |

---

## Installation

=== "uv (recommended)"

    ```bash
    uv add jeelink2mqtt
    ```

=== "pip"

    ```bash
    pip install jeelink2mqtt
    ```

---

## Minimal Configuration

Create a `.env` file in your working directory:

```env
JEELINK2MQTT_SERIAL_PORT=/dev/ttyUSB0
JEELINK2MQTT_MQTT__HOST=localhost
JEELINK2MQTT_SENSORS='[{"name": "living_room"}, {"name": "outdoor"}]'
```

Each entry in the `JEELINK2MQTT_SENSORS` JSON array defines a logical sensor name.
jeelink2mqtt will automatically adopt incoming LaCrosse IDs to these names.

!!! tip "Nested settings use `__`"

    MQTT settings are nested: `JEELINK2MQTT_MQTT__HOST`, `JEELINK2MQTT_MQTT__PORT`,
    `JEELINK2MQTT_MQTT__USERNAME`, etc.  The double underscore mirrors the object
    hierarchy.

---

## First Run

=== "Installed"

    ```bash
    jeelink2mqtt
    ```

=== "Via uv"

    ```bash
    uv run jeelink2mqtt
    ```

---

## Dry-Run Mode (No Hardware)

No JeeLink receiver?  No problem.  Dry-run mode substitutes a fake adapter that
generates synthetic sensor readings:

```bash
jeelink2mqtt --dry-run
```

This is useful for:

- Validating your `.env` configuration
- Testing MQTT topic structure and payloads
- Developing home-automation rules before hardware arrives

---

## Verify Readings

Open a second terminal and subscribe to all jeelink2mqtt topics:

```bash
mosquitto_sub -h localhost -t 'jeelink2mqtt/#' -v
```

You should see output like:

```text
jeelink2mqtt/living_room/state {"temperature": 21.3, "humidity": 52, "low_battery": false, "timestamp": "2026-03-04T10:15:00+00:00"}
jeelink2mqtt/living_room/availability online
jeelink2mqtt/raw/state {"sensor_id": 17, "temperature": 21.3, "humidity": 52, "low_battery": false, "timestamp": "2026-03-04T10:15:00+00:00"}
jeelink2mqtt/mapping/state {"living_room": {"sensor_id": 17, "mapped_at": "...", "last_seen": "..."}}
```

| Topic pattern | What it shows |
|---------------|---------------|
| `{sensor}/state` | Calibrated readings for a named sensor (retained) |
| `{sensor}/availability` | `"online"` or `"offline"` (retained) |
| `raw/state` | Every decoded frame before filtering (not retained) |
| `mapping/state` | Current ID → name mapping snapshot (retained) |
| `mapping/event` | Mapping change notifications (not retained) |

---

## Next Steps

- [Setup](setup.md) — hardware wiring, broker config, full settings reference
- [User Guide](user-guide.md) — how auto-adopt works, manual mapping commands
- [Reference](reference.md) — complete settings and topic reference
