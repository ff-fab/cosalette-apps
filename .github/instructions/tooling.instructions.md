---
description: 'Tooling policy: task runner and uv, never bare python'
applyTo: '**'
---

# Tooling Instructions

## Golden Rule

**Never invoke `python` or `python -m` directly.** All commands go through either:

1. **`task <app>:<name>`** — preferred, uses the Taskfile.yml definitions
2. **`uv run --package <name> <command>`** — fallback when no task exists

## Task Commands (use these first)

Run `task --list` to see all available tasks. Key tasks for development:

| Need                          | Command                                              |
| ----------------------------- | ---------------------------------------------------- |
| Run all unit tests (one app)  | `task gas2mqtt:test:unit`                            |
| Run a specific test file      | `task gas2mqtt:test:file -- packages/tests/unit/test_foo.py` |
| Run tests matching a pattern  | `task gas2mqtt:test:file -- -k test_my_function`     |
| Run tests with coverage       | `task gas2mqtt:test:cov`                             |
| Lint (ruff check + format)    | `task gas2mqtt:lint`                                 |
| Fix lint issues               | `task gas2mqtt:lint:fix`                             |
| Type check (mypy)             | `task gas2mqtt:typecheck`                            |
| All checks (lint+type+test)   | `task gas2mqtt:check`                                |
| Complexity (radon + cognitive) | `task gas2mqtt:complexity`                           |
| Duplication detection          | `task gas2mqtt:similarity`                           |
| Run all apps' tests           | `task test:all`                                      |
| Lint all apps                 | `task lint:all`                                      |
| Pre-PR quality gate           | `task pre-pr`                                        |
| Wait for CI on a PR           | `task ci:wait -- <pr-number>`                        |
| Preview root docs             | `task docs:serve`                                    |
| Preview app docs              | `task <app>:docs:serve`                              |
| Sync dependencies             | `task sync`                                          |

## When no task exists

For one-off commands not covered by the Taskfile, use `uv run --package <name>` from
the repo root:

```bash
uv run --package gas2mqtt pytest apps/gas2mqtt/packages/tests/unit/test_foo.py -v
uv run mypy apps/gas2mqtt/packages/src/

# WRONG — never do this
python -m pytest apps/gas2mqtt/packages/tests/unit/test_foo.py -v
python apps/gas2mqtt/packages/tests/scripts/summarize_tests.py
```

## Why

- `uv run` ensures the correct virtual environment and dependencies are used
- `task` commands encode project conventions (flags, working directory, coverage
  thresholds) so agents don't need to remember them
- Bare `python` may pick up the wrong interpreter or miss dependencies

## Suggesting Taskfile changes

If you find yourself repeatedly needing a command pattern that doesn't have a task,
**propose adding it to `Taskfile.yml`** rather than using raw `uv run` calls. This is
preferred because tasks encode conventions once and all agents/developers benefit.
