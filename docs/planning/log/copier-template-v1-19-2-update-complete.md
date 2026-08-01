## Epic Complete: Copier Template v1.19.2 Update

The workspace now records the `tmpl_python_project_kickstart` template pin at
`v1.19.2` (up from `v1.18.0`) and selectively backports the approved
template improvements without replacing the monorepo-specific CI, docs,
release, `pyproject.toml`, and Taskfile/qa-task.sh structure. Same
"selective monorepo-aware backport" approach as the v1.18.0 update — the
template still hasn't learned this repo's app-matrix architecture, so every
`ci.yml`/`docs.yml`/`release-please.yml`-shaped file needed hand
reconciliation rather than a direct `copier update`.

**Phases Completed:** 6 of 6 (plus one follow-up fix-up commit)
1. [x] Phase 1: Low-risk direct updates (Dockerfile bumps + Claude Code
   install, pre-commit hook bumps, CodeQL hardening, Renovate additive keys,
   `render_adr.py` cleanup)
2. [x] Phase 2: Devcontainer cache correctness (`devcontainer-run` composite
   action env-passthrough fix, buildcache-manifest alignment,
   `devcontainer-build.yml` bumps)
3. [x] Phase 3: CI/docs/release workflow hardening backported onto the
   existing app-matrix/docs-matrix/Docker-release-matrix structure
4. [x] Phase 4: Root + per-app dependency-group version bumps, plus a
   discovered-and-fixed ruff config-inheritance bug (see below)
5. [x] Phase 5: `update:deps`, `update:template` (annotated), `docker:lint`
   tasks
6. [x] Phase 6: `.copier-answers.yml` `_commit` bump (folded into Phase 1)
7. [x] Follow-up: restored `noqa` comments dropped as a side effect of
   Phase 4's `ruff --fix` passes, scoped the release-please GitHub App token
   (zizmor 1.28.0 finding)

**All Files Created/Modified:** (89 files; see `git diff --stat main..HEAD`
for the full list)
- `.copier-answers.yml`, `.devcontainer/Dockerfile`,
  `.devcontainer/devcontainer.json`
- `.github/actions/devcontainer-run/action.yml`
- `.github/workflows/{ci,ci-app,codeql,devcontainer-build,docker-app,
  docs,docs-app,docs-preview,release-please}.yml`
- `.pre-commit-config.yaml`, `.secrets.baseline`, `Taskfile.yml`,
  `renovate.json`, `scripts/qa-task.sh`, `scripts/render_adr.py`
- `pyproject.toml`, `uv.lock`
- All 8 `apps/*/pyproject.toml` (new `[tool.ruff] extend` block)
- ~50 app source/test files (E501 wraps, SIM/C409/E731/UP041/ARG001 fixes,
  restored `noqa` comments) across `wallpanel-control`, `suncast`,
  `caldates2mqtt`, `airthings2mqtt`, `velux2mqtt`, `gas2mqtt`,
  `jeelink2mqtt`, `vito2mqtt`
- `docs/planning/copier-template-v1-19-2-update-evaluation.md` (new)
- `docs/planning/log/copier-template-v1-19-2-update-complete.md` (this file)

**Key Functions/Classes Added:**
- `_do_docker_lint` in `scripts/qa-task.sh` — hadolint over Docker, looped
  across `.devcontainer/Dockerfile` and every `apps/*/Dockerfile`

**Notable Discovery — Ruff Config-Inheritance Bug:**

Bumping ruff 0.15.12 → 0.16.1 (per the template's dependency-group update)
expanded ruff's *default* rule set from ~59 to ~413 rules. Ruff's config
discovery uses the nearest `pyproject.toml` as the sole config source — it
does not merge upward — and every app's `pyproject.toml` already had its own
`[tool.ruff.lint.isort]` table (for `known-first-party`). That table alone
was enough to make ruff treat the app's file as authoritative and ignore
root's explicit `select = [E,W,F,B,I,C4,UP,SIM,ARG]` entirely, silently
falling back to ruff's own default instead. Under the old, narrow default
this was nearly invisible (a strict subset of what root intended); under
0.16's expanded default it surfaced hundreds of new categories (`DTZ`,
`BLE`, etc.) that were never part of this repo's actual lint policy,
alongside some genuinely real, previously-uncaught findings (mostly `E501`,
since apps were never actually enforcing the full `E` pycodestyle family
either). Fixed by adding `[tool.ruff] extend = "../../pyproject.toml"` to
all 8 app `pyproject.toml` files. This is a pre-existing latent gap that
predates this PR — the ruff bump only exposed it — and is unrelated to the
copier template itself, but had to be fixed in this PR since leaving it
would have made `task lint:all`/`task pre-pr` (and the pre-commit ruff hook,
already bumped in Phase 1) unreliable across the whole monorepo going
forward.

**Test Coverage:**
- Total tests written: 0 (no new test files; existing test suites updated
  for E731/SIM105/SIM117 refactors — behavior preserved, verified by
  `task test:all`)
