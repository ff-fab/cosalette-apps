# caldates2mqtt

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ff-fab/cosalette-apps/blob/main/apps/caldates2mqtt/LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)

**CalDAV calendar dates to MQTT bridge**

---

caldates2mqtt connects to one or more CalDAV calendars, fetches upcoming all-day events
within a configurable lookahead window, and publishes them as JSON payloads to MQTT. Each
configured calendar becomes an independent device with periodic polling and on-demand
re-read via MQTT command.
