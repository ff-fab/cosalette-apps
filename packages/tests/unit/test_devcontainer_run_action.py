"""Regression contracts for the devcontainer-run composite action.

Test Techniques Used:
- Error Guessing: a cache saved before the step that populates it (cap-2m52).
- Error Guessing: the prebuilt-image lookup drifts from what is published
  (cap-wvh8).
- Error Guessing: the CI devcontainer starts dockerd again and hangs
  `devcontainer up` (cap-1a0u).
- Error Guessing: a failed step in the merged per-app check job silently
  skips the checks after it (cap-4fbt).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
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


@pytest.mark.unit
def test_uv_cache_is_restored_and_saved_once_per_job() -> None:
    """Later calls in one job reuse the workspace's .cache/uv (cap-4fbt)."""
    skip = "env.DEVCONTAINER_RUN_UV_CACHE != 'done'"
    assert _steps()[_index("Restore uv cache")]["if"] == skip
    assert skip in _steps()[_index("Save uv cache")]["if"]
    mark = _steps()[_index("Mark uv cache handled for this job")]
    assert _index("Mark uv cache handled for this job") > _index("Save uv cache")
    assert mark["if"] == "always()"
    assert mark["run"].strip() == (
        'echo "DEVCONTAINER_RUN_UV_CACHE=done" >> "$GITHUB_ENV"'
    )


@pytest.mark.unit
def test_ci_devcontainer_replaces_the_dind_entrypoint_with_a_noop() -> None:
    """The prebuilt CI config must not start dockerd (cap-1a0u).

    The target is the docker-in-docker:2 feature's entrypoint; a new major
    version of the feature may move it, so the pin is asserted too.
    """
    ci_dir = _ROOT / ".github/devcontainer-ci"
    config = json.loads((ci_dir / "devcontainer.json").read_text())
    assert config["mounts"] == [
        "source=${localWorkspaceFolder}/.github/devcontainer-ci/docker-init.sh,"
        "target=/usr/local/share/docker-init.sh,type=bind,readonly"
    ]
    shim = ci_dir / "docker-init.sh"
    assert shim.stat().st_mode & 0o111
    code = [line for line in shim.read_text().splitlines() if not line.startswith("#")]
    assert code == ['exec "$@"']
    features = (_ROOT / ".devcontainer/devcontainer.json").read_text()
    assert '"ghcr.io/devcontainers/features/docker-in-docker:2"' in features


@pytest.mark.unit
def test_app_check_job_runs_every_step_after_a_failure() -> None:
    """One failing check must not hide the results of the others (cap-4fbt)."""
    workflow = yaml.safe_load((_ROOT / ".github/workflows/ci-app.yml").read_text())
    steps = workflow["jobs"]["check"]["steps"]
    first = next(
        i
        for i, step in enumerate(steps)
        if step.get("uses") == "./.github/actions/devcontainer-run"
    )
    later = steps[first + 1 :]
    assert later
    assert all(step.get("if") == "${{ !cancelled() }}" for step in later)


@pytest.mark.unit
def test_prebuilt_image_tag_matches_the_published_tag() -> None:
    """The action looks up the content-hash tag devcontainer-build.yml pushes."""
    build = yaml.safe_load(
        (_ROOT / ".github/workflows/devcontainer-build.yml").read_text()
    )
    push = next(
        s for s in build["jobs"]["build"]["steps"] if "imageTag" in s.get("with", {})
    )
    published = push["with"]["imageTag"].split(",")[-1]
    image = _steps()[_index("Select prebuilt devcontainer image")]["env"]["IMAGE"]
    assert image == f"{push['with']['imageName']}:{published}"


@pytest.mark.unit
def test_prebuilt_config_exists_and_runs_the_published_image() -> None:
    """The fast path's config must exist and take its image from the action."""
    select = _steps()[_index("Select prebuilt devcontainer image")]["run"]
    config = re.search(r"config=(\S+)\"", select)
    assert config is not None
    assert "${localEnv:DEVCONTAINER_PREBUILT_IMAGE}" in (_ROOT / config[1]).read_text()


@pytest.mark.unit
def test_root_ci_uses_the_timeout_enabled_unit_task() -> None:
    """Root CI must use the CI task for its per-test hang protection."""
    workflow = yaml.safe_load((_ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["root-tests"]["steps"]
    command = next(
        step["with"]["run-cmd"] for step in steps if "run-cmd" in step.get("with", {})
    )
    assert "task ci:test:unit" in command.split(" && ")


@pytest.mark.unit
@pytest.mark.parametrize("prefix", ["", "gas2mqtt:"])
@pytest.mark.parametrize("name", ["ci:test:unit", "ci:test:integration", "test:unit"])
def test_pytest_timeout_is_enabled_only_in_ci(prefix: str, name: str) -> None:
    """Resolve includes and variables so a template wiring regression is caught."""
    task = shutil.which("task")
    assert task is not None
    result = subprocess.run(  # noqa: S603 — resolved task binary, fixed task names
        [task, "--dry", f"{prefix}{name}"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "pytest" in result.stderr
    if name.startswith("ci:"):
        assert "--timeout=300 --timeout-method=thread" in result.stderr
    else:
        assert "--timeout" not in result.stderr
