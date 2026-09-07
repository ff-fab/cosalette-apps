"""Onboarding aid: discover WiZ bulbs on the LAN and print TOML inventory.

Ships as the standalone ``wiz2mqtt-discover`` console script rather than a
``wiz2mqtt discover`` subcommand. cosalette builds the daemon's Typer CLI
internally (ADR-005) and exposes no hook to mount app-specific commands, and
app ADR-002 states discovery is an onboarding aid *explicitly not wired into
the daemon's addressing* — a separate binary encodes that boundary. The
printed ``[[bulbs]]`` blocks are meant to be copied into ``wiz2mqtt.toml``
after renaming the placeholder names.
"""

from __future__ import annotations

import asyncio
import re
import sys
from typing import TYPE_CHECKING, Annotated, Protocol

import typer

if TYPE_CHECKING:
    from collections.abc import Sequence

# pywizlight #200: discover_lights can hang forever waiting on the closed
# transport's connection_lost, so every call is wrapped in asyncio.timeout().
_DEFAULT_WAIT_SECONDS = 5.0
_DEFAULT_TIMEOUT_SECONDS = 30.0
_BROADCAST_DEFAULT = "255.255.255.255"

# BulbConfig accepts a MAC only as bare 12-hex-digit lowercase (settings.py).
_MAC_RE = re.compile(r"^[0-9a-f]{12}$")


class _DiscoveredBulb(Protocol):
    """The slice of pywizlight's ``wizlight`` this module reads."""

    ip: str
    mac: str | None


async def _discover(
    broadcast: str, wait: float, timeout: float
) -> Sequence[_DiscoveredBulb]:
    """Broadcast-discover bulbs, bounded by *timeout* seconds.

    ``pywizlight`` is imported lazily inside the function, matching the
    convention used by every hardware adapter in this app (ADR-003).
    """
    from pywizlight.discovery import (  # noqa: PLC0415 — lazy import by design
        discover_lights,
    )

    async with asyncio.timeout(timeout):
        return await discover_lights(broadcast_space=broadcast, wait_time=wait)


def _render_toml(bulbs: Sequence[_DiscoveredBulb]) -> str:
    """Render discovered bulbs as ``[[bulbs]]`` inventory blocks.

    Names are ``bulb-<n>`` placeholders (sorted by IP for determinism) that
    the operator is expected to rename; the value matches ``BulbConfig``'s
    ``[A-Za-z0-9_-]+`` topic-segment rule so the output is paste-ready.
    """
    ordered = sorted(bulbs, key=lambda bulb: _ip_sort_key(bulb.ip))
    lines = [
        "# Discovered WiZ bulbs — copy the entries below into wiz2mqtt.toml and",
        "# rename each placeholder `name` to something meaningful. IPs must be",
        "# pinned via static DHCP reservations (see ADR-002).",
    ]
    for index, bulb in enumerate(ordered, start=1):
        lines.append("")
        lines.append("[[bulbs]]")
        lines.append(f'name = "bulb-{index}"')
        lines.append(f'ip = "{bulb.ip}"')
        mac = _normalise_mac(bulb.mac)
        if mac:
            lines.append(f'mac = "{mac}"')
    return "\n".join(lines)


def _normalise_mac(mac: str | None) -> str | None:
    """Return the MAC as bare lowercase hex, or ``None`` if unusable.

    Discovery data arrives off the network, so a hostile or buggy responder
    could return a MAC containing quotes or newlines that would break out of
    the TOML string. Emit it only when it matches BulbConfig's 12-hex rule so
    the rendered inventory always parses and validates.
    """
    if mac is None:
        return None
    candidate = mac.lower()
    return candidate if _MAC_RE.match(candidate) else None


def _ip_sort_key(ip: str) -> tuple[int, ...]:
    """Sort key that orders IPv4 addresses numerically, not lexically."""
    try:
        return tuple(int(octet) for octet in ip.split("."))
    except ValueError:
        return (0,)


app = typer.Typer(add_completion=False)


@app.callback(invoke_without_command=True)
def discover(
    broadcast: Annotated[
        str,
        typer.Option(help="Broadcast address to probe for bulbs."),
    ] = _BROADCAST_DEFAULT,
    wait: Annotated[
        float,
        typer.Option(help="Seconds to listen for bulb replies."),
    ] = _DEFAULT_WAIT_SECONDS,
    timeout: Annotated[
        float,
        typer.Option(help="Hard cap on total discovery time (must exceed --wait)."),
    ] = _DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Discover WiZ bulbs on the LAN and print TOML inventory entries.

    Prints paste-ready bulb blocks to stdout; progress notes go to stderr so
    the output can be redirected straight into wiz2mqtt.toml.
    """
    if timeout <= wait:
        # Click quotes the param_hint itself ("Invalid value for '--timeout'"),
        # so the message only needs to state the constraint, not repeat the flag.
        raise typer.BadParameter(
            f"must exceed --wait ({wait})",
            param_hint="'--timeout'",
        )

    print(f"Discovering WiZ bulbs on {broadcast} for {wait}s…", file=sys.stderr)
    try:
        bulbs = asyncio.run(_discover(broadcast, wait, timeout))
    except TimeoutError:
        print(
            f"Discovery timed out after {timeout}s (pywizlight can hang; "
            "try again or narrow --broadcast).",
            file=sys.stderr,
        )
        raise typer.Exit(code=1) from None
    except OSError as exc:
        print(f"Discovery failed: {exc}", file=sys.stderr)
        raise typer.Exit(code=1) from exc

    if not bulbs:
        print("No WiZ bulbs discovered.", file=sys.stderr)
        return

    print(f"Discovered {len(bulbs)} bulb(s).", file=sys.stderr)
    print(_render_toml(bulbs))


def main() -> None:
    """Console-script entry point for ``wiz2mqtt-discover``."""
    app()


if __name__ == "__main__":
    main()
