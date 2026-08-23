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
