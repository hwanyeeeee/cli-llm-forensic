---
name: dev-diff
description: Show drift between this project and Dev-harness (read-only). Use only when explicitly invoked with $dev-diff.
---

# dev-diff (codex wrapper)

1. Resolve repo root: `git rev-parse --show-toplevel`.
2. Read `<root>/.claude/commands/dev-diff.md` completely — it is the single source of truth.
3. The document takes no arguments.
4. Ignore Claude-specific frontmatter (`allowed-tools`, `argument-hint`).
5. Execute the numbered body in order using actual shell tools.
6. Stop on the first failed command and report the exact failure.
7. Do not claim completion unless the commands actually ran successfully.
