# geiger2mqtt

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ff-fab/cosalette-apps/blob/main/apps/geiger2mqtt/LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange?logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyMCAyMCIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIj4KICA8dGl0bGU+Y29zYWxldHRlIGJhZGdlIGljb24g4oCUIHdoaXRlIHZhcmlhbnQ8L3RpdGxlPgogIDxnIGZpbGw9Im5vbmUiIHN0cm9rZT0iI2ZmZmZmZiIgc3Ryb2tlLXdpZHRoPSIxLjYiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+CiAgICA8cG9seWxpbmUgcG9pbnRzPSIxNSw3LjUgMTMsNCA3LDQgNSw3LjUiLz4KICAgIDxwb2x5bGluZSBwb2ludHM9IjUsMTIuNSA3LDE2IDEzLDE2IDE1LDEyLjUiLz4KICAgIDxwb2x5bGluZSBwb2ludHM9IjMsMTAgNywxMCAxMCw1IDEzLDE1IDE2LDEwIDE3LDEwIi8+CiAgPC9nPgo8L3N2Zz4K&color=FFC105&labelColor=0D0D0F)](https://ff-fab.github.io/cosalette/)

**GPIO geiger counter to MQTT bridge**

geiger2mqtt counts the pulses of a Geiger-Müller counter board on one GPIO pin of a
Raspberry Pi. Every 30 seconds it publishes the counts per minute (CPM), the dose rate
derived from them and an average dose rate over the last 15 minutes as one JSON
message. Home Assistant discovers the three values as sensors.

## Features

- **Exact counts.** CPM is the number of pulses in the last 60 s, and the average
  covers the last 15 minutes ([ADR-001](adr/ADR-001-measurement-model.md)).
- **Any tube.** Set the conversion factor for your tube; the default suits an SBM-20.
- **Dead-tube detection.** Five minutes without a pulse mark the sensor offline. The
  next pulse brings it back online, without a restart.
- **Home Assistant discovery.** Three sensors with units and icons.
- **Unprivileged container.** Only `/dev/gpiochip0` is passed in, on every Raspberry
  Pi from the Zero 2 W to the Pi 5 ([ADR-002](adr/ADR-002-gpio-backend.md)).

## Hardware

| Component | Requirement                                                     |
| --------- | --------------------------------------------------------------- |
| Counter   | Geiger counter board with a pulse output (SBM-20, J305, ...)     |
| Interface | One GPIO input; the board pulls its output low for each pulse    |
| Platform  | Raspberry Pi with Docker                                         |

---

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install geiger2mqtt and see your first MQTT messages.

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
