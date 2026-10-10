"""Cross-app guard that the image smoke test runs every shipped console script.

Test Techniques Used:
- Error Guessing: a console script added to an app's ``[project.scripts]``
  ships in the image but no CI step runs it there, so a missing runtime
  dependency only shows in production (cap-f19s: wiz2mqtt-openhab without
  PyYAML in 0.2.13).
- Specification-based: the shared ``docker:smoke`` task runs every
  entrypoint's ``--help`` and ``--version`` and the health probe, and CI
  calls it for every app (cap-r352).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_DIRS = sorted(p.parent.name for p in (_REPO_ROOT / "apps").glob("*/Dockerfile"))
_INCLUDES = yaml.safe_load((_REPO_ROOT / "Taskfile.yml").read_text(encoding="utf-8"))[
    "includes"
]


def _entrypoint(app_dir: str) -> str:
    dockerfile = (_REPO_ROOT / "apps" / app_dir / "Dockerfile").read_text("utf-8")
    match = re.search(r'(?m)^ENTRYPOINT \["([\w-]+)"\]$', dockerfile)
    assert match is not None, f"{app_dir}: no ENTRYPOINT"
    return match.group(1)


def _console_scripts(app_dir: str) -> set[str]:
    pyproject = tomllib.loads(
        (_REPO_ROOT / "apps" / app_dir / "pyproject.toml").read_text("utf-8")
    )
    return set(pyproject["project"].get("scripts", {}))


@pytest.mark.unit
def test_every_app_is_covered() -> None:
    """Technique: Error Guessing — a moved Dockerfile would empty the check."""
    assert len(_APP_DIRS) >= 9


@pytest.mark.unit
@pytest.mark.parametrize("app_dir", _APP_DIRS)
def test_smoke_runs_every_console_script(app_dir: str) -> None:
    """Every script besides the entrypoint has a ``SMOKE`` run in its image.

    Technique: Error Guessing — the entrypoint is covered by the shared
    ``--help``/``--version`` steps; any further script needs its own line.
    """
    smoke = _INCLUDES[app_dir].get("vars", {}).get("SMOKE", "")
    others = _console_scripts(app_dir) - {_entrypoint(app_dir)}

    missing = {s for s in others if f"--entrypoint {s} " not in smoke}

    assert not missing, f"{app_dir}: add {sorted(missing)} to SMOKE in Taskfile.yml"


@pytest.mark.unit
def test_shared_smoke_task_runs_the_entrypoint_and_the_probe() -> None:
    """Technique: Specification-based — the shared steps every app gets."""
    tasks = yaml.safe_load(
        (_REPO_ROOT / "taskfiles" / "PythonApp.yml").read_text(encoding="utf-8")
    )["tasks"]
    cmds = "\n".join(tasks["docker:smoke"]["cmds"])

    assert '"$IMAGE" --help' in cmds
    assert '"$IMAGE" --version' in cmds
    assert '--entrypoint cosalette-health "$IMAGE" --help' in cmds
    assert "{{.SMOKE" in cmds
    assert "pipefail" in tasks["docker:smoke"]["set"]


@pytest.mark.unit
def test_ci_runs_the_smoke_task_on_the_built_image() -> None:
    """Technique: Specification-based — CI loads the image and smoke-tests it."""
    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github" / "workflows" / "ci-app.yml").read_text("utf-8")
    )
    steps = workflow["jobs"]["image-smoke"]["steps"]
    build = next(s for s in steps if "docker/build-push-action" in s.get("uses", ""))
    runs = "\n".join(s.get("run", "") for s in steps)

    assert build["with"]["load"] is True
    assert build["with"]["push"] is False
    assert build["with"]["tags"] == "${{ inputs.app }}:smoke"
    assert 'task "$APP:docker:smoke" IMAGE="$APP:smoke"' in runs
