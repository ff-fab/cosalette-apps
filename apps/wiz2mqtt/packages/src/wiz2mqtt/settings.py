"""Application settings for wiz2mqtt.

Extends cosalette's Settings with the WIZ2MQTT_ environment prefix. All
settings are loaded from environment variables, .env files, or a TOML
config file (bulb inventory only). Priority: CLI > env > .env >
wiz2mqtt.toml > defaults.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Literal

import cosalette
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict


class BulbConfig(BaseModel):
    """Configuration for a single WiZ bulb.

    ``ip`` is the bulb's identity; ``mac``, when given, is used to verify
    that identity against the bulb's own reported MAC on first contact.
    """

    name: str
    ip: str
    mac: str | None = None
    when_unreachable: Literal["unavailable", "off"] = "unavailable"

    @field_validator("name")
    @classmethod
    def _name_must_be_valid_topic_segment(cls, value: str) -> str:
        """Reject names that would form invalid MQTT topic segments."""
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError(
                "Bulb name must be a non-empty MQTT topic segment "
                "matching [A-Za-z0-9_-]+ (no '/', '+', '#', whitespace, "
                "or control chars)"
            )
        return value

    @field_validator("ip")
    @classmethod
    def _ip_must_be_valid_ipv4(cls, value: str) -> str:
        """Reject anything that isn't a literal IPv4 address."""
        try:
            ipaddress.IPv4Address(value)
        except ValueError as exc:
            msg = f"Bulb ip must be a valid IPv4 address, got {value!r}"
            raise ValueError(msg) from exc
        return value

    @field_validator("mac")
    @classmethod
    def _mac_must_be_bare_hex(cls, value: str | None) -> str | None:
        """Reject anything but a bare 12-hex-char MAC, normalized to lowercase.

        WiZ devices report MAC as a bare hex string with no separators
        (pywizlight's ``PilotParser.get_mac()`` passes the device's own
        "mac" field through unchanged) — matching that format here means
        identity verification against the reported MAC is a plain
        case-insensitive string comparison.
        """
        if value is None:
            return value
        if not re.fullmatch(r"[0-9A-Fa-f]{12}", value):
            msg = (
                "Bulb mac must be 12 hex characters with no separators "
                f"(e.g. 'a8bb5006033d'), got {value!r}"
            )
            raise ValueError(msg)
        return value.lower()


class Wiz2MqttSettings(cosalette.Settings):
    """wiz2mqtt application settings."""

    model_config = SettingsConfigDict(
        env_prefix="WIZ2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        # config_file is a cosalette runtime convention read via
        # model_config.get("config_file") — pydantic_settings' own
        # SettingsConfigDict TypedDict doesn't declare this key.
        config_file="wiz2mqtt.toml",  # type: ignore
        # Safe to tighten from the base Settings' extra="ignore": env_prefix
        # is set, so only WIZ2MQTT_* env vars are ever seen. This also
        # rejects any TOML top-level key other than "bulbs" — the config-file
        # source merges the whole parsed file the same way env vars merge.
        extra="forbid",
    )

    bulbs: list[BulbConfig] = Field(
        default_factory=list,
        description="WiZ bulb inventory, normally supplied via wiz2mqtt.toml.",
    )

    @model_validator(mode="after")
    def _bulbs_unique_names(self) -> Wiz2MqttSettings:
        names = [b.name for b in self.bulbs]
        if len(set(names)) != len(names):
            dupes = {n for n in names if names.count(n) > 1}
            msg = f"Bulb names must be unique, duplicates: {dupes}"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _bulbs_unique_identity(self) -> Wiz2MqttSettings:
        ips = [b.ip for b in self.bulbs]
        if len(set(ips)) != len(ips):
            dupes = {ip for ip in ips if ips.count(ip) > 1}
            msg = f"Bulb ip addresses must be unique, duplicates: {dupes}"
            raise ValueError(msg)

        macs = [b.mac for b in self.bulbs if b.mac is not None]
        if len(set(macs)) != len(macs):
            dupes = {mac for mac in macs if macs.count(mac) > 1}
            msg = f"Bulb mac addresses must be unique, duplicates: {dupes}"
            raise ValueError(msg)
        return self
