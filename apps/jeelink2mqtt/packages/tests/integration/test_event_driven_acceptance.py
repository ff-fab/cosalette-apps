"""Downstream acceptance for event-driven publication in jeelink2mqtt (cap-8au).

Discharges the one acceptance item the framework-contract suite cannot:
*jeelink2mqtt publishes a sensor's state within the same virtual tick as
the frame that produced it*.  The framework criteria the proposal lists
alongside it are asserted once, app-independently, in
``packages/tests/unit/test_event_driven_acceptance.py`` at the repo root.

What makes the assertion non-vacuous is the clock.  ``FakeClock.sleep``
advances virtual time instantly, so under it ``DeviceTrigger.wait``'s
heartbeat bound fires immediately and "published without waiting for the
heartbeat" cannot be distinguished from "the heartbeat fired".
:class:`RealSleepClock` sleeps for real, and the heartbeat bound is
lifted out of reach for the test window, so a publish inside it can only
have come from the receiver arming the sensor's trigger — and ``now()``
is still where the test left it.

``AppHarness.run`` always suppresses ``@app.stream`` handlers, and
``inject_stream`` reads the list ``run`` has just emptied, so the two
cannot drive one app at once (cap-doo).  The real ``receiver`` generator is
therefore driven directly instead, over a :class:`~cosalette.DeviceContext`
built from the harness's own MQTT double, clock, settings and shutdown
event — so both halves publish into the same recorder and share the same
virtual clock.  It is handed the ``SharedState`` and ``EntityNotifier``
the running app bound; without those the receiver would cache into one
object and arm a notifier wired to nothing.

Test Techniques Used:
- Integration Testing: frame → receiver → trigger → device → retained MQTT
- Specification-based: the proposal's definition-of-done wording, asserted
- Negative control: a quiet window proves the heartbeat cannot have published
- State Transition Testing: no cached reading → cached → published
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import cosalette
import pytest
from cosalette import DeviceStore, EntityNotifier, MockMqttClient
from cosalette.stores import MemoryStore
from cosalette.testing import AppHarness, FakeClock

from jeelink2mqtt import main as _main
from jeelink2mqtt.errors import error_type_map
from jeelink2mqtt.models import SensorReading, SensorStateModel
from jeelink2mqtt.settings import Jeelink2MqttSettings, SensorConfigSettings
from jeelink2mqtt.state import SharedState, build_shared_state

TOPIC_PREFIX = "jeelink2mqtt"
"""Default MQTT topic prefix used by these tests."""

SENSOR_NAME = "office"
"""The configured sensor the injected frame is mapped to."""

SENSOR_ID = 42
"""Ephemeral LaCrosse ID of the injected frame.

Mapped explicitly in :func:`_deliver`.  Auto-adopt needs *exactly one*
stale configured sensor and both of these are stale at startup, so
leaving it to adopt would make the frame land nowhere — and the
resulting silence would look like the trigger failing.
"""

NO_HEARTBEAT_SECONDS = 3600.0
"""Heartbeat bound no test window can reach — see :class:`RealSleepClock`."""

_TEMPERATURE = 21.5
_HUMIDITY = 55
_TEMP_OFFSET = -0.3
"""Calibration offset on the office sensor, so the published value is derived."""

_QUIET_SECONDS = 0.2
"""Seconds of deliberate inactivity used to prove no heartbeat is due."""

_WAIT_TIMEOUT = 2.0
"""How long :func:`_wait_until` polls before calling a condition failed."""


class RealSleepClock(FakeClock):
    """A :class:`FakeClock` whose ``sleep`` actually waits.

    A fourth copy of a class airthings2mqtt, caldates2mqtt and wiz2mqtt
    each hand-rolled; giving it one home is cap-o9x.
    """

    async def sleep(self, seconds: float) -> None:
        """Sleep for *seconds* of wall-clock time, keeping ``now()`` in step."""
        await asyncio.sleep(seconds)
        if seconds > 0:
            self._time += seconds


def make_settings() -> Jeelink2MqttSettings:
    """Isolated settings with two sensors, ignoring host env and files."""
    return Jeelink2MqttSettings(
        sensors=[
            SensorConfigSettings(name=SENSOR_NAME, temp_offset=_TEMP_OFFSET),
            SensorConfigSettings(name="outdoor"),
        ],
        serial_port="/dev/null",
        _env_file=None,  # type: ignore[call-arg]
    )


def make_reading() -> SensorReading:
    """One decoded frame from an ID the registry has not seen before."""
    return SensorReading(
        sensor_id=SENSOR_ID,
        temperature=_TEMPERATURE,
        humidity=_HUMIDITY,
        low_battery=False,
        timestamp=datetime.now(UTC),
    )


def build_integration_app(captured: dict[str, Any]) -> cosalette.App:
    """Mirror ``jeelink2mqtt.main``'s receiver/sensor wiring for the harness.

    Registers the real ``receiver`` and ``sensor_entity`` handlers, with
    a heartbeat bound out of test reach.  The state factory records the
    ``SharedState`` and the ``EntityNotifier`` the framework builds, so
    ``inject_stream`` can be handed the same two objects the running
    device is using.
    """
    app = cosalette.App(
        name=TOPIC_PREFIX,
        version="0.1.0",
        settings_class=Jeelink2MqttSettings,
        store=MemoryStore(),
        error_type_map=error_type_map,
    )

    @app.state
    def shared_state(
        settings: Jeelink2MqttSettings, notify: EntityNotifier
    ) -> SharedState:
        state = build_shared_state(settings)
        captured["state"] = state
        captured["notify"] = notify
        return state

    @app.device(
        name=lambda s: {sc.name: sc for sc in s.sensors},
        summary="Per-sensor state publisher",
        state_model=SensorStateModel,
        triggerable="local",
    )
    async def sensor_entity(
        ctx: cosalette.DeviceContext,
        config: SensorConfigSettings,
        settings: Jeelink2MqttSettings,
        state: SharedState,
        trigger: cosalette.DeviceTrigger,
    ) -> AsyncIterator[None]:
        """``main.sensor_entity`` with the heartbeat bound lifted out of reach."""
        while not ctx.shutdown_requested:
            payload = await trigger.wait(timeout=NO_HEARTBEAT_SECONDS)
            await _main._receiver.sensor_entity_tick(
                ctx, config.name, settings, state, triggered=payload.is_triggered
            )
            yield

    return app


async def _wait_until(condition, what: str) -> None:
    """Poll *condition* until true, or fail naming *what* was awaited."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _WAIT_TIMEOUT
    while not condition():
        if loop.time() >= deadline:
            raise AssertionError(f"timed out after {_WAIT_TIMEOUT}s waiting for {what}")
        await asyncio.sleep(0.005)


