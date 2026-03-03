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

"""Application configuration via cosalette Settings.

Configuration is loaded from environment variables (prefixed ``VITO2MQTT_``)
and/or ``.env`` files.  MQTT and logging settings are inherited from
:class:`cosalette.Settings`.
"""

from __future__ import annotations

from typing import Literal

from cosalette import Settings
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class Vito2MqttSettings(Settings):
    """Vito2mqtt application settings.

    Inherits ``mqtt`` and ``logging`` nested models from
    :class:`cosalette.Settings`.  Application-specific fields are loaded
    from environment variables with the ``VITO2MQTT_`` prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="VITO2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Optolink serial connection
    serial_port: str
    """Serial device path (e.g. ``/dev/ttyUSB0``). **Required.**"""

    serial_baud_rate: int = 4800
    """Baud rate for the Optolink serial connection."""

    # Device identification
    device_id: str = "vitodens200w"
    """Device identifier used in MQTT topic hierarchy."""

    # Internationalisation
    signal_language: Literal["de", "en"] = "en"
    """Language for signal names (see ADR-006)."""

    # Per-domain polling intervals (seconds) — see ADR-005
    polling_outdoor: float = Field(default=300.0, gt=0)
    """Outdoor sensors polling interval (seconds)."""

    polling_hot_water: float = Field(default=300.0, gt=0)
    """Domestic hot water polling interval (seconds)."""

    polling_burner: float = Field(default=300.0, gt=0)
    """Burner telemetry polling interval (seconds)."""

    polling_heating_radiator: float = Field(default=300.0, gt=0)
    """M1 heating circuit polling interval (seconds)."""

    polling_heating_floor: float = Field(default=300.0, gt=0)
    """M2 floor heating polling interval (seconds)."""

    polling_system: float = Field(default=3600.0, gt=0)
    """System info polling interval (seconds)."""

    polling_diagnosis: float = Field(default=300.0, gt=0)
    """Diagnosis/error polling interval (seconds)."""
