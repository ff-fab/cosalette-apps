---
name: implementation-subagent
description: Implementation subagent — executes task-specific work delegated by the orchestrator
argument-hint: Task objective, files to modify, test requirements, and acceptance criteria from the orchestrator
# tools: union of Copilot and Claude Code names — see CONTRIBUTING.md "AI Agent Setup".
# Enforced by `task check-parity`: at least one name from each vocabulary is required.
tools:
  ['edit', 'search', 'read', 'execute/runInTerminal', 'execute/getTerminalOutput',
   'execute/createAndRunTask', 'todo', 'Read', 'Grep', 'Glob', 'Edit', 'Write', 'Bash',
   'TodoWrite']
# model: Copilot vocabulary. Claude Code recognises this key with a DIFFERENT
# vocabulary (sonnet/opus/haiku/inherit) — see CONTRIBUTING.md "Known gaps".
model: Claude Sonnet 4.6 (copilot)
---

Execute the implementation task described by the orchestrator. Follow the orchestrator's
task-specific instructions exactly.

**Quality gate:** Before returning, run `task lint` and `task test:unit`. Report results
in `quality_results`.

**Output contract:** Return results as JSON conforming to
`.github/agents/schemas/implementation-output.schema.json`.
