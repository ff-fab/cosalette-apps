---
description:
  Execute a plan with strict Implementation → Review gating. First create a plan in plan
  mode (Tab), then use this command to execute it.
agent: implement
model: opencode-go/deepseek-v4-pro
subtask: false
---

<!-- mirrors .github/prompts/implement.prompt.md — keep description in sync -->

Execute the development plan found in `.kilo/plans/`. If no plan exists, tell the user
to enter plan mode (press Tab in TUI) to create one first.

$ARGUMENTS
