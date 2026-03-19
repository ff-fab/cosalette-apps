# Zensical Multi-Site Subpath Findings

Findings from deploying gas2mqtt docs under the cosalette-apps monorepo. These apply to
all future app migrations (Phase 3+).

## Architecture

Each app has its own `zensical.toml` in `apps/<name>/` and builds to its own `site/`
directory. The root monorepo also has a `zensical.toml` for project-level docs. The CI
workflow (`.github/workflows/docs.yml`) builds each site independently and deploys them
to GitHub Pages under nested subpaths:

- Root docs: `https://ff-fab.github.io/cosalette-apps/`
- App docs: `https://ff-fab.github.io/cosalette-apps/<app>/`

## Key Configuration

### site_url must include the subpath

```toml
# apps/<app>/zensical.toml
site_url = "https://ff-fab.github.io/cosalette-apps/<app>/"
```

This is critical for sitemap generation and canonical URLs. Without the trailing app
name, sitemap links point to the wrong location.

### use_directory_urls (default: true)

Keep the default. The built HTML uses relative paths (`./`, `../`) which are
subpath-agnostic. No special handling needed.

### edit_uri must point to the monorepo path

```toml
edit_uri = "edit/main/apps/<app>/docs/"
```

Not the old standalone repo path.

## Relative Links Work Out of the Box

Zensical generates relative `href` attributes (e.g., `./getting-started/`,
`../reference/settings/`). This means the built site works at any subpath without
rewriting links. No `base_url` or path prefix hacks are needed.

## mkdocstrings Directive Syntax

The `:::` directive options must use indented YAML block syntax, not inline. Prettier
will collapse indented blocks back to inline if not excluded.

```markdown
::: mymodule.MyClass
    options:
      show_bases: true
      members_order: source
```

### Prettier Exclusion

The root `.prettierignore` must use `**/docs/**` (not `docs/**`) to cover app docs
directories under `apps/<name>/docs/`.

## Checklist for Phase 3+ App Migrations

1. Set `site_url` to `https://ff-fab.github.io/cosalette-apps/<app>/`
2. Set `edit_uri` to `edit/main/apps/<app>/docs/`
3. Set `repo_url` and `repo_name` to the monorepo
4. Verify `task <app>:docs:build` succeeds
5. Spot-check HTML for relative links (no absolute `/` paths)
6. Add `build-<app>` job to `.github/workflows/docs.yml`
7. Add path filter for `apps/<app>/docs/**` and `apps/<app>/zensical.toml`
