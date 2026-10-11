"""Unit tests for deployment defaults.

Test Techniques Used:
- Specification-based: compose uses host networking for Wake-on-LAN and arms the
  loop-stall watchdog with an overridable value recorded in docs/configuration.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_APP_DIR = Path(__file__).resolve().parents[3]


@pytest.mark.unit
def test_compose_arms_loop_stall_watchdog() -> None:
    """Unexpected event-loop stalls exit after 120 seconds by default.

    Technique: Specification-based — this backstop detects a blocked event loop
    that cannot refresh the native health file.
    """
    compose = yaml.safe_load((_APP_DIR / "compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["wallpanel-control"]["environment"]

    assert environment["COSALETTE_LOOP_STALL_TIMEOUT"] == (
        "${COSALETTE_LOOP_STALL_TIMEOUT:-120}"
    )


@pytest.mark.unit
def test_compose_uses_host_networking_for_wake_on_lan() -> None:
    """The service shares the host network and reaches the broker on loopback.

    Technique: Specification-based — a bridge network does not forward the
    Wake-on-LAN broadcast to the LAN, so wake would accept and do nothing; the
    Compose service name is unresolvable under host networking.
    """
    compose = yaml.safe_load((_APP_DIR / "compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["wallpanel-control"]

    assert service["network_mode"] == "host"
    assert service["environment"]["WALLPANEL_CONTROL_MQTT__HOST"] == "localhost"
