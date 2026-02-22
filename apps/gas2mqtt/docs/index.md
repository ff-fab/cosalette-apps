# gas2mqtt

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ff-fab/gas2mqtt/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)

**Read your domestic gas meter with a magnetometer and publish to MQTT.**

gas2mqtt attaches a QMC5883L magnetometer to a Raspberry Pi, detects gas meter
rotations via a Schmitt trigger, and publishes counter ticks, temperature, and
optional debug data to an MQTT broker — ready for Home Assistant or any MQTT consumer.

---

## Features

- **Gas tick detection** — Schmitt trigger with configurable threshold and hysteresis
- **Temperature monitoring** — EWMA-filtered, empirically calibrated
- **Consumption tracking** — optional cumulative m³ counter with MQTT set command
- **Raw magnetometer output** — optional debug device for calibration
- **Health reporting** — automatic heartbeats, per-device availability, and LWT
- **Docker-ready** — single `docker compose up` deployment

---

## Hardware

| Component     | Details                                      |
| ------------- | -------------------------------------------- |
| **Sensor**    | QMC5883L 3-axis digital magnetometer         |
| **Interface** | I2C (default bus 1, address 0x0D)            |
| **Platform**  | Raspberry Pi (or any Linux SBC with I2C)     |

---

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install gas2mqtt, connect the sensor, and see your first MQTT messages.

    [:octicons-arrow-right-24: Get started](getting-started.md)

-   :material-cog:{ .lg .middle } **Configuration**

    ---

    All settings — environment variables, `.env` files, and CLI flags.

    [:octicons-arrow-right-24: Configure](configuration.md)

-   :material-access-point:{ .lg .middle } **MQTT Topics**

    ---

    Topic reference with payload schemas, directions, and retain flags.

    [:octicons-arrow-right-24: Topics](mqtt-topics.md)

-   :material-sitemap:{ .lg .middle } **Architecture**

    ---

    Hexagonal architecture, domain logic, and cosalette framework integration.

    [:octicons-arrow-right-24: Architecture](architecture.md)

-   :material-code-tags:{ .lg .middle } **API Reference**

    ---

    Auto-generated reference for settings, ports, domain logic, devices, and adapters.

    [:octicons-arrow-right-24: Reference](reference/index.md)

</div>
