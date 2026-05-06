## Epic cap-v6y Complete: Mapping Subcommands

Split the jeelink2mqtt mapping command from a manual dispatch dictionary into declarative cosalette sub-command registrations. Valid command response payloads and persistence behavior remain compatible, while framework-level tests now pin invalid JSON, missing command, and unknown sub-command error behavior.

**Files created/changed:**
- apps/jeelink2mqtt/packages/src/jeelink2mqtt/main.py
- apps/jeelink2mqtt/packages/src/jeelink2mqtt/commands.py
- apps/jeelink2mqtt/packages/tests/integration/test_app_integration.py
- apps/jeelink2mqtt/packages/tests/integration/test_commands.py
- apps/jeelink2mqtt/packages/tests/unit/test_commands.py
- docs/planning/log/jeelink2mqtt-mapping-subcommands-complete.md

**Functions created/changed:**
- mapping_assign
- mapping_reset
- mapping_reset_all
- mapping_list_unknown
- parse_command_payload
- MappingCommandPayloadError

**Tests created/changed:**
- TestMappingSubCommands direct handler coverage
- TestMappingSubCommandErrors framework routing coverage
- TestParseCommandPayload parser validation cases
- TestHandleAssign error-key regression case
- Removed stale manual dispatch integration tests

**Review Status:** APPROVED

**Git Commit Message:**
refactor(jeelink2mqtt): split mapping commands

- Replace manual mapping dispatch with sub-command handlers
- Preserve mapping response payloads and persistence behavior
- Add framework-level sub-command error routing tests
