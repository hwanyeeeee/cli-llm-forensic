#!/usr/bin/env bash
# PostToolUse 훅: Edit/Write로 managed 파일을 수정하면 stderr로 한 줄 안내.
# 파생 프로젝트(.dev-harness-root 존재)에서만 작동. 하네스 본체에서는 무알림.
[ -f "${CLAUDE_PROJECT_DIR:-.}/.dev-harness-root" ] || exit 0

INPUT=$(cat 2>/dev/null || true)
TARGET=$(echo "$INPUT" | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
[ -n "$TARGET" ] || exit 0

# 절대경로를 프로젝트 상대로 변환
PR="${CLAUDE_PROJECT_DIR:-$PWD}"
REL="${TARGET#$PR/}"
REL="${REL#./}"

# dev-sync.sh의 PATHS를 단일 source로 추출 (배열 라인만)
SYNC="$PR/.claude/bin/dev-sync.sh"
[ -f "$SYNC" ] || exit 0
PATHS=$(awk '/^PATHS=\(/{flag=1; next} /^\)/{flag=0} flag {gsub(/^[[:space:]]+|[[:space:]]+$/,""); print}' "$SYNC")

if echo "$PATHS" | grep -qx "$REL"; then
  echo "[하네스 동기화] managed 파일 수정 — 다른 프로젝트에 전파하려면: /dev-push $REL" >&2
fi
exit 0
