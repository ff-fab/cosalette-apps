"""Integration tests for the FakeJeeLinkAdapter callback flow.

Verifies that the adapter correctly routes injected readings through
registered callbacks, simulating the pylacrosse → domain bridge.

Test Techniques Used:
- Integration Testing: Adapter ↔ callback coordination
- State Transition Testing: Adapter lifecycle (open → register → inject)
"""

from __future__ import annotations

import pytest

from jeelink2mqtt.adapters import FakeJeeLinkAdapter
from jeelink2mqtt.app import SharedState
from jeelink2mqtt.models import SensorReading

# ======================================================================
# Callback Routing
# ======================================================================


@pytest.mark.integration
class TestAdapterCallbackFlow:
    """Verify FakeJeeLinkAdapter routes injected readings to callbacks."""

    def test_inject_triggers_callback(
        self, fake_adapter: FakeJeeLinkAdapter, make_reading
    ) -> None:
        """Register a callback, inject one reading, verify callback received it.

        Technique: Integration Testing — adapter → callback routing.
        """
        # Arrange
        received: list[SensorReading] = []
        fake_adapter.register_callback(received.append)
        reading = make_reading(sensor_id=42, temperature=21.5)

        # Act
        fake_adapter.inject(reading)

        # Assert
        assert len(received) == 1
        assert received[0] is reading
        assert received[0].sensor_id == 42

    def test_inject_batch_triggers_all(
        self, fake_adapter: FakeJeeLinkAdapter, make_reading
    ) -> None:
        """Register a callback, inject 3 readings, verify callback got all 3.

        Technique: Integration Testing — batch injection routing.
        """
        # Arrange
        received: list[SensorReading] = []
        fake_adapter.register_callback(received.append)
        readings = [
            make_reading(sensor_id=10, temperature=20.0),
            make_reading(sensor_id=11, temperature=21.0),
            make_reading(sensor_id=12, temperature=22.0),
        ]

        # Act
        fake_adapter.inject_batch(readings)

        # Assert
        assert len(received) == 3
        assert [r.sensor_id for r in received] == [10, 11, 12]


# ======================================================================
# Adapter → Registry Pipeline
# ======================================================================


@pytest.mark.integration
class TestAdapterToRegistryPipeline:
    """Wire FakeJeeLinkAdapter directly to registry.record_reading."""

    def test_adapter_to_registry_pipeline(
        self,
        fake_adapter: FakeJeeLinkAdapter,
        shared_state: SharedState,
        make_reading,
    ) -> None:
        """Wire adapter callback → registry.record_reading, inject a
        reading with a known ID, verify auto-adopt occurs.

        Technique: Integration Testing — adapter ↔ registry wiring.
        """
        # Arrange — assign "outdoor" so only "office" auto-adopts
        shared_state.registry.assign("outdoor", 99)
        shared_state.registry.drain_events()

        resolved_names: list[str | None] = []

        def _on_reading(reading: SensorReading) -> None:
            name = shared_state.registry.record_reading(reading)
            resolved_names.append(name)

        fake_adapter.register_callback(_on_reading)

        # Act
        fake_adapter.inject(make_reading(sensor_id=42))

        # Assert
        assert len(resolved_names) == 1
        assert resolved_names[0] == "office"
        assert shared_state.registry.resolve(42) == "office"
