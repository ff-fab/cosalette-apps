"""Shared helpers for the per-app HA discovery integration tests.

Every app's ``packages/tests/integration/test_schema_discovery.py`` runs
``cosalette schema ha-discovery`` against its committed ``docs/schema.yaml``
and asserts on the payloads. The subprocess call, the failure reporting and
the bridge filtering were byte-identical in seven apps, and PR #250 had to
edit all seven in one pass — the kind of change that drifts next time. They
live here once instead (cap-51s).

Apps reach this module through ``pythonpath = ["../../packages/tests/fixtures"]``
in their ``[tool.pytest.ini_options]``; the monorepo shares one uv venv, so no
packaging change is involved.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BRIDGE_OBJECT_ID = "bridge"
"""Object id of the synthetic per-app bridge entity (ADR-058)."""

_INHERITED_ENV_VARS = ("PATH", "PYTHONPATH", "HOME", "VIRTUAL_ENV")


def run_ha_discovery(schema_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the schema ha-discovery CLI once and return the completed process.

    ``check=False`` so a non-zero exit surfaces as one named assertion failure
    with the CLI's stderr attached. Under ``check=True`` the raised
    ``CalledProcessError`` renders only "returned non-zero exit status 1" and
    the sentence naming the offending channels is lost in the unread
    ``.stderr`` — and because callers scope this to a module, every test in the
    module would ERROR instead of one FAILing with the reason.

    Use this directly only when a non-zero exit or an empty payload list is the
    expected outcome; otherwise call :func:`load_ha_discovery_payloads`.
    """
    return subprocess.run(
        [sys.executable, "-m", "cosalette", "schema", "ha-discovery", str(schema_path)],
        capture_output=True,
        text=True,
        check=False,
        env={k: os.environ[k] for k in _INHERITED_ENV_VARS if k in os.environ},
    )


def parse_ha_discovery(
    result: subprocess.CompletedProcess[str],
) -> list[dict[str, Any]]:
    """Assert the CLI succeeded and return the payloads it emitted."""
    assert result.returncode == 0, (
        f"ha-discovery exited {result.returncode}:\n{result.stderr}"
    )
    payloads: list[dict[str, Any]] = json.loads(result.stdout)
    assert payloads, "ha-discovery CLI returned no payloads"
    return payloads


def load_ha_discovery_payloads(schema_path: Path) -> list[dict[str, Any]]:
    """Run the schema ha-discovery CLI once and return the parsed payloads."""
    return parse_ha_discovery(run_ha_discovery(schema_path))


def entities_without_bridge(
    payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the app's own entity payloads, without the bridge.

    cosalette 0.6.2 (ADR-058) emits one synthetic per-app ``bridge``
    binary_sensor so Home Assistant materialises the device every real entity
    links to via ``via_device``. It is framework plumbing rather than an app
    entity, so apps assert it in its own test and keep it out of their
    per-entity expectations.
    """
    return [p for p in payloads if p["config"]["object_id"] != BRIDGE_OBJECT_ID]


def configs_by_object_id(
    payloads: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index discovery payload configs by their object_id."""
    object_ids = [p["config"]["object_id"] for p in payloads]
    dupes = [x for x, count in Counter(object_ids).items() if count > 1]
    assert not dupes, f"Duplicate object_ids emitted: {dupes}"
    return {p["config"]["object_id"]: p["config"] for p in payloads}
