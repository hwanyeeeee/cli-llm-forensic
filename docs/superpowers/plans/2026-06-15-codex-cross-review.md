# Codex cross-family 리뷰어 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2-pane 하네스에 ephemeral Codex cross-family 리뷰어를 붙여, panel0이 단계 게이트마다 `codex exec --sandbox read-only`로 diff를 리뷰하고 BLOCK은 차단·NIT는 로깅하며 최종 real-run으로 런타임 에러를 잡는다.

**Architecture:** 새 pane 없이 panel0(Claude)이 Bash로 headless codex를 호출. 두 개의 신규 스크립트(`codex-review.sh`, `final-verify.sh`)가 결정적 로직을 담고, panel0-rules `§6`이 이들을 오케스트레이트. cross-step 기억은 `.harness/review-log.md` 파일(codex-review.sh가 append). codex 부재 시 기존 `code-reviewer` 서브에이전트로 폴백.

**Tech Stack:** Bash, git, awk/grep, codex CLI, tmux 하네스, markdown rules 파일.

**Spec:** `docs/superpowers/specs/2026-06-15-codex-cross-review-design.md`

**Branch:** `feat/codex-reviewer` (이미 생성됨)

---

## File Structure

| 파일 | 책임 |
|---|---|
| `.claude/bin/codex-review.sh` (NEW) | 단계# 받아 git diff + plan + review-log을 codex read-only에 넘겨 findings 반환. review-log에 append. exit 0/1/2 = BLOCK없음/있음/codex불가 |
| `.claude/bin/final-verify.sh` (NEW) | plan.md `run:`(없으면 `test:`) 실행, exit+stderr로 런타임 에러 판정. exit 0/1/2 = 통과/실패/명령없음 |
| `tests/codex-review.test.sh` (NEW) | 스텁 codex로 codex-review.sh 결정적 단위 테스트 |
| `tests/final-verify.test.sh` (NEW) | 스텁 명령으로 final-verify.sh 단위 테스트 |
| `.claude/panel0-rules.md` (MODIFY) | `§4-3`에 `run:` 키 추가, `§6` 전면 재작성(싼게이트→codex리뷰→cap→최종검증) |
| `.claude/panel1-rules.md` (MODIFY) | 수정 지시가 codex findings에서 올 수 있다는 한 줄 |
| `.harness/review-log.md` (RUNTIME) | codex-review.sh가 생성/append (gitignored, 코드로 만들지 않음) |

각 신규 스크립트는 단일 책임, bash 파싱 가능한 stdout, 명확한 exit code 계약. 테스트는 외부 codex/명령을 스텁으로 대체해 결정적.

---

## Task 1: codex-review.sh 단위 테스트 (실패 확인)

**Files:**
- Create: `tests/codex-review.test.sh`

스텁 codex를 PATH에 올려 codex-review.sh의 6개 동작(무diff·CLEAN·BLOCK·NIT·codex부재·codex에러)을 결정적으로 검증한다. 스크립트가 아직 없으니 먼저 실패해야 한다.

- [ ] **Step 1: 테스트 파일 작성**

```bash
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `bash tests/codex-review.test.sh`
Expected: FAIL — 모든 체크가 깨짐 (`codex-review.sh` 없음 → 매 호출 rc=127). 마지막 `PASS=0 FAIL=8`, 스크립트 exit ≠ 0.

- [ ] **Step 3: 커밋**

```bash
git add tests/codex-review.test.sh
git commit -m "test: codex-review.sh 단위 테스트 (스텁 codex)"
```

---

## Task 2: codex-review.sh 구현 (테스트 통과)

**Files:**
- Create: `.claude/bin/codex-review.sh`
- Test: `tests/codex-review.test.sh` (Task 1)

- [ ] **Step 1: 스크립트 작성**

```bash
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
```

- [ ] **Step 2: 실행권한 부여**

Run: `chmod +x .claude/bin/codex-review.sh`
Expected: 무출력, exit 0.

- [ ] **Step 3: 테스트 실행 → 통과 확인**

Run: `bash tests/codex-review.test.sh`
Expected: PASS — 마지막 줄 `PASS=8 FAIL=0`, 스크립트 exit 0. (6 케이스 + BLOCK-log + no-diff-CLEAN 보조 체크 = 8 PASS)

- [ ] **Step 4: 커밋**

```bash
git add .claude/bin/codex-review.sh
git commit -m "feat: codex-review.sh — ephemeral cross-family 리뷰어"
```

---

## Task 3: final-verify.sh 테스트 + 구현

**Files:**
- Create: `tests/final-verify.test.sh`
- Create: `.claude/bin/final-verify.sh`

- [ ] **Step 1: 테스트 파일 작성**

```bash
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `bash tests/final-verify.test.sh`
Expected: FAIL — `final-verify.sh` 없음, `PASS=0 FAIL=5`.

