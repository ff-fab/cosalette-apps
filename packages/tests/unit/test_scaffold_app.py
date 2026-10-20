"""Regression checks for generated app deployment defaults.

Test Techniques Used:
- Specification-based: the generated Dockerfile must install from the frozen
  lockfile and compile bytecode during the build.
- Error Guessing: build-only tools must not leak into the runtime image, and a
  scaffolded image must not resolve fresh dependency versions at build time.
"""

from __future__ import annotations

import re
import subprocess
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
    assert re.search(r"(?m)^ENV TYPER_USE_RICH", scaffold) is None
    assert 'dev = ["cosalette[schema]>=0.12.1,<0.13"]' in scaffold
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


def test_scaffold_compose_preserves_tls_default_and_override() -> None:
    """Render the heredoc in isolation to catch shell interpolation mistakes."""
    scaffold = (_REPO_ROOT / "scripts/scaffold-app.sh").read_text(encoding="utf-8")
    template = scaffold.split('cat > "$APP/compose.yml" <<EOF\n', 1)[1].split(
        "\nEOF", 1
    )[0]
    rendered = subprocess.run(
        ["bash", "-eu", "-c", f"cat <<EOF\n{template}\nEOF"],
        env={"NAME": "example", "PKG_NAME": "example", "ENV_PREFIX": "EXAMPLE"},
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "EXAMPLE_MQTT__HOST: mosquitto" in rendered
    tls_setting = "${EXAMPLE_MQTT__TLS:-false}"
    assert f"EXAMPLE_MQTT__TLS: {tls_setting}" in rendered
    for override, expected in [(None, "false"), ("true", "true")]:
        interpolated = subprocess.run(
            ["bash", "-eu", "-c", f'echo "{tls_setting}"'],
            env={} if override is None else {"EXAMPLE_MQTT__TLS": override},
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert interpolated == expected
