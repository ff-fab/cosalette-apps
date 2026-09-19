"""Unit tests for main.py — _bulb_map name-to-config dispatch function.

Test Techniques Used:
- Specification-based: dict key is the bulb name, value is the BulbConfig
- Error Guessing: wrong settings type raises TypeError with the exact message
- Boundary Value Analysis: empty bulbs list returns empty dict
"""

from __future__ import annotations

import pytest
from cosalette import App, EntityNotifier

from tests.fixtures.doubles import FakeDeviceContext, RecordingNotifier
from tests.fixtures.settings import build_settings
from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.errors import (
    WizIdentityError,
    WizTimeoutError,
    WizUnsupportedCommandError,
)
from wiz2mqtt.main import (
    _bulb_map,
    add_power_signal_inbounds,
    bulb_set,
    power_signal,
)
from wiz2mqtt.models import BulbSetCommand
from wiz2mqtt.settings import BulbConfig, Wiz2MqttSettings
from wiz2mqtt.state import SharedState


def _settings_with_bulbs(*bulbs: dict[str, object]) -> Wiz2MqttSettings:
    return build_settings(bulbs)


class TestBulbMap:
    """_bulb_map maps bulb names to their BulbConfig for command dispatch."""

    def test_bulb_map_maps_name_to_config(self) -> None:
        """Each bulb name becomes a key mapping to its BulbConfig.

        Technique: Specification-based — dict key is name, value is config.
        """
        settings = _settings_with_bulbs({"name": "office", "ip": "10.0.0.1"})
        result = _bulb_map(settings)
        assert list(result.keys()) == ["office"]
        assert isinstance(result["office"], BulbConfig)
        assert result["office"].name == "office"

    def test_bulb_map_maps_multiple_bulbs(self) -> None:
        """Multiple configured bulbs all appear as separate keys.

        Technique: Specification-based — multiple-bulb dict shape.
        """
        settings = _settings_with_bulbs(
            {"name": "office", "ip": "10.0.0.1"},
            {"name": "bedroom", "ip": "10.0.0.2"},
        )
        result = _bulb_map(settings)
        assert set(result.keys()) == {"office", "bedroom"}

    def test_bulb_map_returns_empty_dict_for_no_bulbs(self) -> None:
        """An empty bulbs list produces an empty dispatch dict.

        Technique: Boundary Value Analysis — zero-bulb edge case.
        """
        settings = _settings_with_bulbs()
        assert _bulb_map(settings) == {}

    def test_bulb_map_raises_type_error_for_wrong_settings(self) -> None:
        """A non-Wiz2MqttSettings argument raises TypeError with the type name.

        Technique: Error Guessing — defensive isinstance guard.
        """

        class OtherSettings:
            pass

        with pytest.raises(TypeError, match="OtherSettings"):
            _bulb_map(OtherSettings())  # type: ignore[arg-type]


