#!/usr/bin/env bash
# Register THIS pane's harness role so routing self-heals across resume/restart.
# Determines role by the pane's position in its window (1st = panel0, 2nd = panel1),
# then writes a durable @fa_role tag AND refreshes the .harness/<role>.id cache.
#
# Idempotent. Safe to call on every session start (Claude SessionStart hook) and at
# the top of the Stop hook. No-op outside tmux and for claude-mem worker subprocesses.
set -uo pipefail

# Skip claude-mem worker sub-processes (they inherit TMUX_PANE but aren't a panel).
[ -n "${CLAUDE_MEM_WORKER_PORT:-}${CLAUDE_MEM_DATA_DIR:-}" ] && exit 0

P="${TMUX_PANE:-}"
[ -n "$P" ] || exit 0                      # not in tmux
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"

WIN="$(tmux display-message -p -t "$P" '#{window_id}' 2>/dev/null || true)"
[ -n "$WIN" ] || exit 0

# Position of THIS pane among its window's panes (sorted by index).
POS="$(tmux list-panes -t "$WIN" -F '#{pane_index} #{pane_id}' 2>/dev/null \
       | sort -n | awk -v me="$P" '$2==me{print NR; exit}')"
case "$POS" in
  1) ROLE=panel0 ;;
  2) ROLE=panel1 ;;
  *) exit 0 ;;            # ambiguous (>2 panes or not found) — leave existing state
esac

tmux set-option -p -t "$P" @fa_role "$ROLE" 2>/dev/null || true
mkdir -p "$ROOT/.harness"
printf '%s\n' "$P" > "$ROOT/.harness/$ROLE.id"

# 위치기반으로 정한 ROLE을 stdout으로 반환(단일 진실원천). 호출측(CLAUDE.md
# 세션시작 스니펫)이 이 값을 직접 쓰므로 tmux @fa_role 재조회가 불필요해진다 —
# `display-message -p`의 active-pane 기본 타겟 footgun(비활성 panel1이 panel0
# 값을 읽던 버그)을 원천 제거.
printf '%s\n' "$ROLE"
