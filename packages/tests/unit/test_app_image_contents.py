"""Cross-app regression tests for what the app images ship.

Test Techniques Used:
- Error Guessing: build-only tools (uv, pip) leaking into the runtime image,
  where they add about 53 MB and nothing uses them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_DIRS = sorted(p.parent.name for p in (_REPO_ROOT / "apps").glob("*/Dockerfile"))


@pytest.mark.unit
def test_every_app_is_covered() -> None:
    """The glob finds the app Dockerfiles, so the parametrized test is not empty.

    Technique: Error Guessing — a moved Dockerfile would silently skip the check.
    """
    assert len(_APP_DIRS) >= 9


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", _APP_DIRS)
def test_dockerfile_ships_neither_uv_nor_pip(app_dir: str) -> None:
    """uv is bind-mounted for the install step only and pip is uninstalled.

    Technique: Error Guessing — ``COPY --from=...uv`` keeps a 40 MB binary in
    the final layer; the base image's pip adds another 13 MB.
    """
    dockerfile = _REPO_ROOT / "apps" / app_dir / "Dockerfile"
    contents = dockerfile.read_text(encoding="utf-8")

    assert re.search(r"(?im)^\s*COPY\s+--from=ghcr\.io/astral-sh/uv", contents) is None
    assert re.search(
        r"(?m)^RUN --mount=from=ghcr\.io/astral-sh/uv:[\w.]+,source=/uv,target=/bin/uv",
        contents,
    )
    assert "uv pip uninstall --system pip" in contents
