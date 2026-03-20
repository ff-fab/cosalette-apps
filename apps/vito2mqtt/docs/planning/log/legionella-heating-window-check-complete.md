## Epic Legionella Treatment Complete: Heating window check

Pure-logic module `devices/legionella.py` with `is_within_heating_window()` and
`TIMER_SIGNAL_FOR_DAY` mapping. 27 unit tests covering boundary conditions,
empty/None schedules, partial-None slots, zero-duration windows, margin
exceeding window, and negative margin guard.

**Files created/changed:**

- packages/src/vito2mqtt/devices/legionella.py
- packages/tests/unit/devices/test_legionella.py

**Functions created/changed:**

- `TIMER_SIGNAL_FOR_DAY` — dict mapping weekday int (0–6) to timer signal names
- `is_within_heating_window(schedule, now, safety_margin_minutes)` — pure function

**Tests created/changed:**

- `TestIsWithinHeatingWindow` — 17 tests (incl. boundary, edge cases, negative margin)
- `TestTimerSignalForDay` — 10 tests (incl. cross-reference with COMMANDS registry)

**Review Status:** APPROVED (4 review findings addressed: 3 missing edge-case tests + negative margin guard)

**Git Commit Message:**

```
feat: add legionella heating window check module

- Add is_within_heating_window() pure function
- Add TIMER_SIGNAL_FOR_DAY weekday-to-signal mapping
- 27 unit tests covering boundaries and edge cases
```
