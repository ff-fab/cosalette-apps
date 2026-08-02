# Enhancement Proposal: `cosalette ai init` in multi-agent repositories

**Status:** accepted — cosalette will ship the fix; findings 1 and 2 confirmed for
implementation
**Raised by:** cosalette-apps, during the multi-agent configuration consolidation
(beads epic `cap-pm1`)
**Verified against:** cosalette 0.5.8 (`_package_cli/_ai_init.py`,
`_package_cli/_json_config.py`, `_package_cli/__init__.py`)

## Context

cosalette-apps is consolidating its AI agent configuration so that one physical copy
of each instruction, skill and agent definition serves GitHub Copilot, Claude Code and
Kilo at once. The mechanism this relies on is that **every agent tool ignores
frontmatter keys it does not recognise**, so a single file can carry two or three
vocabularies simultaneously.

That works well against the tools themselves. It collides with `cosalette ai init`,
which owns one of those shared files and manages blocks in two others. The findings
below came out of implementing the consolidation; each one is a place where the
framework's generator and a multi-agent downstream repo disagree about who owns what.

None of these are bugs in the sense of crashing. They are all **silent** — the
generator does what it says it does, the repository ends up degraded, and nothing
reports an error. That is what makes them worth fixing centrally rather than
documenting downstream.

## Finding 1 — `--force` destroys downstream frontmatter (highest impact)

`_copy_template_to_target()` performs a wholesale `shutil.copy2(template_path, target)`.
Anything the downstream repository added to `.github/instructions/cosalette.instructions.md`
is gone.

Our concrete case: we add a `paths:` key beside the shipped `applyTo:` key, because
`applyTo` scopes the file for Copilot and `paths` scopes the identical file for Claude
Code.

```yaml
---
description: 'cosalette framework development guidance for AI agents'
applyTo: '**/*.py' # Copilot
paths: # Claude Code
  - '**/*.py'
---
```

After `cosalette ai init --force`, `paths:` is gone. There is no error, no warning, and
no diff — the key simply stops being there.

Once the `.claude/rules/` wiring lands (phase 2 of our consolidation; it does not exist
in the repository yet, so this symptom is not currently reproducible here), Claude Code
will then treat the file as unconditional and load all 10.9 KB of Python framework
guidance into **every** session, including sessions that never touch Python. The only
symptom will be a quietly larger context window.

This is sharpened by `_display_next_steps()`, which tells the user:

> • Customize instruction file for your project

The tool invites customisation and then documents `--force` as the refresh path that
discards it.

**Proposed fix (in preference order):**

1. **Preserve frontmatter on refresh.** Parse the target's frontmatter, overwrite only
   the keys the template owns (`description`, `applyTo`), and carry every other key
   through untouched. Unknown keys are the entire basis of cross-tool config sharing;
   the framework should treat them as downstream property.
2. **Marker-manage the body**, exactly as `_manage_agent_pointer_block()` already does
   for AGENTS.md/CLAUDE.md. Wrap generated content in
   `<!-- BEGIN COSALETTE GUIDANCE v:N -->` / `<!-- END COSALETTE GUIDANCE -->` and
   preserve anything outside the markers. This also lets downstream repos append
   project-specific framework notes that survive upgrades.
3. **At minimum, refuse to discard silently.** Have `--force` diff the target against
   the template and report what it is about to drop.

Options 1 and 2 are complementary and together make refresh non-destructive for both
frontmatter and body.

## Finding 2 — no way to ask "is my guidance current?"

There is no `--check` or dry-run. The only way to find out whether the instruction file
matches the shipped template is to overwrite it, which (per Finding 1) is exactly the
destructive operation you wanted to avoid.

By comparison, `bd setup <recipe> --check` reports installation status and exits
non-zero, which makes it usable as a CI gate.

**Proposed fix:** add `cosalette ai init --check`, exiting non-zero when the target is
missing or its generated content differs from the shipped template, and printing the
diff. Pair it with a version or content-hash marker in the generated file — the pointer
block already carries `v:1`, so the convention exists — so staleness can be detected
without a byte comparison against an installed wheel.

This is what lets a downstream repo protect Finding 1 in pre-commit or CI rather than
relying on people remembering.

## Finding 3 — `--kilo` strips every comment from `kilo.jsonc`

`_manage_json_config()` is called for `kilo.jsonc` with `strip_comments=True`. It parses
the file with comments removed and then writes it back with:

```python
content = json.dumps(existing, indent=2) + "\n"
```

Round-tripping a `.jsonc` file through this deletes every comment in it — which is the
only reason to use JSONC rather than JSON. A downstream `kilo.jsonc` that documents why
each `instructions` entry and `permission` rule exists loses all of it the first time
`cosalette ai init --kilo` has something to add.

**Proposed fix:** perform a surgical text edit that appends to the existing
`instructions` array in place, or use a comment-preserving JSONC round-tripper. Failing
either, detect that comments were present and warn before rewriting, so the loss is at
least visible.

The symlink and malformed-JSON paths are already fail-closed and well handled; this is
the one remaining case where the function silently discards user content.

## Finding 4 — the pointer block is written to both AGENTS.md and CLAUDE.md

