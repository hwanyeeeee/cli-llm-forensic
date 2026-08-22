---
name: dev-swap
description: "Replace panel 1 dev tool (kill+respawn, dispatch handover). Use only when explicitly invoked with $dev-swap and argument claude or codex."
---

# dev-swap (codex wrapper)

Accept input from the explicit invocation: claude|codex. If missing or invalid, print the usage line from the source document and stop.

1. Resolve repo root: `git rev-parse --show-toplevel`.
2. Read `<root>/.claude/commands/dev-swap.md` completely — it is the single source of truth.
3. Treat your invocation argument as that document's `$1`.
4. Ignore Claude-specific frontmatter (`allowed-tools`, `argument-hint`).
5. Execute the numbered body in order using actual shell tools.
6. Stop on the first failed command and report the exact failure.
7. Do not claim completion unless the commands actually ran successfully.
