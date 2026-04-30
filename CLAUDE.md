# Dev-harness

tmux 2-pane 개발 하네스. **역할별 규칙은 이 파일에 없다** — 각 pane이 자기 역할 파일을 직접 Read한다.

## 세션 시작 첫 행동 (필수)

네가 사용자에게 응답을 시작하기 **전에** 아래를 반드시 수행한다.

1. Bash로 자기 역할 판별:
   ```bash
   PR="${CLAUDE_PROJECT_DIR:-.}"
   MP="${TMUX_PANE:-}"
   P0=$(cat "$PR/.harness/panel0.id" 2>/dev/null || true)
   P1=$(cat "$PR/.harness/panel1.id" 2>/dev/null || true)
   if   [ -n "$P1" ] && [ "$MP" = "$P1" ]; then echo panel1
   elif [ -n "$P0" ] && [ "$MP" = "$P0" ]; then echo panel0
   else echo panel0
   fi
   ```
2. 출력이 `panel0`이면 `.claude/panel0-rules.md`를 Read → 그 내용이 너의 규칙이다.
3. 출력이 `panel1`이면 `.claude/panel1-rules.md`를 Read → 그 내용이 너의 규칙이다.
4. **다른 쪽 rules 파일은 절대 Read하지 마라.** 역할 혼동의 원인.
5. 이후 모든 응답은 해당 파일이 유일한 규칙 기준이다.
6. (panel0 한정, 파생 프로젝트만) `.dev-harness-root` 가 있으면 다음을 한 번 실행:
   ```bash
   bash .claude/bin/dev-sync.sh diff > .harness/sync-status 2>&1 || true
   ```
   결과 파일에 `drift` 가 보이면 첫 응답 끝에 한 줄로 사용자에게 알려라 (panel0-rules § 7 참조).

## 공유 상태

- `docs/plan.md` — 전체 플랜 (panel 0 작성/수정, panel 1 읽기만)
- `docs/STATE.md` — 상황판 (panel 0만 수정)
- `.harness/panel0.id`, `.harness/panel1.id` — tmux pane ID (`/dev-spawn`가 관리)
