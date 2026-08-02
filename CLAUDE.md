# CLAUDE.md

@AGENTS.md

## Claude Code

`AGENTS.md` above is the canonical instruction set, shared with GitHub Copilot and Kilo.

**Claude Code does not load `.github/instructions/*.instructions.md`.** There is no
`.claude/rules/` wiring yet — that lands in `cap-pm1` phase 2. Until then, treat those
files as reference you must open yourself:

| When working on            | Read                                                  |
| -------------------------- | ----------------------------------------------------- |
| any file                   | `.github/instructions/tooling.instructions.md`        |
| `**/*.py`                  | `python.instructions.md`, `cosalette.instructions.md` |
| `apps/*/packages/tests/**` | `testing-python.instructions.md`                      |
| `**/*.md`                  | `documentation.instructions.md`                       |

<!-- BEGIN COSALETTE AI SUPPORT v:1 -->
<!-- END COSALETTE AI SUPPORT -->

<!-- The cosalette pointer block is deliberately empty here — AGENTS.md carries it and
     is imported above. `cosalette ai init` re-injects it into both files; see finding 4
     in docs/planning/cosalette-ai-init-enhancement-proposal.md. -->

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->

<!-- END BEADS INTEGRATION -->
