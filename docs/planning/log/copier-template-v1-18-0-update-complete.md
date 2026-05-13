## Epic Complete: Copier Template v1.18.0 Update

The workspace now records the `tmpl_python_project_kickstart` template pin at `v1.18.0` and selectively backports the approved template improvements without replacing the monorepo-specific CI, docs, release, and app task structure. The update adds hardened GitHub Actions usage, a reusable devcontainer action, CodeQL, mandatory security auditing in `task pre-pr`, and a Taskfile-owned safe pre-PR log/tail/status flow.

**Phases Completed:** 5 of 5
1. [x] Phase 1: Evaluate template delta and plan Option B
2. [x] Phase 2: Apply low-risk template updates
3. [x] Phase 3: Harden workflows and add CodeQL
4. [x] Phase 4: Add security audit gates
5. [x] Phase 5: Verify, review, and prepare PR

**All Files Created/Modified:**
- `.beads/issues.jsonl`
- `.copier-answers.yml`
- `.github/actions/devcontainer-run/action.yml`
- `.github/skills/pr-review/feedback-schema.json`
- `.github/workflows/ci-app.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/codeql.yml`
- `.github/workflows/devcontainer-build.yml`
- `.github/workflows/docker-app.yml`
- `.github/workflows/docs-app.yml`
- `.github/workflows/docs-preview.yml`
- `.github/workflows/docs.yml`
- `.github/workflows/release-please.yml`
- `.gitignore`
- `.secrets.baseline`
- `REUSE.toml`
- `Taskfile.yml`
- `apps/jeelink2mqtt/packages/src/jeelink2mqtt/main.py`
- `apps/suncast/packages/src/suncast/app.py`
- `docs/planning/copier-template-v1-18-0-update-evaluation.md`
- `docs/planning/log/copier-template-v1-18-0-update-complete.md`
- `pyproject.toml`
- `renovate.json`
- `scripts/pre-pr.sh`
- `scripts/qa-task.sh`
- `uv.lock`

**Key Functions/Classes Added:**
- `_do_security_deps`
- `_do_security_secrets`
- `_do_security_python`
- `_do_security_actions`
- `run_step`

**Test Coverage:**
- Total tests written: 0
- All tests passing: yes
- Final verification: `task pre-pr` passed with `pre-pr-exit=0`
- Additional targeted checks: `task security:deps`, `task security:secrets`, `task security:actions`, and `task security:audit` passed
- Review status: code-review subagent approved after revision

**Recommendations for Next Steps:**
- Watch the first PR CI run for reusable workflow permission behavior across `ci-gate`, docs, CodeQL, and release workflow syntax.
- Keep `edge` Docker publishing deferred until an app release workflow explicitly needs it.
- Revisit upstream template monorepo support only if future Copier updates continue to require broad manual reconciliation.
