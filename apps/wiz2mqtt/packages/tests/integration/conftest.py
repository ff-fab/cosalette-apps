"""Integration test fixtures for wiz2mqtt.

Provides a fully-wired App instance backed by FakeWizBulbAdapter and
MockMqttClient so integration tests can drive the real ``bulb_set``
command handler without real pywizlight or MQTT I/O.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, EntityNotifier, MockMqttClient, OnChange
from cosalette.stores import MemoryStore
from cosalette.testing import AppHarness, ManualClock

from tests.fixtures.settings import build_settings
from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.entity import bulb_entity_tick
from wiz2mqtt.errors import error_type_map
from wiz2mqtt.main import (
    _SIGNAL_QUEUE_SIZE,
    _bulb_map,
    _power_source_map,
    _signal_source_map,
    _signal_topic,
    bulb_set,
    power_signal,
    power_source_entity,
    shared_state,
)
from wiz2mqtt.ports import WizBulbPort
from wiz2mqtt.settings import Wiz2MqttSettings

TOPIC_PREFIX = "wiz2mqtt"
"""Default MQTT topic prefix used by integration tests."""

_DEFAULT_BULB: dict[str, object] = {"name": "office", "ip": "10.0.0.5"}

_COMMAND_SETTLE_TIME = 0.03
"""Real seconds to wait after command injection for async dispatch to complete."""

_STARTUP_TIMEOUT = 2.0
"""Maximum seconds to wait for the harness to subscribe before timing out."""

_FAST_TICK_INTERVAL = 0.01
"""Interval for the polling-oriented tests.

Under the gating :class:`ManualClock` the runner parks on this sleep after
each run, so a test releases one tick per ``advance_time(_FAST_TICK_INTERVAL)``
— a deterministic run count rather than however many a real-sleep window admits.
"""

NO_TICK_INTERVAL = 30.0
"""The scheduled interval on :func:`push_harness`.

Paired with a ``ManualClock`` the value is unreachable by construction:
nothing but an explicit ``advance()`` releases the runner's sleep, and the
push tests never make one.  A second publish can therefore only have come
from a trigger.
"""


def build_integration_app(
    fake_adapter: FakeWizBulbAdapter, *, interval: float = _FAST_TICK_INTERVAL
) -> App:
    """Construct a fully-wired App with FakeWizBulbAdapter.

    Mirrors the command and telemetry wiring in ``wiz2mqtt.main`` while
    substituting the adapter so tests stay isolated from real pywizlight I/O.
    """

    def _adapter_factory(
        settings: Wiz2MqttSettings, notify: EntityNotifier
    ) -> FakeWizBulbAdapter:
        # Registering the pre-built fake through a closure skips constructor
        # injection, so hand it the same two dependencies by name.  Without
        # this the fake's push path is inert and every test here silently
        # falls back to the interval= heartbeat.
        fake_adapter.bind(settings, notify)
        return fake_adapter

    app = App(
        name="wiz2mqtt",
        settings_class=Wiz2MqttSettings,
        adapters={WizBulbPort: _adapter_factory},
        error_type_map=error_type_map,
        # An isolated, per-test in-memory store: without this the app falls
        # back to the real on-disk default store path, which persists across
        # every test in the session. That was harmless while the only thing
        # it held was the capability cache, but the desired state
        # (cap-bjw9.5/.6) now feeds directly into published payloads, so a
        # leftover record from an earlier test would leak into this one.
        store=MemoryStore(),
    )
    app.add_command(_bulb_map, bulb_set)
    app.state(shared_state)
    app.add_telemetry(
        _bulb_map,
        bulb_entity_tick,
        interval=interval,
        triggerable="local",
        publish=OnChange(),
    )
    # Mirrors main.py's power_source_entity registration: bulb_entity_tick
    # arms a bulb's power source by name (cap-bjw9.7), so a source-bearing
    # bulb needs that entity registered too, or notify() raises
    # UnknownEntityError and the whole bulb tick fails.
    app.add_telemetry(
        _power_source_map,
        power_source_entity,
        interval=interval,
        triggerable="local",
        publish=OnChange(),
    )
    # Mirrors main.py's power_signal registration (minus the schema metadata).
    app.add_inbound(
        _signal_source_map,
        power_signal,
        topic=_signal_topic,
        maxsize=_SIGNAL_QUEUE_SIZE,
        backpressure="drop_oldest",
    )
    return app


def make_settings(
    power_sources: list[dict[str, object]] | None = None, **bulb_overrides: object
) -> Wiz2MqttSettings:
    """Isolated settings with a single bulb, ignoring host env/files."""
    return build_settings([{**_DEFAULT_BULB, **bulb_overrides}], power_sources or [])


async def wait_until_subscribed(harness: AppHarness, topic: str | None = None) -> None:
    """Poll until the harness has subscribed (to *topic*, if given) or time out.

    Avoids a fixed-duration startup sleep — returns as soon as the MQTT
    router is listening, keeping the suite fast even on slow CI runners.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _STARTUP_TIMEOUT
    while not _is_subscribed(harness, topic):
        if loop.time() >= deadline:
            raise AssertionError(
                f"App did not subscribe within {_STARTUP_TIMEOUT}s "
                "— router was not listening yet."
            )
        await asyncio.sleep(0.005)


