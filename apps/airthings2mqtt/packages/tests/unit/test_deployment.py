"""Unit tests for the shipped deployment files — Dockerfile and compose.

The image runs as a dedicated UID so a host D-Bus policy can target the app alone
(ADR-003). The host-side files and docs repeat that UID, so drift breaks the
deployment silently.

Test Techniques Used:
- Specification-based: the Dockerfile pins the documented UID/GID; compose adds
  no capabilities.
- Error Guessing: the commented compose example drifting from the live service.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_APP_DIR = Path(__file__).resolve().parents[3]
_APP_UID = 10001


class TestDockerfileIdentity:
    """The image runs as the dedicated, documented UID/GID."""

    def test_image_user_is_dedicated_uid(self) -> None:
        """USER is the numeric 10001:10001, not the host login user's 1000.

        Technique: Specification-based — docs/host-setup.md documents this UID.
        """
        dockerfile = (_APP_DIR / "Dockerfile").read_text(encoding="utf-8")

        assert re.search(r"^USER 10001:10001$", dockerfile, re.MULTILINE)
        assert f"adduser -D -H -u {_APP_UID} " in dockerfile
        assert f"addgroup -g {_APP_UID} " in dockerfile


class TestComposePrivileges:
    """Shipped compose services add no capabilities and forbid privilege gain."""

    def test_app_service_adds_no_capabilities(self) -> None:
        """The app service has no cap_add and sets no-new-privileges.

        Technique: Specification-based — docs/host-setup.md documents both.
        """
        compose = yaml.safe_load((_APP_DIR / "compose.yml").read_text(encoding="utf-8"))
        service = compose["services"]["airthings2mqtt"]

        assert "cap_add" not in service
        assert service["security_opt"] == ["no-new-privileges:true"]

    def test_commented_example_adds_no_capabilities(self) -> None:
        """The commented multi-device example does not reintroduce cap_add.

        Technique: Error Guessing — copied examples drift from the live service.
        """
        compose = (_APP_DIR / "compose.yml").read_text(encoding="utf-8")

        assert "cap_add" not in compose
        assert compose.count("no-new-privileges:true") == 2
