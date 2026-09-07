"""Unit tests for the ``wiz2mqtt-discover`` onboarding CLI.

``pywizlight`` is never contacted over the network: discovery is faked and the
lazy ``discover_lights`` import is monkeypatched, so these tests exercise the
CLI's own logic (TOML rendering, ordering, MAC hygiene, error/timeout handling)
without hardware.

Test Techniques Used:
- Specification-based: rendered TOML round-trips through tomllib and validates
  against BulbConfig (the paste-ready contract)
- Boundary Value Analysis: ``--timeout`` must strictly exceed ``--wait`` (equal
  case rejected)
- Equivalence Partitioning: TimeoutError vs OSError both map to exit code 1
- Error Guessing: malformed IP sort key, empty discovery result, and TOML
  injection via a hostile MAC
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass

import pytest
from typer.testing import CliRunner

from wiz2mqtt import discover as discover_mod
from wiz2mqtt.discover import _ip_sort_key, _render_toml, app
from wiz2mqtt.settings import BulbConfig

runner = CliRunner()


@dataclass
class _FakeBulb:
    """Stand-in for pywizlight's ``wizlight`` (only ip/mac are read)."""

    ip: str
    mac: str | None = None


def test_render_toml_emits_paste_ready_blocks() -> None:
    rendered = _render_toml([_FakeBulb("192.168.1.10", "A8BB5006033D")])

    parsed = tomllib.loads(rendered)
    assert parsed["bulbs"] == [
        {"name": "bulb-1", "ip": "192.168.1.10", "mac": "a8bb5006033d"},
    ]


def test_render_toml_output_validates_against_bulb_config() -> None:
    rendered = _render_toml(
        [_FakeBulb("192.168.1.10", "a8bb5006033d"), _FakeBulb("192.168.1.11")]
    )

    entries = tomllib.loads(rendered)["bulbs"]
    configs = [BulbConfig.model_validate(entry) for entry in entries]

    assert [c.name for c in configs] == ["bulb-1", "bulb-2"]
    assert configs[1].mac is None


def test_render_toml_omits_mac_when_absent() -> None:
    rendered = _render_toml([_FakeBulb("192.168.1.10")])

    assert "mac =" not in rendered


def test_render_toml_drops_hostile_mac_to_prevent_toml_injection() -> None:
    # A malicious/buggy responder could return a MAC with a quote + newline to
    # break out of the TOML string and inject arbitrary config. It must not
    # reach the output; the rest of the block still renders and parses.
    rendered = _render_toml([_FakeBulb("192.168.1.10", 'a"\nname = "evil')])

    parsed = tomllib.loads(rendered)
    assert parsed["bulbs"] == [{"name": "bulb-1", "ip": "192.168.1.10"}]


def test_render_toml_orders_bulbs_numerically_by_ip() -> None:
    rendered = _render_toml([_FakeBulb("192.168.1.100"), _FakeBulb("192.168.1.9")])

    ips = [entry["ip"] for entry in tomllib.loads(rendered)["bulbs"]]
    assert ips == ["192.168.1.9", "192.168.1.100"]


def test_ip_sort_key_is_numeric() -> None:
    assert _ip_sort_key("192.168.1.9") < _ip_sort_key("192.168.1.100")


def test_ip_sort_key_tolerates_malformed_ip() -> None:
    assert _ip_sort_key("not-an-ip") == (0,)


def test_main_delegates_to_typer_app(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_app() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(discover_mod, "app", fake_app)
    discover_mod.main()

    assert called


def test_cli_prints_toml_for_discovered_bulbs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_discover(broadcast: str, wait: float, timeout: float) -> list:
        return [_FakeBulb("192.168.1.10", "a8bb5006033d")]

    monkeypatch.setattr(discover_mod, "_discover", fake_discover)

    result = runner.invoke(app, ["--wait", "1", "--timeout", "2"])

    assert result.exit_code == 0
    assert "[[bulbs]]" in result.stdout
    assert 'ip = "192.168.1.10"' in result.stdout


def test_cli_reports_when_no_bulbs_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_discover(broadcast: str, wait: float, timeout: float) -> list:
        return []

    monkeypatch.setattr(discover_mod, "_discover", fake_discover)

    result = runner.invoke(app)

    assert result.exit_code == 0
    assert "[[bulbs]]" not in result.stdout


def test_cli_rejects_timeout_not_exceeding_wait() -> None:
    result = runner.invoke(app, ["--wait", "5", "--timeout", "5"])

    assert result.exit_code != 0
    assert "must exceed" in result.output


def test_cli_exits_nonzero_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_discover(broadcast: str, wait: float, timeout: float) -> list:
        raise TimeoutError

    monkeypatch.setattr(discover_mod, "_discover", fake_discover)

    result = runner.invoke(app, ["--wait", "1", "--timeout", "2"])

    assert result.exit_code == 1
    assert "timed out" in result.stderr


def test_cli_exits_nonzero_on_socket_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_discover(broadcast: str, wait: float, timeout: float) -> list:
        raise OSError("network unreachable")

    monkeypatch.setattr(discover_mod, "_discover", fake_discover)

    result = runner.invoke(app, ["--wait", "1", "--timeout", "2"])

    assert result.exit_code == 1
    assert "Discovery failed" in result.stderr


async def test_discover_wraps_call_in_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow_discover_lights(broadcast_space: str, wait_time: float) -> list:
        import asyncio

        await asyncio.sleep(1.0)
        return []

    import pywizlight.discovery

    monkeypatch.setattr(pywizlight.discovery, "discover_lights", slow_discover_lights)

    with pytest.raises(TimeoutError):
        await discover_mod._discover("255.255.255.255", wait=1.0, timeout=0.01)
