#!/usr/bin/env bash
# Stop hook: panel 1(개발 세션) Claude가 턴을 마칠 때 panel 0(메인)에 알림.
# 같은 훅이 panel 0의 Claude에서도 발화하므로 pane ID로 분기. STATE가 idle이면
# 전송 자체를 중단해 무한 루프를 끊는다.

# --- claude-mem 노이즈 필터 (set -e 전에 위치) ---
INPUT=$(cat 2>/dev/null || true)
# Filter 1: claude-mem worker가 spawn한 sub-claude (env 상속)
if [ -n "${CLAUDE_MEM_WORKER_PORT:-}" ] || [ -n "${CLAUDE_MEM_DATA_DIR:-}" ]; then
    exit 0
fi
# Filter 2: transcript_path가 claude-mem 경로
TRANSCRIPT=$(echo "$INPUT" | sed -n 's/.*"transcript_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
if [ -n "$TRANSCRIPT" ] && echo "$TRANSCRIPT" | grep -qE 'claude-mem|observer-sessions'; then
    exit 0
fi
# Filter 3: 마지막 assistant text가 claude-mem observation XML
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    LAST_ASSISTANT=$(tac "$TRANSCRIPT" 2>/dev/null | grep -m1 '"type":"assistant"' || true)
    if [ -n "$LAST_ASSISTANT" ] && echo "$LAST_ASSISTANT" | grep -qE '<observer>|</observer>|<concept>|observer-sessions|<filereferences>'; then
        exit 0
    fi
fi
# --- 필터 끝 ---

set -euo pipefail

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-.}"
PANEL0_FILE="$PROJECT_ROOT/.harness/panel0.id"
PANEL1_FILE="$PROJECT_ROOT/.harness/panel1.id"
STATE_FILE="$PROJECT_ROOT/docs/STATE.md"
SEND_HELPER="$PROJECT_ROOT/.claude/bin/send-to-pane.sh"
LOG_FILE="$PROJECT_ROOT/.harness/notify.log"

log() { printf '[%s] TMUX_PANE=%s %s\n' "$(date +%H:%M:%S)" "${TMUX_PANE:-unset}" "$1" >> "$LOG_FILE"; }

[ -f "$PANEL0_FILE" ] || exit 0
[ -f "$PANEL1_FILE" ] || exit 0

PANEL0="$(cat "$PANEL0_FILE")"
PANEL1="$(cat "$PANEL1_FILE")"

# 중요: $TMUX_PANE을 써야 한다. `tmux display-message -p '#{pane_id}'`는
# "현재 포커스된 pane"을 반환하므로, 사용자가 다른 pane을 보고 있으면 오검출.
# $TMUX_PANE은 tmux가 자식 프로세스에게 넘기는 "네가 속한 pane" 값.
CURRENT="${TMUX_PANE:-}"

if [ -z "$CURRENT" ]; then
  log "skip: TMUX_PANE unset (not in tmux?)"
  exit 0
fi
if [ "$CURRENT" = "$PANEL0" ]; then
  log "skip: main($PANEL0) self-stop"
  exit 0
fi
if [ "$CURRENT" != "$PANEL1" ]; then
  log "skip: not panel1 ($CURRENT vs $PANEL1)"
  exit 0
fi

# 메인 pane이 살아있는지
if ! tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$PANEL0"; then
  log "skip: main pane $PANEL0 is dead"
  exit 0
fi

# STATE.md가 idle(## 완료 / ## ⚠ 막힘 / ## ❓ 결정 필요 중 하나)이면 전송 금지.
# `<!-- ... -->` 안의 템플릿 예시는 idle로 치면 안 되므로 sed로 코멘트 블록을 먼저 제거.
if [ -f "$STATE_FILE" ] && sed '/<!--/,/-->/d' "$STATE_FILE" | grep -qE '^## (완료|⚠ 막힘|❓ 결정 필요)'; then
  log "skip: STATE idle"
  exit 0
fi

# 헬퍼를 통해 분리 전송 (text → sleep → Enter) — paste 감지 회피
log "SEND to $PANEL0"
bash "$SEND_HELPER" "$PANEL0" "[panel1 완료] 파일 변경 확인 후 STATE.md 규칙대로 다음 지시를 내려줘."
