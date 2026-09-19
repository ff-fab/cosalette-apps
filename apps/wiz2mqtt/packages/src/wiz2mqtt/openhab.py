"""Generate deployment openHAB files through cosalette's public schema CLI."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Literal

import typer

from wiz2mqtt.models import openhab_nullable_switch_params
from wiz2mqtt.settings import Wiz2MqttSettings

cli = typer.Typer()


def _schema_cli(*args: str) -> str:
    """Keep framework schema internals behind the supported CLI boundary."""
    return subprocess.run(  # noqa: S603 — fixed executable, argument vector
        [sys.executable, "-m", "cosalette", "schema", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _group_definitions(
    settings: Wiz2MqttSettings,
) -> tuple[list[str], dict[str, list[str]]]:
    """Return the Group definitions and each member bulb's group identifiers."""
    memberships: dict[str, list[str]] = {}
    definitions = ['Group gWiz2Mqtt "WiZ bulbs"']
    group_ids: set[str] = set()
    for group in settings.groups:
        identifier = "gWiz2mqttGroup_" + group.name.replace("-", "_")
        if identifier in group_ids:
            raise ValueError(f"Group names collide in openHAB: {group.name}")
        group_ids.add(identifier)
        definitions.append(f'Group {identifier} "{group.name}"')
        for member in group.members:
            memberships.setdefault(member, []).append(identifier)
    return definitions, memberships


