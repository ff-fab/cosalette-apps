"""Unit tests for main.py — wallpanel-control composition root.

Test Techniques Used:
- Specification-based: Verify app is constructed with correct identity (name,
  version, description, settings class)
- Structural: Verify adapter registry contains both ports (WallpanelPort, WolPort)
- Structural: Verify command names are exactly {brightness, screen, power}
- Structural: Verify telemetry name is exactly {status}
- Specification-based: main() delegates to app.run() — verified with monkeypatch
"""

from __future__ import annotations

from unittest.mock import MagicMock

import cosalette
import pytest

from wallpanel_control import __version__
from wallpanel_control.ports import WallpanelPort, WolPort
from wallpanel_control.settings import WallpanelControlSettings


@pytest.mark.unit
class TestAppIdentity:
    """Verify the module-level App instance has correct identity metadata."""

    def test_app_is_cosalette_app(self) -> None:
        """module-level app is a cosalette App instance.

        Technique: Specification-based — composition root creates App.
        """
        from wallpanel_control.main import app

        assert isinstance(app, cosalette.App)

    def test_app_name(self) -> None:
        """App name is wallpanel-control.

        Technique: Specification-based — MQTT topic root matches app name.
        """
        from wallpanel_control.main import app

        assert app._name == "wallpanel-control"

    def test_app_version_matches_package_metadata(self) -> None:
        """App version matches __version__ from package metadata.

        Technique: Specification-based — ensures composition root wires
        __version__, not a hard-coded placeholder.
        """
        from wallpanel_control.main import app

        assert app._version == __version__

    def test_app_settings_class(self) -> None:
        """App uses WallpanelControlSettings.

        Technique: Specification-based — settings class drives env-var parsing
        and DI injection into handlers.
        """
        from wallpanel_control.main import app

        assert app._settings_class is WallpanelControlSettings


@pytest.mark.unit
class TestAdapterRegistry:
    """Verify both ports are registered in the adapter registry."""

    def test_wallpanel_port_registered(self) -> None:
        """WallpanelPort is present in the adapter registry.

        Technique: Structural — adapter wiring from composition root.
        """
        from wallpanel_control.main import app

        assert WallpanelPort in app._adapters

    def test_wol_port_registered(self) -> None:
        """WolPort is present in the adapter registry.

        Technique: Structural — adapter wiring from composition root.
        """
        from wallpanel_control.main import app

        assert WolPort in app._adapters


@pytest.mark.unit
class TestCommandRegistration:
    """Verify command handlers are registered with the correct names."""

    def test_command_names_are_brightness_screen_power(self) -> None:
        """Exactly three commands registered: brightness, screen, power.

        Technique: Structural — command names drive MQTT /set topic suffixes.
        """
        from wallpanel_control.main import app

        registered = {r.name for r in app._commands}
        assert registered == {"brightness", "screen", "power"}


@pytest.mark.unit
class TestTelemetryRegistration:
    """Verify telemetry handlers are registered with the correct names."""

    def test_telemetry_name_is_status(self) -> None:
        """Exactly one telemetry registered: status.

        Technique: Structural — telemetry name drives MQTT /state topic suffix.
        """
        from wallpanel_control.main import app

        registered = {r.name for r in app._telemetry}
        assert registered == {"status"}


@pytest.mark.unit
class TestMainEntryPoint:
    """Verify main() delegates to app.run()."""

    def test_main_calls_app_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """main() calls app.run() exactly once with no arguments.

        Technique: Specification-based — entry-point contract.
        Monkeypatching app.run avoids starting a real event loop.
        """
        from wallpanel_control import main as main_module

        mock_run = MagicMock()
        monkeypatch.setattr(main_module.app, "run", mock_run)

        main_module.main()

        mock_run.assert_called_once_with()
