"""Unit tests for main.py — _bulb_map name-to-config dispatch function.

Test Techniques Used:
- Specification-based: dict key is the bulb name, value is the BulbConfig
- Error Guessing: wrong settings type raises TypeError with the exact message
- Boundary Value Analysis: empty bulbs list returns empty dict
"""

from __future__ import annotations

import pytest

from wiz2mqtt.main import _bulb_map
from wiz2mqtt.settings import BulbConfig, Wiz2MqttSettings


def _settings_with_bulbs(*bulbs: dict[str, object]) -> Wiz2MqttSettings:
    return Wiz2MqttSettings(bulbs=list(bulbs), _env_file=None, _config_file=None)  # type: ignore[arg-type,call-arg]


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
