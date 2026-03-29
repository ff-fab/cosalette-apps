# suncast

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://github.com/ff-fab/cosalette-apps/blob/main/apps/suncast/LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)

**Solar shadow visualization service**

suncast is a cosalette-based IoT service that computes solar positions from GPS
coordinates and generates shadow visualizations of building footprints. It publishes SVG
(and optionally PNG) images via MQTT and filesystem output, enabling both OpenHAB and
Home Assistant dashboards to display real-time shadow maps.

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

-   :material-file-document-multiple:{ .lg .middle } **ADRs**

    ---

    Architecture decision records documenting design choices.

    [:octicons-arrow-right-24: Decisions](adr/)

</div>
