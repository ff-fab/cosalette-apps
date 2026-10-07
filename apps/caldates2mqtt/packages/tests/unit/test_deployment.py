"""Unit tests for the shipped deployment files.

Test Techniques Used:
- Specification-based: compose arms the loop-stall watchdog with the value that
  docs/configuration.md records, and operators can override it (monorepo ADR-011).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

_APP_DIR = Path(__file__).resolve().parents[3]


@pytest.mark.unit
def test_compose_arms_loop_stall_watchdog() -> None:
    """The service sets COSALETTE_LOOP_STALL_TIMEOUT to 300 s, overridable.

    Technique: Specification-based — nothing should block the event loop, so
    only a defect stalls it, which only the watchdog (exit 6) detects.
    """
    compose = yaml.safe_load((_APP_DIR / "compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["caldates2mqtt"]["environment"]

    assert environment["COSALETTE_LOOP_STALL_TIMEOUT"] == (
        "${COSALETTE_LOOP_STALL_TIMEOUT:-300}"
    )


@pytest.mark.unit
def test_docker_health_probe_ignores_individual_calendar_staleness() -> None:
    """One failed calendar must not make the multi-calendar container unhealthy."""
    dockerfile = (_APP_DIR / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(r"(?m)^\s*CMD\s+(\[.*\])\s*$", dockerfile)

    assert match is not None
    assert json.loads(match.group(1)) == ["cosalette-health", "--fail-on", ""]
