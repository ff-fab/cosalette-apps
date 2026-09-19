"""Specification tests for deployment rendering and consumer-only groups.

Test Techniques Used:
- Specification-based: real inventory renders Things/Items with group wiring
- Decision Table: bulb and group openHAB identifier collisions across
  normalization boundaries (hyphen/underscore, case, empty segments)
- Error Guessing: framework output drift (missing Color command Item) and
  schema CLI failure propagation surface as a failing exit
- Round-trip Testing: overlapping groups resolve end-to-end via the real
  schema CLI with a custom broker uid and topic prefix
- Equivalence Partitioning: a bulb in a power source gets a Powered channel
  and Item; a bulb outside every source keeps the output unchanged
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wiz2mqtt.openhab import add_groups, add_powered, cli
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


def test_missing_state_channel_fails() -> None:
    """Framework output drift cannot silently drop a bulb's Powered Item."""
    settings = Wiz2MqttSettings(
        _env_file=None,
        _config_file=None,
        bulbs=[{"name": "desk", "ip": "10.0.0.1", "power_source": "circuit"}],
        power_sources=[{"name": "circuit", "members": ["desk"]}],
    )
    with pytest.raises(ValueError, match="Expected one State channel"):
        add_powered("", "", settings)


def _generate(tmp_path: Path, toml: str) -> str:
    config = tmp_path / "wiz2mqtt.toml"
    config.write_text(toml)
    result = CliRunner().invoke(cli, ["--config-file", str(config)])
    assert result.exit_code == 0, result.output
    return result.output


_BULBS = (
    '[[bulbs]]\nname="desk"\nip="10.0.0.1"\n'
    '[[bulbs]]\nname="living-room"\nip="10.0.0.2"\n'
    '[[bulbs]]\nname="hall"\nip="10.0.0.3"\n'
)


def test_power_source_generation(tmp_path: Path) -> None:
    """One source with two members: belief, desired power and two Powered Items."""
    output = _generate(
        tmp_path,
        _BULBS + '[[power_sources]]\nname="circuit"\nmembers=["desk", "living-room"]\n',
    )
    items = [line for line in output.splitlines() if line.startswith("Switch")]
    for item, channel in [
        ("Wiz2Mqtt_Circuit_Powered", "wiz2mqtt_circuit:powered"),
        ("Wiz2Mqtt_Circuit_PowerRequest", "wiz2mqtt_circuit:power_request"),
        ("Wiz2Mqtt_Desk_Powered", "wiz2mqtt_desk:powered"),
        ("Wiz2Mqtt_LivingRoom_Powered", "wiz2mqtt_living_room:powered"),
    ]:
        assert any(f" {item} " in i and f':{channel}"' in i for i in items), item
    assert "Wiz2Mqtt_Hall_Powered" not in output
    # The belief's "unknown" and a JSON null both reach openHAB as NULL.
    assert output.count('nullValue="unknown"') == 1
    assert output.count('nullValue="NULL"') == 3
    assert "JSONPATH:$[?(@.power_request != null)].power_request" in output
    # Read-only: no command channel on the source, so no relay mapping.
    assert 'commandTopic="wiz2mqtt/circuit/' not in output


def test_no_power_source_generates_no_powered_output(tmp_path: Path) -> None:
    """Without a source the output is the one from before power awareness."""
    output = _generate(tmp_path, _BULBS)
    assert "powered" not in output.lower()
    assert "nullValue" not in output
