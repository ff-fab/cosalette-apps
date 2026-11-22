"""Regression contract for the Claude Code install in the devcontainer image.

CI builds the image with INSTALL_CLAUDE_CODE=false, so the install step never runs
there. These static checks stand in for it.

Test Techniques Used:
- Error Guessing: a root install leaves /usr/local/bin/claude pointing into /root,
  which is mode 0700 and so unreachable for the vscode user.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_DOCKERFILE = Path(__file__).resolve().parents[3] / ".devcontainer/Dockerfile"


@pytest.mark.unit
def test_claude_installed_and_verified_as_vscode_user() -> None:
    text = _DOCKERFILE.read_text()
    assert 'runuser -u vscode -- bash "${INSTALLER}"' in text
    assert "ln -sf /home/vscode/.local/bin/claude /usr/local/bin/claude" in text
    assert "runuser -u vscode -- claude --version" in text
    assert "ENV DISABLE_AUTOUPDATER=1" in text
