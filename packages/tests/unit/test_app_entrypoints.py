"""Cross-app regression tests for the command every app image runs.

Test Techniques Used:
- Error Guessing: an entry point that calls ``app.run()`` instead of
  ``app.cli()`` ignores ``--help`` and ``--version`` and starts the service
  (cap-fsh0): it fails on missing settings, opens a serial port or hangs.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENTRYPOINTS = sorted(
    match.group(1)
    for dockerfile in (_REPO_ROOT / "apps").glob("*/Dockerfile")
    if (
        match := re.search(
            r'(?m)^ENTRYPOINT \["([\w-]+)"\]$', dockerfile.read_text(encoding="utf-8")
        )
    )
)

# Runs the console script the image's ENTRYPOINT names, as the installed
# launcher would, but under this interpreter so no PATH lookup is involved.
_LAUNCH = (
    "import sys; from importlib.metadata import entry_points; "
    "(ep,) = entry_points(group='console_scripts', name=sys.argv[1]); "
    "sys.argv = sys.argv[1:]; ep.load()()"
)


@pytest.mark.unit
def test_every_app_is_covered() -> None:
    """Every app Dockerfile names an ENTRYPOINT the regex finds.

    Technique: Error Guessing — a reformatted ENTRYPOINT would silently skip
    the parametrized check.
    """
    assert len(_ENTRYPOINTS) == len(list((_REPO_ROOT / "apps").glob("*/Dockerfile")))


@pytest.mark.unit
@pytest.mark.parametrize("flag", ["--version", "--help"])
@pytest.mark.parametrize("entrypoint", _ENTRYPOINTS)
def test_entrypoint_answers_cli_flags(
    entrypoint: str, flag: str, tmp_path: Path
) -> None:
    """``<app> --version`` and ``<app> --help`` exit 0 without starting the app.

    Technique: Error Guessing — runs in an empty directory, so no .env
    supplies settings, as ``docker run --rm <image> --help`` does;
    the timeout catches an entry point that starts the service instead.
    """
    result = subprocess.run(  # noqa: S603 — fixed interpreter and argument vector
        [sys.executable, "-c", _LAUNCH, entrypoint, flag],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
