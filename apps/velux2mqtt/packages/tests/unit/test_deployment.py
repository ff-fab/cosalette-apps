"""Unit tests for deployment defaults.

Test Techniques Used:
- Specification-based: compose arms the loop-stall watchdog with an overridable
  value recorded in docs/configuration.md, passes only the GPIO character device,
  and adds the gpio group by an overridable numeric GID.
- Error Guessing: no privileged mode that would hide a missing device grant.
- Cross-check: .env.example carries the same GID default as compose.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

_APP_DIR = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def service() -> dict[str, Any]:
    compose = yaml.safe_load((_APP_DIR / "compose.yml").read_text(encoding="utf-8"))
    return compose["services"]["velux2mqtt"]


def test_compose_arms_loop_stall_watchdog(service: dict[str, Any]) -> None:
    """Synchronous GPIO stalls exit after 120 seconds by default.

    Technique: Specification-based — this backstop detects a blocked event loop
    that cannot refresh the native health file.
    """
    assert service["environment"]["COSALETTE_LOOP_STALL_TIMEOUT"] == (
        "${COSALETTE_LOOP_STALL_TIMEOUT:-120}"
    )


def test_compose_passes_only_the_gpio_chip(service: dict[str, Any]) -> None:
    """Technique: Error Guessing — no privileged mode, no /dev/mem or /dev/gpiomem."""
    assert service["devices"] == ["/dev/gpiochip0:/dev/gpiochip0"]
    assert "privileged" not in service


def test_gpio_gid_default_matches_env_example(service: dict[str, Any]) -> None:
    """Technique: Cross-check — the image has no gpio group by name."""
    env = (_APP_DIR / ".env.example").read_text(encoding="utf-8").splitlines()

    assert service["group_add"] == ["${VELUX2MQTT_GPIO_GID:-997}"]
    assert "VELUX2MQTT_GPIO_GID=997" in env
