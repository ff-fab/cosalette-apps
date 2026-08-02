# GitHub Copilot Instructions

**See [AGENTS.md](../AGENTS.md) — it is the canonical instruction file for this
repository and applies in full to Copilot.**

This stub exists because `chat.useAgentsMdFile` in `.vscode/settings.json` only reaches
Copilot inside VS Code. Copilot surfaces that do not read workspace settings — the
github.com PR review bot, the Copilot coding agent, and the JetBrains / Visual Studio /
Eclipse / Xcode / CLI clients — read this file instead. Without it they would lose every
repository policy, including "never push directly to `main`" and "never merge a PR
unless the user explicitly asks".

Keep this file a pointer. Do not copy policy into it — a second copy is how `gh pr
create` and `task pr:create` ended up in the repo at the same time.
