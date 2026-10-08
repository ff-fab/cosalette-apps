"""Cross-app regression tests for the container health posture (ADR-011)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_DIRS = {
    "airthings2mqtt",
    "caldates2mqtt",
    "gas2mqtt",
    "jeelink2mqtt",
    "suncast",
    "velux2mqtt",
    "vito2mqtt",
    "wallpanel-control",
    "wiz2mqtt",
}
# Apps that ship the native probe. Each app moves here in its epic cap-fjop task;
# when every app is listed, drop the set and require the probe everywhere.
_PROBE_APP_DIRS = {
    "caldates2mqtt",
    "gas2mqtt",
    "jeelink2mqtt",
    "velux2mqtt",
    "vito2mqtt",
    "wallpanel-control",
    "wiz2mqtt",
}

_HEALTHCHECK = re.compile(
    r"(?im)^\s*HEALTHCHECK\s+(?P<options>(?:--\S+\s+(?:\\\s*)?)*)CMD\s+(?P<cmd>\[.*\])\s*$"
)


def _dockerfile(app_dir: str) -> str:
    return (_REPO_ROOT / "apps" / app_dir / "Dockerfile").read_text(encoding="utf-8")


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", sorted(_APP_DIRS - _PROBE_APP_DIRS))
def test_dockerfile_without_probe_until_adopted(app_dir: str) -> None:
    """An app adopts the probe only together with its _PROBE_APP_DIRS entry."""
    contents = _dockerfile(app_dir)

    assert re.search(r"(?im)^\s*HEALTHCHECK(?:\s|$)", contents) is None, (
        f"{app_dir}: add the app to _PROBE_APP_DIRS when it adopts HEALTHCHECK"
    )
    health_file = r"(?im)^\s*(?:ENV|ARG)\s+COSALETTE_HEALTH_FILE\b"
    assert re.search(health_file, contents) is None, (
        f"{app_dir}: add the app to _PROBE_APP_DIRS when it sets COSALETTE_HEALTH_FILE"
    )


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", sorted(_PROBE_APP_DIRS))
def test_dockerfile_ships_native_probe(app_dir: str) -> None:
    """The image probes with the native binary and the ADR-011 defaults."""
    contents = _dockerfile(app_dir)

    assert re.search(
        rf"(?im)^\s*ENV\s+COSALETTE_HEALTH_FILE=/tmp/{re.escape(app_dir)}-health\.json\s*$",
        contents,
    ), f"{app_dir}: set COSALETTE_HEALTH_FILE=/tmp/{app_dir}-health.json"
    match = _HEALTHCHECK.search(contents)
    assert match, f"{app_dir}: HEALTHCHECK must use the exec form CMD [...]"
    options = match["options"].replace("\\\n", " ").split()
    for name, expected in (
        ("--interval=", "--interval=60s"),
        ("--timeout=", "--timeout=5s"),
        ("--retries=", "--retries=3"),
    ):
        actual = [option for option in options if option.startswith(name)]
        assert actual == [expected], (
            f"{app_dir}: HEALTHCHECK needs {expected} exactly once"
        )
    start_periods = [
        option for option in options if option.startswith("--start-period=")
    ]
    assert len(start_periods) == 1, f"{app_dir}: set one per-app --start-period"
    assert not any(
        option == "--max-age" or option.startswith("--max-age=") for option in options
    ), f"{app_dir}: leave --max-age at the framework default"
    cmd = json.loads(match["cmd"])
    assert cmd[0] == "cosalette-health", f"{app_dir}: probe only with cosalette-health"
    assert not any(
        arg == "--max-age" or arg.startswith("--max-age=") for arg in cmd[1:]
    ), f"{app_dir}: leave --max-age at the framework default"
    assert cmd[1:] == [] or cmd[1] == "--fail-on", (
        f"{app_dir}: only a per-app --fail-on override is allowed"
    )
    assert len(cmd[1:]) in (0, 2), f"{app_dir}: --fail-on requires one value"


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", sorted(_APP_DIRS))
def test_compose_services_do_not_configure_healthchecks(app_dir: str) -> None:
    """The image is the single source of the probe; compose must not override it."""
    compose_path = _REPO_ROOT / "apps" / app_dir / "compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose.get("services") if isinstance(compose, dict) else None

    assert isinstance(services, dict), f"{compose_path} must define services"
    for service_name, service in services.items():
        assert isinstance(service, dict), (
            f"{compose_path} service {service_name!r} must be a mapping"
        )
        assert "healthcheck" not in service, (
            f"{compose_path} service {service_name!r} must not define healthcheck"
        )
