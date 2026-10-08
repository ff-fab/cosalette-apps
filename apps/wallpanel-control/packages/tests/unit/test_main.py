"""Unit tests for main.py — wallpanel-control composition root.

Test Techniques Used:
- Specification-based: Verify app is constructed with correct identity (name,
  version, description, settings class)
- Structural: Verify adapter registry contains both ports (WallpanelPort, WolPort)
- Structural: Verify no devices are registered
- Structural: Verify commands (command/state) are exactly {display, system/action}
- Structural: Verify no telemetry is registered
- Specification-based: main() delegates to app.run() — verified with monkeypatch
- Specification-based: stale, redaction and Docker probe policy (ADR-011)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import cosalette
import pytest

from wallpanel_control import __version__
from wallpanel_control.ports import WallpanelPort, WolPort
from wallpanel_control.settings import WallpanelControlSettings

_APP_DIR = Path(__file__).resolve().parents[3]


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

        assert app.name == "wallpanel-control"

    def test_app_version_matches_package_metadata(self) -> None:
        """App version matches __version__ from package metadata.

        Technique: Specification-based — ensures composition root wires
        __version__, not a hard-coded placeholder.
        """
        from wallpanel_control.main import app

        assert app.version == __version__

    def test_app_settings_class(self) -> None:
        """App uses WallpanelControlSettings.

        Technique: Specification-based — settings class drives env-var parsing
        and DI injection into handlers.
        """
        from wallpanel_control.main import app

        assert app.settings_class is WallpanelControlSettings


@pytest.mark.unit
class TestAdapterRegistry:
    """Verify both ports are registered in the adapter registry."""

    def test_wallpanel_port_registered(self) -> None:
        """WallpanelPort is present in the adapter registry.

        Technique: Structural — adapter wiring from composition root.
        """
        from wallpanel_control.main import app

        assert WallpanelPort in app.adapters

    def test_wol_port_registered(self) -> None:
        """WolPort is present in the adapter registry.

        Technique: Structural — adapter wiring from composition root.
        """
        from wallpanel_control.main import app

        assert WolPort in app.adapters


@pytest.mark.unit
class TestDeviceRegistration:
    """Verify only the startup restore device is registered."""

    def test_only_restore_device_registered(self) -> None:
        """Display is a command; the sole device re-publishes saved answers.

        Technique: Structural — display/set is served by a typed command handler.
        """
        from wallpanel_control.main import app

        assert [r.name for r in app.devices] == ["restore_answers"]


@pytest.mark.unit
class TestCommandRegistration:
    """Verify command handlers are registered with the correct names."""

    def test_command_names_are_display_and_system_action(self) -> None:
        """Exactly two commands registered: display and system/action.

        Technique: Structural — command names drive MQTT /set topic suffixes.
        display → wallpanel-control/display/set.
        system/action → wallpanel-control/system/action/set.
        """
        from wallpanel_control.main import app

        registered = {r.name for r in app.commands}
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

        assert len(app.telemetry_registrations) == 0


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


@pytest.mark.unit
class TestStorePolicy:
    """Verify the app's store policy under runtime discovery adoption."""

    def test_store_defaults_on_for_discovery_snapshot(self) -> None:
        """App keeps the framework-default store (discovery snapshot backing).

        Adopting ``app.discovery()`` (monorepo ADR-004) needs a Store to
        persist the discovery-topic snapshot so entities removed in a future
        release are reconciled (cleared) on the next startup. The registry is
        still static (ADR-049), so the store holds only that snapshot.

        Technique: Specification-based — the composition root omits ``store=``
        so cosalette auto-resolves the default JsonFileStore. ``app.store`` is
        the public store accessor.
        """
        from wallpanel_control.main import app

        assert app.store is not None

    def test_app_is_static(self) -> None:
        """App is classified static, so cosalette skips the ephemeral warning.

        Technique: Specification-based — command-only handlers with static names
        and no @app.on_configure are static under cosalette >=0.5.2 (ADR-049).
        app.has_dynamic_entities is the public dynamic-entity predicate.
        """
        from wallpanel_control.main import app

        assert app.has_dynamic_entities is False


@pytest.mark.unit
class TestCommandUnavailableOnConfig:
    """Verify unavailable_on metadata on command registrations."""

    def test_display_command_has_unavailable_on(self) -> None:
        """display command declares unavailable_on=(WallpanelUnreachableError,).

        Technique: Specification-based — SSH unreachability must surface as
        device unavailability rather than a silent error when the wallpanel
        is off or hibernating.
        """
        from wallpanel_control.main import app
        from wallpanel_control.ports import WallpanelUnreachableError

        reg = next(r for r in app.commands if r.name == "display")
        assert reg.unavailable_on == (WallpanelUnreachableError,)

    def test_system_action_command_has_unavailable_on(self) -> None:
        """system/action command declares unavailable_on=(WallpanelUnreachableError,).

        Technique: Specification-based — SSH unreachability during system
        power commands must surface as device unavailability.
        """
        from wallpanel_control.main import app
        from wallpanel_control.ports import WallpanelUnreachableError

        reg = next(r for r in app.commands if "action" in r.name)
        assert reg.unavailable_on == (WallpanelUnreachableError,)


@pytest.mark.unit
class TestHealthPolicy:
    """Verify the production app's stale, redaction and Docker probe policy."""

    def test_app_has_no_stale_exit_or_restart(self) -> None:
        """The app sets neither exit_after_stale nor restart_on_stale.

        Technique: Specification-based — display and system are command-only
        devices with no telemetry or streams, so nothing can turn stale and
        both options would be inert.
        """
        from wallpanel_control.main import app

        assert app._streams == []
        assert app._exit_after_stale is None
        assert app._restart_on_stale is False

    def test_app_sets_no_redactor(self) -> None:
        """No App(redact=): no secret ever reaches log or error text.

        Technique: Specification-based — the SSH key is passed as a path and
        never read into text, and the MQTT password is a SecretStr.
        """
        from wallpanel_control.main import app

        assert app._redactor is None

    def test_ssh_adapter_has_no_health_check(self) -> None:
        """A powered-off panel is normal, so SSH reachability is no health signal.

        Technique: Specification-based — a health_check would mark both
        devices offline and spend the restart budget whenever the panel sleeps,
        while wake-on-LAN must keep working exactly then.
        """
        from wallpanel_control.adapters.ssh_adapter import SshWallpanel

        assert not hasattr(SshWallpanel, "health_check")

    def test_docker_health_probe_checks_file_freshness_only(self) -> None:
        """The probe ignores per-device status.

        Technique: Specification-based — monorepo ADR-011 sets --fail-on ""
        for apps with several independent devices.
        """
        dockerfile = (_APP_DIR / "Dockerfile").read_text(encoding="utf-8")
        match = re.search(r"(?m)^\s*CMD\s+(\[.*\])\s*$", dockerfile)

        assert match is not None
        assert json.loads(match.group(1)) == ["cosalette-health", "--fail-on", ""]
