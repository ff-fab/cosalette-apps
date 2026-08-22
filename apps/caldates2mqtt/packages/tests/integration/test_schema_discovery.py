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
is ``events``, an array of objects, so the per-event ``consumer()`` annotations
on ``CalendarEvent`` (see :mod:`caldates2mqtt.main`) yield no entity. Since
cosalette 0.6.3 this is a deliberate, *reported* outcome rather than a silent
one — an array of objects has no single value an HA sensor could hold, so the
generator skips those properties and warns, then exits non-zero because the app
produced no payloads at all. Emitting one scalar entity per array field is the
open upstream question (cap-wxg); until it is answered, zero payloads plus a
warning is the honest current state.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: the resolved schema must expose real per-calendar
  channel names, not the qualname placeholder
- Specification-based: HA discovery is still non-functional (an array of
  objects yields no scalar entity); 0 payloads plus a diagnostic warning and a
  non-zero exit is the correct, honest current state
"""

from __future__ import annotations

import json
import os
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
def ha_discovery_run() -> subprocess.CompletedProcess[str]:
    """Run the schema ha-discovery CLI once and return the completed process.

    ``check=False`` because cosalette 0.6.3 deliberately exits non-zero when a
    schema has consumer-visible channels but produces no payloads — which is
    exactly caldates2mqtt's situation, and is asserted below rather than
    raised as a fixture error.
    """
    return subprocess.run(
        [sys.executable, "-m", "cosalette", "schema", "ha-discovery", str(SCHEMA_PATH)],
        capture_output=True,
        text=True,
        check=False,
        env={
            k: v
            for k, v in os.environ.items()
            if k not in {"PYTHONSTARTUP", "PYTHONHOME"}
        },
    )


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

    def test_generates_no_payloads(
        self, ha_discovery_run: subprocess.CompletedProcess[str]
    ) -> None:
        """No discovery payloads are generated despite real channel names.

        ``CalendarState``'s only property (``events``) is an array of objects,
        which has no single value an HA sensor could hold, so the per-event
        ``consumer()`` annotations on ``CalendarEvent`` yield no entity. This
        is the honest current state (cap-wxg), unrelated to the
        qualname-collapse fix verified above.

        Technique: Specification-based — a channel with no emittable
        consumer-annotated property must not yield an HA entity.
        """
        assert json.loads(ha_discovery_run.stdout) == []

    def test_reports_the_array_item_annotations_it_skipped(
        self, ha_discovery_run: subprocess.CompletedProcess[str]
    ) -> None:
        """The CLI names the skipped array-item annotations and exits non-zero.

        cosalette 0.6.3 turned this from a silent ``[]`` into a diagnostic:
        the warning names the offending channels, and the non-zero exit stops
        an empty generation from passing unnoticed in a pipeline. Locking both
        here means the day cap-wxg is answered upstream — and these
        annotations start producing entities — this test fails and points at
        the docstring above.

        Technique: Error Guessing — asserts the diagnostic itself, not just
        the absence of output, so a regression to silence is caught.
        """
        assert ha_discovery_run.returncode != 0
        stderr = ha_discovery_run.stderr
        assert "array-item properties" in stderr
        assert "birthdayState" in stderr
        assert "garbageState" in stderr
