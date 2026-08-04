"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

``app.device`` is registered with a callable ``name=`` (``_cover_map`` in
:mod:`velux2mqtt.main`, keyed off user-configured ``settings.covers``), so
cosalette's static schema pipeline collapses every real per-cover device
(``blind``, ``window``, ...) into a single channel named after the Python
handler's qualname (``cover_device``). ``CoverState.position`` therefore
carries **no** ``x-cosalette-consumer`` annotation (see the docstring on
:class:`velux2mqtt.devices.cover.CoverState`) — annotating it would make
``cosalette schema ha-discovery`` emit a discovery payload whose
``state_topic`` (``velux2mqtt/cover_device/state``) matches no topic any
running cover actually publishes to (real topics are
``velux2mqtt/{cover.name}/state``, e.g. ``velux2mqtt/blind/state`` — see
``docs/mqtt-topics.md``), registering a permanently-unavailable phantom
entity in Home Assistant. This test guards against that regression by
asserting zero payloads are generated today, and — should that ever change
(e.g. once cosalette's schema pipeline resolves callable-``name=``
NameSpecs to per-instance channels) — that every payload's ``state_topic``
actually matches a real per-cover topic pattern.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: HA discovery is currently non-functional for velux2mqtt
  (callable-name devices collapse to a qualname channel); 0 payloads is correct
- Regression guard: any future payload's state_topic must match a real runtime
  topic (``velux2mqtt/{cover}/state``), never the qualname channel address
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
    """Verify HA MQTT discovery generation does not emit a phantom entity."""

    def test_generates_no_payloads_today(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """No discovery payloads are generated while covers use a callable name=.

        ``app.device(name=_cover_map, ...)`` collapses every real per-cover
        device into one qualname-based channel (``cover_device``), so
        ``CoverState.position`` intentionally carries no
        ``x-cosalette-consumer`` annotation (see
        ``velux2mqtt.devices.cover.CoverState``). Generating a payload here
        would point ``state_topic`` at a topic no cover ever publishes to,
        registering a permanently-unavailable phantom entity in Home
        Assistant. This is the honest current state, not a bug — HA
        discovery for velux2mqtt is non-functional until cosalette's schema
        pipeline resolves callable-``name=`` NameSpecs to per-instance
        channels (see ``apps/velux2mqtt/README.md``).

        Technique: Specification-based — the model-driven schema must not
        yield an HA entity while the underlying topic can't be known statically.
        """
        assert ha_payloads == []

    def test_any_future_payload_state_topic_must_be_real(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Regression guard: any generated payload must target a real topic.

        If ``CoverState.position`` ever regains a consumer annotation (e.g.
        after the upstream settings-aware schema pipeline lands and this
        test starts failing above), every payload's ``state_topic`` must
        match a real per-cover runtime topic — never the qualname channel
        address ``velux2mqtt/cover_device/state``.

        Technique: Error Guessing — anticipating the exact regression this
        test suite exists to prevent.
        """
        for payload in ha_payloads:
            state_topic = payload["config"].get("state_topic", "")
            assert _REAL_STATE_TOPIC_RE.match(state_topic), (
                f"state_topic {state_topic!r} does not match a real "
                "velux2mqtt/{cover}/state runtime topic"
            )