- [ ] **Step 3: 스크립트 작성**

```bash
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
```

- [ ] **Step 4: 실행권한 + 테스트 통과**

Run: `chmod +x .claude/bin/final-verify.sh && bash tests/final-verify.test.sh`
Expected: PASS — `PASS=5 FAIL=0`, exit 0.

- [ ] **Step 5: 커밋**

```bash
git add tests/final-verify.test.sh .claude/bin/final-verify.sh
git commit -m "feat: final-verify.sh — 최종 real-run 검증 게이트"
```

---

## Task 4: panel0-rules.md — `run:` 키 + `§6` 재작성

**Files:**
- Modify: `.claude/panel0-rules.md` (`§4-3` frontmatter 목록, `§6` 리뷰 섹션 전체)

마크다운 규칙이라 단위 테스트 불가 — 대신 스크립트 경로 존재 확인 + 셀프 doc-review.

- [ ] **Step 1: `§4-3`에 `run:` 키 추가**

`§4-3 plan.md frontmatter`의 키 목록(`target`/`build`/`test`/`device`)에 한 줄 추가:

```markdown
- `run`: 최종 real-run 검증 명령 (end-to-end 실제 실행). 없으면 `test`로 폴백.
```

- [ ] **Step 2: `§6` 전체를 아래로 교체**

기존 `## 6. 리뷰 (...)` 섹션 전체를 다음으로 대체:

```markdown
## 6. 리뷰 (`[panel1 완료]` 수신 시)

### 6-1. 싼 게이트 (acceptance)

plan.md 현재 단계의 `acceptance:` 라인을 Bash로 실행:

- exit 0 → § 6-2 cross-family 리뷰로 진행
- exit ≠ 0 → 단계 유지 + 실패 로그 첨부해 panel 1에 수정 지시 (§ 4-2 진도 없음)
- `acceptance:`가 비어있으면: 단계 본문 + `git diff`로 spec 적합성·scope creep 점검 후 § 6-2로

### 6-2. cross-family 리뷰 (Codex, read-only)

acceptance 통과 후 codex 리뷰를 돌린다. 현재 단계#는 STATE.md `위치`에서 뽑는다:

\`\`\`bash
STEP=$(awk -F'위치: *' '/위치:/{print $2; exit}' docs/STATE.md | grep -oE '[0-9]+' | head -1)
OUT=$(bash .claude/bin/codex-review.sh "$STEP"); RC=$?
\`\`\`

- `RC=2` (codex 사용불가/에러) → 폴백: `superpowers:code-reviewer` 서브에이전트로 리뷰. 루프 유지.
- `RC=1` (BLOCK 있음) → `OUT`에서 `^BLOCK` 라인만 추려 panel 1에 수정 지시 (**NIT 라인은 보내지 마라**). 단계 유지. Claude가 편집 → 다음 깨어남에 재리뷰. findings는 codex-review.sh가 review-log에 이미 append함.
- `RC=0` (BLOCK 없음) → NIT는 review-log에 이미 기록됨, 차단 안 함. 단계 진행 (§ 4-2 "진도 있음·단계 진행").

UI/모바일 단계 (frontmatter `target: ios|android|web`): codex 리뷰와 **별개로** 기존 도구 검증 병행 — web=`.mcp.json` Playwright MCP, android=`verify-android.sh`, ios=`verify-ios.sh`.

### 6-3. iteration cap

같은 단계에서 BLOCK→수정→재리뷰가 3 라운드 연속 진도 없음(§ 4-2 진도 판정) → `## ⚠ 막힘` idle.

