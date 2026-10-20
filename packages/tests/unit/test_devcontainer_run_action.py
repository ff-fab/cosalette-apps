"""Regression contracts for the devcontainer-run composite action.

Test Techniques Used:
- Error Guessing: a cache saved before the step that populates it (cap-2m52).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_ACTION = _ROOT / ".github/actions/devcontainer-run/action.yml"


def _steps() -> list[dict]:
    return yaml.safe_load(_ACTION.read_text())["runs"]["steps"]


def _index(name: str) -> int:
    return next(i for i, step in enumerate(_steps()) if step["name"] == name)


@pytest.mark.unit
def test_uv_cache_saved_after_the_run_populates_it() -> None:
    """Saving before `uv sync` runs would store only the fallback content."""
    assert _index("Save uv cache") > _index("Run command in devcontainer")
    assert _steps()[_index("Save uv cache")]["if"].startswith("always()")


@pytest.mark.unit
def test_uv_cache_restore_has_no_implicit_post_save() -> None:
    """actions/cache would save a second time in its post step."""
    restore = _steps()[_index("Restore uv cache")]
    assert restore["uses"].startswith("actions/cache/restore@")
