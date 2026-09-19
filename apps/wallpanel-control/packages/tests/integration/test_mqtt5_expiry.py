"""Integration tests for wallpanel-control's MQTT 5 retained-message expiry (ADR-009).

The real cosalette ``MqttClient`` runs the wired app against an in-memory broker
double; the shared contract assertions live in ``mqtt5_contract``. See there for
the test techniques used.

wallpanel-control publishes its two state topics only as the answer to a command,
so the observation first delivers one display command and one system action
through the broker double, as an MQTT client would.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from async_utils import wait_for_condition
from mqtt5_broker import FakeMqtt5Broker, Observation, run_against_broker
from mqtt5_contract import EXPIRY_SECONDS, WINDOWS, Mqtt5Contract, Mqtt311Contract
from tests.fixtures.config import make_wallpanel_control_settings
from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol
from wallpanel_control.devices import display, system
from wallpanel_control.ports import WallpanelPort, WolPort

from .conftest import (
    DISPLAY_SET,
    DISPLAY_STATE,
    SYSTEM_ACTION_SET,
    SYSTEM_ACTION_STATE,
)


def _build_app() -> App:
    """Mirror ``wallpanel_control.main`` with fake adapters."""
    app = App(
        name="wallpanel-control",
        version="0.0.0",
        settings_class=type(make_wallpanel_control_settings()),
        adapters={WallpanelPort: lambda: FakeWallpanel(), WolPort: lambda: FakeWol()},
    )
    app.discovery()
    app.include_router(display.router)
    app.include_router(system.router)
    return app


async def _observe(monkeypatch: pytest.MonkeyPatch, **mqtt: object) -> Observation:
    """Run the wired app for ``WINDOWS`` refresh windows against the broker double."""
    clock = ManualClock()
    broker = FakeMqtt5Broker(clock)
    broker.install(monkeypatch)
    harness = AppHarness(
        app=_build_app(),
        mqtt=MockMqttClient(),
        clock=clock,
        settings=make_wallpanel_control_settings(mqtt={"tls": False, **mqtt}),
        shutdown_event=asyncio.Event(),
    )

    async def commands() -> None:
        broker.deliver(DISPLAY_SET, '{"state": "on"}')
        broker.deliver(SYSTEM_ACTION_SET, '{"action": "wake"}')
        await wait_for_condition(
            lambda: {DISPLAY_STATE, SYSTEM_ACTION_STATE} <= broker.retained.keys(),
            timeout=5.0,
            description="both command answers retained",
        )

    return await run_against_broker(
        harness,
        broker,
        ready_topic=DISPLAY_STATE,
        windows=WINDOWS,
        window_seconds=EXPIRY_SECONDS / 3,
        prepare=commands,
    )


@pytest.fixture
async def mqtt5(monkeypatch: pytest.MonkeyPatch) -> Observation:
    return await _observe(
        monkeypatch, protocol_version="5", message_expiry_interval=EXPIRY_SECONDS
    )


@pytest.fixture
async def mqtt311(monkeypatch: pytest.MonkeyPatch) -> Observation:
    return await _observe(monkeypatch, protocol_version="3.1.1")


@pytest.mark.integration
class TestMqtt5RetainedExpiry(Mqtt5Contract):
    state_topic = DISPLAY_STATE

    def test_a_command_answer_is_refreshed_with_its_payload(
        self, mqtt5: Observation
    ) -> None:
        """Technique: Error Guessing - a refresh replays the last action answer.

        A consumer that reacts to ``system/action/state`` sees the old
        ``accepted`` answer again, but the refresh never re-runs the action:
        the app acts only on the non-retained ``/set`` topics.
        """
        publishes = mqtt5.broker.publishes_to(SYSTEM_ACTION_STATE)

        assert len(publishes) == mqtt5.startup_counts[SYSTEM_ACTION_STATE] + WINDOWS
        assert len({p.payload for p in publishes}) == 1
        assert all(p.retain for p in publishes)

    def test_command_topics_are_never_published_retained(
        self, mqtt5: Observation
    ) -> None:
        """Technique: Specification-based - only the app's own state is retained."""
        retained = {p.topic for p in mqtt5.broker.publishes if p.retain}

        assert DISPLAY_SET not in retained
        assert SYSTEM_ACTION_SET not in retained


@pytest.mark.integration
class TestMqtt311Default(Mqtt311Contract):
    pass
