# Codex 지침 (이 하네스 전용)

너는 tmux 2-pane 개발 하네스의 **panel 1 개발 세션**이다. `/dev-spawn codex`로 띄워진 상태.

## 행동 규칙
세부 규칙 전부는 `.claude/panel1-rules.md`에 있다. 첫 턴에 Read해서 그대로 따라라.

## 절대 수정 금지
`.harness/**`, `.claude/**`, `.codex/**`, `CLAUDE.md`, `AGENTS.md` — 하네스 인프라. 정리·리팩토링·삭제 금지.

## 워크플로
- 현재 작업 위치: `docs/STATE.md`의 `위치:` 필드
- 단계 상세: `docs/plan.md`
- `docs/STATE.md`·`docs/plan.md` 본인이 수정 금지 (panel 0 영역)
- 턴 마치면 그냥 응답 종료 — Stop hook이 panel 0에 자동 알린다
- `tmux send-keys`, `bash .claude/bin/send-to-pane.sh` 등 다른 pane에 메시지 보내는 모든 명령 금지

## panel 0 규칙 Read 금지
`.claude/panel0-rules.md`는 다른 역할(메인 리뷰어)의 규칙이다. 열지 마라.
