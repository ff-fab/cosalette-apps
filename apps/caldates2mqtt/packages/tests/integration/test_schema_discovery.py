"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

``app.telemetry`` is registered with a callable ``name=`` (``_calendar_map`` in
:mod:`caldates2mqtt.main`, keyed off user-configured ``settings.calendars``). A
plain ``cosalette schema init``/``check`` would collapse every real per-calendar
device into a single channel named after the Python handler's qualname
(``calendar``), which is why ``task caldates2mqtt:schema:generate`` instead runs
``cosalette schema dump --resolve-settings`` (ADR-051) against the checked-in
``.env.schema`` profile before writing ``docs/schema.yaml`` — expanding the
NameSpec into real per-calendar channels (``birthdayState``, ``garbageState``,
per ``.env.schema``). This resolves the same qualname-collapse issue fixed for
velux2mqtt (cap-hze), verified below by asserting the real channel names appear.

HA discovery itself (``task caldates2mqtt:schema:ha-discovery``) still emits
zero payloads even with those real channels: ``CalendarState``'s only property
is ``events``, a nested list, and cosalette's HA/OpenHAB generators only walk a
channel's top-level properties — never items inside a nested list — so the
per-event ``consumer()`` annotations on ``CalendarEvent`` (see
:mod:`caldates2mqtt.main`) remain inert. This is a separate, still-open
upstream limitation (cap-wxg), independent of the qualname-collapse fix.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: the resolved schema must expose real per-calendar
  channel names, not the qualname placeholder
- Specification-based: HA discovery is still non-functional (nested list
  payloads aren't walked); 0 payloads is the correct, honest current state
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

# packages/tests/integration/<file> → app root is parents[3]
APP_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = APP_ROOT / "docs" / "schema.yaml"


@pytest.fixture(scope="module")
def schema_channels() -> dict[str, Any]:
    """Return the ``channels`` mapping from the committed docs/schema.yaml."""
    doc = yaml.safe_load(SCHEMA_PATH.read_text())
    return doc["channels"]


@pytest.fixture(scope="module")
def ha_payloads() -> list[dict[str, Any]]:
    """Run the schema ha-discovery CLI once and return the parsed payloads."""
    result = subprocess.run(
        [sys.executable, "-m", "cosalette", "schema", "ha-discovery", str(SCHEMA_PATH)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.integration
class TestResolvedSchemaChannels:
    """Verify schema:generate resolved real per-calendar channels."""

    def test_real_calendar_channels_present(
        self, schema_channels: dict[str, Any]
    ) -> None:
        """docs/schema.yaml exposes real per-calendar channels from .env.schema.

        Guards against a regression back to the qualname-collapse placeholder
        (``calendarState``, address ``caldates2mqtt/calendar/state``) that a
        plain ``cosalette schema init``/``check`` would produce.

        Technique: Specification-based — resolved channel names must match
        the calendar keys configured in ``.env.schema``.
        """
        assert "calendarState" not in schema_channels
        assert set(schema_channels) == {"birthdayState", "garbageState"}
        assert (
            schema_channels["birthdayState"]["address"]
            == "caldates2mqtt/birthday/state"
        )
        assert (
            schema_channels["garbageState"]["address"] == "caldates2mqtt/garbage/state"
        )


@pytest.mark.integration
class TestHaDiscoveryGeneration:
    """Verify HA MQTT discovery generation is still honestly non-functional."""

    def test_generates_no_payloads(self, ha_payloads: list[dict[str, Any]]) -> None:
        """No discovery payloads are generated despite real channel names.

        ``CalendarState``'s only property (``events``) is a nested list;
        cosalette's HA/OpenHAB generators never walk nested list items, so
        the per-event ``consumer()`` annotations on ``CalendarEvent`` stay
        inert. This is the honest current state (cap-wxg), unrelated to the
        qualname-collapse fix verified above.

        Technique: Specification-based — a channel with no top-level
        consumer-annotated property must not yield an HA entity.
        """
        assert ha_payloads == []