class TestTelemetryTriggerConfig:
    """The ``bulb_entity`` registration is what makes push-driven publish work.

    Registration flags are easy to drop in a refactor and produce no
    failure — the app simply reverts to polling. These pin them.
    """

    @staticmethod
    def _bulb_entity_registration() -> object:
        from wiz2mqtt.main import app  # noqa: PLC0415 — module-level app singleton

        regs = [r for r in app._telemetry if r.func.__name__ == "bulb_entity"]  # noqa: SLF001
        assert len(regs) == 1, f"expected one bulb_entity registration, got {regs!r}"
        return regs[0]

    def test_bulb_entity_is_locally_triggerable(self) -> None:
        """Technique: Specification-based — ``local``, not ``True``/``mqtt``.

        ``triggerable=True`` is an alias for ``"mqtt"``, which would
        subscribe a per-bulb trigger topic nobody publishes to and still
        leave the push path dead.
        """
        assert self._bulb_entity_registration().triggerable == "local"  # ty: ignore[unresolved-attribute]

    def test_bulb_entity_leaves_availability_to_three_failure_policy(self) -> None:
        """Framework failures must not bypass bulb_entity_tick's debounce."""
        assert self._bulb_entity_registration().unavailable_on is None  # ty: ignore[unresolved-attribute]

    def test_bulb_entity_carries_no_storm_throttle(self) -> None:
        """Technique: Specification-based — deliberate absence of min_interval.

        A WiZ bulb pushes only on change and ``OnChange()`` already drops
        identical payloads, so a throttle would add latency for no gain.
        """
        assert self._bulb_entity_registration().min_interval is None  # ty: ignore[unresolved-attribute]

    def test_bulb_entity_publishes_on_change(self) -> None:
        """Technique: Specification-based — trigger wakes reuse the publish gate.

        A triggered run goes through the identical publish cycle, so a
        push that carries no actual change must still be suppressed.
        """
        from cosalette import OnChange  # noqa: PLC0415

        assert isinstance(self._bulb_entity_registration().publish_strategy, OnChange)  # ty: ignore[unresolved-attribute]

    def test_heartbeat_interval_matches_the_push_staleness_threshold(self) -> None:
        """Technique: Specification-based — the two constants are one decision.

        A heartbeat tick is only a liveness probe if it finds the push
        cache stale; if the interval drops below the threshold the tick
        just re-reads a cache that cannot have expired.
        """
        from wiz2mqtt.adapters.wizlight import (  # noqa: PLC0415
            _DEFAULT_PUSH_STALENESS_THRESHOLD,
        )
        from wiz2mqtt.main import _TICK_INTERVAL_SECONDS  # noqa: PLC0415

        assert _TICK_INTERVAL_SECONDS == _DEFAULT_PUSH_STALENESS_THRESHOLD


