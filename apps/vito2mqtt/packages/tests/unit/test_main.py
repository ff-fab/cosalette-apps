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
from vito2mqtt.devices import COMMAND_GROUPS, SIGNAL_GROUPS
from vito2mqtt.devices.legionella import legionella_device
from vito2mqtt.devices.telemetry import INTERVAL_ATTR
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

    def test_telemetry_handler_count(self) -> None:
        """Exactly one handler per SIGNAL_GROUPS entry must be registered.

        Technique: Specification-based — every group needs a telemetry device.
        """
        from vito2mqtt.main import app

        assert len(app._telemetry) == len(SIGNAL_GROUPS)

    def test_telemetry_names_match_signal_groups(self) -> None:
        """Registered telemetry names must match SIGNAL_GROUPS keys exactly.

        Technique: Cross-reference — composition root must mirror the group registry.
        """
        from vito2mqtt.main import app

        registered = {r.name for r in app._telemetry}
        assert registered == set(SIGNAL_GROUPS)

    def test_telemetry_all_use_optolink_group(self) -> None:
        """All telemetry handlers must use group='optolink'.

        Technique: Specification-based — ADR-007 coalescing group requirement.
        """
        from vito2mqtt.main import app

        for reg in app._telemetry:
            assert reg.group == "optolink", f"{reg.name!r} missing group='optolink'"

    def test_telemetry_intervals_are_deferred(self) -> None:
        """Each telemetry interval must be a deferred callable (setting_ref).

        Intervals must not be resolved at import time — they are read from
        runtime settings via setting_ref(INTERVAL_ATTR[group]).

        Technique: Specification-based — deferred configuration contract.
        """
        from vito2mqtt.main import app

        for reg in app._telemetry:
            assert callable(reg.interval), (
                f"{reg.name!r} interval is not callable: {reg.interval!r}"
            )

    def test_telemetry_interval_attrs_cover_all_groups(self) -> None:
        """INTERVAL_ATTR must have one entry per registered telemetry name.

        Cross-checks that configure_app passes the correct attribute name
        for every group — no group may be silently skipped.

        Technique: Cross-reference — INTERVAL_ATTR keys must equal SIGNAL_GROUPS keys.
        """
        assert set(INTERVAL_ATTR.keys()) == set(SIGNAL_GROUPS.keys())


class TestCommandRegistration:
    """Verify command handlers are registered."""

    def test_command_handler_count(self) -> None:
        """Exactly one handler per COMMAND_GROUPS entry must be registered.

        Technique: Specification-based — every writable group needs a command.
        """
        from vito2mqtt.main import app

        assert len(app._commands) == len(COMMAND_GROUPS)

    def test_command_names_match_command_groups(self) -> None:
        """Registered command names must match COMMAND_GROUPS keys exactly.

        Technique: Cross-reference — composition root must mirror the group registry.
        """
        from vito2mqtt.main import app

        registered = {r.name for r in app._commands}
        assert registered == set(COMMAND_GROUPS)

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

        Technique: Structural — legionella device is in _devices.
        """
        from vito2mqtt.main import app

        device_names = {d.name for d in app._devices}
        assert "legionella" in device_names

    def test_legionella_uses_legionella_device_function(self) -> None:
        """The legionella device must be wired to the legionella_device function.

        Prevents silently registering the wrong callable under the
        'legionella' name.

        Technique: Structural — function identity check.
        """
        from vito2mqtt.main import app

        reg = next(d for d in app._devices if d.name == "legionella")
        assert reg.func is legionella_device


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


class TestTelemetryRetryConfig:
    """Verify retry metadata on every Optolink telemetry registration."""

    def test_retry_count_is_three(self) -> None:
        """All telemetry registrations have retry=3.

        Technique: Specification-based — conservative retry for transient
        serial/communication errors (workspace-89u).
        """
        from vito2mqtt.main import app

        for reg in app._telemetry:
            assert reg.retry == 3, f"{reg.name!r} retry={reg.retry}, expected 3"

    def test_retry_on_includes_connection_error(self) -> None:
        """retry_on includes OptolinkConnectionError for all telemetry.

        Technique: Specification-based — serial open failures are transient.
        """
        from vito2mqtt.errors import OptolinkConnectionError
        from vito2mqtt.main import app

        for reg in app._telemetry:
            assert OptolinkConnectionError in reg.retry_on, (
                f"{reg.name!r} missing OptolinkConnectionError in retry_on"
            )

    def test_retry_on_includes_timeout_error(self) -> None:
        """retry_on includes OptolinkTimeoutError for all telemetry.

        Technique: Specification-based — device non-response is transient.
        """
        from vito2mqtt.errors import OptolinkTimeoutError
        from vito2mqtt.main import app

        for reg in app._telemetry:
            assert OptolinkTimeoutError in reg.retry_on, (
                f"{reg.name!r} missing OptolinkTimeoutError in retry_on"
            )


class TestAppRestartConfig:
    """Verify adapter recovery restart configuration on the App instance."""

    def test_restart_after_failures_is_five(self) -> None:
        """App is configured to restart after 5 consecutive failures.

        Technique: Specification-based — Optolink adapter recovery
        configuration (workspace-ovq).
        """
        from vito2mqtt.main import app

        assert app._restart_after_failures == 5

    def test_max_restarts_is_three(self) -> None:
        """App allows at most 3 restarts before giving up.

        Technique: Specification-based — bounded restart loop prevents
        runaway restart cycles.
        """
        from vito2mqtt.main import app

        assert app._max_restarts == 3
