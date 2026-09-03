"""Cross-app regression tests for the MQTT transport security posture.

The posture is a per-deployment setting, not an application-code default
(ADR-006). Each app inherits cosalette's TLS-on default and every shipped
deployment declares ``<PREFIX>_MQTT__TLS`` explicitly.

Test Techniques Used:
- Specification-based: no app pins TLS in code; the inherited default stands.
- Equivalence Partitioning: unset env, explicit opt-out, and an opt-out
  accompanied by a sibling ``MQTT__*`` var that exercises nested-model rebuild.
- Error Guessing: nested settings reconstruction is the path that silently
  discards a nested override, so the deployment shape is asserted directly.
- Specification-based: the shipped compose files must carry the declaration the
  ADR relies on — without it an upgrade inherits TLS-on and fails to connect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _shipped_app_dirs() -> set[str]:
    """Return shipped app directories with a first-party compose service."""
    app_dirs: set[str] = set()
    for compose_path in sorted((_REPO_ROOT / "apps").glob("*/compose.yml")):
        compose_doc = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        if not isinstance(compose_doc, dict):
            continue

        services = compose_doc.get("services")
        if not isinstance(services, dict):
            continue

        app_dir = compose_path.parent.name
        service = services.get(app_dir)
        if not isinstance(service, dict):
            continue

        app_dirs.add(app_dir)

    return app_dirs


@dataclass(frozen=True)
class SettingsSpec:
    """Minimal constructor data for one app's root settings model."""

    module_name: str
    class_name: str
    env_prefix: str
    app_dir: str
    ctor_kwargs: dict[str, object] = field(default_factory=dict)
    init_kwargs: dict[str, object] = field(default_factory=dict)

    def build(self, monkeypatch: pytest.MonkeyPatch, **mqtt_env: str) -> object:
        """Construct settings with only the requested MQTT env vars applied."""
        for suffix in ("MQTT__HOST", "MQTT__TLS"):
            monkeypatch.delenv(f"{self.env_prefix}_{suffix}", raising=False)
        for suffix, value in mqtt_env.items():
            monkeypatch.setenv(f"{self.env_prefix}_{suffix}", value)

        settings_cls = getattr(import_module(self.module_name), self.class_name)
        return settings_cls(
            _env_file=None,
            **self.init_kwargs,
            **self.ctor_kwargs,
        )

    def compose_path(self) -> Path:
        """Return this app's shipped compose file."""
        return _REPO_ROOT / "apps" / self.app_dir / "compose.yml"

    def env_example_path(self) -> Path:
        """Return this app's shipped environment template."""
        return _REPO_ROOT / "apps" / self.app_dir / ".env.example"

    def compose_environment(self) -> dict[str, str]:
        """Return this app service's compose environment mapping."""
        compose_doc = yaml.safe_load(self.compose_path().read_text(encoding="utf-8"))
        if not isinstance(compose_doc, dict):
            raise AssertionError(f"{self.compose_path()} must parse to a mapping")

        services = compose_doc.get("services")
        if not isinstance(services, dict):
            raise AssertionError(
                f"{self.compose_path()} must define a services mapping"
            )

        service = services.get(self.app_dir)
        if not isinstance(service, dict):
            raise AssertionError(
                f"{self.compose_path()} must define a {self.app_dir} service"
            )

        environment = service.get("environment")
        if not isinstance(environment, dict):
            raise AssertionError(
                f"{self.compose_path()} must define "
                f"{self.app_dir}.environment as a mapping"
            )

        return {str(key): str(value) for key, value in environment.items()}

    def env_example_settings(self) -> dict[str, str]:
        """Return uncommented settings from this app's ``.env.example``."""
        settings: dict[str, str] = {}
        for line in self.env_example_path().read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", maxsplit=1)
            settings[key] = value
        return settings


