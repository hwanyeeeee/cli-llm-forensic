#!/usr/bin/env bash
# Ephemeral cross-family 리뷰어. panel0이 단계 게이트에서 호출.
# 단계 spec(plan.md 전문) + git diff + review-log을 codex exec read-only에 넘겨
# findings를 받는다. 부수효과: findings를 .harness/review-log.md에 append.
#
# 사용법: codex-review.sh <step#>
# stdout : findings — "CLEAN" 또는 한 줄씩 "<SEVERITY> <file>:<line> | <problem> | <fix>"
# exit   : 0=BLOCK 없음, 1=BLOCK 있음, 2=codex 사용불가/에러(폴백 신호)
# env    : CODEX_CMD (기본 "codex exec --sandbox read-only") — 테스트/플래그조정용 override
set -uo pipefail

STEP="${1:?usage: codex-review.sh <step#>}"
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
PLAN="$ROOT/docs/plan.md"
LOG="$ROOT/.harness/review-log.md"
CODEX_CMD="${CODEX_CMD:-codex exec --sandbox read-only}"

# 1. diff 캡처 (직전 게이트 이후 working tree). 변경 없으면 리뷰할 것 없음.
DIFF="$(git -C "$ROOT" diff 2>/dev/null)"
if [ -z "$DIFF" ]; then
  echo "CLEAN (no diff to review)"
  exit 0
fi

# 2. codex 존재 확인 → 없으면 폴백 신호(rc 2)
CODEX_BIN="${CODEX_CMD%% *}"
if ! command -v "$CODEX_BIN" >/dev/null 2>&1; then
  echo "codex unavailable: $CODEX_BIN not found" >&2
  exit 2
fi

# 3. 컨텍스트 합성
PLAN_TXT="$(cat "$PLAN" 2>/dev/null || echo '(plan.md 없음)')"
LOG_TXT="$(cat "$LOG" 2>/dev/null || echo '(이전 리뷰 없음)')"
PROMPT="너는 read-only 코드 리뷰어다. 절대 파일을 편집하지 마라. 리뷰만 한다.

방금 panel1(구현자)이 plan의 ${STEP}단계를 끝냈다. 아래 plan 전문에서 ${STEP}단계 spec을 찾아,
그 spec과 전체 plan 정합성 기준으로 diff를 검수해라. 실행경로·재현경로가 명확한 실제 버그를 우선 잡아라.

출력 규칙(엄격):
- 이슈 없으면 정확히 한 단어: CLEAN
- 이슈 있으면 한 줄에 하나씩, 다른 텍스트 없이:
  <SEVERITY> <file>:<line> | <problem> | <fix>
  SEVERITY = BLOCK 또는 NIT.
  BLOCK = correctness / 런타임 에러 / 도달가능 버그 (반드시 고쳐야 함).
  NIT   = 스타일 / 리팩토링 / 사소.

=== PLAN ===
${PLAN_TXT}

=== 이전 리뷰 로그 (cross-step 기억) ===
${LOG_TXT}

=== DIFF (${STEP}단계) ===
${DIFF}"

# 4. codex 호출 (read-only). $CODEX_CMD는 의도적으로 unquoted (단어 분할).
ERRF="$(mktemp)"
OUT="$($CODEX_CMD "$PROMPT" 2>"$ERRF")"; RC=$?
ERR="$(cat "$ERRF" 2>/dev/null)"; rm -f "$ERRF"
if [ "$RC" -ne 0 ]; then
  echo "codex error (rc=$RC): $ERR" >&2
  exit 2
fi

# 5. findings 출력
printf '%s\n' "$OUT"

# 6. review-log append (부수효과 — 항상 기록)
mkdir -p "$ROOT/.harness"
{
  printf '\n## %s단계 리뷰\n' "$STEP"
  printf '%s\n' "$OUT"
} >> "$LOG"

# 7. BLOCK 판정 → exit code
if printf '%s\n' "$OUT" | grep -q '^BLOCK '; then
  exit 1
fi
exit 0
