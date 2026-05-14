"""Integration tests for the @app.stream receiver handler.

Verifies cap-5xy acceptance: the receiver handler processes readings from
a cosalette.Stream[SensorReading], publishes raw/sensor/availability MQTT
messages, and persists registry state — without any manual adapter lifecycle
code in main.py.

Test Techniques Used:
- Integration Testing: stream → registry → pipeline → publish
- State Transition Testing: registry restore from store
- Specification-based: MQTT topic/payload contract
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import cosalette
import pytest
from jeelink2mqtt.main import receiver
from jeelink2mqtt.models import SensorReading
from jeelink2mqtt.settings import Jeelink2MqttSettings, SensorConfigSettings
from jeelink2mqtt.state import build_shared_state

from tests.fixtures.doubles import FakeDeviceContext

# ======================================================================
# Helpers
# ======================================================================


def _make_settings(**overrides: object) -> Jeelink2MqttSettings:
    """Minimal settings with two configured sensors."""
    defaults: dict[str, object] = {
        "sensors": [
            SensorConfigSettings(name="office", temp_offset=-0.3),
            SensorConfigSettings(name="outdoor"),
        ],
        "serial_port": "/dev/null",
    }
    defaults.update(overrides)
    return Jeelink2MqttSettings(**defaults)  # type: ignore[arg-type]


def _make_reading(
    sensor_id: int = 42,
    temperature: float = 21.5,
    humidity: int = 55,
) -> SensorReading:
    return SensorReading(
        sensor_id=sensor_id,
        temperature=temperature,
        humidity=humidity,
        low_battery=False,
        timestamp=datetime.now(UTC),
    )


async def _run_receiver(
    readings: list[SensorReading],
    ctx: FakeDeviceContext,
    store_data: dict[str, object],
    settings: Jeelink2MqttSettings,
    state: object,
) -> None:
    """Run the receiver async generator, injecting readings then shutting down.

    Manually invokes the on_registry_events reactor after each yield to simulate
    framework reactor behavior (integration tests bypass the App harness).
    """
    from cosalette import DeviceStore
    from cosalette.stores import MemoryStore
    from jeelink2mqtt.main import on_registry_events
    from jeelink2mqtt.state import SharedState

    backend = MemoryStore(initial={"receiver": store_data} if store_data else None)
    device_store = DeviceStore(backend, "receiver")
    device_store.load()

    stream: cosalette.Stream[SensorReading] = cosalette.Stream()

    async def _inject_and_shutdown() -> None:
        for r in readings:
            stream.put(r)
        await asyncio.sleep(0)  # let generator process items first
        stream.shutdown()

    gen = receiver(
        stream=stream,
        ctx=ctx,  # type: ignore[arg-type]
        store=device_store,
        settings=settings,
        state=state,  # type: ignore[arg-type]
    )

    async def _drain_gen() -> None:
        async for _ in gen:
            # Manually trigger reactor after yield (simulates framework behavior)
            if isinstance(state, SharedState):
                events = state.registry.drain_events()
                if events:
                    await on_registry_events(events, ctx, device_store, state)  # type: ignore[arg-type]

    await asyncio.gather(_drain_gen(), _inject_and_shutdown())


# ======================================================================
# Stream receiver handler tests
# ======================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestStreamReceiverHandler:
    """Integration tests for the @app.stream receiver handler."""

    async def test_raw_published_for_every_reading(self) -> None:
        """Every received frame must be published to raw/state.

        Technique: Specification-based — raw diagnostic topic contract.
        """
        settings = _make_settings()
        state = build_shared_state(settings)
        ctx = FakeDeviceContext()

        reading = _make_reading(sensor_id=99, temperature=20.0, humidity=50)
        await _run_receiver([reading], ctx, {}, settings, state)

        raw_publishes = [t for t, _, _ in ctx.published if t == "raw/state"]
        assert len(raw_publishes) == 1

    async def test_mapped_sensor_publishes_state_and_availability(self) -> None:
        """A reading for a mapped sensor publishes state + availability=online.

        Technique: Integration Testing — registry → pipeline → publish.
        """
        settings = _make_settings()
        state = build_shared_state(settings)
        # Pre-assign office sensor
        state.registry.assign("office", 42)
        state.registry.drain_events()

        ctx = FakeDeviceContext()
        reading = _make_reading(sensor_id=42, temperature=21.5, humidity=55)
        await _run_receiver([reading], ctx, {}, settings, state)

        topics = [t for t, _, _ in ctx.published]
        assert "office/state" in topics
        assert "office/availability" in topics

        avail = next(p for t, p, _ in ctx.published if t == "office/availability")
        assert avail == "online"

    async def test_unmapped_sensor_publishes_only_raw(self) -> None:
        """An unmapped sensor reading publishes only raw, not sensor state.

        Technique: Decision Table — unmapped ID has no pipeline processing.
        """
        settings = _make_settings()
        state = build_shared_state(settings)
        ctx = FakeDeviceContext()

        # Sensor ID 77 is not mapped to any name
        reading = _make_reading(sensor_id=77)
        await _run_receiver([reading], ctx, {}, settings, state)

        topics = [t for t, _, _ in ctx.published]
        assert "raw/state" in topics
        # No sensor-specific state published (no pipeline for unmapped IDs)
        assert not any(t.endswith("/state") and t != "raw/state" for t in topics)
        # No "online" availability (only offline comes from shutdown finally block)
        online_avail = [
            t for t, p, _ in ctx.published if "availability" in t and p == "online"
        ]
        assert len(online_avail) == 0

    async def test_registry_restore_from_store(self) -> None:
        """Receiver restores registry from persisted store on startup.

        Technique: State Transition Testing — registry restored → reading routed.
        """
        settings = _make_settings()
        state = build_shared_state(settings)

        # Pre-assign to get a populated snapshot
        state.registry.assign("office", 42)
        state.registry.drain_events()
        persisted_registry = state.registry.to_dict()

        # New state (fresh, no assignments) should restore from store
        fresh_state = build_shared_state(settings)
        store_data: dict[str, object] = {"registry": persisted_registry}

        ctx = FakeDeviceContext()
        reading = _make_reading(sensor_id=42, temperature=22.0)
        await _run_receiver([reading], ctx, store_data, settings, fresh_state)

        topics = [t for t, _, _ in ctx.published]
        assert "office/state" in topics

    async def test_shutdown_publishes_offline_availability(self) -> None:
        """When stream ends, receiver publishes offline for all sensors.

        Technique: Specification-based — shutdown availability contract.
        """
        settings = _make_settings()
        state = build_shared_state(settings)
        ctx = FakeDeviceContext()

        # No readings — just shutdown
        await _run_receiver([], ctx, {}, settings, state)

        offline_topics = [
            t for t, p, _ in ctx.published if "availability" in t and p == "offline"
        ]
        # Both sensors should receive offline on shutdown
        assert "office/availability" in offline_topics
        assert "outdoor/availability" in offline_topics

    async def test_mapping_event_published_on_new_sensor(self) -> None:
        """A reading for a new sensor_id triggers a mapping/event publish.

        Technique: Specification-based — exercises the reactor pattern
        in receiver, verifying the mapping/event + mapping/state MQTT contract.

        ADR-002: auto-adopt fires when exactly one configured sensor is stale.
        """
        # One sensor so auto-adopt fires unambiguously (ADR-002)
        settings = _make_settings(
            sensors=[SensorConfigSettings(name="office", temp_offset=-0.3)]
        )
        state = build_shared_state(settings)
        ctx = FakeDeviceContext()

        # Sensor ID 99 is not pre-assigned; its first reading triggers auto-adopt
        reading = _make_reading(sensor_id=99)
        await _run_receiver([reading], ctx, {}, settings, state)

        topics = [t for t, _, _ in ctx.published]
        assert "mapping/event" in topics, (
            "reactor pattern not exercised — no mapping/event published"
        )
        assert "mapping/state" in topics

    async def test_registry_persisted_after_mapping_event(self) -> None:
        """A new sensor_id reading persists the registry to the DeviceStore.

        Technique: State Transition Testing — ADR-004 persistence contract.
        Uses an explicit MemoryStore backend to assert the registry key is
        written when a mapping event fires.
        """
        from cosalette import DeviceStore
        from cosalette.stores import MemoryStore
        from jeelink2mqtt.main import on_registry_events

        # One sensor so auto-adopt fires unambiguously (ADR-002)
        settings = _make_settings(
            sensors=[SensorConfigSettings(name="office", temp_offset=-0.3)]
        )
        state = build_shared_state(settings)
        ctx = FakeDeviceContext()
        backend = MemoryStore()
        device_store = DeviceStore(backend, "receiver")
        device_store.load()

        stream: cosalette.Stream[SensorReading] = cosalette.Stream()

        async def _inject_and_shutdown() -> None:
            stream.put(_make_reading(sensor_id=99))
            await asyncio.sleep(0)
            stream.shutdown()

        gen = receiver(
            stream=stream,
            ctx=ctx,  # type: ignore[arg-type]
            store=device_store,
            settings=settings,
            state=state,  # type: ignore[arg-type]
        )

        async def _drain() -> None:
            async for _ in gen:
                # Manually trigger reactor after yield (simulates framework)
                events = state.registry.drain_events()
                if events:
                    await on_registry_events(events, ctx, device_store, state)  # type: ignore[arg-type]

        await asyncio.gather(_drain(), _inject_and_shutdown())

        # ADR-004: on_registry_events reactor persists registry to DeviceStore.
        # (The framework calls store.save() on shutdown; simulate that here.)
        device_store.save()
        assert "receiver" in backend._data, "DeviceStore was never saved"
        assert "registry" in backend._data["receiver"], (
            "registry key absent — reactor did not write to store"
        )
