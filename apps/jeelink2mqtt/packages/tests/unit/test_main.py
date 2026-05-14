"""Unit tests for main.py — command handler invariant guards.

Test Techniques Used:
- Error Guessing: inject the (None, None) impossible return value from
  _parse_or_error to verify the defensive RuntimeError is raised for both
  mapping_assign and mapping_reset command handlers.
- Specification-based: reactor publishes mapping events and state, persists
  registry, and resets filter bank on sensor ID reassignment.
- State Transition: empty-events path still publishes mapping/state and
  persists registry; filter-bank reset observable via post-reset output.
- Equivalence Partitioning: single vs. multiple events, with vs. without
  old_sensor_id, single vs. batch reassignment events.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from cosalette import DeviceStore
from cosalette.stores import MemoryStore

from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.main import _PARSE_OR_ERROR_IMPOSSIBLE
from jeelink2mqtt.models import MappingEvent, SensorConfig, SensorReading
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.state import SharedState
from tests.fixtures.doubles import FakeDeviceContext

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_device_store() -> DeviceStore:
    """Create a MemoryStore-backed DeviceStore for reactor tests."""
    backend = MemoryStore()
    ds = DeviceStore(backend=backend, key="test")
    ds.load()
    return ds


# ── _parse_or_error invariant guard ──────────────────────────────────────────


@pytest.mark.unit
class TestParseOrErrorGuard:
    """Error Guessing: (None, None) path raises RuntimeError with known message."""

    @pytest.mark.asyncio
    async def test_mapping_assign_raises_on_impossible_none(self) -> None:
        """mapping_assign raises RuntimeError when _parse_or_error returns (None, None).

        Technique: Error Guessing — monkey-patch _parse_or_error to trigger the
        invariant that should be unreachable in normal operation.
        """
        with patch("jeelink2mqtt.main._parse_or_error", return_value=(None, None)):
            from jeelink2mqtt.main import mapping_assign

            with pytest.raises(
                RuntimeError, match=re.escape(_PARSE_OR_ERROR_IMPOSSIBLE)
            ):
                await mapping_assign(
                    payload="{}",
                    store=MagicMock(),
                    state=MagicMock(),
                )

    @pytest.mark.asyncio
    async def test_mapping_reset_raises_on_impossible_none(self) -> None:
        """mapping_reset raises RuntimeError when _parse_or_error returns (None, None).

        Technique: Error Guessing — same invariant guard as mapping_assign.
        """
        with patch("jeelink2mqtt.main._parse_or_error", return_value=(None, None)):
            from jeelink2mqtt.main import mapping_reset

            with pytest.raises(
                RuntimeError, match=re.escape(_PARSE_OR_ERROR_IMPOSSIBLE)
            ):
                await mapping_reset(
                    payload="{}",
                    store=MagicMock(),
                    state=MagicMock(),
                )

    def test_impossible_none_message_matches_constant(self) -> None:
        """The guard message constant is non-empty and references the function name.

        Technique: Specification-based — constant value check so future renames
        stay intentional.
        """
        assert "_parse_or_error" in _PARSE_OR_ERROR_IMPOSSIBLE
        assert "(None, None)" in _PARSE_OR_ERROR_IMPOSSIBLE


# ── on_registry_events reactor ───────────────────────────────────────────────


@pytest.mark.unit
class TestOnRegistryEvents:
    """Verifies the on_registry_events reactor publishes events/state and persists.

    Test Techniques Used:
    - Specification-based: reactor contract for mapping lifecycle (events, state,
      persistence).
    - State Transition: filter-bank reset on reassignment; observable via output
      after reset vs. output a non-reset filter would produce.
    - Equivalence Partitioning: single event, multiple events, empty-events batch,
      event with old_sensor_id vs. without.
    """

    @pytest.mark.asyncio
    async def test_publishes_mapping_events_and_state(self) -> None:
        """on_registry_events publishes each mapping event and the registry state.

        Technique: Specification-based — reactor contract for mapping lifecycle.
        """
        from jeelink2mqtt.main import on_registry_events

        # Arrange
        ctx = FakeDeviceContext()
        store = _make_device_store()
        config = SensorConfig(name="office")
        state = SharedState(
            registry=SensorRegistry([config], 600),
            filter_bank=FilterBank(3),
            sensor_configs={"office": config},
        )

        events = [
            MappingEvent(
                event_type="auto_adopt",
                sensor_name="office",
                old_sensor_id=None,
                new_sensor_id=42,
                timestamp=datetime.now(UTC),
                reason="First reading",
            )
        ]

        # Act
        await on_registry_events(events, ctx, store, state)

        # Assert — mapping/event and mapping/state published
        topics = [t for t, _, _ in ctx.published]
        assert "mapping/event" in topics
        assert "mapping/state" in topics

        # Assert — registry persisted with expected structure
        assert "registry" in store
        registry_data = store["registry"]
        assert isinstance(registry_data, dict)
        assert "mappings" in registry_data
        assert "unmapped" in registry_data

    @pytest.mark.asyncio
    async def test_empty_events_still_publishes_state_and_persists(self) -> None:
        """on_registry_events with empty events still publishes mapping/state and persists.

        Technique: Equivalence Partitioning — empty-events branch.
        The reactor always emits a state snapshot and persists, even when the
        drain list is empty (e.g., framework calls reactor spuriously).
        """
        from jeelink2mqtt.main import on_registry_events

        # Arrange
        ctx = FakeDeviceContext()
        store = _make_device_store()
        config = SensorConfig(name="office")
        state = SharedState(
            registry=SensorRegistry([config], 600),
            filter_bank=FilterBank(3),
            sensor_configs={"office": config},
        )

        # Act — empty events list
        await on_registry_events([], ctx, store, state)

        # Assert — no mapping/event published, but mapping/state and registry persisted
        event_topics = [t for t, _, _ in ctx.published if t == "mapping/event"]
        assert len(event_topics) == 0

        state_topics = [t for t, _, _ in ctx.published if t == "mapping/state"]
        assert len(state_topics) == 1

        assert "registry" in store

    @pytest.mark.asyncio
    async def test_resets_filter_bank_on_reassignment(self) -> None:
        """on_registry_events resets filter_bank when old_sensor_id is not None.

        Technique: State Transition — ADR-003 filter reset contract.
        Observable behavior: after 3 extreme-low readings (all 1.0), a non-reset
        filter would keep returning ~1.0 for the next reading; a reset filter
        returns the new reading value (99.0) unaffected by prior history.
        """
        from jeelink2mqtt.main import on_registry_events

        # Arrange
        ctx = FakeDeviceContext()
        store = _make_device_store()
        config = SensorConfig(name="office")
        filter_bank = FilterBank(3)
        state = SharedState(
            registry=SensorRegistry([config], 600),
            filter_bank=filter_bank,
            sensor_configs={"office": config},
        )

        # Fill old sensor ID 10's window with extreme-low values (all 1.0).
        # Without reset, a 99.0 reading would still return ~1.0 (median of
        # [1.0, 1.0, 99.0] = 1.0).  After reset the window is empty, so
        # 99.0 is returned unchanged.
        for _ in range(3):
            filter_bank.filter(SensorReading(10, 1.0, 10, False, datetime.now(UTC)))

        events = [
            MappingEvent(
                event_type="auto_adopt",
                sensor_name="office",
                old_sensor_id=10,  # Reassignment
                new_sensor_id=42,
                timestamp=datetime.now(UTC),
                reason="Battery swap",
            )
        ]

        # Act
        await on_registry_events(events, ctx, store, state)

        # Assert — filter for old ID was reset; new reading is unaffected by
        # prior 1.0 history.  (A non-reset filter returns 1.0, not 99.0.)
        test_reading = SensorReading(10, 99.0, 99, False, datetime.now(UTC))
        filtered_temp, filtered_hum = filter_bank.filter(test_reading)
        assert filtered_temp == 99.0, (
            "filter was not reset — prior 1.0 readings should no longer influence output"
        )
        assert filtered_hum == 99.0

    @pytest.mark.asyncio
    async def test_resets_filter_bank_for_each_old_id_in_batch(self) -> None:
        """on_registry_events resets filter_bank for every reassignment in the batch.

        Technique: Equivalence Partitioning — batch with multiple reassignments.
        Each event with old_sensor_id must trigger its own filter reset.
        """
        from jeelink2mqtt.main import on_registry_events

        # Arrange
        ctx = FakeDeviceContext()
        store = _make_device_store()
        configs = [SensorConfig(name="office"), SensorConfig(name="outdoor")]
        filter_bank = FilterBank(3)
        state = SharedState(
            registry=SensorRegistry(configs, 600),
            filter_bank=filter_bank,
            sensor_configs={c.name: c for c in configs},
        )

        # Fill both old sensor IDs (10 and 20) with extreme-low values
        for old_id in (10, 20):
            for _ in range(3):
                filter_bank.filter(
                    SensorReading(old_id, 1.0, 10, False, datetime.now(UTC))
                )

        events = [
            MappingEvent(
                event_type="auto_adopt",
                sensor_name="office",
                old_sensor_id=10,
                new_sensor_id=42,
                timestamp=datetime.now(UTC),
                reason="Battery swap office",
            ),
            MappingEvent(
                event_type="auto_adopt",
                sensor_name="outdoor",
                old_sensor_id=20,
                new_sensor_id=99,
                timestamp=datetime.now(UTC),
                reason="Battery swap outdoor",
            ),
        ]

        # Act
        await on_registry_events(events, ctx, store, state)

        # Assert — both old IDs' filters were reset; 99.0 passes through unchanged
        for old_id in (10, 20):
            probe = SensorReading(old_id, 99.0, 99, False, datetime.now(UTC))
            temp, _ = filter_bank.filter(probe)
            assert temp == 99.0, f"filter for old sensor ID {old_id} was not reset"

    @pytest.mark.asyncio
    async def test_multiple_events_published_as_individual_event_messages(self) -> None:
        """on_registry_events publishes all events in the batch individually.

        Technique: Specification-based — reactor drains full event list.
        """
        from jeelink2mqtt.main import on_registry_events

        # Arrange
        ctx = FakeDeviceContext()
        store = _make_device_store()
        configs = [SensorConfig(name="office"), SensorConfig(name="outdoor")]
        state = SharedState(
            registry=SensorRegistry(configs, 600),
            filter_bank=FilterBank(3),
            sensor_configs={c.name: c for c in configs},
        )

        events = [
            MappingEvent(
                event_type="auto_adopt",
                sensor_name="office",
                old_sensor_id=None,
                new_sensor_id=42,
                timestamp=datetime.now(UTC),
                reason="First office reading",
            ),
            MappingEvent(
                event_type="auto_adopt",
                sensor_name="outdoor",
                old_sensor_id=None,
                new_sensor_id=99,
                timestamp=datetime.now(UTC),
                reason="First outdoor reading",
            ),
        ]

        # Act
        await on_registry_events(events, ctx, store, state)

        # Assert — two mapping/event publishes, one mapping/state
        event_topics = [t for t, _, _ in ctx.published if t == "mapping/event"]
        assert len(event_topics) == 2

        state_topics = [t for t, _, _ in ctx.published if t == "mapping/state"]
        assert len(state_topics) == 1


# ── App restart configuration ─────────────────────────────────────────────────


@pytest.mark.unit
class TestAppRestartConfig:
    """Verify restart configuration on the App instance."""

    def test_restart_after_failures_is_five(self) -> None:
        """App is configured to restart after 5 consecutive failures.

        Technique: Specification-based — serial adapter recovery configuration.
        """
        from jeelink2mqtt.main import app

        assert app._restart_after_failures == 5

    def test_max_restarts_is_three(self) -> None:
        """App allows at most 3 restarts before giving up.

        Technique: Specification-based — bounded restart loop prevents runaway.
        """
        from jeelink2mqtt.main import app

        assert app._max_restarts == 3
