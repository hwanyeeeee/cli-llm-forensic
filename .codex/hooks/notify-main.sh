#!/usr/bin/env bash
# Codex Stop hook wrapper: codex는 stdin JSON에 `cwd`를 넣어준다.
# 그 값을 CLAUDE_PROJECT_DIR로 승격해 claude용 notify-main.sh를 재사용한다.
# 둘 다 tmux $TMUX_PANE 기반 분기라 메시지 생성 로직을 공유할 수 있다.
set -euo pipefail

INPUT="$(cat || true)"
PROJECT_ROOT=$(printf '%s' "$INPUT" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
PROJECT_ROOT="${PROJECT_ROOT:-$PWD}"

export CLAUDE_PROJECT_DIR="$PROJECT_ROOT"
exec bash "$PROJECT_ROOT/.claude/hooks/notify-main.sh"
