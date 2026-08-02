---
name: implementation-subagent
description: Implementation subagent — executes task-specific work delegated by the orchestrator
argument-hint: Task objective, files to modify, test requirements, and acceptance criteria from the orchestrator
# tools: union of Copilot and Claude Code names — see CONTRIBUTING.md "AI Agent Setup".
# Enforced by `task check:agents`: at least one name from each vocabulary is required.
tools:
  ['edit', 'search', 'read', 'execute/runInTerminal', 'execute/getTerminalOutput',
   'execute/createAndRunTask', 'todo', 'Read', 'Grep', 'Glob', 'Edit', 'Write', 'Bash',
   'TodoWrite']
# model: deliberately absent — the one key that is NOT shareable. Copilot, Claude
# Code and Kilo each parse it with an incompatible vocabulary, and a foreign value
# hard-errors in Claude Code. Preferred model when pinning per tool: Sonnet-class.
# See CONTRIBUTING.md "AI Agent Setup" > "The one key that cannot be shared".
---

Execute the implementation task described by the orchestrator. Follow the orchestrator's
task-specific instructions exactly.

**Quality gate:** Before returning, run `task lint` and `task test:unit`. Report results
in `quality_results`.

**Output contract:** Return results as JSON conforming to
`.github/agents/schemas/implementation-output.schema.json`.
