---
description:
  Implementation subagent — executes task-specific work delegated by the orchestrator
mode: subagent
model: opencode-go/deepseek-v4-pro
steps: 35
permission:
  edit: allow
  search: allow
  read: allow
  bash: ask
---

<!-- mirrors .github/agents/implementation-subagent.agent.md — keep description in sync -->

Execute the implementation task described by the orchestrator. Follow the orchestrator's
task-specific instructions exactly.

**Quality gate:** Before returning, run `task lint` and `task test:unit`. Report results
in `quality_results`.

**Output contract:** Return results as JSON conforming to
`.github/agents/schemas/implementation-output.schema.json`.
