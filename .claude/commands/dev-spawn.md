---
description: Open dev session in tmux panel 1 (claude or codex)
argument-hint: claude | codex
allowed-tools: Bash, Read, Write, Edit
---

`$1` 도구로 tmux panel 1을 열어 개발 세션을 기동한다. 아래 절차를 **순서대로** 정확히 수행해라. 한 단계라도 실패하면 즉시 중단하고 사용자에게 원인과 복구 방법을 보고해라.

## 1. 인자 검증

`$1`이 `claude` 또는 `codex`가 아니면 즉시 중단하고 다음을 출력:

> 사용법: `/dev-spawn claude` 또는 `/dev-spawn codex`

## 2. panel 1 중복 기동 방지

이미 panel 1이 살아있으면 기동하지 않는다.

```bash
if [ -f .harness/panel1.id ]; then
  PID=$(cat .harness/panel1.id)
  if tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$PID"; then
    echo "panel 1 already alive: $PID"; exit 1
  fi
fi
```

중단 시 사용자에게 안내:
> "panel 1이 이미 열려있다. 먼저 `tmux kill-pane -t $(cat .harness/panel1.id)` 로 종료한 뒤 다시 실행해라."

## 3. panel 0 (메인) pane ID 저장

Stop hook이 여기로 알림을 보낼 수 있도록 현재 pane 을 기록한다.

```bash
tmux display-message -p '#{pane_id}' > .harness/panel0.id
```

## 4. tmux 수평 분할 + panel 1 ID 저장

```bash
tmux split-window -h -P -F '#{pane_id}' > .harness/panel1.id
```

## 5. 도구 기동 명령 전송

`$1`에 따라 고정된 명령을 쓴다 (다른 플래그로 바꾸지 말 것).

- `claude` → `claude --dangerously-skip-permissions --model sonnet --effort max`
- `codex` → `codex --dangerously-bypass-approvals-and-sandbox --enable codex_hooks` (feature flag 보장용 — 로컬에서 꺼져있어도 하네스 루프를 유지)

```bash
PANEL1=$(cat .harness/panel1.id)
# Fresh spawn은 직전 프로젝트의 dispatch 버퍼가 tmux 서버에 남아있으면
# /dev-swap이 stale 내용을 인계할 수 있다. 깨끗하게 비우고 시작.
tmux delete-buffer -b panel1-last-dispatch 2>/dev/null || true
case "$1" in
  claude) CMD="claude --dangerously-skip-permissions --model sonnet --effort max" ;;
  codex)  CMD="codex --dangerously-bypass-approvals-and-sandbox --enable codex_hooks" ;;
esac
bash .claude/bin/send-to-pane.sh "$PANEL1" "$CMD"
```

## 6. 기동 대기 후 초기 지시 전송

도구가 프롬프트 대기 상태가 되는 데 2~4초 걸린다. **codex는 새 디렉터리에서 첫 기동 시 "Do you trust..." 신뢰 다이얼로그를 띄운다** — 기본값(1. Yes, continue) 수락을 위해 Enter 한 번을 추가로 보낸다. 다이얼로그가 안 뜨는 경우(이미 신뢰된 디렉터리)에도 빈 Enter는 무해하다.

```bash
sleep 4
if [ "$1" = "codex" ]; then
  tmux send-keys -t "$PANEL1" Enter
  sleep 2
fi
INIT_MSG='너는 panel 1이다. .claude/panel1-rules.md → docs/STATE.md → docs/plan.md 순으로 읽고 현재 단계를 구현해라.'
bash .claude/bin/send-to-pane.sh "$PANEL1" "$INIT_MSG"
```

## 7. STATE.md의 도구 라인 갱신

`docs/STATE.md`에서 `- 도구:` 로 시작하는 라인을 `- 도구: $1`로 변경 (파일이 초기 템플릿 상태면 해당 라인이 존재한다).

Edit 도구로 `- 도구: (claude|codex)` 또는 `- 도구: claude` / `- 도구: codex` 를 `- 도구: $1`로 교체.

## 8. 보고

사용자에게 한 문장으로만 보고:

> `panel 1 기동 완료 (도구: $1). 이제 대기 모드다. CLAUDE.md 섹션 8의 자율 진행 규칙을 따른다.`

그리고 **더 이상 행동하지 말고 턴을 마쳐라**. 이후의 진행은 panel 1의 Stop hook 알림이 들어올 때 깨어나서 처리한다.
