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
- Specification-based: the channel-level ha_entities() composite yields one
  event-count sensor per calendar; the array-item annotations stay inert and
  still warn, but the composite satisfies the per-channel gate (ADR-073)
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
    """Verify the channel-level composite yields one sensor per calendar."""

    def test_emits_one_event_count_sensor_per_calendar(
        self, ha_discovery_run: subprocess.CompletedProcess[str]
    ) -> None:
        """Each configured calendar yields a sensor counting its events.

        ``CalendarState`` carries an ``ha_entities()`` composite (ADR-057) —
        the supported path for a payload whose only property is an array of
        objects. cosalette resolves each per-calendar ``state_topic`` from the
        channel address, so one model-level spec serves every calendar.

        Technique: Specification-based — the composite must produce one entity
        per real channel, keyed to that channel's own topic.
        """
        assert ha_discovery_run.returncode == 0
        payloads = json.loads(ha_discovery_run.stdout)
        by_object_id = {p["config"]["object_id"]: p["config"] for p in payloads}

        assert set(by_object_id) == {"birthday_events", "garbage_events", "bridge"}
        for calendar in ("birthday", "garbage"):
            config = by_object_id[f"{calendar}_events"]
            assert config["state_topic"] == f"caldates2mqtt/{calendar}/state"
            assert config["value_template"] == "{{ value_json.events | length }}"
            assert config["unit_of_measurement"] == "events"

    def test_still_reports_the_array_item_annotations_it_skips(
        self, ha_discovery_run: subprocess.CompletedProcess[str]
    ) -> None:
        """The CLI names the skipped array-item annotations but now exits 0.

        The ``consumer()`` annotations on ``CalendarEvent`` remain, and
        cosalette still skips them: an array item has no single value. The
        warning stays because those annotations are genuinely inert for Home
        Assistant. The exit code is 0 because the channel-level composite
        satisfies the per-channel discovery gate (ADR-073).

        Technique: Error Guessing — asserts the diagnostic survives the fix,
        so a regression to silence is caught.
        """
        assert ha_discovery_run.returncode == 0
        stderr = ha_discovery_run.stderr
        assert "array-item properties" in stderr
        assert "birthdayState" in stderr
        assert "garbageState" in stderr
