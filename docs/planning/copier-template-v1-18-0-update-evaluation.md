# Copier Template v1.18.0 Update Evaluation

Date: 2026-05-12

Branch: `chore/evaluate-copier-template-0.18.0`

Status: planning only. Do not implement template changes until this plan is reviewed.

## Summary

The requested target was `0.18.0`, but the upstream template repository has no
`v0.18.0` or `0.18.0` tag. The available successor to the current pin is
`v1.18.0`, and Copier would also select version tags using PEP 440 ordering when
no explicit `--vcs-ref` is supplied.

Current template state:

| Item | Value |
| --- | --- |
| Answers file | `.copier-answers.yml` |
| Current template | `https://github.com/ff-fab/tmpl_python_project_kickstart` |
| Current pin | `v1.17.0` |
| Requested target | `0.18.0` |
| Existing upstream target | `v1.18.0` |
| Exact `0.18.0` tag exists | No |
| Evaluation command | `uvx --from copier --with jinja2-time copier update --trust --defaults --vcs-ref v1.18.0 --skip-tasks --conflict rej /tmp/cosalette-apps-copier-eval` |

The simulation produced useful changes, but a direct `copier update` should not be
accepted wholesale. This repository is a monorepo with per-app task includes and
reusable workflows; the template delta still contains single-project assumptions
that would regress local CI, docs, packaging, and quality-gate behavior.

## Simulation Result

| Path | Simulated result | Conflict file | Initial assessment |
| --- | --- | --- | --- |
| `.copier-answers.yml` | Modified `_commit` from `v1.17.0` to `v1.18.0` | No | Apply only after the selected update set is implemented and validated. |
| `.github/actions/devcontainer-run/action.yml` | New file | No | Strong candidate, but adapt rollout across root and per-app workflows. |
| `.github/skills/pr-review/feedback-schema.json` | Modified cleanly | No | Low-risk direct update. |
| `.github/workflows/ci.yml` | Modified with rejected hunks | `.github/workflows/ci.yml.rej` | Do not accept directly; adapt hardening to existing monorepo CI. |
| `.github/workflows/devcontainer-build.yml` | Modified cleanly | No | Good candidate: action SHA pinning. |
| `.github/workflows/docs.yml` | Modified with rejected hunks | `.github/workflows/docs.yml.rej` | Do not accept directly; preserve current root plus per-app docs deployment model. |
| `.github/workflows/release-please.yml` | Modified with rejected hunks | `.github/workflows/release-please.yml.rej` | Do not accept directly; preserve current app release matrix. |
| `Taskfile.yml` | Modified with rejected hunks | `Taskfile.yml.rej` | Do not accept directly; template wrapper conflicts with app includes and current task policy. |
| `pyproject.toml` | Modified with rejected hunks | `pyproject.toml.rej` | Do not accept directly; keep root as virtual workspace and retain local docs/MCP deps. |
| `renovate.json` | Modified cleanly | No | Low-risk direct update. |
| `scripts/pre-pr.sh` | New file | No | Candidate if adapted to monorepo task graph and existing pre-PR workflow. |
| `scripts/qa-task.sh` | New file | No | Candidate, but requires careful monorepo and security-tooling adaptation. |

Upstream also changed template files that were not reintroduced by Copier because
the corresponding generated files are absent or disabled locally.

| Upstream template path | Local status | Assessment |
| --- | --- | --- |
| `template/.github/workflows/codeql.yml` | No local `codeql.yml` | Optional new workflow; evaluate separately because it introduces a new security signal. |
| `template/.github/workflows/{% if docker_publish %}build-edge.yml{% endif %}.jinja` | No local `build-edge.yml` | Optional; if wanted, implement as per-app edge image workflow, not the single-image template version. |
| `template/.github/workflows/{% if surge_token %}docs-preview.yml{% endif %}.jinja` | Disabled by `surge_token: false` | Skip unless docs preview hosting is intentionally enabled. |

## Candidate Updates

