"""Generate deployment openHAB files through cosalette's public schema CLI."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Literal

import typer

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


def add_groups(items: str, settings: Wiz2MqttSettings) -> str:
    """Attach Color command Items to write-only groups; preserve channel links.

    A no-op when no groups are configured, so the generator leaves the
    framework's Items output untouched unless groups are explicitly declared.
    """
    if not settings.groups:
        return items
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

    seen: set[str] = set()
    segments: dict[str, str] = {}
    for bulb in settings.bulbs:
        slug = re.sub(r"[^a-z0-9]+", "_", bulb.name.lower()).strip("_")
        segment = slug.title().replace("_", "")
        if not segment or segment in seen:
            raise ValueError(f"Bulb names collide or are empty in openHAB: {bulb.name}")
        seen.add(segment)
        segments[bulb.name] = segment

    # Validate identifiers fully before mutating: a collision must never leave
    # a partially-rewritten Items document behind.
    for bulb in settings.bulbs:
        if bulb.name not in memberships:
            continue
        segment = segments[bulb.name]
        pattern = rf"(Color\s+Wiz2Mqtt_{segment}_Hsb_Cmd\s+[^\n]*?\()([^)]*)(\))"
        groups = ", ".join(memberships[bulb.name])
        items, count = re.subn(pattern, rf"\g<1>\g<2>, {groups}\g<3>", items)
        if count != 1:
            raise ValueError(f"Expected one Color command Item for {bulb.name}")
    return "\n".join(definitions) + "\n\n" + items


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
            items = add_groups(_schema_cli(*args, "--output", "items"), settings)
            things = _schema_cli(*args, "--output", "things")
            # schema dump uses the app name even when runtime overrides the prefix.
            prefix = settings.mqtt.topic_prefix or "wiz2mqtt"
            escaped = prefix.replace("\\", "\\\\").replace('"', '\\"')
            things = re.sub(
                r'((?:state|command)Topic=")wiz2mqtt/',
                lambda match: match[1] + escaped + "/",
                things,
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
