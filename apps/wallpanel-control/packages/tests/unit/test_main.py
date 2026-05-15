"""Unit tests for main.py — wallpanel-control composition root.

Test Techniques Used:
- Specification-based: Verify app is constructed with correct identity (name,
  version, description, settings class)
- Structural: Verify adapter registry contains both ports (WallpanelPort, WolPort)
- Structural: Verify no devices are registered
- Structural: Verify commands (command/state) are exactly {display, system/action}
- Structural: Verify no telemetry is registered
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

    # Accesses cosalette.App private attributes; no public introspection API
    # exists in cosalette 0.4 for these composition-root assertions.

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

    # Accesses cosalette.App private attributes; no public introspection API
    # exists in cosalette 0.4 for these composition-root assertions.

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
class TestDeviceRegistration:
    """Verify no device handlers are registered (display is now a command)."""

    # Accesses cosalette.App private attributes; no public introspection API
    # exists in cosalette 0.4 for these composition-root assertions.

    def test_no_devices_registered(self) -> None:
        """No devices registered; display is handled as a command.

        Technique: Structural — display/set is served by a typed command handler.
        """
        from wallpanel_control.main import app

        assert len(app._devices) == 0


@pytest.mark.unit
class TestCommandRegistration:
    """Verify command handlers are registered with the correct names."""

    # Accesses cosalette.App private attributes; no public introspection API
    # exists in cosalette 0.4 for these composition-root assertions.

    def test_command_names_are_display_and_system_action(self) -> None:
        """Exactly two commands registered: display and system/action.

        Technique: Structural — command names drive MQTT /set topic suffixes.
        display → wallpanel-control/display/set.
        system/action → wallpanel-control/system/action/set.
        """
        from wallpanel_control.main import app

        registered = {r.name for r in app._commands}
        assert registered == {"display", "system/action"}


@pytest.mark.unit
class TestTelemetryRegistration:
    """Verify no standalone telemetry handlers are registered."""

    # Display state is published by the display command handler, not as a
    # separate telemetry registration.

    def test_no_telemetry_registered(self) -> None:
        """No standalone telemetry registered; display state is published on command.

        Technique: Structural — display state is published after accepted commands,
        not on a polling timer.
        """
        from wallpanel_control.main import app

        assert len(app._telemetry) == 0


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