| ID | Candidate update | Source path or feature | Apply mode | Why | Risks and constraints | Validation |
| --- | --- | --- | --- | --- | --- | --- |
| U1 | Move Copier pin to `v1.18.0` | `.copier-answers.yml` | Final bookkeeping only | Records that the repo has intentionally consumed the template release. | If changed before resolving manual adaptations, future Copier updates will assume this release is fully applied. | Confirm all selected updates are present; run `copier update --pretend --vcs-ref :current:` after implementation. |
| U2 | Accept PR feedback schema compatibility changes | `.github/skills/pr-review/feedback-schema.json` | Direct | Allows metadata fetch failures through an error object and makes check-run output summaries consistently strings. | Low risk, but should match `.github/skills/pr-review/fetch-pr-feedback.sh` output. | Run or inspect `task pr:feedback -- <pr>` on a PR when available. |
| U3 | Add reusable devcontainer composite action | `.github/actions/devcontainer-run/action.yml` | Adapt | Removes repeated checkout/cache/login/devcontainer steps and adds uv, pre-commit, and optional Cargo cache handling. | Current workflows use per-app reusable jobs; action inputs and paths must work for root, app CI, docs, and future Rust-backed cosalette builds. | Run `actionlint`; verify CI jobs still execute inside the devcontainer. |
| U4 | Pin GitHub Actions by SHA in devcontainer build workflow | `.github/workflows/devcontainer-build.yml` | Direct or near-direct | Improves supply-chain integrity by replacing mutable tags with pinned SHAs plus version comments. | Pinned SHAs need Renovate support and periodic updates. | Run `actionlint`; rely on workflow execution. |
| U5 | Apply action SHA pinning broadly | `ci.yml`, `ci-app.yml`, `docs.yml`, `docs-app.yml`, `docker-app.yml`, `docs-preview.yml`, release workflow | Adapt | The release intent is broader than one workflow: reduce mutable GitHub Action references across all CI surfaces. | Large review surface; pins can stale quickly without Renovate support. | `uv run actionlint` or `task` wrapper once available; CI dry run through PR. |
| U6 | Preserve and harden monorepo CI detection | `.github/workflows/ci.yml` | Adapt, not direct | Current CI discovers changed apps and dispatches `.github/workflows/ci-app.yml`; this must remain. | The simulated direct update collapses back toward a root single-project CI and would skip or mis-route app checks. | Open a PR with app-only, shared-only, and docs-only changes; confirm `ci-gate` behavior. |
| U7 | Reuse devcontainer composite in per-app CI | `.github/workflows/ci-app.yml` plus U3 | Adapt | Reduces duplicated login/devcontainer steps in lint, typecheck, test, and integration jobs. | Composite action must support app task commands and coverage output paths. | Run CI for at least one app with unit and integration tests. |
| U8 | Preserve app-aware docs workflow while adopting hardening | `.github/workflows/docs.yml`, `.github/workflows/docs-app.yml` | Adapt, not direct | Current docs workflow builds root docs and per-app docs incrementally, then merges artifacts into GitHub Pages. | Simulated update removes app docs paths and incremental merge behavior. | Run `task docs:build`; PR docs workflow should build changed root/app docs. |
| U9 | Preserve app release matrix while adopting hardening | `.github/workflows/release-please.yml`, `docker-app.yml` | Adapt, not direct | Current release workflow maps Release Please outputs to per-app Docker builds. | Template changes can revert to single-image assumptions if applied blindly. | Validate workflow syntax and inspect release-please output contract before merge. |
| U10 | Add Docker digest Renovate rule | `renovate.json` | Direct | Groups Docker digest updates and keeps manual review for supply-chain changes. | Low risk; may increase dependency PR volume if digest management is enabled. | Validate Renovate config schema or wait for Renovate onboarding/check. |
| U11 | Update root dev dependencies | `pyproject.toml`, `uv.lock` | Adapt | Upstream bumps `coverage`, `mkdocstrings`, `zensical`, `ty`, `ruff`, `types-PyYAML`, and `pre-commit`. | Do not re-add root runtime dependencies or build backend; this repo intentionally treats root as a virtual workspace. Keep `mkdocs-click-zoom`, `reuse`, and `cosalette[mcp]` unless explicitly removed. | `task sync`; `task lint`; `task typecheck`; app test sample or full `task pre-pr`. |
| U12 | Add security audit tooling dependencies | `pyproject.toml` | Adapt | Enables `pip-audit`, `detect-secrets`, `actionlint`, and `zizmor` checks from the new QA wrapper. | No `.secrets.baseline` currently exists; adopting `detect-secrets` requires baseline creation and policy choices. `zizmor` may flag existing workflows. | Run security checks separately before gating them in `pre-pr`. |
| U13 | Introduce durable QA wrapper | `scripts/qa-task.sh` | Adapt heavily | Provides per-task logs, status files, timeouts, nested-wrapper prevention, and common task implementations. | Template assumes one package at `packages/src/<module>` and one module name; monorepo app tasks need app-specific `PKG`, `MODULE_NAME`, working directory, coverage files, and skip behavior. | Start with root-only wrapper or one app pilot; run `task test:file`, app unit tests, and failure-path checks. |
| U14 | Introduce pre-PR timeout wrapper | `scripts/pre-pr.sh`, `Taskfile.yml` | Adapt | Gives each pre-PR phase a deadline and stops at first failure with readable logs. | Must preserve current required gates: `pre-commit`, `reuse:lint`, `lint:all`, `typecheck:all`, `test:all`, `complexity`, `similarity`. Security audit should be staged after U12 is stable. | Run `task pre-pr` locally after adaptation. |
| U15 | Add `security:*` task family | `Taskfile.yml`, `scripts/qa-task.sh` | Adapt | Provides dependency, secret, Python security lint, Actions, and aggregate audit checks. | Needs `.secrets.baseline`, new dependencies, and a decision on whether security audit is required for every PR. Also avoid breaking local development when Docker or optional tools are unavailable. | Run each `security:*` task independently; then include in `pre-pr` only after stable. |
| U16 | Keep current app task includes | `Taskfile.yml` | Preserve local behavior | Existing `APPS` list and app includes are core monorepo structure. | Simulated update removed includes from the visible diff and would break `task <app>:...` commands. | `task --list`; run representative `task gas2mqtt:test:unit` or another app task. |
| U17 | Reconcile planning task changes | `Taskfile.yml` | Selective | Template reintroduces or adjusts `plan:order` and task lookup ergonomics. | Avoid churn unless `bd graph` based ordering is still useful; current planning scripts may be preferred. | Manual smoke test: `task plan:ready`, `task plan:task -- <id>`. |
| U18 | Consider CodeQL workflow | `.github/workflows/codeql.yml` | Optional new work | Adds GitHub-native Python static analysis on push, PR, and schedule. | New required-status or alert surface; must decide paths and whether CodeQL should analyze all app packages. | Add as separate PR or separate commit; validate with Actions. |
| U19 | Consider per-app edge Docker workflow | `build-edge.yml` equivalent | Optional new work | Rebuilds `edge` tags after base-image or dependency refresh without cutting releases. | Single-project template workflow is wrong for this repo; needs app matrix and per-app image names. | Manual `workflow_dispatch` dry run for one app if implemented. |
| U20 | Keep docs preview disabled | `docs-preview.yml` equivalent | Skip for now | `surge_token: false` means the template should not generate this workflow. | Enabling preview would add secrets, hosted preview lifecycle, and `pull_request_target` security considerations. | None unless the feature is explicitly requested. |

