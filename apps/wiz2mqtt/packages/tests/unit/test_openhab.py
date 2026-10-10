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
  and Item; a bulb outside every source gets none. Every bulb gets an Error
  channel and Item either way
- Specification-based: every bulb exposes colour temperature, effect speed,
  power draw and the error topic, with commands openHAB can actually send
- Error Guessing: the generator needing PyYAML, which only the dev group
  provides, and dotenv filtering's version floor living only in a
  workspace constraint, where downstream installs cannot see it
"""

from __future__ import annotations

import importlib.metadata
import re
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wiz2mqtt.openhab import add_bulb_channels, add_groups, cli
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


def test_generator_runs_without_pyyaml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The image ships no PyYAML, so the schema CLI the generator runs must not need it.

    Technique: Error Guessing — the dev group provides PyYAML, so the other
    end-to-end tests pass even when the image cannot generate (0.2.13). A
    ``yaml`` stub that fails to import shadows the real one in the schema CLI.
    """
    stub = tmp_path / "stub" / "yaml"
    stub.mkdir(parents=True)
    (stub / "__init__.py").write_text("raise ImportError('PyYAML blocked')\n")
    monkeypatch.setenv("PYTHONPATH", str(stub.parent))
    config = tmp_path / "wiz2mqtt.toml"
    config.write_text('[[bulbs]]\nname="desk"\nip="10.0.0.1"\n')

    result = CliRunner().invoke(cli, ["--config-file", str(config)])

    assert result.exit_code == 0, result.output
    assert "Wiz2Mqtt_Desk_Hsb_Cmd" in result.output


def test_dotenv_filtering_dependency_floor_ships_at_runtime() -> None:
    """The config option must be supported by the downstream installed version."""
    requires = importlib.metadata.requires("wiz2mqtt") or []
    runtime = [r for r in requires if "extra ==" not in r]

    assert any(
        re.match(r"(?i)pydantic-settings>=2\.14\.2(?:[; ]|$)", r) for r in runtime
    )


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


@pytest.mark.parametrize("in_source", [True, False])
def test_missing_state_channel_fails(in_source: bool) -> None:
    """Framework output drift cannot silently drop a bulb's Error or Powered Item.

    Technique: Error Guessing — every bulb gets an Error Item, so a missing
    State channel fails for a bulb outside every source as well.
    """
    settings = Wiz2MqttSettings(
        _env_file=None,
        _config_file=None,
        bulbs=[{"name": "desk", "ip": "10.0.0.1"}],
        power_sources=([{"name": "circuit", "members": ["desk"]}] if in_source else []),
    )
    with pytest.raises(ValueError, match="Expected one State channel"):
        add_bulb_channels("", "", settings)


def test_cross_kind_identifier_collision_fails() -> None:
    """A source and bulb must not render to the same openHAB Thing ID."""
    settings = Wiz2MqttSettings(
        _env_file=None,
        _config_file=None,
        bulbs=[{"name": "living-room", "ip": "10.0.0.1"}],
        power_sources=[{"name": "living_room", "members": ["living-room"]}],
    )
    with pytest.raises(ValueError, match="Power-source name collides"):
        add_bulb_channels("", "", settings)


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
    # Error comes on every bulb, beside Powered or without it.
    for bulb in ("Desk", "LivingRoom", "Hall"):
        assert f"String  Wiz2Mqtt_{bulb}_Error " in output, bulb
    # The belief's "unknown" and a JSON null both reach openHAB as NULL:
    # two Powered bulbs and power_request, plus pending/last_applied per bulb.
    assert output.count('nullValue="unknown"') == 1
    assert output.count('nullValue="NULL"') == 3 + 2 * _BULBS.count("[[bulbs]]")
    assert "JSONPATH:$[?(@.power_request != null)].power_request" in output
    # Read-only: no command channel on the source, so no relay mapping.
    assert 'commandTopic="wiz2mqtt/circuit/' not in output
    # Sources expose belief, not reachability; they publish no availability topic.
    assert 'availabilityTopic="wiz2mqtt/circuit/availability"' not in output


def test_no_power_source_generates_no_powered_output(tmp_path: Path) -> None:
    """Without a source no bulb gets a Powered channel, Item or null mapping.

    The only null mappings left are each bulb's pending and last_applied.
    """
    output = _generate(tmp_path, _BULBS)
    assert "powered" not in output.lower()
    assert 'nullValue="unknown"' not in output
    assert output.count("nullValue=") == 2 * _BULBS.count("[[bulbs]]")


def _channel(output: str, local: str) -> str:
    """The ``Type ... : <local> "..." [ ... ]`` block of one Thing channel."""
    assert f" : {local} " in output, f"no {local} channel"
    start = output.index(f" : {local} ")
    return output[start : output.index("]", start)]


def test_bulb_channels_cover_commands_and_diagnostics(tmp_path: Path) -> None:
    """Commands and diagnostics are generated with no manual edits."""
    output = _generate(tmp_path, _BULBS)
    for local, needle in [
        ("color_temp_cmd", "min=2200"),
        ("effect_speed_cmd", "min=10"),
        ("effect_cmd", 'allowedStates="Alarm,'),
        ("power_draw_w", "JSONPATH:$.power_draw_w"),
        ("error", 'stateTopic="wiz2mqtt/desk/error"'),
        ("reachable", 'on="true"'),
        ("pending", "JSONPATH:$[?(@.pending != null)"),
        ("last_applied", "JSONPATH:$[?(@.last_applied != null)"),
    ]:
        assert needle in _channel(output, local), local
    for read_only in ("power_draw_w", "error", "reachable", "pending", "last_applied"):
        assert "commandTopic" not in _channel(output, read_only), read_only
        assert f"{read_only}_cmd" not in output, read_only
    assert output.count(':error"') == _BULBS.count("[[bulbs]]")
    for item in [
        'Number  Wiz2Mqtt_Desk_ColorTemp_Cmd  "Color temperature [%s K]"',
        'Number  Wiz2Mqtt_Desk_PowerDrawW  "Power [%s W]"',
        'String  Wiz2Mqtt_Desk_Error  "Error [%s]"',
        'Switch  Wiz2Mqtt_Desk_Reachable  "Reachable [%s]"',
        'String  Wiz2Mqtt_Desk_Pending  "Pending [%s]"',
        'String  Wiz2Mqtt_Desk_LastApplied  "Last applied [%s]"',
    ]:
        assert item in output, item


def test_on_off_commands_are_formattable(tmp_path: Path) -> None:
    """openHAB formats on/off through ``formatBeforePublish``, so they are bare.

    Dimmer and Color carry no on/off: openHAB sends OFF as brightness 0.
    """
    output = _generate(tmp_path, _BULBS)
    switch = _channel(output, "state_cmd")
    assert 'on="ON"' in switch
    assert 'off="OFF"' in switch
    assert '{\\"state\\": \\"ON\\"}' not in output
    for local in ("brightness_cmd", "hsb_cmd"):
        assert "on=" not in _channel(output, local), local
    assert "min=0" in _channel(output, "brightness_cmd")
    assert 'formatBeforePublish="{\\"hsb\\":\\"%1$d,%2$d,%3$d\\"}"' in _channel(
        output, "hsb_cmd"
    )