class TestBulbSet:
    """Command-side intent and transient queue behavior.

    Technique: Decision Table — no-op, transient, and permanent port outcomes.
    """

    @staticmethod
    def _config() -> BulbConfig:
        return BulbConfig(name="office", ip="10.0.0.1")

    @staticmethod
    def _ctx() -> FakeDeviceContext:
        settings = _settings_with_bulbs({"name": "office", "ip": "10.0.0.1"})
        return FakeDeviceContext(settings=settings)

    async def test_empty_command_is_a_true_no_op(self) -> None:
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        notify = RecordingNotifier()

        await bulb_set(
            BulbSetCommand(), self._config(), adapter, state, self._ctx(), notify
        )

        assert state.desired_state == {}
        assert adapter.set_state_calls == []
        assert notify.armed == []

    async def test_timeout_marks_offline_and_queues_a_later_command(self) -> None:
        """Technique: State Transition — transient failure arms one-slot queueing."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        notify = RecordingNotifier()
        ctx = self._ctx()
        adapter.fail_next("10.0.0.1", WizTimeoutError("timeout"))

        with pytest.raises(WizTimeoutError):
            await bulb_set(
                BulbSetCommand(brightness=50),
                self._config(),
                adapter,
                state,
                ctx,
                notify,
            )
        await bulb_set(
            BulbSetCommand(brightness=200),
            self._config(),
            adapter,
            state,
            ctx,
            notify,
        )

        assert state.last_availability["office"] == "offline"
        assert ctx.availability_calls == ["unavailable"]
        assert state.pending_commands["office"].kwargs["brightness"] == 200
        assert len(adapter.set_state_calls) == 1
        assert notify.armed == ["office", "office"]

    @pytest.mark.parametrize(
        "error",
        [WizIdentityError("wrong bulb"), WizUnsupportedCommandError("unsupported")],
    )
    async def test_permanent_failures_do_not_queue(self, error: Exception) -> None:
        """Technique: Equivalence Partitioning — permanent errors are not replayable."""
        adapter = FakeWizBulbAdapter()
        state = SharedState()
        notify = RecordingNotifier()
        adapter.fail_next("10.0.0.1", error)

        with pytest.raises(type(error)):
            await bulb_set(
                BulbSetCommand(brightness=50),
                self._config(),
                adapter,
                state,
                self._ctx(),
                notify,
            )

        assert state.pending_commands == {}
        assert state.last_availability == {}
        assert notify.armed == []


_SIGNAL_TOPIC = "openhab/relay/downstairs/state"


def _signal_settings() -> Wiz2MqttSettings:
    return build_settings(
        [
            {"name": "office", "ip": "10.0.0.1"},
            {"name": "hall", "ip": "10.0.0.2"},
        ],
        [
            {
                "name": "downstairs",
                "members": ["office", "hall"],
                "signal_topic": _SIGNAL_TOPIC,
            }
        ],
    )


class TestPowerSignal:
    """``power_signal`` feeds a relay signal into the belief of its source."""

    @pytest.mark.parametrize("signal", ["on", "off"])
    async def test_valid_signal_is_stored_and_arms_source_and_members(
        self, signal: str
    ) -> None:
        """Technique: Specification-based — state updated, source and members armed."""
        state, notify = SharedState(), RecordingNotifier()

        await power_signal(signal, _SIGNAL_TOPIC, _signal_settings(), state, notify)

        assert state.source_signal == {"downstairs": signal}
        assert notify.armed == ["downstairs", "hall", "office"]

    async def test_repeated_signal_does_not_arm_again(self) -> None:
        """Technique: State Transition — a signal equal to the stored one is a no-op.

        A relay that republishes its state, or a retained redelivery after a
        reconnect, must not wake every member bulb for a read.
        """
        state, notify = SharedState(), RecordingNotifier()
        settings = _signal_settings()
        await power_signal("off", _SIGNAL_TOPIC, settings, state, notify)
        notify.armed.clear()

        await power_signal("off", _SIGNAL_TOPIC, settings, state, notify)

        assert notify.armed == []

    async def test_changed_signal_arms_again(self) -> None:
        """Technique: State Transition — a real change wakes the entities again."""
        state, notify = SharedState(), RecordingNotifier()
        settings = _signal_settings()
        await power_signal("off", _SIGNAL_TOPIC, settings, state, notify)
        notify.armed.clear()

        await power_signal("on", _SIGNAL_TOPIC, settings, state, notify)

        assert state.source_signal == {"downstairs": "on"}
        assert notify.armed == ["downstairs", "hall", "office"]

    async def test_invalid_signal_changes_nothing_and_never_echoes_the_payload(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Technique: Error Guessing — a broker-supplied payload stays out of logs."""
        state, notify = SharedState(), RecordingNotifier()

        with caplog.at_level("WARNING", logger="wiz2mqtt.main"):
            await power_signal(
                "SECRET-TOKEN", _SIGNAL_TOPIC, _signal_settings(), state, notify
            )

        assert state.source_signal == {}
        assert notify.armed == []
        assert "downstairs" in caplog.text
        assert "SECRET-TOKEN" not in caplog.text

    @pytest.mark.parametrize("payload", ["garbage", ""])
    async def test_invalid_signal_keeps_the_previous_signal(self, payload: str) -> None:
        """Technique: State Transition — a bad or empty payload does not clear it.

        An empty payload is a cleared retained topic. It keeps the last known
        signal, the same as any other payload that is not ``on`` or ``off``.
        """
        state, notify = SharedState(), RecordingNotifier()
        settings = _signal_settings()
        await power_signal("off", _SIGNAL_TOPIC, settings, state, notify)

        await power_signal(payload, _SIGNAL_TOPIC, settings, state, notify)

        assert state.source_signal == {"downstairs": "off"}

    async def test_unknown_topic_is_ignored(self) -> None:
        """Technique: Error Guessing — a topic no source declares is a no-op."""
        state, notify = SharedState(), RecordingNotifier()

        await power_signal("on", "other/topic", _signal_settings(), state, notify)

        assert state.source_signal == {}
        assert notify.armed == []

    async def test_signal_updates_only_the_source_of_its_topic(self) -> None:
        """Technique: Decision Table — two sources, one topic each, one without.

        A signal on the topic of one source must not reach the other sources
        or their bulbs.
        """
        settings = build_settings(
            [
                {"name": "a", "ip": "10.0.0.1"},
                {"name": "b", "ip": "10.0.0.2"},
                {"name": "c", "ip": "10.0.0.3"},
            ],
            [
                {"name": "up", "members": ["a"], "signal_topic": "relay/up"},
                {"name": "down", "members": ["b"], "signal_topic": "relay/down"},
                {"name": "quiet", "members": ["c"]},
            ],
        )
        state, notify = SharedState(), RecordingNotifier()

        await power_signal("on", "relay/down", settings, state, notify)

        assert state.source_signal == {"down": "on"}
        assert notify.armed == ["down", "b"]