## Implementation Options

| Option | What it does | Advantages | Disadvantages | Recommendation |
| --- | --- | --- | --- | --- |
| A: Direct Copier update | Apply the simulated update and resolve conflicts in place. | Fastest route to bump `_commit`; preserves a simple template-update story. | High regression risk for monorepo CI, docs, release, `Taskfile.yml`, and root packaging. Reject files already show multiple contested areas. | Not recommended. |
| B: Selective monorepo-aware backport | Apply clean low-risk updates directly, adapt CI/docs/release/task/security changes to existing monorepo patterns, then bump `_commit`. | Captures the release value while preserving local architecture. Keeps reviewable commits by concern. | More manual work; future Copier updates may still conflict unless upstream template learns these monorepo patterns. | Recommended. |
| C: Defer pin bump, file follow-up tasks | Do not consume `v1.18.0` now; record candidate updates as separate issues. | Lowest immediate risk; useful if current branch is time-boxed. | Leaves template drift unresolved and security hardening deferred. | Acceptable only if no implementation capacity is available. |
| D: Upstream monorepo support first | Update `tmpl_python_project_kickstart` so its generated output matches this repo's monorepo architecture, then rerun Copier. | Best long-term Copier ergonomics; fewer local conflict resolutions later. | Larger scope across repositories and template design. May need ADR-level decision. | Consider after this update if future Copier drift remains painful. |