### 6-4. 최종 real-run 검증 (모든 단계 `[x]` 도달 시)

`## 완료` 선언 전에 프로그램을 실제 실행한다:

\`\`\`bash
bash .claude/bin/final-verify.sh; RC=$?
\`\`\`

- `RC=0` → `## 완료` 추가 (idle).
- `RC=1` (런타임 에러) → codex로 실패 출력 리뷰 후 panel 1에 수정 지시, 해당 단계 재개 (완료 보류).
- `RC=2` (`run:`/`test:` 없음) → `## ❓ 결정 필요`로 사용자에게 실행 명령 요청.

스타일·리팩토링은 codex가 NIT로 분류해 review-log에만 남긴다. 자율 루프 속도보다 정합성 우선.
```

(주: 위 코드펜스의 `\`\`\``는 실제 파일에선 백틱 3개. STATE.md `위치` 라인 형식은 `- 위치: 2단계` 이므로 awk가 `2단계`를 뽑고 grep이 `2`만 남긴다.)

- [ ] **Step 3: 스크립트 경로 참조 검증**

Run: `for f in codex-review.sh final-verify.sh; do test -x ".claude/bin/$f" && echo "ok $f" || echo "MISSING $f"; done`
Expected: `ok codex-review.sh` / `ok final-verify.sh` (둘 다 존재 + 실행가능).

- [ ] **Step 4: doc 셀프리뷰**

확인: `§6`이 codex-review.sh의 exit 계약(0/1/2)과 정확히 일치하는가? final-verify.sh exit 계약(0/1/2)과 일치하는가? `## 완료`/`## ⚠ 막힘`/`## ❓ 결정 필요` idle 플래그가 `§4-2`·notify-main.sh 필터와 같은 문자열인가? (notify-main.sh는 `^## (완료|⚠ 막힘|❓ 결정 필요)` grep.) 불일치 있으면 인라인 수정.

- [ ] **Step 5: 커밋**

```bash
git add .claude/panel0-rules.md
git commit -m "feat: panel0-rules §6 — codex 리뷰 게이트 + 최종 real-run 검증"
```

---

## Task 5: panel1-rules.md — 리뷰 수정지시 안내 한 줄

**Files:**
- Modify: `.claude/panel1-rules.md` (`## 애매한 경우` 섹션)

- [ ] **Step 1: 한 줄 추가**

`## 애매한 경우` 섹션 끝에 추가:

```markdown
- panel 0의 수정 지시가 codex 리뷰의 `BLOCK` findings에서 올 수 있다. 형식은 `<file>:<line> | <problem> | <fix>`. 받은 항목을 고치면 된다 — 평소 구현과 동작 동일. 리뷰어(codex)와 너는 직접 통신하지 않는다.
```

- [ ] **Step 2: 커밋**

```bash
git add .claude/panel1-rules.md
git commit -m "docs: panel1-rules — codex BLOCK 수정지시 수신 안내"
```

---

## Task 6: end-to-end 검증 (실제 codex)

**Files:**
- 임시 검증 프로젝트 (커밋 안 함)

[[project_redesign_validated]] 패턴 — 실제 codex로 전체 루프를 돌려 계약을 실측한다. 6a는 스크립트로, 6b는 하네스 tmux 루프로.

- [ ] **Step 1 (6a): 실제 codex 플래그·출력 스모크 테스트**

임시 git repo를 만들고 `wc.sh`에 **도달가능 BLOCK 버그**(예: 인자 없을 때 `$1` 무가드 참조)를 심은 뒤 실제 codex로 호출:

