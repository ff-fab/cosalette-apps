"""Shared settings builder for wiz2mqtt tests."""

from __future__ import annotations

from collections.abc import Sequence

from wiz2mqtt.settings import Wiz2MqttSettings


def build_settings(
    bulbs: Sequence[dict[str, object]] = (),
    power_sources: Sequence[dict[str, object]] = (),
) -> Wiz2MqttSettings:
    """Isolated settings that ignore any host ``.env`` or config file."""
    return Wiz2MqttSettings(
        bulbs=list(bulbs),
        power_sources=list(power_sources),
        _env_file=None,
        _config_file=None,
    )  # type: ignore[arg-type,call-arg]
