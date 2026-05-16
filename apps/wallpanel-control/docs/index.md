# wallpanel-control

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ff-fab/cosalette-apps/blob/main/apps/wallpanel-control/LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange?logo=data:image/svg%2bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyMCAyMCIgd2lkdGg9IjIwIiBoZWlnaHQ9IjIwIj4KICA8dGl0bGU+Y29zYWxldHRlIGJhZGdlIGljb24g4oCUIHdoaXRlIHZhcmlhbnQ8L3RpdGxlPgogIDxnIGZpbGw9Im5vbmUiIHN0cm9rZT0iI2ZmZmZmZiIgc3Ryb2tlLXdpZHRoPSIxLjYiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+CiAgICA8cG9seWxpbmUgcG9pbnRzPSIxNSw3LjUgMTMsNCA3LDQgNSw3LjUiLz4KICAgIDxwb2x5bGluZSBwb2ludHM9IjUsMTIuNSA3LDE2IDEzLDE2IDE1LDEyLjUiLz4KICAgIDxwb2x5bGluZSBwb2ludHM9IjMsMTAgNywxMCAxMCw1IDEzLDE1IDE2LDEwIDE3LDEwIi8+CiAgPC9nPgo8L3N2Zz4K&color=FFC105&labelColor=0D0D0F)](https://ff-fab.github.io/cosalette/)

**MQTT bridge for controlling a wall-panel display and system via SSH and Wake-on-LAN.**

---

wallpanel-control translates typed JSON MQTT commands into SSH-executed backlight writes
and power actions on a dedicated wall-panel device. The app connects to an always-on
device (e.g. a small x86 SBC running a kiosk browser) via SSH and exposes two command
channels: one for display state and brightness, and one for system actions such as wake,
suspend, and hibernate. Unavailable-device scenarios are surfaced through the availability
field in state payloads rather than connection-level errors. Wake-on-LAN handles
power-on for the suspend/hibernate use case.

---

## Features

- Typed JSON MQTT command and state topics -- no raw strings or legacy topic aliases
- Display control: turn on/off and set backlight brightness (1-100%) in a single command
- System actions: `wake` (WoL), `suspend`, and `hibernate` via SSH
- Availability reported per-state payload -- no separate availability topic required
- Error published to `{prefix}/error` (QoS 1, not retained) on adapter failures
- Configurable SSH host, user, key path, port, and timeout
- Configurable sysfs backlight path for different hardware

---

## Hardware

| Component         | Details                                              |
| ----------------- | ---------------------------------------------------- |
| Wall panel device | Linux device with a GNOME desktop session (Intel NUC, x86 board, ...) |
| Display backlight | Intel backlight via sysfs (configurable path)        |
| Screen on/off     | GNOME Mutter via `busctl --user set-property org.gnome.Mutter.DisplayConfig` |
| Network           | Ethernet or Wi-Fi with WoL support for power-on      |
| SSH access        | Public-key authentication required                   |

---

## Quick Links

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } **Getting Started**

    ---

    Install wallpanel-control and see your first MQTT messages.

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
