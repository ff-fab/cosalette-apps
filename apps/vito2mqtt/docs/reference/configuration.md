---
title: Configuration Reference
---

# Configuration Reference

vito2mqtt is configured via environment variables or a `.env` file. All variables
use the `VITO2MQTT_` prefix. Settings are validated at startup using
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
through the [cosalette](https://github.com/ff-fab/cosalette) framework
(see [ADR-001](../adr/ADR-001-framework-choice.md)).

---

## Base Settings (from cosalette)

These settings are inherited from the cosalette `Settings` base class:

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `VITO2MQTT_MQTT__HOST` | MQTT broker hostname or IP | `localhost` |
| `VITO2MQTT_MQTT__PORT` | MQTT broker port | `1883` |
| `VITO2MQTT_MQTT__USERNAME` | MQTT username (optional) | — |
| `VITO2MQTT_MQTT__PASSWORD` | MQTT password (optional) | — |
| `VITO2MQTT_LOGGING__LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) | `INFO` |

!!! note "Nested delimiter"
    MQTT settings use `__` (double underscore) as the nested delimiter. The variable
    `VITO2MQTT_MQTT__HOST` maps to the `mqtt.host` field in the settings model.
    This is the standard
    [pydantic-settings nested model convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values).

---

## Application Settings

These settings are specific to vito2mqtt and defined in `Vito2MqttSettings`:

### Connection

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `serial_port` | `VITO2MQTT_SERIAL_PORT` | `str` | **Required** | Serial device path (e.g., `/dev/ttyUSB0`) |
| `serial_baud_rate` | `VITO2MQTT_SERIAL_BAUD_RATE` | `int` | `4800` | Baud rate for Optolink connection |

### Device Identification

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `device_id` | `VITO2MQTT_DEVICE_ID` | `str` | `vitodens200w` | Device identifier in MQTT topic hierarchy |
| `signal_language` | `VITO2MQTT_SIGNAL_LANGUAGE` | `"de"` \| `"en"` | `"en"` | Language for signal names (see [ADR-006](../adr/ADR-006-configurable-signal-language.md)) |

### Polling Intervals

Per-domain polling intervals in seconds. Each controls how often a signal group is
read from the boiler (see [ADR-005](../adr/ADR-005-configuration-settings.md)).

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `polling_outdoor` | `VITO2MQTT_POLLING_OUTDOOR` | `float` | `300.0` | Outdoor sensors polling interval |
| `polling_hot_water` | `VITO2MQTT_POLLING_HOT_WATER` | `float` | `300.0` | Hot water polling interval |
| `polling_burner` | `VITO2MQTT_POLLING_BURNER` | `float` | `300.0` | Burner telemetry polling interval |
| `polling_heating_radiator` | `VITO2MQTT_POLLING_HEATING_RADIATOR` | `float` | `300.0` | M1 radiator circuit polling interval |
| `polling_heating_floor` | `VITO2MQTT_POLLING_HEATING_FLOOR` | `float` | `300.0` | M2 floor heating circuit polling interval |
| `polling_system` | `VITO2MQTT_POLLING_SYSTEM` | `float` | `3600.0` | System info polling interval |
| `polling_diagnosis` | `VITO2MQTT_POLLING_DIAGNOSIS` | `float` | `300.0` | Diagnosis/error polling interval |

!!! tip "Polling tuning"
    All intervals must be greater than zero. Outdoor and diagnosis groups default to
    5 minutes (300s). The system group defaults to 1 hour (3600s) since its signals
    change infrequently. Adjust based on your monitoring needs vs. serial bus load.

### Legionella Treatment

Settings for the automated legionella prevention cycle. The treatment temporarily
raises hot water temperature to kill bacteria.

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `legionella_temperature` | `VITO2MQTT_LEGIONELLA_TEMPERATURE` | `int` | `68` | Target hot water temp during treatment (°C) |
| `legionella_duration_minutes` | `VITO2MQTT_LEGIONELLA_DURATION_MINUTES` | `int` | `40` | Duration of treatment cycle (minutes) |
| `legionella_safety_margin_minutes` | `VITO2MQTT_LEGIONELLA_SAFETY_MARGIN_MINUTES` | `int` | `30` | Minimum remaining heating-window time for treatment to start (minutes) |

!!! warning "Legionella safety"
    The safety margin ensures the treatment only starts if there is enough time
    remaining in the current heating window to complete the full cycle. Setting this
    too low risks an incomplete treatment.

---

## Complete `.env` Example

```bash title=".env"
# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
VITO2MQTT_SERIAL_PORT=/dev/ttyUSB0
VITO2MQTT_SERIAL_BAUD_RATE=4800

# ---------------------------------------------------------------------------
# MQTT Broker
# ---------------------------------------------------------------------------
VITO2MQTT_MQTT__HOST=192.168.1.100
VITO2MQTT_MQTT__PORT=1883
VITO2MQTT_MQTT__USERNAME=vito2mqtt
VITO2MQTT_MQTT__PASSWORD=secret

# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------
VITO2MQTT_DEVICE_ID=vitodens200w
VITO2MQTT_SIGNAL_LANGUAGE=en
VITO2MQTT_LOGGING__LEVEL=INFO

# ---------------------------------------------------------------------------
# Polling Intervals (seconds)
# ---------------------------------------------------------------------------
VITO2MQTT_POLLING_OUTDOOR=300
VITO2MQTT_POLLING_HOT_WATER=300
VITO2MQTT_POLLING_BURNER=300
VITO2MQTT_POLLING_HEATING_RADIATOR=300
VITO2MQTT_POLLING_HEATING_FLOOR=300
VITO2MQTT_POLLING_SYSTEM=3600
VITO2MQTT_POLLING_DIAGNOSIS=300

# ---------------------------------------------------------------------------
# Legionella Treatment
# ---------------------------------------------------------------------------
VITO2MQTT_LEGIONELLA_TEMPERATURE=68
VITO2MQTT_LEGIONELLA_DURATION_MINUTES=40
VITO2MQTT_LEGIONELLA_SAFETY_MARGIN_MINUTES=30
```
