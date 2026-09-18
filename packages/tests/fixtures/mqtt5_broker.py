"""In-memory MQTT broker double for the retained-expiry regression tests.

cosalette's MQTT 5 opt-in (ADR-078) lives in the real ``MqttClient``: it stamps
``MessageExpiryInterval`` on retained publishes and re-publishes them from its
ledger every ``message_expiry_interval / 3``. ``MockMqttClient`` bypasses that
code, so a test that wants to see the wire behaviour must drive the real client
against something that behaves like a broker.

:class:`FakeMqtt5Broker` replaces ``aiomqtt.Client`` and records what a broker
would see: the connect arguments, every publish with its expiry property, and
the retained store. It never sleeps: ages come from the injected clock, so a
``ManualClock`` moves a whole expiry window in one ``advance``.

Apps reach this module through ``pythonpath = ["../../packages/tests/fixtures"]``
in their ``[tool.pytest.ini_options]``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import aiomqtt
import pytest
from cosalette import ClockPort, MqttClient
from cosalette.testing import AppHarness


@dataclass(frozen=True)
class BrokerPublish:
    """One PUBLISH packet as the broker received it."""

    topic: str
    payload: str
    retain: bool
    qos: int
    expiry: int | None
    at: float


@dataclass
class FakeMqtt5Broker:
    """Records connections and publishes; models MQTT 5 retained expiry."""

    clock: ClockPort
    connects: list[dict[str, Any]] = field(default_factory=list)
    publishes: list[BrokerPublish] = field(default_factory=list)
    retained: dict[str, BrokerPublish] = field(default_factory=dict)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Route ``aiomqtt.Client`` (imported lazily by cosalette) to this broker."""
        monkeypatch.setattr(
            aiomqtt, "Client", lambda **kwargs: _BrokerConnection(self, kwargs)
        )

    def record(
        self, topic: str, payload: str, *, retain: bool, qos: int, expiry: int | None
    ) -> None:
        publish = BrokerPublish(topic, payload, retain, qos, expiry, self.clock.now())
        self.publishes.append(publish)
        if not retain:
            return
        if payload == "":
            self.retained.pop(topic, None)
        else:
            self.retained[topic] = publish

    def publishes_to(self, topic: str) -> list[BrokerPublish]:
        return [p for p in self.publishes if p.topic == topic]

    def expired_topics(self) -> list[str]:
        """Retained topics a MQTT 5 broker would already have discarded."""
        now = self.clock.now()
        return sorted(
            topic
            for topic, p in self.retained.items()
            if p.expiry is not None and now - p.at >= p.expiry
        )


class _BrokerConnection:
    """Stand-in for ``aiomqtt.Client``: connects instantly, never delivers."""

    def __init__(self, broker: FakeMqtt5Broker, kwargs: dict[str, Any]) -> None:
        self._broker = broker
        self._broker.connects.append(kwargs)

    async def __aenter__(self) -> _BrokerConnection:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        return None

    async def publish(
        self,
        topic: str,
        payload: str,
        *,
        retain: bool = False,
        qos: int = 0,
        properties: Any = None,
    ) -> None:
        expiry = getattr(properties, "MessageExpiryInterval", None)
        self._broker.record(topic, payload, retain=retain, qos=qos, expiry=expiry)

    @property
    def messages(self) -> AsyncIterator[Any]:
        return self._never()

    @staticmethod
    async def _never() -> AsyncIterator[Any]:
        await asyncio.Event().wait()
        yield  # pragma: no cover - makes this an async generator


@dataclass
class Observation:
    """What the broker saw over the observed refresh windows."""

    broker: FakeMqtt5Broker
    startup_counts: dict[str, int]
    """Publishes per retained topic once startup publishing had settled."""
    window_counts: list[dict[str, int]] = field(default_factory=list)
    """Publishes per retained topic after each window."""
    window_expired: list[list[str]] = field(default_factory=list)
    """Topics a MQTT 5 broker would have expired after each window."""


def _retained_counts(broker: FakeMqtt5Broker) -> dict[str, int]:
    return {topic: len(broker.publishes_to(topic)) for topic in broker.retained}


def _started(client: MqttClient, broker: FakeMqtt5Broker, ready_topic: str) -> bool:
    return ready_topic in broker.retained and client._connect_ready.is_set()


async def run_against_broker(
    harness: AppHarness,
    broker: FakeMqtt5Broker,
    *,
    ready_topic: str,
    windows: int,
    window_seconds: float,
) -> Observation:
    """Run the app on the real ``MqttClient`` for *windows* refresh windows.

    The harness's mock client is swapped for a real one that shares the
    harness clock, so the client's refresh loop and the app's own schedules
    run on one virtual timeline. Startup is over once *ready_topic* is retained
    and the client has finished its connect callbacks (discovery, registry and
    status re-announce), which is what ``_connect_ready`` signals.
    """
    client = MqttClient(settings=harness.settings.mqtt, clock=harness.clock)
    harness.mqtt = client  # type: ignore[assignment]
    task = asyncio.create_task(harness.run())
    try:
        async with asyncio.timeout(5):
            while not _started(client, broker, ready_topic):
                await asyncio.sleep(0.005)
        await harness.advance_time(0)
        observation = Observation(broker, _retained_counts(broker))
        for _ in range(windows):
            await harness.advance_time(window_seconds)
            observation.window_counts.append(_retained_counts(broker))
            observation.window_expired.append(broker.expired_topics())
        return observation
    finally:
        harness.shutdown_event.set()
        try:
            await asyncio.wait_for(task, timeout=5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
