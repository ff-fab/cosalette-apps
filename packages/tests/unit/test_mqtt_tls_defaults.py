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

_REPO_ROOT = Path(__file__).resolve().parents[3]


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

    def compose_settings(self) -> list[str]:
        """Return the uncommented lines of this app's ``compose.yml``."""
        compose = _REPO_ROOT / "apps" / self.app_dir / "compose.yml"
        return [
            stripped
            for line in compose.read_text(encoding="utf-8").splitlines()
            if (stripped := line.strip()) and not stripped.startswith("#")
        ]


_SPECS = [
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
]


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
def test_compose_declares_the_tls_posture(spec: SettingsSpec) -> None:
    """Every shipped deployment states its transport posture explicitly.

    Technique: Specification-based — ADR-006 moves the posture into deployment
    config. An app whose compose file omits the declaration inherits TLS-on and
    fails to reach the plaintext broker.
    """
    declaration = f"{spec.env_prefix}_MQTT__TLS:"

    assert any(line.startswith(declaration) for line in spec.compose_settings()), (
        f"{spec.app_dir}/compose.yml must declare {declaration} (see ADR-006)"
    )
