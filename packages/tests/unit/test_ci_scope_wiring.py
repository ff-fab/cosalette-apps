"""CI job scoping contracts (cap-2ydw).

scripts/tests/test_ci_scope.sh covers which paths select which job; these
tests guard the workflow wiring around it, so a skipped job can never turn
into a silent pass.

Test Techniques Used:
- Decision Table: upstream job results versus the ci-gate verdict.
- Error Guessing: a new job left out of ci-gate's needs, a scope output that
  is never exported, CodeQL triggers that drop Python.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

_WORKFLOWS = Path(__file__).resolve().parents[3] / ".github/workflows"
_CI = yaml.safe_load((_WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
_JOBS = _CI["jobs"]


@pytest.mark.unit
def test_ci_gate_needs_every_other_job() -> None:
    """A job missing from ci-gate's needs could fail without blocking a merge."""
    assert set(_JOBS["ci-gate"]["needs"]) == set(_JOBS) - {"ci-gate"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("results", "expected"),
    [
        ({"detect": "success", "root-tests": "skipped"}, 0),
        ({"detect": "skipped", "app-ci": "skipped"}, 0),
        ({"detect": "failure", "app-ci": "skipped"}, 1),
        ({"detect": "success", "root-tests": "cancelled"}, 1),
        ({"detect": "success", "docker-lint": "failure"}, 1),
    ],
)
def test_ci_gate_verdict(results: dict[str, str], expected: int) -> None:
    """Skipped jobs pass; a failed or cancelled job, detect included, fails."""
    step = _JOBS["ci-gate"]["steps"][0]
    needs = {job: {"result": result} for job, result in results.items()}
    result = subprocess.run(  # noqa: S603 — fixed shell, repository script only
        ["bash", "-e", "-c", step["run"]],
        env={**os.environ, "NEEDS": json.dumps(needs)},
        capture_output=True,
        check=False,
    )
    assert result.returncode == expected


@pytest.mark.unit
@pytest.mark.parametrize("job", ["root-tests", "docker-lint"])
def test_scoped_jobs_read_an_exported_scope_output(job: str) -> None:
    """The condition reads a detect output that ci-scope.sh actually sets."""
    output = job.replace("-", "_")
    detect = _JOBS["detect"]
    scope = next(s for s in detect["steps"] if s.get("id") == "scope")

    assert f"needs.detect.outputs.{output} == 'true'" in _JOBS[job]["if"]
    assert detect["outputs"][output] == f"${{{{ steps.scope.outputs.{output} }}}}"
    assert "scripts/ci-scope.sh" in scope["run"]


@pytest.mark.unit
def test_codeql_runs_on_every_python_change() -> None:
    """Push and PR runs trigger on Python; the weekly scan stays unscoped."""
    codeql = yaml.safe_load((_WORKFLOWS / "codeql.yml").read_text(encoding="utf-8"))
    triggers = codeql[True]  # PyYAML reads the bare `on:` key as True

    for event in ("push", "pull_request"):
        assert "**/*.py" in triggers[event]["paths"]
        assert "paths-ignore" not in triggers[event]
    assert "schedule" in triggers