def state_topic(name: str = SENSOR_NAME) -> str:
    """The retained state topic for one configured sensor."""
    return f"{TOPIC_PREFIX}/{name}/state"


@pytest.fixture
def captured() -> dict[str, Any]:
    """Receives the SharedState and EntityNotifier the app builds."""
    return {}


@pytest.fixture
def harness(captured: dict[str, Any]) -> AppHarness:
    """A harness whose clock only moves when something really sleeps."""
    return AppHarness(
        app=build_integration_app(captured),
        mqtt=MockMqttClient(),
        clock=RealSleepClock(),
        settings=make_settings(),
        shutdown_event=asyncio.Event(),
    )


@contextlib.asynccontextmanager
async def running(harness: AppHarness, captured: dict[str, Any]) -> AsyncIterator[None]:
    """Run *harness* until its devices are wired and their state exists."""
    task = asyncio.create_task(harness.run())
    try:
        await _wait_until(
            lambda: "notify" in captured and bool(captured["notify"].entities),
            "the framework to bind the sensor entities' trigger slots",
        )
        yield
    finally:
        harness.shutdown_event.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(task, timeout=_WAIT_TIMEOUT)
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def _receiver_context(harness: AppHarness) -> cosalette.DeviceContext:
    """A real context for the receiver, on the harness's own doubles."""
    return cosalette.DeviceContext(
        name="receiver",
        settings=harness.settings,
        mqtt=harness.mqtt,
        topic_prefix=TOPIC_PREFIX,
        shutdown_event=harness.shutdown_event,
        adapters={},
        clock=harness.clock,
        # The receiver is a root handler in production, so its raw
        # diagnostic belongs on {prefix}/raw/state, not under a segment.
        is_root=True,
    )


async def _deliver(harness: AppHarness, captured: dict[str, Any]) -> None:
    """Run the real receiver over one frame, wired to the running app."""
    captured["state"].registry.assign(SENSOR_NAME, SENSOR_ID)
    store = DeviceStore(MemoryStore(), "receiver")
    store.load()
    stream: cosalette.Stream[SensorReading] = cosalette.Stream()
    stream.put(make_reading())

    generator = _main.receiver(
        stream=stream,
        ctx=_receiver_context(harness),
        store=store,
        settings=harness.settings,
        state=captured["state"],
        notify=captured["notify"],
    )
    try:
        async for _ in generator:
            break  # one frame is all these tests deliver
    finally:
        await generator.aclose()


@pytest.mark.integration
@pytest.mark.slow
class TestFrameToPublishInOneTick:
    """cap-8au acceptance 2 — the frame publishes without a tick elapsing."""

    async def test_a_frame_publishes_within_the_same_virtual_tick(
        self, harness: AppHarness, captured: dict[str, Any]
    ) -> None:
        """The assertion the proposal's definition of done names for this app.

        Technique: Integration — the whole frame→publish path in one
        assertion, with virtual time pinned either side of it.
        """
        async with running(harness, captured):
            assert not harness.messages_for(state_topic()), (
                "a sensor published before any frame arrived"
            )
            started_at = harness.clock.now()

            await _deliver(harness, captured)
            await _wait_until(
                lambda: bool(harness.messages_for(state_topic())),
                f"the frame-driven publish on {state_topic()}",
            )

            assert harness.clock.now() == started_at
            payload, retain, _qos = harness.messages_for(state_topic())[0]
            assert retain is True
            assert json.loads(payload)["temperature"] == pytest.approx(
                _TEMPERATURE + _TEMP_OFFSET
            )

    async def test_without_a_frame_the_heartbeat_bound_really_holds(
        self, harness: AppHarness, captured: dict[str, Any]
    ) -> None:
        """The negative control for the test above.

        Without it, the publish asserted there could be the heartbeat and
        the whole acceptance item would be vacuous.

        Technique: Negative control — no frame, no publish, no time passing.
        """
        async with running(harness, captured):
            await asyncio.sleep(_QUIET_SECONDS)

            assert not harness.messages_for(state_topic())
            assert harness.clock.now() == 0.0

    async def test_only_the_frame_s_own_sensor_publishes(
        self, harness: AppHarness, captured: dict[str, Any]
    ) -> None:
        """A frame wakes the sensor it is mapped to, and no other.

        Technique: Equivalence Partitioning — the mapped sensor vs the
        configured sensor that has seen no frame.
        """
        async with running(harness, captured):
            await _deliver(harness, captured)
            await _wait_until(
                lambda: bool(harness.messages_for(state_topic())),
                f"the frame-driven publish on {state_topic()}",
            )
            await asyncio.sleep(_QUIET_SECONDS)

            assert not harness.messages_for(state_topic("outdoor"))