## Recommended Plan

| Phase | Changes | Files | Gate before next phase |
| --- | --- | --- | --- |
| 1 | Apply low-risk direct updates: PR schema, Renovate Docker digest rule, devcontainer-build action pins. | `.github/skills/pr-review/feedback-schema.json`, `renovate.json`, `.github/workflows/devcontainer-build.yml` | `uv run actionlint` or wrapper equivalent; JSON validation. |
| 2 | Add and pilot the devcontainer composite action without changing all workflows at once. | `.github/actions/devcontainer-run/action.yml`, one workflow caller | CI for the pilot caller passes. |
| 3 | Adapt action pinning and composite usage across CI/docs/release workflows while preserving monorepo dispatch. | `.github/workflows/*.yml` | `actionlint`; PR CI on app-only and shared-only changes. |
| 4 | Update dependency pins without changing root package semantics. | `pyproject.toml`, `uv.lock` | `task sync`; `task lint`; `task typecheck`; selected app tests. |
| 5 | Introduce QA wrapper and pre-PR timeout behavior as monorepo-aware scripts. | `scripts/qa-task.sh`, `scripts/pre-pr.sh`, `Taskfile.yml` | `task pre-pr` succeeds locally. |
| 6 | Add security tasks as a staged gate only after baseline and tool noise are known. | `Taskfile.yml`, `.secrets.baseline` if needed, `pyproject.toml` | Each `security:*` task passes independently. |
| 7 | Decide optional workflows separately. | `codeql.yml`, per-app `build-edge.yml` equivalent, docs preview if requested | Separate review or ADR if they become required checks. |
| 8 | Bump Copier commit after selected updates are implemented. | `.copier-answers.yml` | `copier update --pretend --vcs-ref :current:` shows no unexpected drift for selected scope. |

## Open Questions

| Question | Why it matters | Suggested default |
| --- | --- | --- |
| Should the target be recorded as `v1.18.0` despite the request saying `0.18.0`? | There is no upstream `0.18.0` tag. | Use `v1.18.0`. |
| Should security audit become part of `task pre-pr` immediately? | It adds new tools and currently lacks a detect-secrets baseline. | Add security tasks first, gate later. |
| Should CodeQL be introduced now? | It creates a new GitHub security signal and possibly new required-check policy. | Separate PR or later phase. |
| Should `edge` Docker builds exist per app? | The template has a single-image edge workflow, but this repo publishes app images. | Defer until an app release workflow needs it. |
| Should upstream template learn this repo's monorepo structure? | Repeated manual conflict resolution means the template and consumer architecture have diverged. | Consider after completing this update. |

## Notes

Copier update is a three-way merge anchored by `_commit`. The reject files mean
both the template and this repository changed the same areas since `v1.17.0`.
That is expected for workflow and task files in this monorepo: local changes are
architectural, not incidental formatting. The safe path is to preserve local
ownership boundaries first, then backport the upstream hardening where it fits.
