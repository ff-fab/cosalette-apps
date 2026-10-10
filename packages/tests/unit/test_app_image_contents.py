"""Cross-app regression tests for what the app images ship.

Test Techniques Used:
- Error Guessing: build-only tools (uv, pip) leaking into the runtime image,
  where they add about 53 MB and nothing uses them.
- Error Guessing: rich, pygments and markdown-it-py (about 14 MB) creeping back
  into the image through a re-resolve, or a Typer CLI crashing without them.
- Error Guessing: the cosalette[schema] extra (PyYAML, jsonschema; about
  5.7 MB) returning as a runtime dependency, though only the schema tasks use it.
- Error Guessing: bytecode for stdlib modules no app imports.
- Error Guessing: the workspace pyproject.toml and uv.lock left under /app after
  the install step, and local build output uploaded in the build context.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_DIRS = sorted(p.parent.name for p in (_REPO_ROOT / "apps").glob("*/Dockerfile"))

# Runtime packages the cosalette[schema] extra brings in, which the apps keep in
# their dev group only (ADR-004). Apps that need one at runtime, with the reason.
_SCHEMA_EXTRA_PACKAGES = frozenset({"jsonschema", "pyyaml"})
_SCHEMA_EXTRA_ALLOWED = {
    "caldates2mqtt": {"pyyaml"},  # caldav depends on it
    "suncast": {"pyyaml"},  # the geometry loader reads YAML
}


def _builds_own_typer_cli(app_dir: str) -> bool:
    sources = (_REPO_ROOT / "apps" / app_dir / "packages" / "src").rglob("*.py")
    return any(
        re.search(
            r"(?m)^\s*(?:import\s+typer\b|from\s+typer\s+import\b)",
            p.read_text(encoding="utf-8"),
        )
        is not None
        for p in sources
    )


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
    """rich and its helpers stay out of the image (ADR-013).

    Technique: Error Guessing — without ``--no-deps`` on the locked install, uv
    re-resolves typer's dependencies and pulls the latest rich back in behind
    ``--prune``.
    """
    dockerfile = _REPO_ROOT / "apps" / app_dir / "Dockerfile"
    contents = dockerfile.read_text(encoding="utf-8")

    assert re.search(r"(?m)^\s*uv export [^\n]*--prune rich\b", contents)
    assert "uv pip install --system --no-cache --compile-bytecode --no-deps -r" in (
        contents
    )


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", _APP_DIRS)
def test_dockerfile_sets_typer_use_rich_only_for_own_typer_cli(app_dir: str) -> None:
    """``TYPER_USE_RICH=0`` is set exactly where the app builds a Typer CLI (ADR-013).

    Technique: Error Guessing — cosalette's own CLIs fall back to plain Click
    without rich, but a ``typer.Typer()`` the app builds itself
    (wiz2mqtt-discover) crashes on ``--help`` without the variable.
    """
    dockerfile = _REPO_ROOT / "apps" / app_dir / "Dockerfile"
    contents = dockerfile.read_text(encoding="utf-8")

    has_env = re.search(r"(?m)^ENV TYPER_USE_RICH=0$", contents) is not None
    assert has_env is _builds_own_typer_cli(app_dir)


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", _APP_DIRS)
def test_runtime_export_omits_schema_extra(app_dir: str) -> None:
    """The image's locked graph carries no PyYAML or jsonschema (ADR-004).

    Technique: Error Guessing — ``cosalette[schema]`` back in ``dependencies``
    ships about 5.7 MB that only the schema:* tasks use; it belongs in the dev
    group. Runs the same ``uv export`` the Dockerfile runs.
    """
    uv = shutil.which("uv")
    assert uv is not None
    export = subprocess.run(  # noqa: S603 — resolved uv binary, fixed arguments
        [
            uv,
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-workspace",
            "--package",
            app_dir,
            "--format",
            "requirements-txt",
            "--no-header",
            "--no-hashes",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=_REPO_ROOT,
    ).stdout
    shipped = set(re.findall(r"(?m)^([\w.-]+)==", export)) & _SCHEMA_EXTRA_PACKAGES

    assert shipped == _SCHEMA_EXTRA_ALLOWED.get(app_dir, set())


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
