---
name: orchestrator
description: Run the repository's orchestrator workflow in Codex, delegating implementation, documentation, and review work to the configured GPT-5.6 subagent models.
---

Run the workflow defined in `.github/agents/orchestrator.agent.md`. Treat that file as
the source of truth for the orchestrator's process and stopping rules.

When that workflow delegates work, first read the corresponding source prompt in
`.github/agents/`, then create a subagent with that prompt's task and these fixed model
overrides:

| Source prompt | Codex model |
| --- | --- |
| `implementation-subagent.agent.md` | `gpt-5.6-sol` |
| `docs-subagent.agent.md` | `gpt-5.6-sol` |
| `code-review-subagent.agent.md` | `gpt-5.6-terra` |

Pass the parent task's concrete context and acceptance criteria to every subagent. The
subagent must follow its source prompt, including its output contract and read-only
restriction where applicable. Do not use a different model for these roles.
