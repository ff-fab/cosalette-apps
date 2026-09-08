"""Specification tests for deployment rendering and consumer-only groups.

Test Techniques Used:
- Specification-based: real inventory renders Things/Items with group wiring
- Decision Table: bulb and group openHAB identifier collisions across
  normalization boundaries (hyphen/underscore, case, empty segments)
- Error Guessing: framework output drift (missing Color command Item) and
  schema CLI failure propagation surface as a failing exit
- Round-trip Testing: overlapping groups resolve end-to-end via the real
  schema CLI with a custom broker uid and topic prefix
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wiz2mqtt.openhab import add_groups, cli
from wiz2mqtt.settings import Wiz2MqttSettings


def _settings(names: list[str], groups: list[dict[str, object]]) -> Wiz2MqttSettings:
    return Wiz2MqttSettings(
        _env_file=None,
        _config_file=None,
        bulbs=[{"name": n, "ip": f"10.0.0.{i}"} for i, n in enumerate(names, 1)],
        groups=groups,
    )


def test_no_groups_is_noop() -> None:
    """With no groups configured the framework Items output is left untouched."""
    items = 'Color Wiz2Mqtt_Desk_Hsb_Cmd "Desk" {channel="x"}'
    assert add_groups(items, _settings(["desk"], [])) == items


@pytest.mark.parametrize("names", [["a-b", "a_b"], ["Desk", "desk"], ["___"]])
def test_bulb_identifier_collisions(names: list[str]) -> None:
    """Distinct MQTT names must not silently merge into one openHAB Item."""
    groups = [{"name": "g", "members": [names[0]]}]
    with pytest.raises(ValueError, match="openHAB"):
        add_groups("", _settings(names, groups))


def test_group_identifier_collisions() -> None:
    """Hyphen normalization must not produce duplicate Group declarations."""
    settings = _settings(
        ["desk"],
        [{"name": name, "members": ["desk"]} for name in ["a-b", "a_b"]],
    )
    with pytest.raises(ValueError, match="Group names collide"):
        add_groups("", settings)


def test_missing_command_item_fails() -> None:
    """Framework output drift cannot silently leave a group disconnected."""
    settings = _settings(["desk"], [{"name": "all", "members": ["desk"]}])
    with pytest.raises(ValueError, match="Expected one Color"):
        add_groups("", settings)


def test_framework_failure_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CLI propagates the schema tool's useful diagnostic and a failing exit."""
    config = tmp_path / "wiz2mqtt.toml"
    config.write_text("bulbs=[]\n")

    def fail(*args: str) -> str:
        raise subprocess.CalledProcessError(2, args, stderr="schema failed")

    monkeypatch.setattr("wiz2mqtt.openhab._schema_cli", fail)
    result = CliRunner().invoke(cli, ["--config-file", str(config)])
    assert result.exit_code == 1
    assert "schema failed" in result.output


@pytest.mark.parametrize("output", ["things", "items", "both"])
def test_real_inventory_generation(tmp_path: Path, output: str) -> None:
    """End-to-end: real schema CLI, overlapping groups and custom broker/prefix."""
    config = tmp_path / "wiz2mqtt.toml"
    config.write_text(
        '[mqtt]\ntopic_prefix="house/wiz"\n'
        '[[bulbs]]\nname="desk"\nip="10.0.0.1"\n'
        '[[bulbs]]\nname="living-room"\nip="10.0.0.2"\n'
        '[[groups]]\nname="all"\nmembers=["desk", "living-room"]\n'
        '[[groups]]\nname="office"\nmembers=["desk"]\n'
    )
    result = CliRunner().invoke(
        cli, ["--config-file", str(config), "--broker-uid", "home", "--output", output]
    )
    assert result.exit_code == 0, result.output
    if output in ("items", "both"):
        assert 'Group gWiz2mqttGroup_all "all"' in result.output
        desk = next(
            line
            for line in result.output.splitlines()
            if "Wiz2Mqtt_Desk_Hsb_Cmd" in line
        )
        assert "(gWiz2Mqtt, gWiz2mqttGroup_all, gWiz2mqttGroup_office)" in desk
        assert 'channel="mqtt:topic:home:wiz2mqtt_desk:hsb_cmd"' in desk
        state = next(
            line for line in result.output.splitlines() if "Wiz2Mqtt_Desk_Hsb " in line
        )
        assert "gWiz2mqttGroup" not in state
    if output in ("things", "both"):
        assert 'commandTopic="house/wiz/desk/set"' in result.output
        assert "house/wiz/all/" not in result.output
        assert "house/wiz/office/" not in result.output