`_handle_agent_file_management()` calls `_manage_agent_pointer_block()` on AGENTS.md and
CLAUDE.md unconditionally. In a repository following the documented cross-tool pattern —
`AGENTS.md` canonical, `CLAUDE.md` reduced to an `@AGENTS.md` import — Claude Code then
receives the cosalette section **twice**: once through the import, once from CLAUDE.md's
own copy.

Harmless in isolation, but it is duplicated context in every session, and it grows if
the block ever grows.

**Proposed fix:** before writing the CLAUDE.md block, check whether CLAUDE.md already
pulls in AGENTS.md — either an `@AGENTS.md` import line or a symlink — and skip it if so.
A `--no-claude` escape hatch would also do, but detection needs no flag and is right by
default.

Related, minor: when CLAUDE.md **is** a symlink, `_manage_agent_pointer_block()` correctly
refuses to follow it (CWE-59) and returns `False` — but the caller then prints
`ℹ️ CLAUDE.md exists but no updates needed`, which reads as "all good" rather than
"skipped". The symlink message is printed by the callee, so the two lines contradict each
other.

## Finding 5 — MCP config is VS Code-only and pins an absolute interpreter path

`_manage_mcp_config()` writes `.vscode/mcp.json` with:

```python
cos_cfg = {"command": sys.executable, "args": ["-m", "cosalette", "ai", "mcp", "serve"]}
```

Two consequences:

- **Portability.** `sys.executable` is an absolute path. In our committed
  `.vscode/mcp.json` that is `/workspaces/cosalette-apps/.venv/bin/python3`, which is
  correct only for a devcontainer checked out at that exact path. Any other clone
  location, or a host-side (non-container) checkout, gets a broken server entry in a
  tracked file.
- **Coverage.** Claude Code reads `mcpServers` (in `.mcp.json` or a plugin manifest) and
  Kilo reads an `mcp` block in `kilo.jsonc`, with `type: local | remote`. The three
  formats are not interchangeable, so a repository wanting the cosalette MCP server in
  all three tools writes two of them by hand and keeps them in sync manually.

**Proposed fix:** emit a relocatable command (for example `uv run --package cosalette
python -m cosalette ai mcp serve`, or plain `python3 -m cosalette ...` resolved through
the active environment) rather than an absolute interpreter path. Then extend the
generator with per-tool MCP targets — `--claude` and `--kilo` writing the corresponding
formats — so the server is configured once for every agent, the same way the instruction
pointer already is.

## Finding 6 — `--opencode` is now redundant with `--kilo`

Kilo v7 is a fork of OpenCode; a single `kilo.jsonc` drives the Kilo VS Code extension,
the Kilo CLI and Kilo Cloud Agents, and Kilo's loader still accepts `opencode.json` as a
legacy path. This repository is in the process of deleting its `opencode.json` and
`.opencode` symlinks precisely because maintaining both surfaces produced two
configurations that had to agree and silently did not.

**Proposed fix:** deprecate `--opencode` in favour of `--kilo`, with a deprecation notice
pointing at the replacement. This is a report from the field rather than a defect —
offering both flags nudges downstream repos into the duplication we just spent an epic
removing.

## Summary

| # | Finding                                        | Impact                                             | Suggested fix                              |
| - | ---------------------------------------------- | -------------------------------------------------- | ------------------------------------------ |
| 1 | `--force` overwrites downstream frontmatter    | Silent loss of cross-tool scoping keys              | Preserve frontmatter; marker-manage body   |
| 2 | No `--check` / dry-run                         | Staleness cannot be gated in CI                     | Add `--check` + version marker             |
| 3 | `--kilo` strips JSONC comments                 | Silent loss of downstream config documentation      | In-place edit or comment-preserving writer |
| 4 | Pointer block written to AGENTS.md *and* CLAUDE.md | Duplicated context under the `@AGENTS.md` pattern | Detect the import/symlink and skip         |
| 5 | MCP config VS Code-only, absolute interpreter  | Broken outside one checkout path; two hand-written copies | Relocatable command; `--claude` / `--kilo` targets |
| 6 | `--opencode` redundant with `--kilo`           | Encourages duplicate config surfaces                | Deprecate `--opencode`                     |

Findings 1 and 2 are the ones that actively cost this repository something today, and
they are best fixed together: non-destructive refresh, plus a way to verify it.

## What cosalette-apps is doing

Findings 1 and 2 will be fixed in the framework, so this repository builds **no local
guard** against them — `cap-pm1.13` was closed as dropped rather than implemented. A
downstream workaround would defend against a failure mode that is about to disappear,
and it would have pushed the config checker (`cap-pm1.10`) past the deliberately thin
scope of symlink resolution plus JSON-schema validation.

- `paths:` stays in `cosalette.instructions.md`, with an inline comment in that file
  warning that `--force` drops it, and a matching warning beside the `cosalette ai init
  --force` invocation in `AGENTS.md`. Once the framework preserves downstream
  frontmatter, both become documentation rather than warnings.
- `--opencode` is not used; `opencode.json` is being deleted.
- The `.vscode/mcp.json` entry is kept as generated, with the absolute path accepted as a
  devcontainer-only constraint.

**One request on the shape of the fix.** The value of finding 1 is entirely in
preserving keys the framework does not recognise. A fix that preserves a known allowlist
of extra keys would not help — the next tool this repository adopts will bring a key
nobody has thought of yet. Unknown keys need to be treated as downstream property by
default. If the change lands narrower than that, we will need the local guard after all.
