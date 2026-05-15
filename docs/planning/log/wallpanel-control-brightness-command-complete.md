## Epic Wallpanel Control Complete: Brightness Command

Implemented the brightness command slice for wallpanel-control. The new router module handles raw 0-100 MQTT payloads, scales percentages to raw backlight values, suppresses publishes when the panel is unreachable, and introduces a port-level unreachable exception so device code stays decoupled from SSH transport details.

**Files created/changed:**
- apps/wallpanel-control/packages/src/wallpanel_control/devices/__init__.py
- apps/wallpanel-control/packages/src/wallpanel_control/devices/brightness.py
- apps/wallpanel-control/packages/src/wallpanel_control/ports.py
- apps/wallpanel-control/packages/src/wallpanel_control/adapters/ssh_adapter.py
- apps/wallpanel-control/packages/src/wallpanel_control/adapters/fake.py
- apps/wallpanel-control/packages/tests/unit/test_brightness.py
- apps/wallpanel-control/packages/tests/unit/test_fake_adapter.py
- apps/wallpanel-control/packages/tests/unit/test_ports.py
- .beads/issues.jsonl

**Functions created/changed:**
- BrightnessState
- create_brightness_state
- handle_brightness
- WallpanelUnreachableError
- SshWallpanel._run
- SshWallpanel._run_or_none
- FakeWallpanel._check_reachable
- FakeWallpanel.get_max_brightness

**Tests created/changed:**
- TestBrightnessState
- TestDefaultMaxBrightness
- TestCreateBrightnessState
- TestHandleBrightnessValidation
- TestHandleBrightnessZero
- TestHandleBrightnessScreenOn
- TestHandleBrightnessRawCalculation
- TestHandleBrightnessUnreachable
- TestRouterRegistration
- Fake adapter unreachable tests updated for WallpanelUnreachableError
- Port exception inheritance tests

**Review Status:** APPROVED

**Git Commit Message:**
feat(wallpanel): add brightness command

- Add brightness router command and state factory
- Normalize unreachable SSH failures at the port boundary
- Cover scaling, validation, and unreachable paths