def _openhab_segment(name: str) -> str:
    """Return the CamelCase openHAB identifier segment for a configured name."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug.title().replace("_", "")


def _bulb_segments(settings: Wiz2MqttSettings) -> dict[str, str]:
    """Map each bulb name to its openHAB identifier segment; reject collisions."""
    seen: set[str] = set()
    segments: dict[str, str] = {}
    for bulb in settings.bulbs:
        segment = _openhab_segment(bulb.name)
        if not segment or segment in seen:
            raise ValueError(f"Bulb names collide or are empty in openHAB: {bulb.name}")
        seen.add(segment)
        segments[bulb.name] = segment
    return segments


def _check_openhab_identifier_collisions(settings: Wiz2MqttSettings) -> None:
    """Reject bulb and power-source names that render to one Thing identifier."""
    bulb_segments = set(_bulb_segments(settings).values())
    source_segments: set[str] = set()
    for source in settings.power_sources:
        segment = _openhab_segment(source.name)
        if not segment or segment in bulb_segments or segment in source_segments:
            raise ValueError(
                f"Power-source name collides or is empty in openHAB: {source.name}"
            )
        source_segments.add(segment)


def add_groups(items: str, settings: Wiz2MqttSettings) -> str:
    """Attach Color command Items to write-only groups; preserve channel links.

    A no-op when no groups are configured, so the generator leaves the
    framework's Items output untouched unless groups are explicitly declared.
    """
    if not settings.groups:
        return items
    definitions, memberships = _group_definitions(settings)
    segments = _bulb_segments(settings)

    # Validate identifiers fully before mutating: a collision must never leave
    # a partially-rewritten Items document behind.
    for bulb in settings.bulbs:
        if bulb.name not in memberships:
            continue
        pattern = (
            rf"(Color\s+Wiz2Mqtt_{segments[bulb.name]}_Hsb_Cmd\s+[^\n]*?\()([^)]*)(\))"
        )
        groups = ", ".join(memberships[bulb.name])
        items, count = re.subn(pattern, rf"\g<1>\g<2>, {groups}\g<3>", items)
        if count != 1:
            raise ValueError(f"Expected one Color command Item for {bulb.name}")
    return "\n".join(definitions) + "\n\n" + items


def _powered_channel(match: re.Match[str]) -> str:
    """Append a read-only Powered channel on the state topic of *match*."""
    params = {"stateTopic": match[1]} | openhab_nullable_switch_params(
        "powered", on="true", off="false"
    )
    lines = ",\n".join(f'            {key}="{value}"' for key, value in params.items())
    return f'{match[0]}        Type switch : powered "Powered" [\n{lines}\n        ]\n'


def remove_power_source_availability(things: str, settings: Wiz2MqttSettings) -> str:
    """Remove generated availability for sources, which have no such topic."""
    prefix = settings.mqtt.topic_prefix or "wiz2mqtt"
    for source in settings.power_sources:
        topic = re.escape(f"{prefix}/{source.name}/availability")
        availability = (
            rf'^[ \t]*availabilityTopic="{topic}",\n'
            r'^[ \t]*payloadAvailable="online",\n'
            r'^[ \t]*payloadNotAvailable="offline"\n'
        )
        things, count = re.subn(availability, "", things, flags=re.MULTILINE)
        if count != 1:
            raise ValueError(f"Expected one availability block for {source.name}")
    return things


def add_powered(things: str, items: str, settings: Wiz2MqttSettings) -> tuple[str, str]:
    """Add a Powered channel and Item to each bulb that has a power source.

    Every bulb payload carries ``powered``, but it stays ``null`` for a bulb
    outside a source, so only a bulb in a source gets the Item (ADR-007). A
    rule then computes "lit" as ``State == ON && Powered == ON``.
    """
    _check_openhab_identifier_collisions(settings)
    if things:
        things = remove_power_source_availability(things, settings)
    segments = _bulb_segments(settings)
    for bulb in settings.bulbs:
        if settings.power_source_of(bulb.name) is None:
            continue
        channel = (
            r' {8}Type switch : state "State" \[\n {12}stateTopic='
            rf'"([^"]*/{re.escape(bulb.name)}/state)",\n.*?\n {{8}}\]\n'
        )
        things, count = re.subn(channel, _powered_channel, things, flags=re.DOTALL)
        segment = segments[bulb.name]
        item = (
            rf'^Switch\s+Wiz2Mqtt_{segment}_State\s+"State \[%s\]"\s+'
            r'(\([^)]*\))\s+\{ channel="([^"]+):state" \}$'
        )
        powered = (
            rf'\g<0>\nSwitch  Wiz2Mqtt_{segment}_Powered  "Powered [%s]"  '
            r'\1  { channel="\2:powered" }'
        )
        items, item_count = re.subn(item, powered, items, flags=re.MULTILINE)
        if (count, item_count) != (1, 1):
            raise ValueError(f"Expected one State channel and Item for {bulb.name}")
    return things, items


@cli.command()
def generate(
    config_file: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "wiz2mqtt.toml"
    ),
    broker_uid: Annotated[str, typer.Option()] = "broker",
    output: Annotated[Literal["things", "items", "both"], typer.Option()] = "both",
) -> None:
    """Render the configured inventory without contacting bulbs or the broker."""
    try:
        settings = Wiz2MqttSettings(_config_file=str(config_file.resolve()))
        with tempfile.TemporaryDirectory() as directory:
            schema = Path(directory) / "schema.yaml"
            schema.write_text(
                _schema_cli(
                    "dump",
                    "--app",
                    "wiz2mqtt.main:app",
                    "--resolve-settings",
                    "--config-file",
                    str(config_file.resolve()),
                )
            )
            args = ("openhab", str(schema), "--broker-uid", broker_uid)
            things, items = add_powered(
                _schema_cli(*args, "--output", "things"),
                add_groups(_schema_cli(*args, "--output", "items"), settings),
                settings,
            )
        if output in ("things", "both"):
            typer.echo(things)
        if output == "both":
            typer.echo("// ---\n")
        if output in ("items", "both"):
            typer.echo(items)
    except (ValueError, subprocess.CalledProcessError) as exc:
        detail = (
            exc.stderr if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        )
        typer.echo(detail, err=True)
        raise typer.Exit(1) from exc


def main() -> None:
    """Console script entry point."""
    cli()


if __name__ == "__main__":
    main()
