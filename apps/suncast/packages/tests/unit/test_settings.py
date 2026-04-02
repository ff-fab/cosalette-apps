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

"""Unit tests for SuncastSettings.

Test Techniques Used:
- Specification-based: defaults match documented specification
- Boundary Value Analysis: latitude/longitude/port range limits
- Error Guessing: missing required fields, zero/negative poll_interval
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from suncast.settings import SuncastSettings


def _make_settings(**overrides: object) -> SuncastSettings:
    """Create settings with required fields filled in."""
    defaults: dict[str, object] = {
        "latitude": 50.0,
        "longitude": 8.0,
        "timezone": "Europe/Berlin",
    }
    defaults.update(overrides)
    return SuncastSettings(**defaults)  # type: ignore[arg-type]


@pytest.mark.unit
class TestDefaults:
    """Default values match the specification."""

    def test_geometry_file(self) -> None:
        s = _make_settings()
        assert s.geometry_file == Path("geometry.yaml")

    def test_poll_interval(self) -> None:
        s = _make_settings()
        assert s.poll_interval == 360.0

    def test_rendering_colors(self) -> None:
        s = _make_settings()
        assert s.primary_color == "#614c1f"
        assert s.secondary_color == "#b38c3a"
        assert s.light_color == "#f1b023"
        assert s.shadow_color == "#0A0A0A"
        assert s.stroke_width == 1.0

    def test_output_defaults(self) -> None:
        s = _make_settings()
        assert s.output_path == Path("/output")
        assert s.png_enabled is False
        assert s.png_width == 800
        assert s.png_height == 800

    def test_http_defaults(self) -> None:
        s = _make_settings()
        assert s.http_enabled is False
        assert s.http_host == "0.0.0.0"  # noqa: S104
        assert s.http_port == 8080


@pytest.mark.unit
class TestRequiredFields:
    """Required fields raise validation error when missing."""

    def test_missing_latitude(self) -> None:
        with pytest.raises(ValidationError, match="latitude"):
            SuncastSettings(longitude=8.0, timezone="Europe/Berlin")  # type: ignore[call-arg]

    def test_missing_longitude(self) -> None:
        with pytest.raises(ValidationError, match="longitude"):
            SuncastSettings(latitude=50.0, timezone="Europe/Berlin")  # type: ignore[call-arg]

    def test_missing_timezone(self) -> None:
        with pytest.raises(ValidationError, match="timezone"):
            SuncastSettings(latitude=50.0, longitude=8.0)  # type: ignore[call-arg]


@pytest.mark.unit
class TestCustomValues:
    """Custom values override defaults."""

    def test_location(self) -> None:
        s = _make_settings(latitude=-33.8, longitude=151.2, timezone="Australia/Sydney")
        assert s.latitude == -33.8
        assert s.longitude == 151.2
        assert s.timezone == "Australia/Sydney"

    def test_rendering_overrides(self) -> None:
        s = _make_settings(primary_color="#000", stroke_width=2.5)
        assert s.primary_color == "#000"
        assert s.stroke_width == 2.5

    def test_output_path_none_disables(self) -> None:
        s = _make_settings(output_path=None)
        assert s.output_path is None

    def test_http_custom(self) -> None:
        s = _make_settings(http_enabled=True, http_port=9090)
        assert s.http_enabled is True
        assert s.http_port == 9090


@pytest.mark.unit
class TestValidation:
    """Field constraints are enforced."""

    def test_latitude_out_of_range(self) -> None:
        with pytest.raises(ValidationError, match="latitude"):
            _make_settings(latitude=91.0)

    def test_longitude_out_of_range(self) -> None:
        with pytest.raises(ValidationError, match="longitude"):
            _make_settings(longitude=181.0)

    def test_poll_interval_not_positive(self) -> None:
        with pytest.raises(ValidationError, match="poll_interval"):
            _make_settings(poll_interval=0)

    def test_png_width_not_positive(self) -> None:
        with pytest.raises(ValidationError, match="png_width"):
            _make_settings(png_width=0)

    def test_http_port_out_of_range(self) -> None:
        with pytest.raises(ValidationError, match="http_port"):
            _make_settings(http_port=70000)
