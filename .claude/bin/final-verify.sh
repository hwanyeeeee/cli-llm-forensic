#!/usr/bin/env bash
# 최종 real-run 검증. plan.md frontmatter의 run:(없으면 test:) 명령을 실행해
# 프로그램이 런타임 에러 없이 도는지 확인. "내가 직접 테스트해도 에러 없음" 게이트.
#
# 사용법: final-verify.sh
# exit : 0=통과, 1=실패(비정상 종료 또는 stderr 에러 흔적), 2=실행 명령 없음
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
PLAN="$ROOT/docs/plan.md"

CMD="$(awk -F': ' '/^run:/{sub(/^run: */,""); print; exit}' "$PLAN" 2>/dev/null)"
[ -n "$CMD" ] || CMD="$(awk -F': ' '/^test:/{sub(/^test: */,""); print; exit}' "$PLAN" 2>/dev/null)"
if [ -z "$CMD" ]; then
  echo "no run:/test: command in plan.md" >&2
  exit 2
fi

ERRF="$(mktemp)"
( cd "$ROOT" && eval "$CMD" ) >/dev/null 2>"$ERRF"
RC=$?
ERR="$(cat "$ERRF" 2>/dev/null)"; rm -f "$ERRF"

if [ "$RC" -ne 0 ]; then
  echo "real-run FAILED (rc=$RC): $ERR" >&2
  exit 1
fi
if printf '%s' "$ERR" | grep -qiE 'traceback|exception|error|panic|segfault|fatal'; then
  echo "real-run produced error output: $ERR" >&2
  exit 1
fi
echo "real-run OK"
exit 0
