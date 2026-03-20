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

"""Integration tests for command dispatch via MQTT.

Exercises the full command path: MQTT inbound → TopicRouter → command
handler → FakeOptolinkAdapter.writes, using the real application wiring
with in-memory test doubles.

Test Techniques Used
--------------------
- **State-based testing**: observe side-effects in ``fake_adapter.writes``
  rather than mocking internal collaborators, so the entire dispatch stack
  is exercised (ADR-004, ADR-002).
- **Specification-based**: command routing follows the topic layout defined
  in ADR-002: ``{prefix}/{group_name}/set``.
- **Error guessing**: invalid JSON, unknown signal names, and non-dict
  payloads are delivered to verify graceful error handling without crashing
  the application.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient

from vito2mqtt.adapters.fake import FakeOptolinkAdapter
from vito2mqtt.config import Vito2MqttSettings

from .conftest import TOPIC_PREFIX

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_with_commands(
    app: App,
    mock_mqtt: MockMqttClient,
    test_settings: Vito2MqttSettings,
    commands: list[tuple[str, str]],
    *,
    startup_wait: float = 0.15,
    per_command_wait: float = 0.1,
) -> None:
    """Start the app, deliver commands, then shut down cleanly.

    The app is given ``startup_wait`` seconds to start up and wire the
    TopicRouter before the first command is delivered.  Each command is
    delivered sequentially with ``per_command_wait`` seconds between them
    to allow the handler coroutine to complete.

    Args:
        app: Fully-wired App instance.
        mock_mqtt: MockMqttClient to use for MQTT I/O.
        test_settings: Settings with short polling intervals.
        commands: Ordered list of ``(topic, payload)`` pairs to deliver.
        startup_wait: Seconds to wait after task creation before delivering.
        per_command_wait: Seconds to wait after each delivered command.
    """
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        app._run_async(
            mqtt=mock_mqtt,
            settings=test_settings,
            shutdown_event=shutdown_event,
        )
    )
    await asyncio.sleep(startup_wait)
    for topic, payload in commands:
        await mock_mqtt.deliver(topic, payload)
        await asyncio.sleep(per_command_wait)
    shutdown_event.set()
    await task


def _has_error_message(mock_mqtt: MockMqttClient, group: str = "hot_water") -> bool:
    """Return True if an error was published on the global or per-group topic."""
    error_topics = [
        f"{TOPIC_PREFIX}/error",
        f"{TOPIC_PREFIX}/{group}/error",
    ]
    published_topics = {topic for topic, *_ in mock_mqtt.published}
    return any(t in published_topics for t in error_topics)


# ---------------------------------------------------------------------------
# TestCommandDispatch
# ---------------------------------------------------------------------------


class TestCommandDispatch:
    """Happy-path command routing tests.

    Verifies that valid MQTT command payloads are routed to the correct
    handler and that the resulting write reaches the adapter (ADR-004).
    """

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_hot_water_setpoint_write_dispatched(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
        fake_adapter: FakeOptolinkAdapter,
    ) -> None:
        """A setpoint command is written to the adapter.

        Arrange: fresh app wired with FakeOptolinkAdapter (default IUNON=42).
        Act: deliver ``{"hot_water_setpoint": 60}`` to the hot_water set topic.
        Assert: ``fake_adapter.writes["hot_water_setpoint"]`` equals 60.

        The payload value 60 differs from the FakeOptolinkAdapter default (42),
        so the read-before-write guard does NOT suppress the write.
        """
        await _run_with_commands(
            integration_app,
            mock_mqtt,
            test_settings,
            [(f"{TOPIC_PREFIX}/hot_water/set", '{"hot_water_setpoint": 60}')],
        )

        assert "hot_water_setpoint" in fake_adapter.writes, (
            f"Expected write for hot_water_setpoint; writes: {fake_adapter.writes}"
        )
        assert fake_adapter.writes["hot_water_setpoint"] == 60

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_write_skipped_when_value_unchanged(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
        fake_adapter: FakeOptolinkAdapter,
    ) -> None:
        """The read-before-write guard suppresses a write when value is unchanged.

        Arrange: FakeOptolinkAdapter returns 42 for IUNON signals (the default).
        Act: deliver ``{"hot_water_setpoint": 42}`` — the same value as the
             current reading.
        Assert: ``fake_adapter.writes`` does NOT contain ``hot_water_setpoint``.

        This tests that the handler's read-before-write optimisation (PEP:
        "avoid unnecessary bus traffic") is effective: if the boiler is already
        at the desired setpoint, no write command is issued over the Optolink.
        """
        await _run_with_commands(
            integration_app,
            mock_mqtt,
            test_settings,
            [(f"{TOPIC_PREFIX}/hot_water/set", '{"hot_water_setpoint": 42}')],
        )

        assert "hot_water_setpoint" not in fake_adapter.writes, (
            "Write should have been suppressed because value matches current; "
            f"writes: {fake_adapter.writes}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_force_flag_bypasses_read_before_write(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
        fake_adapter: FakeOptolinkAdapter,
    ) -> None:
        """The ``__force`` flag causes a write even when value is unchanged.

        Arrange: FakeOptolinkAdapter default for IUNON is 42.
        Act: deliver ``{"hot_water_setpoint": 42, "__force": true}``.
        Assert: ``fake_adapter.writes["hot_water_setpoint"]`` equals 42.

        The ``__force`` flag is an escape hatch for cases where the boiler
        state may have drifted without the bridge knowing — it bypasses the
        read-before-write comparison entirely.
        """
        await _run_with_commands(
            integration_app,
            mock_mqtt,
            test_settings,
            [
                (
                    f"{TOPIC_PREFIX}/hot_water/set",
                    '{"hot_water_setpoint": 42, "__force": true}',
                )
            ],
        )

        assert "hot_water_setpoint" in fake_adapter.writes, (
            "Expected forced write for hot_water_setpoint; "
            f"writes: {fake_adapter.writes}"
        )
        assert fake_adapter.writes["hot_water_setpoint"] == 42

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_heating_radiator_command_dispatched(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
        fake_adapter: FakeOptolinkAdapter,
    ) -> None:
        """A command on the heating_radiator group is routed correctly.

        Verifies that topic routing is not hard-coded to a single group:
        ADR-002 requires each device group to have its own ``/set`` topic.

        Arrange: FakeOptolinkAdapter IS10 default is 20.5.
        Act: deliver ``{"heating_curve_gradient_m1": 1.4}`` to
             ``vito2mqtt/heating_radiator/set``.
        Assert: ``heating_curve_gradient_m1`` appears in ``fake_adapter.writes``.

        The value 1.4 ≠ 20.5 (default), so the read-before-write guard
        does not suppress the write.
        """
        await _run_with_commands(
            integration_app,
            mock_mqtt,
            test_settings,
            [
                (
                    f"{TOPIC_PREFIX}/heating_radiator/set",
                    '{"heating_curve_gradient_m1": 1.4}',
                )
            ],
        )

        assert "heating_curve_gradient_m1" in fake_adapter.writes, (
            "Expected write for heating_curve_gradient_m1; "
            f"writes: {fake_adapter.writes}"
        )


# ---------------------------------------------------------------------------
# TestCommandErrors
# ---------------------------------------------------------------------------


class TestCommandErrors:
    """Verify that malformed commands produce error messages without crashing.

    These tests exercise the error-guessing technique: common failure modes
    for command handlers include invalid JSON, unrecognised signal names, and
    payloads of the wrong type.  The app must publish an error message and
    remain running for subsequent commands.
    """

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_invalid_json_publishes_error(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
        fake_adapter: FakeOptolinkAdapter,
    ) -> None:
        """A non-parseable payload causes an error message to be published.

        Arrange: fresh app.
        Act: deliver ``"not-valid-json{{"`` to ``vito2mqtt/hot_water/set``.
        Assert: at least one message on ``vito2mqtt/error`` or
                ``vito2mqtt/hot_water/error`` is present.
        """
        await _run_with_commands(
            integration_app,
            mock_mqtt,
            test_settings,
            [(f"{TOPIC_PREFIX}/hot_water/set", "not-valid-json{{")],
        )

        assert _has_error_message(mock_mqtt, "hot_water"), (
            "Expected an error message after invalid JSON; "
            f"published topics: {[t for t, *_ in mock_mqtt.published]}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_unknown_signal_in_payload_publishes_error(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
        fake_adapter: FakeOptolinkAdapter,
    ) -> None:
        """A payload with an unrecognised signal name causes an error message.

        Arrange: fresh app.
        Act: deliver ``{"nonexistent_signal": 99}`` to ``vito2mqtt/hot_water/set``.
        Assert: an error message is published on the error or group-error topic.

        This tests the registry-lookup branch of the command handler: if the
        signal name does not exist in ``COMMANDS``, an ``InvalidSignalError``
        is raised and must be reported over MQTT rather than propagated.
        """
        await _run_with_commands(
            integration_app,
            mock_mqtt,
            test_settings,
            [(f"{TOPIC_PREFIX}/hot_water/set", '{"nonexistent_signal": 99}')],
        )

        assert _has_error_message(mock_mqtt, "hot_water"), (
            "Expected an error message after unknown signal; "
            f"published topics: {[t for t, *_ in mock_mqtt.published]}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_non_dict_json_publishes_error(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
        fake_adapter: FakeOptolinkAdapter,
    ) -> None:
        """A JSON payload that is not a dict causes an error message.

        Arrange: fresh app.
        Act: deliver ``"[1, 2, 3]"`` to ``vito2mqtt/hot_water/set``.
        Assert: an error message is published and no writes occur.

        This covers the edge case where the payload is valid JSON but
        not the expected ``dict[str, Any]`` mapping — the handler must
        reject it gracefully rather than raising ``AttributeError``.
        """
        await _run_with_commands(
            integration_app,
            mock_mqtt,
            test_settings,
            [(f"{TOPIC_PREFIX}/hot_water/set", "[1, 2, 3]")],
        )

        assert _has_error_message(mock_mqtt, "hot_water"), (
            "Expected an error for non-dict JSON payload; "
            f"published topics: {[t for t, *_ in mock_mqtt.published]}"
        )
        assert not fake_adapter.writes, (
            "No writes should occur for a non-dict payload; "
            f"writes: {fake_adapter.writes}"
        )


# ---------------------------------------------------------------------------
# TestCommandIsolation
# ---------------------------------------------------------------------------


class TestCommandIsolation:
    """Verify that command errors do not crash or stall the application.

    A single bad command must not prevent subsequent valid commands from
    being processed — the error path must be isolated from the happy path.
    """

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_command_error_does_not_crash_app(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
        fake_adapter: FakeOptolinkAdapter,
    ) -> None:
        """The app processes a valid command after a preceding bad command.

        Arrange: fresh app wired with FakeOptolinkAdapter.
        Act: deliver an invalid payload followed by a valid command.
        Assert: the valid command's write lands in ``fake_adapter.writes``,
                proving the app continued running after the first error.

        This is the Single Responsibility principle in action: error
        handling in one command handler must not leak into the event loop
        and affect other handlers (Open/Closed from SOLID).
        """
        await _run_with_commands(
            integration_app,
            mock_mqtt,
            test_settings,
            [
                # Bad command first — must not crash the app
                (f"{TOPIC_PREFIX}/hot_water/set", "not-valid-json{{"),
                # Valid command second — must still be processed
                (f"{TOPIC_PREFIX}/hot_water/set", '{"hot_water_setpoint": 55}'),
            ],
        )

        assert "hot_water_setpoint" in fake_adapter.writes, (
            "Valid command after an error should still be processed; "
            f"writes: {fake_adapter.writes}"
        )
        assert fake_adapter.writes["hot_water_setpoint"] == 55