_SPEC_MATRIX = (
    pytest.param(
        SettingsSpec(
            module_name="airthings2mqtt.settings",
            class_name="Airthings2MqttSettings",
            env_prefix="AIRTHINGS2MQTT",
            app_dir="airthings2mqtt",
            ctor_kwargs={"device_mac": "11:22:33:44:55:66"},
        ),
        id="airthings2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="caldates2mqtt.settings",
            class_name="CalDates2MqttSettings",
            env_prefix="CALDATES2MQTT",
            app_dir="caldates2mqtt",
            ctor_kwargs={
                "calendars": [
                    {
                        "key": "test",
                        "url": "https://example.com/",
                        "calendar_name": "cal",
                        "username": "u",
                        "password": "p",
                    }
                ]
            },
        ),
        id="caldates2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="gas2mqtt.settings",
            class_name="Gas2MqttSettings",
            env_prefix="GAS2MQTT",
            app_dir="gas2mqtt",
        ),
        id="gas2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="jeelink2mqtt.settings",
            class_name="Jeelink2MqttSettings",
            env_prefix="JEELINK2MQTT",
            app_dir="jeelink2mqtt",
        ),
        id="jeelink2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="suncast.settings",
            class_name="SuncastSettings",
            env_prefix="SUNCAST",
            app_dir="suncast",
            ctor_kwargs={
                "latitude": 52.52,
                "longitude": 13.405,
                "timezone": "Europe/Berlin",
            },
        ),
        id="suncast",
    ),
    pytest.param(
        SettingsSpec(
            module_name="velux2mqtt.settings",
            class_name="Velux2MqttSettings",
            env_prefix="VELUX2MQTT",
            app_dir="velux2mqtt",
        ),
        id="velux2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="vito2mqtt.config",
            class_name="Vito2MqttSettings",
            env_prefix="VITO2MQTT",
            app_dir="vito2mqtt",
            ctor_kwargs={"serial_port": "/dev/ttyUSB0"},
        ),
        id="vito2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="wallpanel_control.settings",
            class_name="WallpanelControlSettings",
            env_prefix="WALLPANEL_CONTROL",
            app_dir="wallpanel-control",
            ctor_kwargs={"wol_mac": "11:22:33:44:55:66"},
        ),
        id="wallpanel-control",
    ),
    pytest.param(
        SettingsSpec(
            module_name="wiz2mqtt.settings",
            class_name="Wiz2MqttSettings",
            env_prefix="WIZ2MQTT",
            app_dir="wiz2mqtt",
            init_kwargs={"_config_file": None},
        ),
        id="wiz2mqtt",
    ),
)

_SPECS = list(_SPEC_MATRIX)
_ENV_EXAMPLE_SPECS = [
    spec for spec in _SPEC_MATRIX if spec.values[0].env_example_path().exists()
]


@pytest.mark.unit
def test_spec_matrix_covers_every_shipped_app() -> None:
    """Every shipped compose deployment with MQTT TLS must be in the matrix."""
    assert {spec.values[0].app_dir for spec in _SPEC_MATRIX} == _shipped_app_dirs()


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_tls_is_not_pinned_in_application_code(
    spec: SettingsSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With nothing configured, cosalette's TLS-on default stands.

    Technique: Specification-based — ADR-006 removed the per-app ``tls=False``
    pins, so an unconfigured app must inherit the framework default rather than
    a local override.
    """
    settings = spec.build(monkeypatch)

    assert settings.mqtt.tls is True


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_deployment_can_opt_out_of_tls(
    spec: SettingsSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The per-deployment ``MQTT__TLS=false`` declaration wins over the default.

    Technique: Equivalence Partitioning — explicit opt-out class. This is the
    setting every shipped compose file carries.
    """
    settings = spec.build(monkeypatch, **{"MQTT__TLS": "false"})

    assert settings.mqtt.tls is False


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_sibling_mqtt_env_var_preserves_configured_tls(
    spec: SettingsSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sibling nested MQTT var must not discard the configured opt-out.

    Technique: Error Guessing — nested-model reconstruction is the path that can
    drop a nested override. This mirrors the real deployment shape, where
    ``MQTT__HOST`` and ``MQTT__TLS`` are always set together.
    """
    settings = spec.build(
        monkeypatch, **{"MQTT__HOST": "broker.local", "MQTT__TLS": "false"}
    )

    assert settings.mqtt.host == "broker.local"
    assert settings.mqtt.tls is False


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_compose_defaults_tls_to_false_without_masking_overrides(
    spec: SettingsSpec,
) -> None:
    """Every shipped deployment keeps a false default without blocking opt-in.

    Technique: Specification-based — ADR-006 moves the posture into deployment
    config. The compose layer must keep the bundled plaintext broker working,
    while still letting `.env` or shell overrides opt back into TLS.
    """
    setting_name = f"{spec.env_prefix}_MQTT__TLS"
    expected_value = f"${{{setting_name}:-false}}"

    assert spec.compose_environment().get(setting_name) == expected_value, (
        f"{spec.app_dir}/compose.yml must set {setting_name} to {expected_value} "
        "(see ADR-006)"
    )


@pytest.mark.unit
@pytest.mark.parametrize("spec", _ENV_EXAMPLE_SPECS)
def test_env_example_defaults_tls_to_false(spec: SettingsSpec) -> None:
    """Every shipped environment template keeps the bundled-broker default visible."""
    setting_name = f"{spec.env_prefix}_MQTT__TLS"

    assert spec.env_example_settings().get(setting_name) == "false", (
        f"{spec.app_dir}/.env.example must set {setting_name}=false (see ADR-006)"
    )
