"""Unit tests for caldates2mqtt application-level configuration.

Test Techniques Used:
- Specification-based: Verify declared retry configuration on the telemetry registration
- Round-trip Testing: Render the live HA attributes template against a real payload
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
class TestTelemetryRetryConfig:
    """Verify retry metadata on the calendar telemetry registration.

    caldates2mqtt uses name=_calendar_map (a callable), not a string constant,
    so app.telemetry_registrations[0] is used instead of the name-based lookup used in
    airthings2mqtt.
    """

    def test_retry_count_is_three(self) -> None:
        """Telemetry registration has retry=3.

        Technique: Specification-based — verify declared retry configuration.
        """
        from caldates2mqtt.main import app

        reg = app.telemetry_registrations[0]
        assert reg.retry == 3

    def test_retry_on_includes_caldav_connection_error(self) -> None:
        """retry_on tuple contains CalDavConnectionError.

        Technique: Specification-based — connection failures should be retried.
        """
        from caldates2mqtt.errors import CalDavConnectionError
        from caldates2mqtt.main import app

        reg = app.telemetry_registrations[0]
        assert CalDavConnectionError in reg.retry_on

    def test_retry_on_includes_caldav_timeout_error(self) -> None:
        """retry_on tuple contains CalDavTimeoutError.

        Technique: Specification-based — timeout failures should be retried.
        """
        from caldates2mqtt.errors import CalDavTimeoutError
        from caldates2mqtt.main import app

        reg = app.telemetry_registrations[0]
        assert CalDavTimeoutError in reg.retry_on


@pytest.mark.unit
class TestEventAttributesTemplate:
    """Render the HA attributes template that main.py declares .

    The integration suite reads the committed docs/schema.yaml. This class reads
    the live model, so a template removed from main.py fails even when the schema
    is not regenerated.
    """

    @pytest.mark.parametrize(
        "titles", [(), ("Gelber Sack", "Müll <Bio> & 'Rest'")], ids=["empty", "events"]
    )
    def test_attributes_are_an_object_holding_the_event_list(
        self, titles: tuple[str, ...]
    ) -> None:
        """The template yields ``{"events": [...]}`` and nothing else.

        Home Assistant rejects a bare array as attributes, and only the event
        list is meant to reach them.

        Technique: Round-trip Testing — serialise a real CalendarState, render
        the template as Home Assistant does, and parse the result back.
        """
        import json

        from jinja2.sandbox import ImmutableSandboxedEnvironment
        from pydantic import TypeAdapter

        from caldates2mqtt.main import CalendarEvent, CalendarState

        adapter = TypeAdapter(CalendarState)
        (entity,) = adapter.json_schema()["x-cosalette-ha-discovery"]["entities"]
        # Home Assistant renders templates in a sandboxed environment too.
        template = ImmutableSandboxedEnvironment(autoescape=True).from_string(
            entity["extra"]["json_attributes_template"]
        )
        state = CalendarState(
            events=[CalendarEvent(title=t, date="2026-04-01") for t in titles]
        )

        rendered = template.render(value_json=json.loads(adapter.dump_json(state)))

        assert json.loads(rendered) == {
            "events": [{"title": t, "date": "2026-04-01"} for t in titles]
        }


@pytest.mark.unit
class TestAppVersion:
    """Verify the app reports its package version (not the 0.0.0 default)."""

    def test_app_version_matches_package(self) -> None:
        """App version is stamped from package metadata, not the 0.0.0 default.

        Technique: Cross-reference — guards smoke-test finding A-1 (status/log
        reported version 0.0.0 because version= was never passed to App()).
        """
        from caldates2mqtt import __version__
        from caldates2mqtt.main import app

        assert app.version == __version__
        assert not app.version.startswith("0.0.0")


@pytest.mark.unit
class TestTriggerThrottleRegistration:
    """Guard the ADR-066 throttle declared on the production registration."""

    def test_public_set_topic_is_throttled(self) -> None:
        """The /set trigger carries the declared min_interval.

        Technique: Specification-based — caldates2mqtt/{calendar}/set is a
        public MQTT topic, so an unthrottled trigger lets any client queue one
        CalDAV round-trip per message against a third-party server.
        """
        from caldates2mqtt.main import _TRIGGER_MIN_INTERVAL_SECONDS, app

        reg = app.telemetry_registrations[0]
        assert reg.min_interval == _TRIGGER_MIN_INTERVAL_SECONDS

    def test_throttle_is_still_triggerable(self) -> None:
        """min_interval= throttles the trigger, it does not disable it.

        Technique: Specification-based — the throttle requires triggerable=.
        """
        from caldates2mqtt.main import app

        assert app.telemetry_registrations[0].triggerable is not None

    def test_schedule_is_untouched_by_the_throttle(self) -> None:
        """The cron schedule still drives its own cadence.

        Technique: Specification-based — min_interval bounds trigger-initiated
        runs only; a scheduled fire is not a trigger and is never throttled.
        """
        from caldates2mqtt.main import app

        assert app.telemetry_registrations[0].schedule_spec is not None

    def test_resolver_reads_the_configured_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A deployment override flows from settings into the throttle .

        Technique: Specification-based — the whole point of the field is that a
        non-default value reaches min_interval= at registration time.
        """
        import json

        import cosalette

        from caldates2mqtt.main import _resolve_trigger_min_interval
        from caldates2mqtt.settings import CalDates2MqttSettings

        monkeypatch.setenv(
            "CALDATES2MQTT_CALENDARS",
            json.dumps(
                [
                    {
                        "key": "birthdays",
                        "url": "https://example.test/dav",
                        "calendar_name": "Birthdays",
                        "username": "user",
                        "password": "p",  # pragma: allowlist secret
                    }
                ]
            ),
        )
        monkeypatch.setenv("CALDATES2MQTT_TRIGGER_MIN_INTERVAL", "90")
        configured_app = cosalette.App(
            name="caldates2mqtt", settings_class=CalDates2MqttSettings
        )

        assert _resolve_trigger_min_interval(configured_app) == 90.0

    def test_resolver_falls_back_when_settings_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing required fields fall back to the default, keeping import safe.

        Technique: Error Guessing — ``app.settings`` raises when ``calendars``
        is unset (``--help``, tests, schema generation); the resolver must not
        propagate that at import time.
        """
        import cosalette

        from caldates2mqtt.main import (
            _TRIGGER_MIN_INTERVAL_SECONDS,
            _resolve_trigger_min_interval,
        )
        from caldates2mqtt.settings import CalDates2MqttSettings

        monkeypatch.delenv("CALDATES2MQTT_CALENDARS", raising=False)
        bare_app = cosalette.App(
            name="caldates2mqtt", settings_class=CalDates2MqttSettings
        )

        assert _resolve_trigger_min_interval(bare_app) == _TRIGGER_MIN_INTERVAL_SECONDS
