"""Integration tests for gas2mqtt application wiring.

Verifies that module-level declarations in ``main.py`` correctly wire
all components, that adapter lifecycle methods (__aenter__/__aexit__)
properly manage the magnetometer, and that device registration uses
eager settings with ``enabled=`` for conditional registration.

Test Techniques Used:
- Specification-based: App configuration matches expectations
- Integration: Handler factories exercised end-to-end with real domain objects
- State Transition: Adapter __aenter__/__aexit__ lifecycle
- Branch Coverage: Magnetometer conditional registration via enabled=
- Error Guessing: __aexit__ closes adapter even on error
"""

from __future__ import annotations

import cosalette
import pytest

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.main import app

# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAppCreation:
    """Verify module-level app is a properly configured App."""

    def test_creates_app_instance(self) -> None:
        """Module-level app is a cosalette App.

        Technique: Specification-based — verifying module-level wiring.
        """
        # Assert
        assert isinstance(app, cosalette.App)


# ---------------------------------------------------------------------------
# Adapter lifecycle (__aenter__ / __aexit__)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAdapterLifecycle:
    """Verify adapter __aenter__/__aexit__ manages magnetometer lifecycle."""

    async def test_aenter_initializes_magnetometer(self) -> None:
        """__aenter__ calls initialize() on the adapter.

        Technique: State Transition — verifying startup lifecycle.
        """
        # Arrange
        mag = FakeMagnetometer()

        # Act
        async with mag:
            # Assert
            assert mag.initialized is True

    async def test_aexit_closes_magnetometer(self) -> None:
        """__aexit__ calls close() on the adapter.

        Technique: State Transition — verifying shutdown lifecycle.
        """
        # Arrange
        mag = FakeMagnetometer()

        # Act
        async with mag:
            pass

        # Assert
        assert mag.closed is True

    async def test_aexit_closes_on_error(self) -> None:
        """__aexit__ closes adapter even if the body raises.

        Technique: Error Guessing — cleanup must happen on exceptions.
        """
        # Arrange
        mag = FakeMagnetometer()

        # Act
        with pytest.raises(RuntimeError, match="boom"):
            async with mag:
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
        """Module-level app registers temperature as a telemetry device.

        Technique: Specification-based — verifying registration contract.
        """
        # Assert
        telemetry_names = [t.name for t in app._telemetry]  # noqa: SLF001
        assert "temperature" in telemetry_names


# ---------------------------------------------------------------------------
# Debug magnetometer registration (enabled= parameter)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMagnetometerRegistration:
    """Verify magnetometer conditional registration via enabled= parameter.

    The module-level app uses ``enabled=settings.enable_debug_device``
    on the ``app.add_telemetry("magnetometer", ...)`` call.  Since the
    default settings have ``enable_debug_device=False``, the magnetometer
    is NOT registered in the singleton app.

    The handler in ``gas2mqtt.devices.magnetometer`` can still be tested
    directly to verify correctness independent of wiring.
    """

    def test_noop_when_disabled_by_default(self) -> None:
        """Default settings disable magnetometer registration.

        Technique: Branch Coverage — verifying enabled=False path.
        Default ``enable_debug_device`` is False, so the magnetometer
        telemetry is skipped during module-level registration.
        """
        # Assert
        telemetry_names = [t.name for t in app._telemetry]  # noqa: SLF001
        assert "magnetometer" not in telemetry_names

    async def test_magnetometer_handler_returns_readings(self) -> None:
        """magnetometer handler returns correct reading dict.

        Technique: Integration — exercise the handler directly with a
        fake magnetometer to verify it works regardless of enabled= wiring.
        """
        # Arrange
        from gas2mqtt.devices.magnetometer import magnetometer

        mag = FakeMagnetometer()
        async with mag:
            # Act
            result = await magnetometer(mag)

        # Assert
        assert "bx" in result
        assert "by" in result
        assert "bz" in result


# ---------------------------------------------------------------------------
# Storage adapter wiring
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStoreWiring:
    """Verify cosalette Store is wired via App constructor."""

    def test_app_has_store_configured(self) -> None:
        """Module-level app has a Store backend set.

        Technique: Specification-based — store is wired at module level.
        """
        assert app._store is not None  # noqa: SLF001

    def test_app_has_null_store_by_default(self) -> None:
        """App uses NullStore when state_file is not configured (default).

        Technique: Specification-based — default state_file is None.
        """
        assert isinstance(app._store, cosalette.NullStore)  # noqa: SLF001
