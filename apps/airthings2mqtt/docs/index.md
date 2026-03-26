# airthings2mqtt

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ff-fab/cosalette-apps/blob/main/apps/airthings2mqtt/LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)

**Read Airthings Wave air quality sensors over BLE and publish to MQTT.**

airthings2mqtt connects to Airthings Wave sensors via Bluetooth Low Energy on a
Raspberry Pi, reads temperature, humidity, and radon levels, and publishes the data
to an MQTT broker — ready for Home Assistant or any MQTT consumer.

---

## Features

- **BLE sensor polling** — connects to Airthings Wave, Wave Plus, and Wave Mini sensors via BlueZ
- **Radon monitoring** — publishes 24-hour and long-term average radon concentrations
- **Temperature & humidity** — ambient readings alongside air quality data
- **Health reporting** — automatic heartbeats, per-device availability, and LWT
- **Simple `.env` configuration** — all settings via environment variables or a `.env` file, powered by [cosalette](https://github.com/ff-fab/cosalette)
- **Docker-ready** — single `docker compose up` deployment with BLE passthrough

---

## Hardware

| Component          | Details                                           |
| ------------------ | ------------------------------------------------- |
| **Sensor**         | Airthings Wave, Wave Plus, or Wave Mini (BLE)     |
| **Interface**      | Bluetooth Low Energy (BlueZ)                      |
| **Platform**       | Raspberry Pi (any model with Bluetooth: 3/4/5, Zero 2 W) |

---

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install airthings2mqtt, find your sensor, and see your first MQTT messages.

    [:octicons-arrow-right-24: Get started](getting-started.md)

-   :material-cog:{ .lg .middle } **Configuration**

    ---

    All settings — environment variables, `.env` files, and CLI flags.

    [:octicons-arrow-right-24: Configure](configuration.md)

-   :material-access-point:{ .lg .middle } **MQTT Topics**

    ---

    Topic reference with payload schemas, directions, and retain flags.

    [:octicons-arrow-right-24: Topics](mqtt-topics.md)

-   :material-file-document-multiple:{ .lg .middle } **ADRs**

    ---

    Architecture decision records documenting design choices.

    [:octicons-arrow-right-24: Decisions](adr/)

</div>
