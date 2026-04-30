#!/usr/bin/env bash
# 하네스 ↔ 파생 프로젝트 양방향 동기화.
# Usage:
#   dev-sync.sh pull              하네스 → 현 프로젝트 (managed 파일 일괄 덮어쓰기)
#   dev-sync.sh push <path>       현 프로젝트 → 하네스 (단일 managed 파일)
#   dev-sync.sh diff              차이만 보고 (read-only)
#
# 하네스 루트는 .dev-harness-root (1줄, 절대경로) 또는 sibling ../Dev-harness 로 추정.
# 파생 프로젝트에만 의미 있음 — 하네스 본체에서는 호출 시 자기 자신과 비교돼서 무의미.
set -euo pipefail

# managed 파일 단일 source of truth. managed-file-warn.sh 도 이 배열을 awk로 파싱하므로
# `PATHS=(` 라인과 `)` 라인 형식 유지할 것.
PATHS=(
  .claude/bin/send-to-pane.sh
  .claude/bin/verify-android.sh
  .claude/bin/verify-ios.sh
  .claude/bin/dev-sync.sh
  .claude/hooks/notify-main.sh
  .claude/hooks/managed-file-warn.sh
  .claude/commands/dev-spawn.md
  .claude/commands/dev-swap.md
  .claude/commands/dev-pull.md
  .claude/commands/dev-push.md
  .claude/commands/dev-diff.md
  .claude/panel0-rules.md
  .claude/panel1-rules.md
  .claude/settings.json
  .codex/hooks.json
  .codex/hooks/notify-main.sh
)

HARNESS=""
if [ -f .dev-harness-root ]; then
  HARNESS=$(cat .dev-harness-root)
fi
if [ -z "$HARNESS" ] && [ -d ../Dev-harness ]; then
  HARNESS=$(realpath ../Dev-harness)
fi
if [ -z "$HARNESS" ] || [ ! -d "$HARNESS" ]; then
  echo "하네스 루트 못 찾음. .dev-harness-root 에 절대경로 적어라." >&2
  exit 1
fi

is_managed() {
  local target="$1"
  for p in "${PATHS[@]}"; do
    [ "$p" = "$target" ] && return 0
  done
  return 1
}

cmd="${1:-}"
case "$cmd" in
  pull)
    n=0
    for p in "${PATHS[@]}"; do
      [ -f "$HARNESS/$p" ] || continue
      mkdir -p "$(dirname "$p")"
      if ! cmp -s "$HARNESS/$p" "$p" 2>/dev/null; then
        cp -p "$HARNESS/$p" "$p"
        echo "  pulled: $p"
        n=$((n+1))
      fi
    done
    [ "$n" -eq 0 ] && echo "in sync — 변경 없음" || echo "$n 파일 갱신됨"
    ;;
  push)
    target="${2:-}"
    [ -n "$target" ] || { echo "사용법: dev-sync.sh push <path>"; exit 1; }
    is_managed "$target" || { echo "managed 파일 아님: $target"; exit 1; }
    [ -f "$target" ] || { echo "파일 없음: $target"; exit 1; }
    mkdir -p "$HARNESS/$(dirname "$target")"
    cp -p "$target" "$HARNESS/$target"
    echo "pushed: $target → 하네스"
    ;;
  diff)
    n=0
    for p in "${PATHS[@]}"; do
      if [ -f "$HARNESS/$p" ] && [ -f "$p" ]; then
        cmp -s "$HARNESS/$p" "$p" || { echo "  drift: $p"; n=$((n+1)); }
      elif [ -f "$HARNESS/$p" ]; then
        echo "  missing: $p"; n=$((n+1))
      fi
    done
    [ "$n" -eq 0 ] && echo "in sync" || echo "$n 파일 drift"
    ;;
  *)
    echo "사용법: dev-sync.sh {pull|push <path>|diff}"
    exit 1
    ;;
esac
