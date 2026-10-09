---
status: Accepted
date: 2026-10-09
impact: moderate
tags: [packaging, dependencies, cli]
---

# ADR-013: App images ship without rich

## Status

Accepted **Date:** 2026-10-09 | Amended **Date:** 2026-10-09

## Context

cosalette depends on typer, and typer requires rich, which pulls in pygments, markdown-it-py and mdurl. Every app image shipped all four although they load only to colour `--help` output and usage errors, never on the run path. Measured in the built images (python:3.14-alpine, cosalette 0.11.2): the four packages take 14.4 MB of site-packages, and every image is 18.6 MB larger with their bytecode included (gas2mqtt 161.9 MB, caldates2mqtt 229.9 MB). Nine apps on one host pay that nine times, because the install layer is per app.

cosalette 0.11.1 (upstream ADR-005 amendment) makes its own Typer instances fall back to Click's plain formatter when rich, pygments or markdown-it-py are missing, and its containerize guide suggests excluding rich with a uv `override-dependencies = ["rich; sys_platform == 'never'"]` entry. In this repo that override would sit in the root pyproject and rewrite the one workspace lock, but the dev group needs rich: pip-audit, cyclonedx-python-lib, fastmcp and cyclopts (through `cosalette[mcp]`) all depend on it. Separately, wiz2mqtt ships two Typer CLIs of its own (`wiz2mqtt-discover`, `wiz2mqtt-openhab`) that the cosalette fallback does not cover; without rich they crash on `--help` unless typer is told rich is absent.

The Dockerfiles install from `uv export` output. That export already lists the full locked closure, but the install step re-resolved it: with rich left out of the file, uv fetched the newest rich from PyPI to satisfy typer's requirement.

## Decision

Remove rich from the app images at export time, not in the lock: each Dockerfile runs `uv export --prune rich`, installs the exported file with `--no-deps`, and sets `ENV TYPER_USE_RICH=0`. `--prune rich` drops rich and the packages only it needs (pygments, markdown-it-py, mdurl) from the exported requirements while uv.lock and the dev environment keep them. `--no-deps` makes the install take the exported closure as final, so nothing re-resolves rich back in. `TYPER_USE_RICH=0` switches every Typer CLI in the image, including app-owned ones, to Click's plain help and error output.

```dockerfile
RUN --mount=from=ghcr.io/astral-sh/uv:0.6,source=/uv,target=/bin/uv \
    uv export --frozen --no-dev --no-emit-workspace --prune rich --package <app> \
      --format requirements-txt >/tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode --no-deps -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --compile-bytecode --no-deps ./apps/<app> \
    ...

ENV TYPER_USE_RICH=0
```

## Decision Drivers

- Image size on small hosts: 18.6 MB per image for code that never runs on the service path
- Dev tooling (pip-audit, cosalette[mcp]) must keep rich, so the change cannot touch the shared workspace lock
- --help and usage errors must keep working for every CLI in the image, including app-owned Typer apps
- The image must keep installing exactly the locked versions, with no PyPI re-resolve

## Considered Options

### Option 1: Export-time prune with TYPER_USE_RICH=0 (chosen)

`uv export --prune rich` in each Dockerfile, `--no-deps` on the locked install, and `ENV TYPER_USE_RICH=0` in the image.

- *Advantages:* uv.lock and the dev environment are unchanged, so pip-audit and cosalette[mcp] keep rich; Drops exactly rich, pygments, markdown-it-py and mdurl and nothing else (verified by diffing installed distributions per image); --no-deps also closes a latent gap: the locked install can no longer pull anything from PyPI that the lock does not list; Covers app-owned Typer CLIs such as wiz2mqtt-discover
- *Disadvantages:* Help output in the images is plain Click text without rich panels; Every Dockerfile and the scaffold template carry the flags; a unit test guards them

### Option 2: Root uv override-dependencies

Add `override-dependencies = ["rich; sys_platform == 'never'"]` to the root pyproject, as the cosalette containerize guide suggests.

- *Advantages:* One line, and the lock itself proves rich is gone; The upstream-documented approach
- *Disadvantages:* Applies to the whole workspace lock: pip-audit, cyclonedx-python-lib, fastmcp and cyclopts lose a hard dependency and break in the dev environment; App-owned Typer CLIs still crash on --help without TYPER_USE_RICH=0

