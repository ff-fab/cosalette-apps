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

"""Unit tests for main.py — Application composition root.

Test Techniques Used:
- Specification-based: Verify app is constructed with correct settings
- Structural: Verify adapter, telemetry, and command registration
- Import: Verify cli entry point is importable
"""

from __future__ import annotations

from cosalette import App

from vito2mqtt import __version__
from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.ports import OptolinkPort


class TestAppConstruction:
    """Verify the app module-level App instance is configured correctly."""

    def test_app_is_app_instance(self) -> None:
        """The module-level app must be a cosalette App.

        Technique: Specification-based — composition root creates App.
        """
        from vito2mqtt.main import app

        assert isinstance(app, App)

    def test_app_name(self) -> None:
        """App name must be 'vito2mqtt'.

        Technique: Specification-based.
        """
        from vito2mqtt.main import app

        assert app._name == "vito2mqtt"

    def test_app_version(self) -> None:
        """App version must match _version.__version__.

        Technique: Cross-reference.
        """
        from vito2mqtt.main import app

        assert app._version == __version__

    def test_app_settings_type(self) -> None:
        """App must use Vito2MqttSettings as its settings class.

        Technique: Specification-based.
        """
        from vito2mqtt.main import app

        assert app._settings_class is Vito2MqttSettings


class TestAdapterRegistration:
    """Verify adapter wiring in the composition root."""

    def test_optolink_port_registered(self) -> None:
        """OptolinkPort must be in the adapter registry.

        Technique: Structural — verify adapter mapping.
        """
        from vito2mqtt.main import app

        assert OptolinkPort in app._adapters


class TestTelemetryRegistration:
    """Verify telemetry handlers are registered."""

    def test_telemetry_handlers_registered(self) -> None:
        """At least one telemetry handler must be registered.

        Technique: Structural — register_telemetry populates _telemetry.
        """
        from vito2mqtt.main import app

        assert len(app._telemetry) > 0


class TestCommandRegistration:
    """Verify command handlers are registered."""

    def test_command_handlers_registered(self) -> None:
        """At least one command handler must be registered.

        Technique: Structural — register_commands populates _commands.
        """
        from vito2mqtt.main import app

        assert len(app._commands) > 0

    def test_command_names_subset_of_telemetry_names(self) -> None:
        """Command group names must be a subset of telemetry group names.

        ADR-002 requires ``/{group}/state`` and ``/{group}/set`` to share
        the same namespace.  This is only true when every command
        registration name also exists as a telemetry registration name.

        Technique: Specification-based — ADR-002 regression guard.
        """
        from vito2mqtt.main import app

        telemetry_names = {r.name for r in app._telemetry}
        command_names = {r.name for r in app._commands}
        assert command_names <= telemetry_names


class TestDeviceRegistration:
    """Verify device handlers are registered."""

    def test_legionella_device_registered(self) -> None:
        """The legionella device must be registered.

        Technique: Structural — register_legionella populates _devices.
        """
        from vito2mqtt.main import app

        device_names = {d.name for d in app._devices}
        assert "legionella" in device_names


class TestStoreConfiguration:
    """Verify store is configured."""

    def test_app_has_store(self) -> None:
        """The app must have a store configured for device persistence.

        Technique: Specification-based — legionella device requires DeviceStore.
        """
        from vito2mqtt.main import app

        assert app._store is not None

    def test_store_is_json_file_store(self) -> None:
        """The store must be a JsonFileStore instance.

        Technique: Specification-based — verifies the store backend type.
        """
        from cosalette import JsonFileStore

        from vito2mqtt.main import app

        assert isinstance(app._store, JsonFileStore)


class TestCliEntryPoint:
    """Verify the CLI entry point is importable and callable."""

    def test_cli_is_callable(self) -> None:
        """The cli object must be callable (bound method).

        Technique: Specification-based — pyproject.toml points here.
        """
        from vito2mqtt.main import cli

        assert callable(cli)


class TestDunderMain:
    """Verify __main__.py module is importable."""

    def test_dunder_main_importable(self) -> None:
        """__main__.py must be importable without executing the CLI.

        Technique: Structural — python -m vito2mqtt support.
        """
        import vito2mqtt.__main__  # noqa: F401
