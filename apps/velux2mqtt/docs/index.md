# velux2mqtt

[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](https://github.com/ff-fab/cosalette-apps/blob/main/apps/velux2mqtt/LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)

**Control Velux covers via KLF 050 remotes and M74HC4066 GPIO switches.**

velux2mqtt bridges Velux blinds and windows to MQTT by driving KLF 050 remote buttons
through M74HC4066 analogue switch ICs connected to Raspberry Pi GPIO pins. It tracks
cover position, supports homing, and accepts MQTT commands — ready for Home Assistant
or any MQTT consumer.

---

## Features

- **GPIO cover control** — drives KLF 050 remote buttons via M74HC4066 bilateral switch ICs
- **Position tracking** — estimates cover position from travel duration and direction
- **Automatic homing** — configurable homing sequence on startup for accurate positioning
- **Drift compensation** — periodic re-homing to correct accumulated position drift
- **Auto-calibration** — measure travel times automatically with the calibration command
- **Health reporting** — automatic heartbeats, per-device availability, and LWT
- **Simple `.env` configuration** — all settings via environment variables or a `.env` file, powered by [cosalette](https://github.com/ff-fab/cosalette)
- **Docker-ready** — single `docker compose up` deployment with GPIO passthrough

---

## Hardware

| Component        | Details                                              |
| ---------------- | ---------------------------------------------------- |
| **Switch IC**    | M74HC4066 quad bilateral switch (one per KLF 050)    |
| **Remote**       | VELUX KLF 050 with soldered button contacts           |
| **Interface**    | Raspberry Pi GPIO                                     |
| **Platform**     | Raspberry Pi (any model with GPIO: 3/4/5, Zero 2 W)  |

---

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Wire the hardware, install velux2mqtt, and verify cover control via MQTT.

    [:octicons-arrow-right-24: Get started](getting-started.md)

-   :material-cog:{ .lg .middle } **Configuration**

    ---

    All settings — covers, timing, homing, drift compensation, and MQTT.

    [:octicons-arrow-right-24: Configure](configuration.md)

-   :material-access-point:{ .lg .middle } **MQTT Topics**

    ---

    Topic reference with payload schemas, directions, and retain flags.

    [:octicons-arrow-right-24: Topics](mqtt-topics.md)

-   :material-tune:{ .lg .middle } **Calibration**

    ---

    Measure travel times automatically for accurate position tracking.

    [:octicons-arrow-right-24: Calibrate](calibration.md)

-   :material-sitemap:{ .lg .middle } **Architecture**

    ---

    Hexagonal architecture, domain logic, and cosalette framework integration.

    [:octicons-arrow-right-24: Architecture](architecture.md)

-   :material-file-document-multiple:{ .lg .middle } **ADRs**

    ---

    Architecture decision records documenting design choices.

    [:octicons-arrow-right-24: Decisions](adr/)

</div>
