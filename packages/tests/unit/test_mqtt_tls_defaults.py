"""Cross-app regression tests for the MQTT TLS compatibility override.

Test Techniques Used:
- Specification-based: each upgraded app keeps the documented plaintext default
  unless the deployment opts into TLS explicitly.
- Equivalence Partitioning: default construction, explicit TLS opt-in, and a
  sibling MQTT env var that still exercises nested-model reconstruction.
- Error Guessing: any ``MQTT__*`` sibling used to risk restoring the framework's
  ``tls=True`` default during nested settings rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module

import pytest


@dataclass(frozen=True)
class SettingsSpec:
    """Minimal constructor data for one app's root settings model."""

    module_name: str
    class_name: str
    env_prefix: str
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


_SPECS = [
    pytest.param(
        SettingsSpec(
            module_name="airthings2mqtt.settings",
            class_name="Airthings2MqttSettings",
            env_prefix="AIRTHINGS2MQTT",
            ctor_kwargs={"device_mac": "11:22:33:44:55:66"},
        ),
        id="airthings2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="caldates2mqtt.settings",
            class_name="CalDates2MqttSettings",
            env_prefix="CALDATES2MQTT",
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
        ),
        id="gas2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="jeelink2mqtt.settings",
            class_name="Jeelink2MqttSettings",
            env_prefix="JEELINK2MQTT",
        ),
        id="jeelink2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="suncast.settings",
            class_name="SuncastSettings",
            env_prefix="SUNCAST",
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
        ),
        id="velux2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="vito2mqtt.config",
            class_name="Vito2MqttSettings",
            env_prefix="VITO2MQTT",
            ctor_kwargs={"serial_port": "/dev/ttyUSB0"},
        ),
        id="vito2mqtt",
    ),
    pytest.param(
        SettingsSpec(
            module_name="wallpanel_control.settings",
            class_name="WallpanelControlSettings",
            env_prefix="WALLPANEL_CONTROL",
            ctor_kwargs={"wol_mac": "11:22:33:44:55:66"},
        ),
        id="wallpanel-control",
    ),
    pytest.param(
        SettingsSpec(
            module_name="wiz2mqtt.settings",
            class_name="Wiz2MqttSettings",
            env_prefix="WIZ2MQTT",
            init_kwargs={"_config_file": None},
        ),
        id="wiz2mqtt",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_tls_defaults_to_false_for_plaintext_brokers(
    spec: SettingsSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default TLS remains off until a deployment opts in explicitly.

    Technique: Specification-based — this PR preserves pre-0.7 broker behavior.
    """
    settings = spec.build(monkeypatch)

    assert settings.mqtt.tls is False


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_prefixed_tls_env_var_can_enable_tls(
    spec: SettingsSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The documented per-app ``MQTT__TLS=true`` override still wins.

    Technique: Equivalence Partitioning — explicit opt-in class.
    """
    settings = spec.build(monkeypatch, **{"MQTT__TLS": "true"})

    assert settings.mqtt.tls is True


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_sibling_mqtt_env_var_does_not_restore_tls_true(
    spec: SettingsSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sibling nested MQTT env var must not undo the subclass default.

    Technique: Error Guessing — this is the subtle nested-model reconstruction
    path the compatibility override is protecting.
    """
    settings = spec.build(monkeypatch, **{"MQTT__HOST": "broker.local"})

    assert settings.mqtt.host == "broker.local"
    assert settings.mqtt.tls is False
