"""Unit tests for settings.py — WallpanelControlSettings validation.

Test Techniques Used:
- Specification-based Testing: Default values match documented configuration
- Boundary Value Analysis: Numeric field constraints (ge, gt, le)
- Error Guessing: Missing required fields raise ValidationError
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.fixtures.config import make_wallpanel_control_settings


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.unit
class TestWallpanelControlSettingsDefaults:
    """Verify default values match documented configuration.

    Technique: Specification-based Testing — defaults match beads task description.
    """

    def test_default_ssh_host(self) -> None:
        """Default SSH host is wallpanel.lan."""
        settings = make_wallpanel_control_settings()
        assert settings.ssh_host == "wallpanel.lan"

    def test_default_ssh_user(self) -> None:
        """Default SSH user is jl4."""
        settings = make_wallpanel_control_settings()
        assert settings.ssh_user == "jl4"

    def test_default_ssh_key_path(self) -> None:
        """Default SSH key path is ~/.ssh/wallpanel."""
        settings = make_wallpanel_control_settings()
        assert settings.ssh_key_path == "~/.ssh/wallpanel"

    def test_default_ssh_port(self) -> None:
        """Default SSH port is 22."""
        settings = make_wallpanel_control_settings()
        assert settings.ssh_port == 22

    def test_default_ssh_timeout(self) -> None:
        """Default SSH timeout is 5.0 seconds."""
        settings = make_wallpanel_control_settings()
        assert settings.ssh_timeout == 5.0

    def test_default_backlight_path(self) -> None:
        """Default backlight path is the Intel backlight sysfs entry."""
        settings = make_wallpanel_control_settings()
        assert (
            settings.backlight_path == "/sys/class/backlight/intel_backlight/brightness"
        )

    def test_default_poll_interval(self) -> None:
        """Default poll interval is 180 seconds (3 minutes)."""
        settings = make_wallpanel_control_settings()
        assert settings.poll_interval == 180.0

    def test_default_wol_broadcast(self) -> None:
        """Default WoL broadcast is 255.255.255.255."""
        settings = make_wallpanel_control_settings()
        assert settings.wol_broadcast == "255.255.255.255"

    def test_wol_mac_uses_provided_value(self) -> None:
        """wol_mac is required and uses the provided value."""
        settings = make_wallpanel_control_settings(wol_mac="11:22:33:44:55:66")
        assert settings.wol_mac == "11:22:33:44:55:66"


@pytest.mark.unit
class TestWallpanelControlSettingsRequired:
    """Verify required field validation.

    Technique: Error Guessing — missing required fields raise ValidationError.
    """

    def test_missing_wol_mac_raises(self) -> None:
        """wol_mac is required — omitting it raises ValidationError."""
        with pytest.raises(ValidationError):
            make_wallpanel_control_settings(wol_mac=None)


@pytest.mark.unit
class TestWallpanelControlSettingsValidation:
    """Verify field validation constraints.

    Technique: Boundary Value Analysis — test at and beyond boundaries.
    """

    def test_ssh_port_rejects_zero(self) -> None:
        """SSH port must be >= 1."""
        with pytest.raises(ValidationError):
            make_wallpanel_control_settings(ssh_port=0)

    def test_ssh_port_accepts_one(self) -> None:
        """SSH port 1 is valid (minimum boundary)."""
        settings = make_wallpanel_control_settings(ssh_port=1)
        assert settings.ssh_port == 1

    def test_ssh_port_accepts_65535(self) -> None:
        """SSH port 65535 is valid (maximum boundary)."""
        settings = make_wallpanel_control_settings(ssh_port=65535)
        assert settings.ssh_port == 65535

    def test_ssh_port_rejects_65536(self) -> None:
        """SSH port must be <= 65535."""
        with pytest.raises(ValidationError):
            make_wallpanel_control_settings(ssh_port=65536)

    def test_ssh_timeout_rejects_zero(self) -> None:
        """SSH timeout must be > 0."""
        with pytest.raises(ValidationError):
            make_wallpanel_control_settings(ssh_timeout=0)

    def test_ssh_timeout_rejects_negative(self) -> None:
        """SSH timeout must be > 0."""
        with pytest.raises(ValidationError):
            make_wallpanel_control_settings(ssh_timeout=-1.0)

    def test_ssh_timeout_accepts_small_positive(self) -> None:
        """Very small SSH timeout is valid."""
        settings = make_wallpanel_control_settings(ssh_timeout=0.001)
        assert settings.ssh_timeout == 0.001

    def test_poll_interval_rejects_zero(self) -> None:
        """Poll interval must be > 0."""
        with pytest.raises(ValidationError):
            make_wallpanel_control_settings(poll_interval=0)

    def test_poll_interval_rejects_negative(self) -> None:
        """Poll interval must be > 0."""
        with pytest.raises(ValidationError):
            make_wallpanel_control_settings(poll_interval=-1.0)

    def test_poll_interval_accepts_small_positive(self) -> None:
        """Very small poll interval is valid."""
        settings = make_wallpanel_control_settings(poll_interval=0.001)
        assert settings.poll_interval == 0.001