- All tests passing: yes
- Final verification: `task pre-pr` passed with `pre-pr-exit=0`
  (pre-commit, `reuse:lint`, `lint:all`, `typecheck:all`, `test:all`,
  `complexity`, `similarity`, `security:audit` all green)
- Additional targeted checks: `task lint`, `task typecheck`, `task test`,
  `uv run actionlint` (repo-wide), `bash scripts/qa-task.sh security:actions`
  (zizmor 1.28.0, clean), `task docker:lint` (new — surfaces pre-existing
  hadolint warnings across several Dockerfiles; not wired into `pre-pr`)
- Review status: self-reviewed against the evaluation doc's Recommended
  Plan; no external code-review subagent run this session

**What Was Applied Directly vs. Adapted vs. Skipped:**

See `docs/planning/copier-template-v1-19-2-update-evaluation.md` for the
full Candidate Updates table (24 entries, IDs U1–U24). Summary:

- **Direct**: devcontainer tool bumps + Claude Code install,
  `devcontainer.json` build arg, pre-commit hook bumps (codespell, ruff,
  prettier source switch to the maintained `rbubley/mirrors-prettier`
  fork), CodeQL hardening, Renovate's three new additive keys
  (`dependencyDashboard`, `minimumReleaseAge`, `internalChecksFilter`),
  `render_adr.py` cleanup, `update:deps` task, `.copier-answers.yml` bump.
- **Adapted**: `devcontainer-run` composite action (env-passthrough fix +
  buildcache alignment, not the template's literal values —
  `/workspaces/cosalette-apps` not `/workspace`), `devcontainer-build.yml`
  (bumps only, kept the dedicated buildcache manifest), `ci.yml`/`ci-app.yml`
  (hardening backported onto the app-matrix dispatch, not the template's
  collapsed single-project version), `docs.yml`/`docs-app.yml` (hardening
  backported onto the root+per-app docs matrix and site-merge/cache
  pipeline), `release-please.yml`/`docker-app.yml` (action bumps backported
  onto the GitHub App token auth and per-app Docker release matrix),
  `pyproject.toml` (dependency-group version bumps only — kept the
  virtual-workspace structure, `[tool.uv.workspace]`, CVE
  `constraint-dependencies`, full `extraPaths`, and repo-specific deps),
  `docker:lint` (adapted to lint all Dockerfiles, not just the devcontainer
  one), `update:template` (kept as a manual entry point, heavily annotated
  that its output needs the same hand-reconciliation this PR did).
- **Skipped**: `update:template:pr`'s `gh pr merge --auto --squash`
  behavior — never added, since this repo's `CLAUDE.md` explicitly forbids
  agents from merging PRs without the user's explicit ask, and a blind
  `copier update --trust` needs manual monorepo reconciliation nearly every
  time (proven by this very update), making unattended auto-merge doubly
  wrong here. `renovate.json`'s automerge removal — kept this repo's
  existing `automerge: true` for Python minor/patch and Docker digest
  updates rather than the template's more conservative all-manual default;
  that's a deliberate, previously-reviewed choice, not incidental
  formatting. `scripts/setup-github-remote.sh` — only runs on a fresh
  `copier copy` with `create_remote_repo: true`; never fires on this
  already-existing repo. `qa-task.sh`'s full timeout/log/tail wrapper
  rewrite — this repo's existing wrapper already has the monorepo-specific
  hardening the template's rewrite reinvents in single-package form
  (`--all-packages` pip-audit, `PIP_AUDIT_CACHE_DIR`, `--isolated` ruff
  `security:python`, parallelized `security:audit`); the template's
  per-task deadline/tail UX improvements are real but deferred as a
  separate, lower-priority follow-up.

**Recommendations for Next Steps:**
- Watch the first post-merge `main` push closely for `docs.yml`'s new
  `actions/configure-pages` step (Pages deploy only runs on push, never on
  PR, so this PR's CI cannot exercise it) and `release-please.yml`'s
  `googleapis/release-please-action` v5.0.0 + scoped App token (also only
  exercised on `main` push).
- `task docker:lint` is new and currently surfaces real (if minor)
  hadolint warnings — mostly `DL3008`/`DL3018` unpinned apt/apk package
  versions and `DL4006` missing `pipefail` before piped `RUN` steps — across
  several Dockerfiles. Left unfixed and NOT wired into `task pre-pr`
  (opt-in only), matching the staged-rollout approach used for the
  `security:*` family during the v1.18.0 update. File a follow-up if these
  should be addressed.
- Consider whether `qa-task.sh`'s missing per-task timeout wrapper (present
  in the template's rewrite, absent here) is worth adopting later — this
  repo has no reported "CI job hangs forever" incidents yet, so it was
  deferred rather than adopted this round.
- Revisit upstream template monorepo support (Implementation Option D in
  the evaluation doc) if the next Copier release still requires this same
  breadth of hand reconciliation — this is the third consecutive template
  update (v1.16.0→v1.17.0, v1.17.0→v1.18.0, v1.18.0→v1.19.2) where
  `ci.yml`/`docs.yml`/`release-please.yml` all needed full manual
  adaptation rather than a clean merge.
