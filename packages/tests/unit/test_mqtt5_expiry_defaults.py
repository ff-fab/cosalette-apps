"""Cross-app regression tests for the MQTT 5 retained-expiry posture (ADR-009).

Each opted-in app inherits cosalette's MQTT 3.1.1 default in code and every
shipped compose file declares ``<PREFIX>_MQTT__PROTOCOL_VERSION`` next to the
broker host, defaulting it to ``5`` for the bundled mosquitto 2 broker. The
wire behaviour (expiry property, refresh ledger) is asserted per app in
``test_mqtt5_expiry.py``; this module asserts the deployment declaration that
decides which of the two behaviours an operator gets.

Apps join ``_MQTT5_APP_DIRS`` as their adoption task lands (epic cap-pnjx).

Test Techniques Used:
- Specification-based: the compose declaration, the resolved settings and the
  bundled broker image agree on MQTT 5.
- Equivalence Partitioning: compose default, explicit MQTT 3.1.1 fallback, and
  an expiry interval that is only valid under MQTT 5.
- Error Guessing: an expiry interval under MQTT 3.1.1 would be silently
  ignored, so cosalette rejects it; the fallback must not trip that check.
"""

from __future__ import annotations

import re

import pytest
import yaml
from test_mqtt_tls_defaults import _SPEC_MATRIX, SettingsSpec

_MQTT5_APP_DIRS = {"airthings2mqtt", "caldates2mqtt", "gas2mqtt"}
_SPECS = [
    pytest.param(spec.values[0], id=spec.id)
    for spec in _SPEC_MATRIX
    if spec.values[0].app_dir in _MQTT5_APP_DIRS
]
_DEFAULT_EXPIRY_SECONDS = 86_400


def _build(
    spec: SettingsSpec, monkeypatch: pytest.MonkeyPatch, **mqtt_env: str
) -> object:
    for suffix in ("MQTT__PROTOCOL_VERSION", "MQTT__MESSAGE_EXPIRY_INTERVAL"):
        monkeypatch.delenv(f"{spec.env_prefix}_{suffix}", raising=False)
    return spec.build(monkeypatch, **mqtt_env)


@pytest.mark.unit
def test_every_mqtt5_app_is_in_the_spec_matrix() -> None:
    """A renamed or removed app must not silently drop out of this module."""
    assert {spec.values[0].app_dir for spec in _SPECS} == _MQTT5_APP_DIRS


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_mqtt5_is_not_pinned_in_application_code(
    spec: SettingsSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With nothing configured, the framework's MQTT 3.1.1 default stands.

    Technique: Specification-based — the opt-in is a deployment declaration, so
    a bare process (tests, ``uv run``, an external broker) stays on 3.1.1.
    """
    settings = _build(spec, monkeypatch)

    assert settings.mqtt.protocol_version == "3.1.1"


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_compose_defaults_to_mqtt5_without_masking_overrides(
    spec: SettingsSpec,
) -> None:
    """The compose default is 5, and `.env` or the shell can still override it.

    Technique: Specification-based — same interpolation shape as ADR-006's TLS
    declaration, so the bundled mosquitto 2 broker gets expiry by default and a
    3.1.1-only broker has a one-line fallback.
    """
    setting_name = f"{spec.env_prefix}_MQTT__PROTOCOL_VERSION"
    expected_value = f"${{{setting_name}:-5}}"

    assert spec.compose_environment().get(setting_name) == expected_value, (
        f"{spec.app_dir}/compose.yml must set {setting_name} to {expected_value} "
        "(see ADR-009)"
    )


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_compose_default_resolves_to_mqtt5_with_a_24_hour_expiry(
    spec: SettingsSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The compose default yields MQTT 5 and the documented expiry contract.

    Technique: Equivalence Partitioning — the default class. The 86 400 s expiry
    means retained topics are refreshed every 8 h; the docs state both figures.
    """
    declared = spec.compose_environment()[f"{spec.env_prefix}_MQTT__PROTOCOL_VERSION"]
    default = re.fullmatch(r"\$\{[A-Z0-9_]+:-(.+)\}", declared)
    assert default is not None

    settings = _build(spec, monkeypatch, **{"MQTT__PROTOCOL_VERSION": default[1]})

    assert settings.mqtt.protocol_version == "5"
    assert settings.mqtt.message_expiry_interval == _DEFAULT_EXPIRY_SECONDS


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_operator_can_fall_back_to_mqtt_311(
    spec: SettingsSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`PROTOCOL_VERSION=3.1.1` is the documented fallback for an old broker.

    Technique: Error Guessing — cosalette rejects an expiry interval under
    MQTT 3.1.1, so the fallback must resolve without one being set.
    """
    settings = _build(spec, monkeypatch, **{"MQTT__PROTOCOL_VERSION": "3.1.1"})

    assert settings.mqtt.protocol_version == "3.1.1"


@pytest.mark.unit
@pytest.mark.parametrize("spec", _SPECS)
def test_bundled_broker_supports_mqtt5(spec: SettingsSpec) -> None:
    """The bundled broker image is mosquitto 2 or newer, which speaks MQTT 5.

    Technique: Specification-based — mosquitto 1.x is MQTT 3.1.1 only, so a
    downgrade of the image tag would break the compose default.
    """
    compose = yaml.safe_load(spec.compose_path().read_text(encoding="utf-8"))
    image = compose["services"]["mosquitto"]["image"]

    match = re.fullmatch(r"eclipse-mosquitto:(\d+)(?:\..+)?", image)
    assert match is not None, f"unexpected broker image {image!r}"
    assert int(match[1]) >= 2