def _is_subscribed(harness: AppHarness, topic: str | None) -> bool:
    subscriptions = harness.mqtt.subscriptions
    return bool(subscriptions) if topic is None else topic in subscriptions


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_adapter() -> FakeWizBulbAdapter:
    """A fresh FakeWizBulbAdapter."""
    return FakeWizBulbAdapter()


@pytest.fixture
def test_settings() -> Wiz2MqttSettings:
    """Isolated settings with a single bulb named 'office'."""
    return make_settings()


@pytest.fixture
def harness(
    fake_adapter: FakeWizBulbAdapter, test_settings: Wiz2MqttSettings
) -> AppHarness:
    """Fresh AppHarness wired with FakeWizBulbAdapter and one bulb.

    Gated by a :class:`ManualClock`, so telemetry ticks fire only on an
    explicit :meth:`AppHarness.advance_time`; command tests inject directly
    and never advance it.
    """
    return AppHarness(
        app=build_integration_app(fake_adapter),
        mqtt=MockMqttClient(),
        clock=ManualClock(),
        settings=test_settings,
        shutdown_event=asyncio.Event(),
    )


@pytest.fixture
def push_harness(
    fake_adapter: FakeWizBulbAdapter, test_settings: Wiz2MqttSettings
) -> AppHarness:
    """Harness whose scheduled tick cannot fire without an explicit advance.

    The gating :class:`~cosalette.testing.ManualClock` is what makes that
    true, so the only thing that can produce a second publish is the
    adapter's push wake.
    """
    return AppHarness(
        app=build_integration_app(fake_adapter, interval=NO_TICK_INTERVAL),
        mqtt=MockMqttClient(),
        clock=ManualClock(),
        settings=test_settings,
        shutdown_event=asyncio.Event(),
    )


@pytest.fixture
def settings_when_off() -> Wiz2MqttSettings:
    """Settings with a power source (when_unreachable='no_power') claiming the
    'office' bulb, for the OFF-policy integration tests."""
    return make_settings(
        power_sources=[
            {
                "name": "office-power",
                "members": ["office"],
                "when_unreachable": "no_power",
            }
        ]
    )


@pytest.fixture
def harness_when_off(
    fake_adapter: FakeWizBulbAdapter, settings_when_off: Wiz2MqttSettings
) -> AppHarness:
    """AppHarness wired with when_unreachable='off' settings, gated by ManualClock."""
    return AppHarness(
        app=build_integration_app(fake_adapter),
        mqtt=MockMqttClient(),
        clock=ManualClock(),
        settings=settings_when_off,
        shutdown_event=asyncio.Event(),
    )
