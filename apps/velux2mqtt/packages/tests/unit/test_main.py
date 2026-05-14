# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Unit tests for main.py — velux app composition.

Test Techniques Used:
- Specification-based: app uses dict-name @app.device registration
- Error Guessing: _cover_map rejects unexpected settings types
"""

from __future__ import annotations

import cosalette
import pytest

from velux2mqtt.main import _cover_map, app, cover
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


@pytest.mark.unit
class TestAppComposition:
    """Verify velux2mqtt app composition uses declarative device expansion."""

    def test_app_registers_cover_device_with_name_map(self) -> None:
        """App has a single dict-name @app.device registration for covers.

        Technique: Specification-based — verifies composition root shape.
        """
        # Act
        registrations = [
            registration for registration in app.devices if registration.name == "cover"
        ]

        # Assert
        assert len(registrations) == 1
        registration = registrations[0]
        assert registration.func is cover
        assert registration.name_spec is _cover_map
        assert registration.summary == "Velux cover: open/close/stop control"
