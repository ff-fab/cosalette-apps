"""Regression checks for generated app deployment defaults."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_scaffold_dockerfile_compiles_installed_bytecode() -> None:
    """Generated images compile Python bytecode during the build."""
    scaffold = (_REPO_ROOT / "scripts/scaffold-app.sh").read_text(encoding="utf-8")

    assert "--compile-bytecode -r /tmp/requirements.txt" in scaffold
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

    assert "uv export --frozen --no-dev --no-emit-workspace --package $NAME" in scaffold
    assert "RUN uv pip install --system --no-cache --compile-bytecode ./apps" not in (
        scaffold
    )
