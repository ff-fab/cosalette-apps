---
status: Accepted
date: 2026-10-08
impact: moderate
tags: [testing, security, ci, tooling]
---

# ADR-012: Change-scoped pre-PR gate with a shared-path fallback

## Status

Accepted **Date:** 2026-10-08 | Amended **Date:** 2026-10-08

## Context

`task pre-pr` checked every app and every file on each run. A warm run took about 3.5–4 minutes, most of it work a typical one-app branch cannot affect:

| Step | Warm time |
| --- | --- |
| `security:audit` (pip-audit, detect-secrets over every file, ruff S, actionlint/zizmor) | ~75 s |
| unit + integration tests for every app | ~113 s |
| `test:scripts` | ~14 s |
| `docker:lint` (every Dockerfile) | ~7 s |
| `pre-commit --all-files` | ~5 s |

The gate also ran similarity twice and ran ruff and reuse both as fixing pre-commit hooks and as check-only tasks. A fixing hook could rewrite files and still let the gate pass. Per-app `complexity` and `similarity` ran nowhere, neither in pre-pr nor in CI, so wiz2mqtt and airthings2mqtt had drifted past the thresholds unnoticed.

CI already scopes per app with dorny/paths-filter. However, a change to a shared path (`uv.lock`, `Taskfile.yml`, `scripts/`, `.github/`) ran only the root jobs and no app CI. A lockfile bump could therefore merge without any app's tests running.

## Decision

Use a change-scoped `task pre-pr` that checks only the apps a branch changed, or every app when a shared path changed. The shared-path list is `.github/ci-shared-paths.txt`, one file that both CI's paths-filter and the local gate read. `task pre-pr:full` and `APPS="a b"` are explicit escape hatches.

The changed files are the diff since `git merge-base origin/main HEAD`, plus uncommitted and untracked files.

- **App selection:**
  - a change under `apps/<app>/` selects that app;
  - a match in the shared list selects every app;
  - root unit tests always run;
  - `APPS="a b"` overrides the selection;
  - a missing `origin/main`, which the gate tries to fetch first, falls back to the full run.
- **Cheaper local steps:**
  - pre-commit runs on changed files, or `--all-files` when its config changed;
  - detect-secrets scans only changed files, through a pre-commit hook;
  - pip-audit runs only when `uv.lock` or a `pyproject.toml` changed;
  - actionlint/zizmor run only when workflows changed;
  - `test:scripts` and `docker:lint` run only when their inputs changed.
- **Duplicate work removed:**
  - the duplicate similarity step is gone;
  - the fixing ruff and reuse hooks are skipped inside the gate, which runs them check-only.
- **CI:**
  - per-app `complexity` and `similarity` gate both locally and in per-app CI;
  - CI runs every app when a shared path changes;
  - CI keeps the full `security:audit`.

```bash
task pre-pr                    # apps changed since the merge-base (all apps on a shared change)
task pre-pr APPS="gas2mqtt"    # exactly these apps
task pre-pr:full               # every app, every file, full security audit
```

## Decision Drivers

- A one-app branch should not pay for every app's integration tests and a repo-wide security audit before each push.
- Local scoping must never be looser than CI scoping, so both read one shared-path list.
- Required CI (the `ci-gate` check) is the authoritative gate; the local gate exists to fail fast before a push.
- Secrets must be caught before a push publishes them, which only a local check can do.
- Quality gates must not silently rewrite files and still report success.

## Considered Options

### Option 1: Change-scoped gate with shared-path fallback (chosen)

Select apps from the diff against the merge-base with origin/main. Fall back to every app on a shared-path change and to the full run when origin/main is missing. Scope the security, script and Docker steps to their inputs. Provide `APPS=` and `pre-pr:full` as overrides.

- *Advantages:* Typical one-app branches skip the other apps' tests and the repo-wide audit.; The same shared-path list drives CI and the local gate, guarded by a drift test.; The overrides keep a full or targeted run one command away.
- *Disadvantages:* Scoping logic is new code that can mis-select; the fallback paths and tests must stay correct.; A file outside apps/ and outside the shared list (for example root docs) selects no app.

### Option 2: Keep the full gate and parallelise its steps

Keep checking everything and run independent steps concurrently to cut wall-clock time.

- *Advantages:* No scoping logic, so there is nothing to mis-select.; Every run covers every app.
- *Disadvantages:* The total work stays the same, and the caldates2mqtt integration tests dominate the critical path.; Interleaved output and shared caches make failures harder to read; tracked separately as cap-eh1m, blocked on cap-0xkz.

### Option 3: Drop the local gate and rely on CI

