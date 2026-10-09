"""Regression checks for generated app deployment defaults.

Test Techniques Used:
- Specification-based: the generated Dockerfile must install from the frozen
  lockfile and compile bytecode during the build.
- Error Guessing: build-only tools must not leak into the runtime image, and a
  scaffolded image must not resolve fresh dependency versions at build time.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_scaffold_dockerfile_compiles_installed_bytecode() -> None:
    """Generated images compile Python bytecode during the build."""
    scaffold = (_REPO_ROOT / "scripts/scaffold-app.sh").read_text(encoding="utf-8")

    assert "--compile-bytecode --no-deps -r /tmp/requirements.txt" in scaffold
    assert "--compile-bytecode --no-deps ./apps/$NAME" in scaffold
    assert "python -m compileall -q -j0" in scaffold
    assert r"\$(python -c" in scaffold
    assert 'sysconfig.get_path("stdlib")' in scaffold


def test_scaffold_dockerfile_ships_neither_uv_nor_pip() -> None:
    """Generated images mount uv for the install step and uninstall pip."""
    scaffold = (_REPO_ROOT / "scripts/scaffold-app.sh").read_text(encoding="utf-8")

    assert "COPY --from=ghcr.io/astral-sh/uv" not in scaffold
    assert "RUN --mount=from=ghcr.io/astral-sh/uv:" in scaffold
    assert "uv pip uninstall --system pip" in scaffold


def test_scaffold_dockerfile_installs_from_the_lockfile() -> None:
    """Generated images install the uv.lock graph, not a fresh PyPI resolve."""
    scaffold = (_REPO_ROOT / "scripts/scaffold-app.sh").read_text(encoding="utf-8")

    assert (
        "uv export --frozen --no-dev --no-emit-workspace --prune rich --package $NAME"
        in scaffold
    )
    assert "ENV TYPER_USE_RICH=0" in scaffold
    assert "RUN uv pip install --system --no-cache --compile-bytecode ./apps" not in (
        scaffold
    )


def test_scaffold_main_parses_the_command_line() -> None:
    """Generated apps answer --help and --version instead of starting (cap-fsh0)."""
    scaffold = (_REPO_ROOT / "scripts/scaffold-app.sh").read_text(encoding="utf-8")

    assert "    app.cli()\n" in scaffold
    assert r"\`\`cli()\`\` rather than" in scaffold
    assert "    app.run()\n" not in scaffold


def test_scaffold_dockerfile_leaves_no_uv_lock_in_app() -> None:
    """Generated images bind-mount the workspace pyproject.toml and uv.lock."""
    scaffold = (_REPO_ROOT / "scripts/scaffold-app.sh").read_text(encoding="utf-8")

    assert "COPY pyproject.toml uv.lock" not in scaffold
    assert "--mount=type=bind,source=uv.lock,target=/app/uv.lock" in scaffold
