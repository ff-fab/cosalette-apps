## Epic Protocol Layer Complete: Command Registry

Implemented the Vitodens 200-W command registry as a frozen dataclass model with
`AccessMode` enum, 89-command `COMMANDS` dictionary, and `lookup_by_address()`
helper. All 11 codec types are represented. Known legacy bugs resolved: 0x0808
collision excluded, 0x7665/0x7660 dual-view retained, uncertain write access
defaulted to read-only.

**Files created/changed:**

- packages/src/vito2mqtt/optolink/commands.py (full implementation, was stub)
- packages/tests/unit/optolink/test_commands.py (new)

**Functions created/changed:**

- `AccessMode` enum (READ, WRITE, READ_WRITE)
- `Command` frozen dataclass (name, address, length, type_code, access_mode)
- `COMMANDS: dict[str, Command]` — 89 entries keyed by English signal name
- `lookup_by_address(address: int) -> list[Command]` — reverse lookup

**Tests created/changed:**

- `TestCommandModel` (6 tests): frozen, hashable, slots, equality, repr, enum size
- `TestCommandRegistry` (10 tests): count, snake_case, type codes, addresses,
  lengths, duplicates, key/name match, access modes, all 11 types, instances
- `TestLookupByAddress` (5 tests): unique, shared ×2, unknown, collision avoidance
- `TestSpecificCommands` (11 parametrized): spot-checks across all categories
- `TestAccessModeDistribution` (3 tests): timer→WRITE, error_history→READ, totals

**Review Status:** APPROVED with minor recommendations (slots test added,
IS10-with-length-1 documented)

**Git Commit Message:**

```
feat: implement Vitodens 200-W command registry with 35 tests

- Add AccessMode enum and Command frozen dataclass with slots
- Register 89 commands across 15 groups with English signal names
- Implement lookup_by_address() for reverse address lookup
- Resolve 0x0808 collision, retain 0x7665/0x7660 dual-view
- Default uncertain write access to read-only for safety
```
