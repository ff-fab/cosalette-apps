"""Unit tests for the shipped deployment files — Dockerfile, compose, D-Bus policy.

The image runs as a dedicated UID so a host D-Bus policy can target the app alone
(ADR-003). The host-side files and docs repeat that UID, so drift breaks the
deployment silently.

Test Techniques Used:
- Specification-based: the Dockerfile pins the documented UID/GID, which the host
  D-Bus policy repeats; compose adds no capabilities.
- Error Guessing: the commented compose example drifting from the live service; the
  image probe drifting from monorepo ADR-011.
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

    def test_image_stores_state_on_the_data_volume(self) -> None:
        """The store path defaults to the volume, not the missing home directory.

        Technique: Error Guessing — ``adduser -H`` creates no home, so the
        framework's ``~/.local/state`` default fails every save.
        """
        dockerfile = (_APP_DIR / "Dockerfile").read_text(encoding="utf-8")

        assert re.search(r"^VOLUME /app/data$", dockerfile, re.MULTILINE)
        assert re.search(
            r"^ENV AIRTHINGS2MQTT_STORE_PATH=/app/data/store\.json$",
            dockerfile,
            re.MULTILINE,
        )


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
        block = compose.split("  # airthings2mqtt-bedroom:", maxsplit=1)[1]
        lines = block.split("\n\n", maxsplit=1)[0].splitlines()[1:]
        example = "airthings2mqtt-bedroom:\n" + "\n".join(
            line[4:] for line in lines if line.startswith("  # ")
        )
        service = yaml.safe_load(example)["airthings2mqtt-bedroom"]

        assert "cap_add" not in service
        assert service["security_opt"] == ["no-new-privileges:true"]


class TestHealthProbe:
    """The image ships the native probe; compose adds none (monorepo ADR-011)."""

    def test_image_probes_the_health_file(self) -> None:
        """The Dockerfile sets the health file and runs cosalette-health.

        Technique: Specification-based — one sensor per instance, so the probe
        keeps the default --fail-on stale; the start period covers the measured
        28.6 s Pi 4 startup.
        """
        dockerfile = (_APP_DIR / "Dockerfile").read_text(encoding="utf-8")

        assert re.search(
            r"^ENV COSALETTE_HEALTH_FILE=/tmp/airthings2mqtt-health\.json$",
            dockerfile,
            re.MULTILINE,
        )
        assert re.search(
            r'^HEALTHCHECK .*--start-period=60s .*\n\s+CMD \["cosalette-health"\]$',
            dockerfile,
            re.MULTILINE,
        )

    def test_compose_has_no_healthcheck_and_restarts(self) -> None:
        """The service has no healthcheck and restarts on a non-zero exit.

        Technique: Specification-based — exit codes 5 (exit_after_stale) and 6
        (loop stall) only heal when the restart policy brings the container back.
        """
        compose = yaml.safe_load((_APP_DIR / "compose.yml").read_text(encoding="utf-8"))
        service = compose["services"]["airthings2mqtt"]

        assert "healthcheck" not in service
        assert service["restart"] == "unless-stopped"
        assert service["environment"]["COSALETTE_LOOP_STALL_TIMEOUT"] == (
            "${COSALETTE_LOOP_STALL_TIMEOUT:-120}"
        )


class TestBluezPolicy:
    """The opt-in host D-Bus policy targets the image UID and only BlueZ Set."""

    def test_policy_targets_image_uid_and_denies_only_set(self) -> None:
        """The policy's user matches the Dockerfile UID and denies one call.

        Technique: Specification-based — a UID drift would leave the app unguarded.
        """
        policy = (_APP_DIR / "deploy" / "airthings2mqtt-bluez.conf").read_text(
            encoding="utf-8"
        )

        assert re.findall(r'<policy\s+user="(\d+)"', policy) == [str(_APP_UID)]
        deny_rules = re.findall(r"<deny\b[^>]*/>", policy, re.DOTALL)
        assert len(deny_rules) == 1
        assert 'send_destination="org.bluez"' in deny_rules[0]
        assert 'send_interface="org.freedesktop.DBus.Properties"' in deny_rules[0]
        assert 'send_member="Set"' in deny_rules[0]
        assert "<allow" not in policy
