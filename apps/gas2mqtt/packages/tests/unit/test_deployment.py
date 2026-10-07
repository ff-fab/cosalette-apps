"""Unit tests for the shipped compose file.

Test Techniques Used:
- Specification-based: compose arms the loop-stall watchdog with the value that
  docs/configuration.md records, and operators can override it (monorepo ADR-011).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_APP_DIR = Path(__file__).resolve().parents[3]


@pytest.mark.unit
def test_compose_arms_loop_stall_watchdog() -> None:
    """The service sets COSALETTE_LOOP_STALL_TIMEOUT to 120 s, overridable.

    Technique: Specification-based — a blocking I2C read stalls the event loop,
    which only the watchdog (exit 6) detects.
    """
    compose = yaml.safe_load((_APP_DIR / "compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["gas2mqtt"]["environment"]

    assert environment["COSALETTE_LOOP_STALL_TIMEOUT"] == (
        "${COSALETTE_LOOP_STALL_TIMEOUT:-120}"
    )
