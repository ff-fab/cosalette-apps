---
title: Getting Started
---

# Getting Started

This guide takes you from zero to seeing live boiler telemetry on your MQTT broker.

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **Python** | ≥ 3.14 |
| **Optolink adapter** | USB-to-serial adapter connected to the Vitodens 200-W service port |
| **MQTT broker** | Any MQTT 3.1.1+ broker — e.g., [Mosquitto](https://mosquitto.org/) |
| **uv** | Recommended Python package manager ([docs](https://docs.astral.sh/uv/)) |

!!! note "No hardware? No problem"
    You can run vito2mqtt in **dry-run mode** with a fake adapter — no serial port or
    boiler needed. Great for exploring the MQTT topic structure.

---

## Installation

### From PyPI

```bash
uv pip install vito2mqtt
```

### From source

```bash
git clone https://github.com/ff-fab/vito2mqtt.git
cd vito2mqtt
uv sync
```

---

## Minimal Configuration

vito2mqtt reads settings from environment variables or a `.env` file in the working
directory. Create a `.env` file with the minimum required settings:

```bash title=".env"
# Required — serial port for the Optolink adapter
VITO2MQTT_SERIAL_PORT=/dev/ttyUSB0

# Required — MQTT broker connection
VITO2MQTT_MQTT__HOST=localhost
VITO2MQTT_MQTT__PORT=1883

# Optional — MQTT authentication
# VITO2MQTT_MQTT__USERNAME=vito2mqtt
# VITO2MQTT_MQTT__PASSWORD=secret
```

!!! tip "Nested delimiter"
    MQTT settings use `__` (double underscore) as a nested delimiter — e.g.,
    `VITO2MQTT_MQTT__HOST` maps to the `mqtt.host` setting. This follows the
    [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
    convention.

See the [Configuration Reference](../reference/configuration.md) for all available
settings.

---

## First Run

### With hardware

```bash
uv run vito2mqtt
```

vito2mqtt connects to the Optolink adapter, initializes the P300 protocol, and starts
polling telemetry. You should see log output indicating successful connection and
first data reads.

### Dry-run mode (no hardware)

```bash
uv run vito2mqtt --dry-run
```

Dry-run mode uses a fake adapter that returns simulated values. This is useful for:

- Testing your MQTT broker setup
- Exploring the topic structure
- Developing Home Assistant configurations

---

## Verifying Output

Subscribe to the telemetry topics to see data flowing:

```bash
# Subscribe to all state topics
mosquitto_sub -h localhost -t 'vito2mqtt/vitodens200w/+/state' -v
```

You should see JSON payloads for each signal group:

```json title="vito2mqtt/vitodens200w/outdoor/state"
{
  "outdoor_temperature": 8.5,
  "outdoor_temperature_lowpass": 8.3,
  "outdoor_temperature_damped": 8.4
}
```

```json title="vito2mqtt/vitodens200w/burner/state"
{
  "boiler_temperature": 42.1,
  "boiler_temperature_lowpass": 41.8,
  "boiler_temperature_setpoint": 45.0,
  "exhaust_temperature": 52.3,
  "burner_modulation": 67,
  "burner_starts": 14523,
  "burner_hours_stage1": 8241.5,
  "plant_power_output": 72.5
}
```

```json title="vito2mqtt/vitodens200w/diagnosis/state"
{
  "error_status": 0,
  "error_history_1": ["Flame failure", "2026-01-15T14:30:00"],
  "error_history_2": ["Flow sensor fault", "2025-12-03T08:15:00"]
}
```

---

## Next Steps

- **[Configuration Reference](../reference/configuration.md)** — tune polling intervals,
  legionella settings, signal language
- **[MQTT Signal Reference](../reference/signals.md)** — full list of 88 signals with
  addresses, types, and access modes
- **[Guides](../guides/index.md)** — Home Assistant integration, Docker deployment,
  common recipes
