"""Cross-app regression tests for the MQTT-only container health posture (ADR-010)."""

from __future__ import annotations

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


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", sorted(_APP_DIRS))
def test_dockerfile_does_not_configure_container_health(app_dir: str) -> None:
    """MQTT is the health signal; images must not define a Docker health probe."""
    dockerfile = _REPO_ROOT / "apps" / app_dir / "Dockerfile"
    contents = dockerfile.read_text(encoding="utf-8")

    assert re.search(r"(?im)^\s*HEALTHCHECK(?:\s|$)", contents) is None, (
        f"{dockerfile} must not define HEALTHCHECK"
    )
    health_file = r"(?im)^\s*(?:ENV|ARG)\s+COSALETTE_HEALTH_FILE\b"
    assert re.search(health_file, contents) is None, (
        f"{dockerfile} must not set COSALETTE_HEALTH_FILE"
    )


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", sorted(_APP_DIRS))
def test_compose_services_do_not_configure_healthchecks(app_dir: str) -> None:
    """No shipped compose service may override the MQTT health signal."""
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