Push and let per-app CI find failures.

- *Advantages:* No local wait at all.
- *Disadvantages:* Feedback arrives minutes later, after a push.; Secrets are published before CI could flag them.; Pre-commit-only checks (editorconfig, prettier, codespell) have no CI counterpart.

## Decision Matrix

| Criterion | Change-scoped gate with shared-path fallback | Keep the full gate and parallelise its steps | Drop the local gate and rely on CI |
| --- | --- | --- | --- |
| Local wall-clock for a one-app branch | 5 | 3 | 4 |
| Risk of missing a regression before merge | 4 | 5 | 3 |
| Secrets caught before a push | 5 | 5 | 1 |
| Implementation and maintenance cost | 3 | 3 | 5 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- A one-app branch checks one app plus the root package instead of every app, and skips pip-audit, the Docker lint and the script tests unless their inputs changed.
- CI now runs every app when a shared path changes, which closes the gap where a lockfile or tooling change merged without app tests.
- Per-app complexity and duplication are gated locally and in per-app CI.
- The gate prints the selected apps and the reason on its first lines, so a wrong selection is visible immediately.

### Negative

- Risk: the local gate checks less than before. Mitigation: required CI (`ci-gate`) still runs every affected app and the full `security:audit`, and `task pre-pr:full` is one command away.
- Risk: pre-commit-only checks (editorconfig, prettier, codespell, detect-private-key) exist only locally and now see only changed files. Mitigation: changed files are exactly the ones those checks can newly break, and a change to `.pre-commit-config.yaml` runs them on every file.
- Risk: a secret leaks before CI scans it. Mitigation: the detect-secrets scan stays local on every changed file, now also as a commit hook, because a push publishes.
- Risk: a shared file outside the list escapes app selection. Mitigation: the list errs broad (`.github/**`, `scripts/**`, `packages/**`, `taskfiles/**`, lockfile, root configs), any match selects every app, and a missing `origin/main` falls back to the full run.
- Risk: CI and the local gate drift apart. Mitigation: both read `.github/ci-shared-paths.txt`, and `scripts/tests/test_pre_pr_scope.sh` fails if `ci.yml` stops reading it or hardcodes a shared path.

## Amendment (2026-10-08) — Additive

**Rationale:** Option 2 (parallelise the steps) was rejected as a replacement for scoping, but it combines with scoping. It was blocked on cap-0xkz because the caldates2mqtt integration tests are flaky under CPU load (cap-zh2o). Running the app tests alone in their own phase removes that conflict, so the gate now does both (cap-eh1m).

### Additional Sub-Decision: Two-phase parallel execution

`scripts/pre-pr.sh` runs the selected steps in two phases.

- **Phase 1:** the cheap or I/O-bound step groups run concurrently, `PRE_PR_JOBS` at a time (default: `nproc`). These are pre-commit, reuse, lint, typecheck, root unit tests, script tests, complexity, Docker lint and security.
- **Phase 2:** `test:apps` runs alone, so CPU-sensitive app tests (caldates2mqtt integration, cap-zh2o) never share the CPU with heavy phase-1 steps such as `complexity:all`.

Every step runs, so one pass reports every failure, and the exit code is the code of the first failing step in the fixed order. Result lines print in that fixed order, not in completion order. Each step group keeps its own log under `PRE_PR_LOG.steps/`; those logs are appended to `PRE_PR_LOG` in the same order, and on failure the gate tails each failed group's log. Per-step timeouts, `[DONE]`/`[FAIL]` and `pre-pr-exit=<rc>` are unchanged. `PRE_PR_JOBS=1` runs the same steps one at a time with live progress, for debugging. pytest-xdist is not used.

!!! note "Editorial note (2026-10-08)"
    Measured on this branch (6 CPUs, all apps selected), three parallel runs each: `task pre-pr:full` took 149–160 s, against 224 s for a same-day `PRE_PR_JOBS=1` run (246 s before this change); the scoped `task pre-pr` took 149–150 s, against 251 s sequentially before this change. Phase 1 takes about 45 s; `test:apps` (about 105 s) is now the critical path.

### Additional Positive Consequences

- The gate is about 30 % faster on a full run, and a single run reports every failing step instead of stopping at the first.

### Additional Negative Consequences

- Risk: a failure in an early step no longer saves the time of the later steps. Mitigation: phase 1 is short, and `test:apps` is the only long step either way.
- Risk: parallel steps contend for CPU and shared caches. Mitigation: the app tests run alone in phase 2, each step keeps its own log and timeout, and `PRE_PR_JOBS=1` reproduces a sequential run.
