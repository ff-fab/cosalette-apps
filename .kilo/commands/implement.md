---
description:
  Execute a plan with strict Implementation → Review gating. First create a plan in plan
  mode (Tab), then use this command to execute it.
agent: implement
model: opencode-go/deepseek-v4-pro
subtask: false
---

<!-- Kilo-only. `.github/prompts/` was removed in cap-pm1 phase 1 and this command never
     had a Copilot source; it drives the Kilo `implement` agent (.kilo/agents/implement.md,
     mirrored from .github/agents/orchestrator.agent.md). -->

Execute the development plan found in `.kilo/plans/`. If no plan exists, tell the user
to enter plan mode (press Tab in TUI) to create one first.

$ARGUMENTS
