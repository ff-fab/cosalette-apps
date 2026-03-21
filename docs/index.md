---
hide:
  - navigation
  - toc
---

# cosalette-apps

A monorepo collection of IoT-to-MQTT bridge applications for smart home automation, all
built on the [cosalette](https://github.com/ff-fab/cosalette) framework.

## Apps

<div class="grid cards" markdown>

-   **[gas2mqtt](https://ff-fab.github.io/cosalette-apps/gas2mqtt/)** · MIT

    ---

    Reads a domestic gas meter using a QMC5883L magnetometer over I2C and publishes
    counter ticks, temperature, and debug data to MQTT.

-   **[jeelink2mqtt](https://ff-fab.github.io/cosalette-apps/jeelink2mqtt/)** · MIT

    ---

    Bridges LaCrosse temperature and humidity sensors to MQTT via a JeeLink USB receiver.

-   **[vito2mqtt](https://ff-fab.github.io/cosalette-apps/vito2mqtt/)** · GPL-3.0-or-later

    ---

    Controls a Viessmann Vitodens gas boiler over the Optolink serial interface,
    publishing telemetry and accepting commands via MQTT.

</div>

## Architecture

- **Framework:** [cosalette](https://github.com/ff-fab/cosalette) — async MQTT lifecycle,
  decorator-based device registration, hexagonal architecture
- **Build system:** [uv](https://docs.astral.sh/uv/) workspaces +
  [Taskfile](https://taskfile.dev/)
- **Licensing:** [REUSE](https://reuse.software/)-compliant (MIT default, GPL-3.0-or-later
  for vito2mqtt)
- **CI:** Per-app change detection with reusable workflows
- **Releases:** Release Please manifest mode (per-app versioning)
