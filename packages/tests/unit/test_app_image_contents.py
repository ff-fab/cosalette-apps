"""Cross-app regression tests for what the app images ship.

Test Techniques Used:
- Error Guessing: build-only tools (uv, pip) leaking into the runtime image,
  where they add about 53 MB and nothing uses them.
- Error Guessing: rich, pygments and markdown-it-py (about 14 MB) creeping back
  into the image through a re-resolve, or a Typer CLI crashing without them.
- Error Guessing: bytecode for stdlib modules no app imports.
- Error Guessing: the workspace pyproject.toml and uv.lock left under /app after
  the install step, and local build output uploaded in the build context.
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


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", _APP_DIRS)
def test_dockerfile_ships_without_rich(app_dir: str) -> None:
    """rich and its helpers stay out of the image, and Typer knows it (ADR-013).

    Technique: Error Guessing — without ``--no-deps`` on the locked install, uv
    re-resolves typer's dependencies and pulls the latest rich back in behind
    ``--prune``; without ``TYPER_USE_RICH=0``, a Typer app the image ships
    itself (wiz2mqtt-discover) crashes on ``--help``.
    """
    dockerfile = _REPO_ROOT / "apps" / app_dir / "Dockerfile"
    contents = dockerfile.read_text(encoding="utf-8")

    assert re.search(r"(?m)^\s*uv export [^\n]*--prune rich\b", contents)
    assert "uv pip install --system --no-cache --compile-bytecode --no-deps -r" in (
        contents
    )
    assert re.search(r"(?m)^ENV TYPER_USE_RICH=0$", contents)


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", _APP_DIRS)
def test_dockerfile_skips_bytecode_for_unused_stdlib(app_dir: str) -> None:
    """compileall leaves out the GUI, turtle and pydoc help modules.

    Technique: Error Guessing — no app imports them, yet their .pyc add about
    3.5 MB to every image.
    """
    dockerfile = _REPO_ROOT / "apps" / app_dir / "Dockerfile"
    contents = dockerfile.read_text(encoding="utf-8")

    assert (
        "compileall -q -j0 -x '/(idlelib|tkinter|turtledemo|pydoc_data)/|/turtle\\.py$'"
        in contents
    )


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", _APP_DIRS)
def test_dockerfile_leaves_no_uv_lock_in_app(app_dir: str) -> None:
    """The workspace pyproject.toml and uv.lock are bind-mounted, never copied.

    Technique: Error Guessing — ``COPY pyproject.toml uv.lock ./`` keeps about
    0.5 MB under /app that nothing reads after the install step.
    """
    dockerfile = _REPO_ROOT / "apps" / app_dir / "Dockerfile"
    contents = dockerfile.read_text(encoding="utf-8")

    assert re.search(r"(?im)^\s*COPY\b[^\n]*\buv\.lock\b", contents) is None
    assert re.search(r"(?im)^\s*COPY\s+pyproject\.toml\b", contents) is None
    assert "--mount=type=bind,source=uv.lock,target=/app/uv.lock" in contents
    assert (
        "--mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml" in contents
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "pattern", [".venv/", "apps/*/site/", "**/.cache/", "**/coverage.xml"]
)
def test_dockerignore_excludes_local_output(pattern: str) -> None:
    """Local virtualenv, docs site, caches and coverage stay out of the context.

    Technique: Error Guessing — none of them reach the image, but a local build
    would upload them on every run.
    """
    lines = (_REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert pattern in lines
