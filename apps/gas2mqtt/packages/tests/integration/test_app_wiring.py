"""Integration tests for gas2mqtt application wiring.

Verifies that ``create_app()`` correctly wires all components, that
the lifespan properly manages the magnetometer adapter lifecycle,
and that device registration uses eager settings.

Test Techniques Used:
- Specification-based: App configuration matches expectations
- Integration: Handler factories exercised end-to-end with real domain objects
- State Transition: Lifespan startup/shutdown lifecycle
- Branch Coverage: Magnetometer conditional registration
- Error Guessing: Lifespan closes adapter even on error
"""

from __future__ import annotations

from pathlib import Path

import cosalette
import pytest

from gas2mqtt.adapters.fake import FakeMagnetometer, NullStorage
from gas2mqtt.adapters.json_storage import JsonFileStorage
from gas2mqtt.main import _make_storage_adapter, create_app, lifespan
from gas2mqtt.ports import MagnetometerPort, StateStoragePort
from tests.fixtures.config import make_gas2mqtt_settings

# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAppCreation:
    """Verify create_app() produces a properly configured App."""

    def test_creates_app_instance(self) -> None:
        """create_app() returns a cosalette App.

        Technique: Specification-based — verifying factory contract.
        """
        # Act
        app = create_app()

        # Assert
        assert isinstance(app, cosalette.App)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLifespan:
    """Verify lifespan initializes and cleans up the magnetometer."""

    async def test_initializes_magnetometer(self) -> None:
        """Lifespan calls magnetometer.initialize() on startup.

        Technique: State Transition — verifying startup lifecycle.
        """
        # Arrange
        mag = FakeMagnetometer()
        ctx = cosalette.AppContext(
            settings=make_gas2mqtt_settings(),
            adapters={MagnetometerPort: mag},
        )

        # Act
        async with lifespan(ctx):
            # Assert
            assert mag.initialized is True

    async def test_closes_magnetometer(self) -> None:
        """Lifespan calls magnetometer.close() on shutdown.

        Technique: State Transition — verifying shutdown lifecycle.
        """
        # Arrange
        mag = FakeMagnetometer()
        ctx = cosalette.AppContext(
            settings=make_gas2mqtt_settings(),
            adapters={MagnetometerPort: mag},
        )

        # Act
        async with lifespan(ctx):
            pass

        # Assert
        assert mag.closed is True

    async def test_closes_on_error(self) -> None:
        """Lifespan closes magnetometer even if the body raises.

        Technique: Error Guessing — cleanup must happen on exceptions.
        """
        # Arrange
        mag = FakeMagnetometer()
        ctx = cosalette.AppContext(
            settings=make_gas2mqtt_settings(),
            adapters={MagnetometerPort: mag},
        )

        # Act
        with pytest.raises(RuntimeError, match="boom"):
            async with lifespan(ctx):
                raise RuntimeError("boom")

        # Assert
        assert mag.closed is True


# ---------------------------------------------------------------------------
# Temperature registration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestTemperatureRegistration:
    """Verify temperature is registered as telemetry with PT1 filter."""

    def test_temperature_registered_as_telemetry(self) -> None:
        """create_app() registers temperature as a telemetry device.

        Technique: Specification-based — verifying registration contract.
        """
        # Act
        app = create_app()

        # Assert
        telemetry_names = [t.name for t in app._telemetry]  # noqa: SLF001
        assert "temperature" in telemetry_names


# ---------------------------------------------------------------------------
# Debug magnetometer registration
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMagnetometerRegistration:
    """Verify magnetometer conditional registration via eager settings."""

    def test_registered_when_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """create_app() registers magnetometer when debug device is on.

        Technique: Branch Coverage — verifying conditional registration
        (True branch) via eager settings and env var override.
        """
        # Arrange — set env var so eager settings picks up the override
        monkeypatch.setenv("GAS2MQTT_ENABLE_DEBUG_DEVICE", "true")

        # Act
        app = create_app()

        # Assert
        telemetry_names = [t.name for t in app._telemetry]  # noqa: SLF001
        assert "magnetometer" in telemetry_names

    def test_noop_when_disabled(self) -> None:
        """create_app() does not register magnetometer when debug is off.

        Technique: Branch Coverage — verifying conditional registration
        behavior (default settings have enable_debug_device=False).
        """
        # Act
        app = create_app()

        # Assert
        telemetry_names = [t.name for t in app._telemetry]  # noqa: SLF001
        assert "magnetometer" not in telemetry_names


# ---------------------------------------------------------------------------
# Storage adapter wiring
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStorageAdapterWiring:
    """Verify StateStoragePort adapter registration.

    Technique: Specification-based — adapter factory produces correct type
    depending on the ``state_file`` setting.
    """

    def test_storage_adapter_returns_null_when_no_state_file(self) -> None:
        """Factory returns NullStorage when state_file is None (default)."""
        # Arrange
        settings = make_gas2mqtt_settings(state_file=None)

        # Act
        storage = _make_storage_adapter(settings)

        # Assert
        assert isinstance(storage, NullStorage)

    def test_storage_adapter_returns_json_file_when_configured(
        self,
        tmp_path: Path,
    ) -> None:
        """Factory returns JsonFileStorage when state_file is set."""
        # Arrange
        state_path = tmp_path / "state.json"
        settings = make_gas2mqtt_settings(state_file=state_path)

        # Act
        storage = _make_storage_adapter(settings)

        # Assert
        assert isinstance(storage, JsonFileStorage)

    def test_storage_port_registered_in_app(self) -> None:
        """create_app() registers StateStoragePort in the adapter registry."""
        # Act
        app = create_app()

        # Assert
        assert StateStoragePort in app._adapters  # noqa: SLF001