class _RecordingApp:
    """Records ``add_inbound`` calls in place of a real ``cosalette.App``."""

    def __init__(self) -> None:
        self.inbounds: list[tuple[object, dict[str, object]]] = []

    def add_inbound(self, name: object, func: object, **kwargs: object) -> None:
        assert func is power_signal
        self.inbounds.append((name, kwargs))


class TestAddPowerSignalInbounds:
    """One bounded inbound per source that declares a ``signal_topic``."""

    def test_registers_one_inbound_per_declared_topic_verbatim(self) -> None:
        """Technique: Specification-based — two sources with, one without a topic."""
        settings = build_settings(
            [
                {"name": "a", "ip": "10.0.0.1"},
                {"name": "b", "ip": "10.0.0.2"},
                {"name": "c", "ip": "10.0.0.3"},
            ],
            [
                {"name": "up", "members": ["a"], "signal_topic": "relay/up"},
                {"name": "down", "members": ["b"], "signal_topic": "relay/down"},
                {"name": "quiet", "members": ["c"]},
            ],
        )
        app = _RecordingApp()

        add_power_signal_inbounds(app, settings)  # type: ignore[arg-type]

        assert [(name, kw["topic"]) for name, kw in app.inbounds] == [
            ("up", "relay/up"),
            ("down", "relay/down"),
        ]

    def test_inbound_queue_is_bounded_and_drops_the_oldest(self) -> None:
        """Technique: Specification-based — a flooded topic cannot grow memory."""
        app = _RecordingApp()

        add_power_signal_inbounds(app, _signal_settings())  # type: ignore[arg-type]

        [(_, kwargs)] = app.inbounds
        assert kwargs["maxsize"] == 8
        assert kwargs["backpressure"] == "drop_oldest"

    def test_registers_nothing_without_power_sources(self) -> None:
        """Technique: Boundary Value Analysis — zero sources."""
        app = _RecordingApp()

        add_power_signal_inbounds(app, _settings_with_bulbs())  # type: ignore[arg-type]

        assert app.inbounds == []


class TestInboundWiring:
    """The production ``app`` gives ``power_signal`` its state and notifier.

    cosalette 0.10.2 injects ``@app.state`` values and the ``EntityNotifier``
    into inbound handlers, so no adapter entry is needed.
    """

    @staticmethod
    def _app() -> App:
        from wiz2mqtt.main import app  # noqa: PLC0415 — module-level app singleton

        return app

    def test_shared_state_is_the_only_app_state(self) -> None:
        """Technique: Specification-based — one registration, not two instances."""
        factories = self._app().state_factories

        assert [reg.state_type for reg in factories] == [SharedState]

    def test_state_and_notifier_are_not_adapters(self) -> None:
        """Technique: Specification-based — no adapter shadows the injected values."""
        adapters = self._app()._adapters  # noqa: SLF001

        assert SharedState not in adapters
        assert EntityNotifier not in adapters

    def test_one_configure_hook_registers_the_signal_inbounds(self) -> None:
        """Technique: Specification-based — the hook is what feeds schema and ACL."""
        hooks = self._app()._configure_hooks  # noqa: SLF001

        assert [hook.__name__ for hook in hooks] == [  # ty: ignore[unresolved-attribute]
            "_configure_power_signals"
        ]
