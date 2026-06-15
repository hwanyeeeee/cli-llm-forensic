#!/usr/bin/env bash
# codex-review.sh 단위 테스트. 스텁 codex로 결정적 검증.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REVIEW="$REPO/.claude/bin/codex-review.sh"
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then echo "  ok: $1"; PASS=$((PASS+1)); else echo "  FAIL: $1 (expected rc=$2, got $3)"; FAIL=$((FAIL+1)); fi; }
checkgrep() { if grep -q "$2" "$3" 2>/dev/null; then echo "  ok: $1"; PASS=$((PASS+1)); else echo "  FAIL: $1"; FAIL=$((FAIL+1)); fi; }

setup() { # 새 fixture git repo 경로 출력
  d="$(mktemp -d)"
  git -C "$d" init -q
  git -C "$d" config user.email t@t; git -C "$d" config user.name t
  mkdir -p "$d/docs" "$d/.harness"
  printf '# plan\n- [ ] 1단계: wc 구현\n  acceptance: test -f wc.sh\n' > "$d/docs/plan.md"
  echo 'orig' > "$d/wc.sh"
  git -C "$d" add -A; git -C "$d" commit -qm init >/dev/null
  echo "$d"
}
mkstub() { # repo_dir, body → codex 스텁이 든 PATH 디렉터리 출력
  bindir="$1/stubbin"; mkdir -p "$bindir"
  printf '#!/usr/bin/env bash\n%s\n' "$2" > "$bindir/codex"
  chmod +x "$bindir/codex"; echo "$bindir"
}

# 1. diff 없음 → CLEAN, rc 0
d="$(setup)"
out="$(CLAUDE_PROJECT_DIR="$d" bash "$REVIEW" 1)"; rc=$?
check "no diff → rc 0" 0 "$rc"
printf '%s' "$out" | grep -q CLEAN && { echo "  ok: no-diff prints CLEAN"; PASS=$((PASS+1)); } || { echo "  FAIL: no-diff CLEAN"; FAIL=$((FAIL+1)); }
rm -rf "$d"

# 2. codex CLEAN → rc 0
d="$(setup)"; echo 'changed' >> "$d/wc.sh"
b="$(mkstub "$d" 'echo CLEAN')"
CLAUDE_PROJECT_DIR="$d" PATH="$b:$PATH" bash "$REVIEW" 1 >/dev/null; rc=$?
check "codex CLEAN → rc 0" 0 "$rc"
rm -rf "$d"

# 3. codex BLOCK → rc 1 + review-log 기록
d="$(setup)"; echo 'changed' >> "$d/wc.sh"
b="$(mkstub "$d" 'echo "BLOCK wc.sh:3 | off-by-one | use <="')"
CLAUDE_PROJECT_DIR="$d" PATH="$b:$PATH" bash "$REVIEW" 1 >/dev/null; rc=$?
check "codex BLOCK → rc 1" 1 "$rc"
checkgrep "BLOCK가 review-log에 append됨" "BLOCK" "$d/.harness/review-log.md"
rm -rf "$d"

# 4. codex NIT only → rc 0
d="$(setup)"; echo 'changed' >> "$d/wc.sh"
b="$(mkstub "$d" 'echo "NIT wc.sh:3 | unused var | remove"')"
CLAUDE_PROJECT_DIR="$d" PATH="$b:$PATH" bash "$REVIEW" 1 >/dev/null; rc=$?
check "codex NIT only → rc 0" 0 "$rc"
rm -rf "$d"

# 5. codex 부재 → rc 2 (폴백 신호)
d="$(setup)"; echo 'changed' >> "$d/wc.sh"
CLAUDE_PROJECT_DIR="$d" CODEX_CMD="definitely_no_such_codex_bin exec" bash "$REVIEW" 1 >/dev/null 2>&1; rc=$?
check "codex 부재 → rc 2" 2 "$rc"
rm -rf "$d"

# 6. codex 에러(비정상 종료) → rc 2
d="$(setup)"; echo 'changed' >> "$d/wc.sh"
b="$(mkstub "$d" 'echo boom >&2; exit 3')"
CLAUDE_PROJECT_DIR="$d" PATH="$b:$PATH" bash "$REVIEW" 1 >/dev/null 2>&1; rc=$?
check "codex 에러 → rc 2" 2 "$rc"
rm -rf "$d"

echo "---"; echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
