## Epic Cleanup: Enable Docker GHCR Builds on Release

Re-enabled Docker image builds to GHCR that were intentionally deferred during monorepo
migration. Fixed a build context bug in docker-app.yml and replaced the commented-out
static Docker trigger in release-please.yml with a dynamic matrix that scales
automatically with new apps.

**Files created/changed:**

- `.github/workflows/docker-app.yml`
- `.github/workflows/release-please.yml`

**Functions created/changed:**

- `docker-app.yml` build step: corrected `context` to `.` and added explicit
  `file:` path
- `release-please.yml` `docker-matrix` job: new job that parses release-please outputs
  with jq to build dynamic matrix
- `release-please.yml` `docker` job: new job that fans out Docker builds per released app

**Tests created/changed:**

- None (CI workflow changes — validated by GitHub Actions on push)

**Review Status:** APPROVED

**Git Commit Message:**

```
fix: enable Docker GHCR builds on release

- Fix docker-app.yml build context from apps/<app> to repo root
- Add explicit Dockerfile path via file: parameter
- Replace commented-out static Docker trigger with dynamic matrix
- Parse release-please outputs with jq for automatic app discovery
- Add packages:write permission to release-please.yml
```
