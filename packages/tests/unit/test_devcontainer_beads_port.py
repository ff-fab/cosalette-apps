"""Regression contract for the pinned beads dolt sql-server port.

bd >= 1.3 ranks the local, often stale ``.beads/dolt/config.yaml`` ``listener.port``
above ``dolt.port`` and ``dolt_server_port``. Only ``BEADS_DOLT_SERVER_PORT`` outranks
it, so the devcontainer must set it, and the fallbacks must agree with it.

Test Techniques Used:
- Error Guessing: dropping the variable, or moving it to ``remoteEnv`` (which
  ``docker exec`` sessions and post-start do not see), brings back port drift
  (cap-fp5u) silently.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]


def _devcontainer() -> dict:
    text = (_ROOT / ".devcontainer/devcontainer.json").read_text()
    return json.loads(re.sub(r"(?m)^\s*//.*$", "", text))


@pytest.mark.unit
def test_beads_port_pinned_in_container_env_and_matches_fallbacks() -> None:
    config = _devcontainer()
    port = config["containerEnv"]["BEADS_DOLT_SERVER_PORT"]
    assert "BEADS_DOLT_SERVER_PORT" not in config.get("remoteEnv", {})

    metadata = json.loads((_ROOT / ".beads/metadata.json").read_text())
    beads_config = (_ROOT / ".beads/config.yaml").read_text()
    yaml_port = re.search(r"(?m)^dolt\.port:\s*(\d+)\s*$", beads_config)

    assert yaml_port is not None
    assert port == str(metadata["dolt_server_port"]) == yaml_port.group(1)
