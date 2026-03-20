---
title: Home
---

# vito2mqtt

**A smart home app to control a Vitodens gas heating via MQTT.**

vito2mqtt is an IoT-to-MQTT bridge daemon for Viessmann Vitodens 200-W gas boilers.
It reads telemetry data — temperatures, pressures, burner hours, error codes — over the
Optolink serial interface using the P300 protocol, publishes everything to an MQTT
broker, and accepts commands to modify boiler parameters like setpoints, schedules, and
operating modes.

---

## Key Features

<div class="grid cards" markdown>

-   :material-thermometer:{ .lg .middle } **46 Telemetry Signals**

    ---

    Temperatures, pressures, burner stats, pump states, and error codes across
    7 domain groups — outdoor, hot water, burner, radiator (M1), floor heating (M2),
    system, and diagnosis.

-   :material-pencil:{ .lg .middle } **42 Writable Commands**

    ---

    Control heating schedules, setpoints, operating modes, and pump timers.
    Modify your boiler configuration remotely via MQTT.

-   :material-clock-fast:{ .lg .middle } **Configurable Polling Intervals**

    ---

    Set per-domain polling intervals — poll outdoor sensors every 5 minutes,
    system info every hour. Fine-tune to your needs.

-   :material-shield-check:{ .lg .middle } **Read-Before-Write Optimization**

    ---

    Skips writes when values are unchanged, reducing serial bus traffic and
    EEPROM wear on the boiler controller. Use `__force` to override.

-   :material-group:{ .lg .middle } **Coalescing Groups**

    ---

    Signals due for polling at the same tick are batched into a single serial
    session, minimizing Optolink bus occupancy (see [ADR-007](adr/ADR-007-telemetry-coalescing-groups.md)).

-   :material-translate:{ .lg .middle } **Bilingual Signal Names**

    ---

    Signal names available in German and English. Set `VITO2MQTT_SIGNAL_LANGUAGE`
    to `de` or `en` (see [ADR-006](adr/ADR-006-configurable-signal-language.md)).

-   :material-bacteria:{ .lg .middle } **Automated Legionella Treatment**

    ---

    Configurable hot water temperature boost with duration and safety-margin
    settings to prevent legionella growth.

-   :material-cog:{ .lg .middle } **Simple `.env` Configuration**

    ---

    All settings via environment variables or a `.env` file. No YAML, no config
    files to manage. Powered by [cosalette](https://github.com/ff-fab/cosalette).

</div>

---

## Quick Start

```bash
# Install
uv pip install vito2mqtt

# Create minimal .env
cat > .env << 'EOF'
VITO2MQTT_SERIAL_PORT=/dev/ttyUSB0
VITO2MQTT_MQTT__HOST=localhost
EOF

# Run
uv run vito2mqtt
```

Or try without hardware using the dry-run mode:

```bash
uv run vito2mqtt --dry-run
```

See the [Getting Started](getting-started/index.md) guide for the full walkthrough.

---

## Documentation

| Section | Description |
|---------|-------------|
| [Getting Started](getting-started/index.md) | Prerequisites, installation, first run |
| [Guides](guides/index.md) | Home Assistant integration, Docker, recipes |
| [Configuration Reference](reference/configuration.md) | All settings and environment variables |
| [MQTT Signal Reference](reference/signals.md) | Complete signal tables with addresses and types |
| [Architecture Decisions](adr/index.md) | ADRs documenting project design choices |

---

## License

vito2mqtt is licensed under the [GNU General Public License v3.0 or later](https://www.gnu.org/licenses/gpl-3.0.html).
