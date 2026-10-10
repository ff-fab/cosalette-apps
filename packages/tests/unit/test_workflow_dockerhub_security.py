"""Workflow credential and docs discovery regression contracts.

Test Techniques Used:
- Decision Table: optional credentials are complete, missing, or partial.
- Error Guessing: PR-controlled actions receive long-lived credentials.
- Equivalence Partitioning: valid app slugs versus shell and YAML metacharacters.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOWS = _ROOT / ".github/workflows"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("ref", "event", "expected"),
    [
        ("refs/heads/main", "push", 0),
        ("refs/heads/main", "workflow_dispatch", 0),
        ("refs/pull/362/merge", "pull_request", 1),
        ("refs/heads/main", "pull_request_target", 1),
        ("refs/heads/feature", "workflow_dispatch", 1),
        ("refs/heads/main", "schedule", 1),
    ],
)
def test_dockerhub_handoff_allowlist_rejects_untrusted_events(
    ref: str, event: str, expected: int
) -> None:
    """Execute the handoff predicate with secrets present, including PR events."""
    contents = (_WORKFLOWS / "ci.yml").read_text()
    match = re.search(r"dockerhub-token: \$\{\{ (.*?) \}\}", contents)
    assert match is not None
    condition = (
        match[1]
        .replace("github.ref", '"$TEST_REF"')
        .replace("github.event_name", '"$TEST_EVENT"')
        .replace("secrets.DOCKERHUB_TOKEN", '"$TEST_SECRET"')
    )
    result = subprocess.run(  # noqa: S603 — fixed shell, repository predicate only
        ["bash", "-c", f"[[ {condition} ]]"],
        env={
            **os.environ,
            "TEST_REF": ref,
            "TEST_EVENT": event,
            "TEST_SECRET": "present",  # pragma: allowlist secret
        },
        check=False,
    )
    assert result.returncode == expected


@pytest.mark.unit
@pytest.mark.parametrize("workflow", ["ci", "ci-app", "docs", "docs-app"])
def test_ci_docs_credentials_require_trusted_main_event(workflow: str) -> None:
    """Every credential handoff requires the main event allowlist."""
    contents = (_WORKFLOWS / f"{workflow}.yml").read_text()
    credential_lines = [
        line for line in contents.splitlines() if "secrets.DOCKERHUB_" in line
    ]
    assert credential_lines
    for line in credential_lines:
        assert "github.ref == 'refs/heads/main'" in line
        assert (
            "(github.event_name == 'push' || github.event_name == 'workflow_dispatch')"
            in line
        )
        assert "|| '' }}" in line


@pytest.mark.unit
@pytest.mark.parametrize("workflow", ["devcontainer-build", "docker-app"])
def test_publication_requires_main_workflow_ref(workflow: str) -> None:
    """Dispatching a branch must not publish images or expose registry secrets."""
    data = yaml.safe_load((_WORKFLOWS / f"{workflow}.yml").read_text())
    assert data["jobs"]["build"]["if"] == "github.ref == 'refs/heads/main'"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("username", "token", "expected"),
    [("user", "token", 0), ("", "", 1), ("user", "", 1), ("", "token", 1)],
)
def test_optional_login_requires_complete_credentials(
    username: str, token: str, expected: int
) -> None:
    """Execute the actual action condition for each credential partition."""
    data = yaml.safe_load(
        (_ROOT / ".github/actions/devcontainer-run/action.yml").read_text()
    )
    login = next(
        step for step in data["runs"]["steps"] if step["name"] == "Log in to Docker Hub"
    )
    condition = (
        login["if"]
        .replace("inputs.dockerhub-username", '"$TEST_USERNAME"')
        .replace("inputs.dockerhub-token", '"$TEST_TOKEN"')
    )
    result = subprocess.run(  # noqa: S603 — fixed shell, repository condition only
        ["bash", "-c", f"[[ {condition} ]]"],
        env={**os.environ, "TEST_USERNAME": username, "TEST_TOKEN": token},
        check=False,
    )
    assert result.returncode == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "app",
    [
        "gas2mqtt",
        "valid-app",
        "bad name",
        "bad\nname",
        "bad'name",
        "$(touch injected)",
        "-option",
    ],
)
def test_docs_discovery_rejects_unsafe_app_names(tmp_path: Path, app: str) -> None:
    """Run the real discovery script against valid and hostile directory names."""
    config = tmp_path / "apps" / app / "zensical.toml"
    config.parent.mkdir(parents=True)
    config.touch()
    output = tmp_path / "output"
    data = yaml.safe_load((_WORKFLOWS / "docs.yml").read_text())
    discovery = next(
        step for step in data["jobs"]["detect"]["steps"] if step.get("id") == "discover"
    )
    result = subprocess.run(  # noqa: S603 — fixed workflow script, isolated workspace
        ["bash", "-e", "-c", discovery["run"]],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
        check=False,
    )
    if app in {"gas2mqtt", "valid-app"}:
        assert result.returncode == 0
        assert json.loads(output.read_text().removeprefix("apps=")) == [app]
    else:
        assert result.returncode == 1
        assert not output.exists()
    assert not (tmp_path / "injected").exists()


@pytest.mark.unit
def test_docs_shell_scripts_do_not_interpolate_step_outputs() -> None:
    """Untrusted JSON reaches scripts through environment variables."""
    data = yaml.safe_load((_WORKFLOWS / "docs.yml").read_text())
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            assert "${{ steps." not in step.get("run", "")
            assert "${{ needs." not in step.get("run", "")
