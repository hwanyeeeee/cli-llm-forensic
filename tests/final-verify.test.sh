#!/usr/bin/env bash
# final-verify.sh 단위 테스트.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERIFY="$REPO/.claude/bin/final-verify.sh"
PASS=0; FAIL=0
check() { if [ "$2" = "$3" ]; then echo "  ok: $1"; PASS=$((PASS+1)); else echo "  FAIL: $1 (expected $2, got $3)"; FAIL=$((FAIL+1)); fi; }
setup() { d="$(mktemp -d)"; mkdir -p "$d/docs"; echo "$d"; }

# 1. run: 성공(exit 0, stderr 없음) → rc 0
d="$(setup)"
printf -- '---\nrun: bash ok.sh\n---\n' > "$d/docs/plan.md"
printf '#!/usr/bin/env bash\necho hi\n' > "$d/ok.sh"; chmod +x "$d/ok.sh"
CLAUDE_PROJECT_DIR="$d" bash "$VERIFY" >/dev/null 2>&1; rc=$?
check "run: 성공 → rc 0" 0 "$rc"; rm -rf "$d"

# 2. run: 비정상 종료(exit 1) → rc 1
d="$(setup)"
printf -- '---\nrun: bash bad.sh\n---\n' > "$d/docs/plan.md"
printf '#!/usr/bin/env bash\nexit 1\n' > "$d/bad.sh"; chmod +x "$d/bad.sh"
CLAUDE_PROJECT_DIR="$d" bash "$VERIFY" >/dev/null 2>&1; rc=$?
check "run: 비정상종료 → rc 1" 1 "$rc"; rm -rf "$d"

# 3. run: exit 0이지만 stderr에 Traceback → rc 1
d="$(setup)"
printf -- '---\nrun: bash err.sh\n---\n' > "$d/docs/plan.md"
printf '#!/usr/bin/env bash\necho "Traceback (most recent call last)" >&2\nexit 0\n' > "$d/err.sh"; chmod +x "$d/err.sh"
CLAUDE_PROJECT_DIR="$d" bash "$VERIFY" >/dev/null 2>&1; rc=$?
check "run: stderr 에러 → rc 1" 1 "$rc"; rm -rf "$d"

# 4. run:/test: 둘 다 없음 → rc 2
d="$(setup)"
printf -- '---\nbuild: make\n---\n' > "$d/docs/plan.md"
CLAUDE_PROJECT_DIR="$d" bash "$VERIFY" >/dev/null 2>&1; rc=$?
check "run/test 없음 → rc 2" 2 "$rc"; rm -rf "$d"

# 5. run: 없고 test: 만 있음 → test: 사용, rc 0
d="$(setup)"
printf -- '---\ntest: bash ok.sh\n---\n' > "$d/docs/plan.md"
printf '#!/usr/bin/env bash\necho ok\n' > "$d/ok.sh"; chmod +x "$d/ok.sh"
CLAUDE_PROJECT_DIR="$d" bash "$VERIFY" >/dev/null 2>&1; rc=$?
check "test: 폴백 → rc 0" 0 "$rc"; rm -rf "$d"

echo "---"; echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