```bash
D="$(mktemp -d)"; git -C "$D" init -q
git -C "$D" config user.email t@t; git -C "$D" config user.name t
mkdir -p "$D/docs" "$D/.harness"
printf '# plan\n- [ ] 1단계: wc.sh — 파일 줄 수 출력\n  acceptance: bash wc.sh wc.sh\n' > "$D/docs/plan.md"
printf '#!/usr/bin/env bash\nwc -l "$1"\n' > "$D/wc.sh"   # $1 무가드 = 인자 없으면 깨짐
git -C "$D" add -A; git -C "$D" commit -qm init >/dev/null
printf '#!/usr/bin/env bash\nwc -l < "$1"\necho done\n' > "$D/wc.sh"  # diff 생성
CLAUDE_PROJECT_DIR="$D" bash .claude/bin/codex-review.sh 1; echo "rc=$?"
```

Expected: codex가 `--sandbox read-only`를 거부하지 않고 실행됨. 출력이 `CLEAN` 또는 `BLOCK ...`/`NIT ...` 고정포맷. `$D/.harness/review-log.md` 생성됨. rc ∈ {0,1}.
- 만약 codex가 `--sandbox read-only` 플래그를 거부하면 → `codex --help`로 정확한 read-only 모드 플래그 확인 후 `codex-review.sh`의 `CODEX_CMD` 기본값을 수정하고 Task 2 테스트 재실행.
- 만약 codex 출력이 고정포맷을 안 지키면 → 프롬프트의 "출력 규칙(엄격)" 문구를 강화하고 재시도.
정리: `rm -rf "$D"`.

- [ ] **Step 2 (6b): 폴백 경로 확인**

codex를 일시적으로 가린 채 codex-review.sh가 rc 2를 내는지:

```bash
D="$(mktemp -d)"; git -C "$D" init -q
git -C "$D" config user.email t@t; git -C "$D" config user.name t
mkdir -p "$D/docs"; printf '# plan\n- [ ] 1단계\n' > "$D/docs/plan.md"
echo a > "$D/f"; git -C "$D" add -A; git -C "$D" commit -qm i >/dev/null; echo b >> "$D/f"
CLAUDE_PROJECT_DIR="$D" CODEX_CMD="no_such_codex exec" bash .claude/bin/codex-review.sh 1 >/dev/null 2>&1; echo "rc=$? (expect 2)"
rm -rf "$D"
```

Expected: `rc=2 (expect 2)`. panel0이 이걸 받으면 서브에이전트 폴백 (§6-2). 루프 hard-stop 안 함.

- [ ] **Step 3 (6b): 전체 하네스 루프 (수동, 선택)**

`/dev-start codex-review-test`로 임시 프로젝트 생성 → panel0에서 wc CLI 5단계 plan 작성(2단계에 도달가능 버그 심기) → `/dev-spawn claude` → 자율 루프 관찰:
1. acceptance 통과 후 codex 리뷰 발화 확인.
2. 심은 BLOCK이 잡힘 → review-log 기록 → panel1에 BLOCK만 전달 → 수정 → 재리뷰 CLEAN.
3. NIT는 review-log에만, 단계 진행 차단 안 함.
4. 모든 단계 후 final-verify가 실제 실행됨, 런타임 에러 시 완료 보류.
5. review-log가 완료 후에도 보존됨.

관찰 결과를 이 플랜 파일 하단에 메모로 기록.

- [ ] **Step 4: 검증 메모 커밋**

```bash
git add docs/superpowers/plans/2026-06-15-codex-cross-review.md
git commit -m "docs: codex 리뷰어 e2e 검증 결과 메모"
```

---

## 머지 (사용자 게이트)

검증 통과 후 사용자 승인 받아:

```bash
git checkout main && git merge --no-ff feat/codex-reviewer
git tag pre-codex-reviewer 16b504a   # 선택: 초기 커밋을 롤백 포인트로
```

파생 프로젝트(Nursing-app, WinForensic 등)는 다음 세션 시작 시 drift 알림을 받고 각자 `/dev-pull`로 갱신. 강제 전파 아님.