### Option 3: Uninstall rich after the install

Keep the install as it is and run `uv pip uninstall --system rich pygments markdown-it-py mdurl` in the same RUN step.

- *Advantages:* No change to the export or install flags
- *Disadvantages:* The package list is maintained by hand and goes stale when rich changes its own dependencies; The image still re-resolves at build time, so it can install versions the lock does not list

### Option 4: Keep rich in the images

Leave the images as they are.

- *Advantages:* Coloured help output in the container
- *Disadvantages:* 18.6 MB per image for code the service never loads

## Decision Matrix

| Criterion | Export-time prune with TYPER_USE_RICH=0 | Root uv override-dependencies | Uninstall rich after the install | Keep rich in the images |
| --- | --- | --- | --- | --- |
| Image size saved | 5 | 5 | 5 | 1 |
| Dev tooling unaffected | 5 | 1 | 5 | 5 |
| Every CLI in the image keeps working | 5 | 2 | 2 | 5 |
| Image installs exactly the locked graph | 5 | 4 | 3 | 4 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Every app image is 18.6 MB smaller (for example gas2mqtt 161.9 MB to 143.3 MB, caldates2mqtt 229.9 MB to 211.2 MB)
- The locked install no longer re-resolves against PyPI, so the image gets exactly the exported closure
- --help, --version and usage errors still work in every image, with the same exit codes

### Negative

- Help in the images is plain text; the dev environment keeps the rich panels, so the two look different
- A new app Dockerfile must carry the three changes; the scaffold template and test_app_image_contents.py enforce them

## Amendment (2026-10-09) — Additive

**Rationale:** cosalette 0.11.3 documented a uv sync recipe for slim images. We asked upstream to move its CLI from Typer to Click so that a default install carries no rich (cap-6d4k). Upstream deferred that again (cos-l8bp) and instead made this ADR's pattern the official rule for images installed from uv export. This amendment records that ADR-013 follows upstream and that the workaround is permanent, not a stopgap.

### Additional Sub-Decision: Follow the upstream install-time rule; the workaround is permanent

Upstream (cosalette, cos-l8bp) now documents this ADR's pattern as the rule for export-based images: `uv export --frozen --no-dev --prune rich` followed by `uv pip install --no-deps`. `--no-deps` is required, because without it uv resolves typer's dependencies again and installs rich, pygments, markdown-it-py and mdurl. Upstream verified this with uv 0.6.17 and 0.12.19. This repo installs from `uv export` rather than `uv sync`, so it follows that rule and does not diverge from upstream.

Upstream deferred the Click migration. It will reconsider only if one of these happens:

- Typer is no longer maintained.
- rich can no longer be skipped at install time.
- A measured runtime problem appears with the Typer packages that remain.

Upstream accepts that a default `pip install cosalette` still installs rich, and that every slim image has to repeat the exclusion. It treats both as known costs, not as reasons to reconsider. Moving to Click would save only about 0.3 MB per image: typer, shellingham and annotated-doc take 1.38 MB, and click takes 1.10 MB (typer 0.27.3, click 8.5.0).

The workaround is therefore permanent. It consists of `--prune rich` and `--no-deps` in the 9 Dockerfiles and `scripts/scaffold-app.sh`, plus the guard `test_dockerfile_ships_without_rich` in `packages/tests/unit/test_app_image_contents.py`. Revisit it only if upstream reconsiders under one of the conditions above.

### Additional Sub-Decision: TYPER_USE_RICH=0 stays for now

Upstream's recipe needs `TYPER_USE_RICH=0` only for apps that build their own Typer CLI; here that is wiz2mqtt alone. cosalette 0.11.3 already switches its own Typer instances to plain Click output when rich is missing (`_utils._typer_options()`).

The gas2mqtt image was built from main and run with the variable unset. `--help`, `--version`, usage errors, `schema` and `health` all kept their exit codes and printed no traceback. The `--help` and usage-error output was byte-identical with and without the variable. The variable is therefore redundant for apps without their own Typer CLI.

It stays in every image until cap-fbbg removes it where redundant. It also still guards wiz2mqtt.

### Additional Negative Consequences

- Every Dockerfile carries the exclusion permanently. Upstream accepts this repetition as a known cost and will not remove it with a framework change.
