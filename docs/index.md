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

-   **[airthings2mqtt](airthings2mqtt/)** <span class="card-license">MIT</span>

    ---

    Bridges Airthings Wave BLE air quality sensors to MQTT, publishing 24-hour and
    long-term radon averages.

-   **[caldates2mqtt](caldates2mqtt/)** <span class="card-license">MIT</span>

    ---

    Reads CalDAV calendar dates and publishes upcoming all-day events to MQTT, with
    multi-calendar support and on-demand re-read commands.

-   **[gas2mqtt](gas2mqtt/)** <span class="card-license">MIT</span>

    ---

    Reads a domestic gas meter using a QMC5883L magnetometer over I2C and publishes
    counter ticks, temperature, and debug data to MQTT.

-   **[jeelink2mqtt](jeelink2mqtt/)** <span class="card-license">MIT</span>

    ---

    Bridges LaCrosse temperature and humidity sensors to MQTT via a JeeLink USB receiver.

-   **[velux2mqtt](velux2mqtt/)** <span class="card-license">MIT</span>

    ---

    Controls Velux covers via Velux remotes and relays connected to GPIO pins,
    publishing state and accepting commands via MQTT.

-   **[vito2mqtt](vito2mqtt/)** <span class="card-license">GPL-3.0-or-later</span>

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
