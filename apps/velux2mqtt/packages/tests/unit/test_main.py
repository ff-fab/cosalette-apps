"""Unit tests for main.py — velux app composition.

Test Techniques Used:
- Specification-based: app uses dict-name @app.device registration
- Error Guessing: _cover_map rejects unexpected settings types
- Boundary Value Analysis: _cover_map with empty covers list
- Specification-based: Velux2MqttSettings rejects duplicate cover names
- Specification-based: cover_device registered directly with declarative metadata
"""

from __future__ import annotations

import cosalette
import pytest
from pydantic import ValidationError

from velux2mqtt import __version__
from velux2mqtt.devices.cover import cover_device
from velux2mqtt.main import _cover_map, app
from velux2mqtt.settings import CoverConfig, Velux2MqttSettings


def _cover(name: str, pin_base: int) -> CoverConfig:
    """Create a minimal cover config with distinct GPIO pins."""
    return CoverConfig(
        name=name,
        pin_up=pin_base,
        pin_stop=pin_base + 1,
        pin_down=pin_base + 2,
        travel_duration_up=10.0,
        travel_duration_down=12.0,
    )


def _settings(*covers: CoverConfig) -> Velux2MqttSettings:
    """Create settings with the supplied covers."""
    return Velux2MqttSettings(covers=list(covers))


@pytest.mark.unit
class TestCoverMap:
    """Verify settings-driven cover name mapping."""

    def test_maps_cover_names_to_configs(self) -> None:
        """_cover_map returns dict-name mapping expected by cosalette.

        Technique: Specification-based — verifies name=callable contract.
        """
        # Arrange
        blind = _cover("blind", 1)
        window = _cover("window", 4)
        settings = _settings(blind, window)

        # Act
        result = _cover_map(settings)

        # Assert
        assert result == {"blind": blind, "window": window}

    def test_rejects_wrong_settings_type(self) -> None:
        """_cover_map fails clearly if called with the wrong settings type.

        Technique: Error Guessing — defensive guard for framework misuse.
        """
        # Arrange
        settings = cosalette.Settings()

        # Act & Assert
        with pytest.raises(TypeError, match="Expected Velux2MqttSettings"):
            _cover_map(settings)

    def test_empty_covers_returns_empty_map(self) -> None:
        """_cover_map returns {} when no covers are configured.

        Technique: Boundary Value Analysis — empty input partition.
        """
        # Arrange
        settings = _settings()

        # Act
        result = _cover_map(settings)

        # Assert
        assert result == {}

    def test_duplicate_names_rejected_by_settings(self) -> None:
        """_cover_map never receives duplicate names: Velux2MqttSettings rejects them.

        Technique: Specification-based — validator is the enforcement point,
        so _cover_map itself has no duplicate-handling responsibility.
        Distinct GPIO pin bases avoid the cross-cover pin-overlap validator.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError, match="Cover names must be unique"):
            Velux2MqttSettings(
                covers=[
                    _cover("blind", 1),
                    _cover("blind", 4),  # same name, different pins
                ]
            )


@pytest.mark.unit
class TestAppVersion:
    """Verify the app version is sourced from package metadata."""

    def test_version_matches_package_metadata(self) -> None:
        """app.version equals the installed package version.

        Technique: Specification-based — ensures the composition root wires
        __version__ into the App instance, not a hard-coded placeholder.
        """
        assert app.version == __version__

    def test_version_is_not_placeholder(self) -> None:
        """app.version is not the zero-version placeholder.

        Technique: Error Guessing — guards against forgetting to set version
        in pyproject.toml or the App() constructor.
        """
        assert app.version != "0.0.0"


@pytest.mark.unit
class TestAppComposition:
    """Verify velux2mqtt app composition uses declarative device expansion."""

    def test_app_registers_cover_device_directly(self) -> None:
        """App has a single dict-name device registration pointing to cover_device.

        cover_device is registered directly — no wrapper layer.  The
        declarative metadata (summary, behavior, effects) describes the
        device contract without embedding business logic in main.py.

        Technique: Specification-based — verifies composition root shape.
        """
        # Act
        registrations = [r for r in app.devices if r.func is cover_device]

        # Assert
        assert len(registrations) == 1
        registration = registrations[0]
        assert registration.name_spec is _cover_map
        assert "cover" in registration.summary.lower()
        assert registration.behavior is not None and len(registration.behavior) > 0
        assert registration.effects is not None and len(registration.effects) > 0
