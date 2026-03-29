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

"""Solar position computation using the astral library."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import azimuth, elevation, sun


@dataclass(frozen=True, slots=True)
class SunPosition:
    """Computed solar position and daily sun event data."""

    azimuth: float
    """0-360 degrees clockwise from north."""

    elevation: float
    """-90 to +90 degrees above/below horizon."""

    sunrise_azimuth: float | None
    """Azimuth at sunrise, or None during polar day/night."""

    sunset_azimuth: float | None
    """Azimuth at sunset, or None during polar day/night."""

    sunrise_time: dt.datetime | None
    """Time of sunrise, or None during polar day/night."""

    sunset_time: dt.datetime | None
    """Time of sunset, or None during polar day/night."""

    hourly_azimuths: tuple[float, ...]
    """24 azimuth entries for hours 00:00-23:00."""

    is_daylight: bool
    """True when elevation > 0."""


def compute_solar_position(
    latitude: float,
    longitude: float,
    timezone: str,
    at: dt.datetime,
) -> SunPosition:
    """Compute the solar position for a given location and time.

    Args:
        latitude: Degrees north (negative for south).
        longitude: Degrees east (negative for west).
        timezone: IANA timezone string (e.g. "Europe/Berlin").
        at: The moment to compute for. If naive, interpreted in *timezone*.

    Returns:
        A frozen SunPosition with current angles, rise/set data, and hourly azimuths.
    """
    observer = Observer(latitude=latitude, longitude=longitude)
    tz = ZoneInfo(timezone)

    if at.tzinfo is None:
        at_aware = at.replace(tzinfo=tz)
    else:
        at_aware = at

    current_azimuth = azimuth(observer, at_aware)
    current_elevation = elevation(observer, at_aware)

    # Sunrise / sunset — may not exist in polar regions.
    sunrise_dt: dt.datetime | None = None
    sunset_dt: dt.datetime | None = None
    try:
        sun_data = sun(observer, date=at_aware.date(), tzinfo=tz)
        sunrise_dt = sun_data["sunrise"]
        sunset_dt = sun_data["sunset"]
    except ValueError:
        # astral raises ValueError when the sun never rises or sets (polar regions).
        pass

    sunrise_az = azimuth(observer, sunrise_dt) if sunrise_dt else None
    sunset_az = azimuth(observer, sunset_dt) if sunset_dt else None

    # Hourly azimuths for the same calendar day.
    base_date = at_aware.date()
    hourly = tuple(
        azimuth(
            observer,
            dt.datetime(base_date.year, base_date.month, base_date.day, h, tzinfo=tz),
        )
        for h in range(24)
    )

    return SunPosition(
        azimuth=current_azimuth,
        elevation=current_elevation,
        sunrise_azimuth=sunrise_az,
        sunset_azimuth=sunset_az,
        sunrise_time=sunrise_dt,
        sunset_time=sunset_dt,
        hourly_azimuths=hourly,
        is_daylight=current_elevation > 0,
    )
