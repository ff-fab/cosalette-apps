"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

``app.device`` is registered with a callable ``name=`` (``_cover_map`` in
:mod:`velux2mqtt.main`, keyed off user-configured ``settings.covers``). A
plain ``cosalette schema init``/``check`` would collapse every real per-cover
device (``blind``, ``window``, ...) into a single channel named after the
Python handler's qualname (``cover_device``), which is why
``task velux2mqtt:schema:generate`` instead runs ``cosalette schema dump
--resolve-settings`` (ADR-051) against the checked-in ``.env.schema``
profile before writing ``docs/schema.yaml`` — expanding the NameSpec into
real per-cover channels (``blindState``, ``windowState``, ...). With those
real channels, ``CoverState.position``'s ``x-cosalette-consumer`` annotation
(see :class:`velux2mqtt.devices.cover.CoverState`) now produces one discovery
payload per configured cover, with ``state_topic`` matching the real runtime
topic (``velux2mqtt/{cover.name}/state``, e.g. ``velux2mqtt/blind/state`` —
see ``docs/mqtt-topics.md``) rather than the qualname channel
``velux2mqtt/cover_device/state`` that produced a phantom entity before this
fix (cap-hze).

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: every payload must describe a real, currently
  configured cover with a matching real runtime state_topic
- Regression guard: no payload may ever target the qualname channel address
  (``velux2mqtt/cover_device/state``) — the phantom entity this test suite
  was written to prevent (cap-hze)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# packages/tests/integration/<file> → app root is parents[3]
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schema.yaml"


@pytest.fixture(scope="module")
def ha_payloads() -> list[dict[str, Any]]:
    """Run the schema ha-discovery CLI once and return the parsed payloads."""
    result = subprocess.run(
        [sys.executable, "-m", "cosalette", "schema", "ha-discovery", str(SCHEMA_PATH)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


# Real runtime state topics follow velux2mqtt/{cover}/state (docs/mqtt-topics.md).
# The qualname collapse this test guards against would instead produce
# velux2mqtt/cover_device/state — never a real per-cover topic.
_REAL_STATE_TOPIC_RE = re.compile(r"^velux2mqtt/(?!cover_device/)[^/]+/state$")


@pytest.mark.integration
class TestHaDiscoveryGeneration:
    """Verify HA MQTT discovery generation emits real, per-cover entities."""

    def test_generates_one_payload_per_configured_cover(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """One discovery payload is generated per cover in .env.schema.

        ``docs/schema.yaml`` is generated via ``cosalette schema dump
        --resolve-settings`` against the checked-in ``.env.schema`` profile
        (``task velux2mqtt:schema:generate``), which expands the
        ``_cover_map`` NameSpec into real per-cover channels. This test
        pins the count to that profile's two covers (``blind``, ``window``);
        update it alongside ``.env.schema`` if the profile's cover count
        changes.

        Technique: Specification-based — the resolved schema must yield
        exactly one HA entity per configured cover.
        """
        assert len(ha_payloads) == 2

    def test_payload_state_topic_must_be_real(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Regression guard: every payload must target a real runtime topic.

        Every payload's ``state_topic`` must match a real per-cover runtime
        topic — never the qualname channel address
        ``velux2mqtt/cover_device/state`` that produced a phantom entity
        before this fix (cap-hze).

        Technique: Error Guessing — anticipating the exact regression this
        test suite exists to prevent.
        """
        for payload in ha_payloads:
            state_topic = payload["config"].get("state_topic", "")
            assert _REAL_STATE_TOPIC_RE.match(state_topic), (
                f"state_topic {state_topic!r} does not match a real "
                "velux2mqtt/{cover}/state runtime topic"
            )
