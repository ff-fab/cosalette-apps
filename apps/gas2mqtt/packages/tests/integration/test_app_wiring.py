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
from gas2mqtt.devices.gas_counter import GasCounterState
from gas2mqtt.main import _make_store, app, create_app
from tests.fixtures.config import make_gas2mqtt_settings

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _find_gas_counter_state_factory(fresh_app: cosalette.App):
    """Return the @app.state factory registered for GasCounterState.

    Uses return-annotation inspection to locate the factory among all
    registered state providers.  Raises AssertionError if not found.
    """
    for factory in fresh_app._state_factories:
        if hasattr(factory.factory, "__annotations__"):
            return_annotation = factory.factory.__annotations__.get("return")
            if (
                return_annotation is GasCounterState
                or return_annotation == "GasCounterState"
            ):
                return factory
    raise AssertionError("No GasCounterState factory registered in _state_factories")


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
        """Fresh app instance registers temperature telemetry declaratively.

        Technique: Specification-based — verifying registration contract.
        """
        fresh_app = create_app()

        # Assert
        telemetry_names = [t.name for t in fresh_app.telemetry_registrations]
        assert "temperature" in telemetry_names


# ---------------------------------------------------------------------------
# Debug magnetometer registration (enabled= parameter)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMagnetometerRegistration:
    """Verify magnetometer conditional registration via enabled= parameter.

    The registration stays declarative in ``main.py`` while deferring the
    enabled decision to resolved settings.
    """

    def test_enabled_spec_tracks_debug_setting(self) -> None:
        """Magnetometer enabled spec follows enable_debug_device.

        Technique: Branch Coverage — verifying both enabled branches.
        """
        fresh_app = create_app()
        registration = next(
            telemetry
            for telemetry in fresh_app.telemetry_registrations
            if telemetry.name == "magnetometer"
        )

        assert callable(registration.enabled_spec)
        assert (
            registration.enabled_spec(make_gas2mqtt_settings(enable_debug_device=False))
            is False
        )
        assert (
            registration.enabled_spec(make_gas2mqtt_settings(enable_debug_device=True))
            is True
        )

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
    """Verify store factory wiring without mutating the singleton app."""

    def test_make_store_uses_explicit_state_file(self, tmp_path) -> None:
        """Explicit state_file setting overrides the XDG fallback.

        Technique: Decision Table — explicit override branch.
        """
        state_file = tmp_path / "custom-state.json"
        store = _make_store(make_gas2mqtt_settings(state_file=state_file))

        store.save("gas_counter", {"counter": 1})

        assert state_file.exists()

    def test_make_store_uses_xdg_path_when_state_file_unset(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        """Unset state_file falls back to the XDG state path.

        Technique: Decision Table — fallback branch.
        """
        monkeypatch.delenv("GAS2MQTT_STATE_FILE", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))

        store = _make_store(make_gas2mqtt_settings(state_file=None))
        store.save("gas_counter", {"counter": 1})

        assert (tmp_path / "xdg-state" / "gas2mqtt" / "state.json").exists()


# ---------------------------------------------------------------------------
# State provider registration (@app.state)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStateProviderRegistration:
    """Verify GasCounterState is provided via @app.state, not lifespan."""

    def test_app_registers_gas_counter_state_factory(self) -> None:
        """create_app() registers a @app.state factory for GasCounterState.

        Technique: Specification-based — verifying cosalette 0.4 provider wiring.
        """
        # Arrange
        fresh_app = create_app()

        # Assert — structural preconditions
        assert hasattr(fresh_app, "_state_factories")
        assert len(fresh_app._state_factories) > 0

        # Assert — correct factory is registered
        factory = _find_gas_counter_state_factory(fresh_app)
        assert factory.factory.__name__ == "gas_counter_state"

    def test_state_provider_builds_gas_counter_state(self, tmp_path) -> None:
        """The registered provider returns a valid GasCounterState.

        Technique: Integration — exercise factory with real domain objects,
        no hardware required.
        """
        # Arrange
        settings = make_gas2mqtt_settings(state_file=tmp_path / "state.json")
        factory = _find_gas_counter_state_factory(create_app())

        # Act
        state = factory.factory(settings)

        # Assert
        assert isinstance(state, GasCounterState)
        assert state.counter == 0

    def test_state_provider_restores_persisted_counter(self, tmp_path) -> None:
        """State provider loads counter from a pre-populated store.

        Technique: State Transition — verifying restore-from-disk path.
        """
        # Arrange — seed the store file then resolve the registered factory
        settings = make_gas2mqtt_settings(state_file=tmp_path / "state.json")
        _make_store(settings).save("gas_counter", {"counter": 99})
        factory = _find_gas_counter_state_factory(create_app())

        # Act
        state = factory.factory(settings)

        # Assert
        assert state.counter == 99
