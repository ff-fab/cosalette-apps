"""Unit tests for the shipped compose file and .env.example.

Test Techniques Used:
- Specification-based: compose arms the loop-stall watchdog with the value that
  docs/configuration.md records (monorepo ADR-011), passes only the GPIO
  character device, and adds the gpio group by an overridable numeric GID.
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
    return compose["services"]["geiger2mqtt"]


def test_compose_arms_loop_stall_watchdog(service: dict[str, Any]) -> None:
    assert service["environment"]["COSALETTE_LOOP_STALL_TIMEOUT"] == (
        "${COSALETTE_LOOP_STALL_TIMEOUT:-120}"
    )


def test_compose_passes_only_the_gpio_chip(service: dict[str, Any]) -> None:
    """Technique: Error Guessing — no privileged mode, no /dev/mem."""
    assert service["devices"] == ["/dev/gpiochip0:/dev/gpiochip0"]
    assert "privileged" not in service


def test_gpio_gid_default_matches_env_example(service: dict[str, Any]) -> None:
    env = (_APP_DIR / ".env.example").read_text(encoding="utf-8").splitlines()

    assert service["group_add"] == ["${GEIGER2MQTT_GPIO_GID:-997}"]
    assert "GEIGER2MQTT_GPIO_GID=997" in env
