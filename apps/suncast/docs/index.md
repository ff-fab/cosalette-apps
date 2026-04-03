# suncast

[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](https://github.com/ff-fab/cosalette-apps/blob/main/apps/suncast/LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)

**Solar shadow visualization service**

suncast is a cosalette-based IoT service that computes solar positions from GPS
coordinates and generates shadow visualizations of building footprints. It publishes SVG
(and optionally PNG) images via MQTT and filesystem output, enabling both OpenHAB and
Home Assistant dashboards to display real-time shadow maps.

<div class="grid" markdown>

![Morning shadows](images/generated/showcase-morning.svg){ width="220" }
![Noon shadows](images/generated/showcase-noon.svg){ width="220" }
![Afternoon shadows](images/generated/showcase-afternoon.svg){ width="220" }
![Night — no shadows](images/generated/showcase-night.svg){ width="220" }

</div>

---

## Features

- **Real-time solar position** — computes azimuth, elevation, sunrise/sunset from GPS coordinates
- **Building shadow projection** — parallel shadow casting from arbitrary convex polygons
- **SVG and PNG output** — publishes images via MQTT, filesystem, and optional HTTP server
- **Configurable geometry** — YAML or SVG-based building footprint definitions
- **Sundial ring and day/night arc** — visual indicators of sun path and direction
- **Health reporting** — automatic heartbeats, per-device availability, and LWT
- **Docker-ready** — single `docker compose up` deployment with nginx sidecar

---

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install suncast and see your first MQTT messages.

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

    Rendering pipeline, domain layers, and cosalette framework integration.

    [:octicons-arrow-right-24: Architecture](architecture.md)

-   :material-compass-outline:{ .lg .middle } **Geometry Guide**

    ---

    Define building footprints in YAML or import from SVG.

    [:octicons-arrow-right-24: Geometry](geometry-guide.md)

-   :material-file-document-multiple:{ .lg .middle } **ADRs**

    ---

    Architecture decision records documenting design choices.

    [:octicons-arrow-right-24: Decisions](adr/)

</div>
