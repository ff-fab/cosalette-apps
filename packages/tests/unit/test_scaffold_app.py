"""Regression checks for generated app deployment defaults."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_scaffold_dockerfile_compiles_installed_bytecode() -> None:
    """Generated images compile Python bytecode during the build."""
    scaffold = (_REPO_ROOT / "scripts/scaffold-app.sh").read_text(encoding="utf-8")

    assert "--compile-bytecode ./apps/$NAME" in scaffold
    assert "python -m compileall -q -j0" in scaffold
    assert r"\$(python -c" in scaffold
    assert 'sysconfig.get_path("stdlib")' in scaffold
