# CLAUDE.md

@AGENTS.md

## Claude Code

`AGENTS.md` above is the canonical instruction set, shared with GitHub Copilot and Kilo.

**Claude Code loads `.github/instructions/*.instructions.md` automatically.** Each one
is symlinked into `.claude/rules/`, where Claude honours the `paths:` frontmatter key.
You do not need to open them yourself:

| When working on                 | Loads automatically                                 |
| ------------------------------- | --------------------------------------------------- |
| any file                        | `tooling`, `workflow` (no `paths:` — unconditional) |
| `**/*.py`                       | `python`, `cosalette`                               |
| `apps/*/packages/tests/**/*.py` | `testing-python`                                    |
| `**/*.md`                       | `documentation`                                     |

The symlinks are committed (git stores them as links, mode `120000`). To add a rule,
create the file in `.github/instructions/`. For file-scoped rules add both `applyTo:`
(Copilot) and `paths:` (Claude Code), then symlink it. Kilo ignores both and loads every
instruction file unconditionally. For unconditional rules use `applyTo: '**'` and omit
`paths:` — its absence means "load every session":

```bash
ln -s ../../.github/instructions/<name>.instructions.md .claude/rules/<name>.md
```

<!-- BEGIN COSALETTE AI SUPPORT v:1 -->
<!-- END COSALETTE AI SUPPORT -->

<!-- The cosalette pointer block is deliberately empty here — AGENTS.md carries it and
     is imported above. `cosalette ai init` re-injects it into both files, so expect this
     block to reappear populated after a refresh; emptying it again is the intended fix. -->

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->

<!-- END BEADS INTEGRATION -->
