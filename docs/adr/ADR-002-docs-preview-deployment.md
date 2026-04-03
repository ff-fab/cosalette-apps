# ADR-002: Docs Preview Deployment Strategy

## Status

Accepted **Date:** 2026-04-03

## Context

This monorepo has multiple app doc sites + 1 root site, all built with zensical (MkDocs
wrapper). Production docs deploy to GitHub Pages via `actions/deploy-pages@v4`
(artifact-based, NOT "deploy from branch"). The docs workflow already builds docs on PRs
but discards the artifacts (deploy is gated on pushes to main). Reviewers cannot see
rendered documentation changes before merging. We need automated preview deployments for
PRs that touch docs.

## Decision

Use Surge.sh for PR documentation preview deployments via a separate `docs-preview.yml`
GitHub Actions workflow, keeping the production deployment pipeline (`docs.yml`)
untouched.

## Decision Drivers

- Live preview URL for doc reviewers (not just downloadable artifacts)
- Zero impact on production deployment pipeline
- Minimal infrastructure/setup complexity
- Automatic cleanup on PR close/merge
- Free and suitable for open-source projects
- Potential for extraction as a reusable GitHub Action

## Considered Options

- **Option A: Surge.sh preview deploys** — Deploy merged doc site to
  `<project>-pr-<N>.surge.sh` on PR creation/update. Comment on PR with preview URL.
  Teardown on PR close.
- **Option B: Cloudflare Pages** — Use Cloudflare Pages with automatic preview URLs per
  branch. Enterprise-grade CDN, free tier available.
- **Option C: Artifact-only + download link** — Upload merged doc artifact, post comment
  with download link. No live preview URL.
- **Option D: rossjrw/pr-preview-action** — Commits preview builds to subdirectories on
  `gh-pages` branch.
- **Option E: Separate GitHub Pages repo** — Push previews to a dedicated
  `cosalette-apps-previews` repo with its own GitHub Pages.

## Decision Matrix

| Criterion            | Surge.sh | Cloudflare Pages | Artifact-only | pr-preview-action | Separate repo |
| -------------------- | -------- | ---------------- | ------------- | ----------------- | ------------- |
| Live URL             | 5        | 5                | 1             | 5                 | 5             |
| Setup complexity     | 5        | 3                | 5             | 1                 | 2             |
| Production isolation | 5        | 5                | 5             | 1                 | 5             |
| Auto-cleanup         | 4        | 5                | 5             | 4                 | 3             |
| External deps        | 3        | 2                | 5             | 5                 | 4             |
| Extractability       | 4        | 3                | 2             | 3                 | 2             |
| **Total**            | **26**   | **23**           | **23**        | **19**            | **21**        |

_Scale: 1 (poor) to 5 (excellent)_

**Notes:** pr-preview-action scores 1 on production isolation because it requires
switching GitHub Pages from "Deploy from Actions" to "Deploy from branch" mode — a
fundamental rearchitecture of the current deployment pipeline. Cloudflare Pages scores
lower on setup complexity due to account/API token/wrangler configuration requirements.

## Consequences

### Positive

- Reviewers get instant live preview URLs for documentation changes
- Production pipeline remains completely untouched
- Single secret (`SURGE_TOKEN`) is the only infrastructure requirement
- Workflow logic is simple enough to extract as a reusable action later
- Surge.sh free tier has no bandwidth or project limits for public sites

### Negative

- External SaaS dependency (Surge.sh must remain available)
- Preview URLs use `surge.sh` domain, not the project's GitHub Pages domain
- Full doc rebuild on every PR update (no incremental caching), though this ensures
  previews are always self-contained
- Requires `SURGE_TOKEN` repository secret to be configured

## Implementation Notes

- Separate workflow (`docs-preview.yml`) triggered on PR events
- Full rebuild of all doc sites (not incremental) — previews are self-contained
- Sticky PR comment with preview URL and list of changed pages
- Automatic teardown via `surge teardown` on PR close

_2026-04-03_
