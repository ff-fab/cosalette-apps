# caldates2mqtt

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ff-fab/cosalette-apps/blob/main/apps/caldates2mqtt/LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)

**CalDAV calendar dates to MQTT bridge**

---

caldates2mqtt connects to one or more CalDAV calendars (such as Nextcloud), fetches
upcoming all-day events within a configurable lookahead window, and publishes them as
JSON payloads to MQTT. Each configured calendar becomes an independent device with
periodic polling and on-demand re-read via MQTT command.

## Features

- **Multi-calendar support** --- configure any number of CalDAV calendars, each published as its own MQTT device
- **All-day event filtering** --- extracts only all-day events (birthdays, garbage collection, holidays), ignoring timed appointments
- **On-demand re-read** --- send a JSON command to any calendar's `/set` topic to trigger an immediate re-read with optional parameter overrides
- **Configurable lookahead** --- per-calendar `days` and `entries` settings control the event window and result count
- **Health reporting** --- automatic heartbeats, per-device availability, and LWT via [cosalette](https://github.com/ff-fab/cosalette)
- **Simple `.env` configuration** --- all settings via environment variables or a `.env` file
- **Docker-ready** --- single `docker compose up` deployment, no special hardware required

---

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install caldates2mqtt, configure your CalDAV calendars, and see your first MQTT messages.

    [:octicons-arrow-right-24: Get started](getting-started.md)

-   :material-cog:{ .lg .middle } **Configuration**

    ---

    All settings --- environment variables, `.env` files, and CLI flags.

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
