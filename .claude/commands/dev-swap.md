---
description: panel 1 개발 도구 교체 (kill+재기동, 직전 dispatch를 tmux 버퍼로 인계)
argument-hint: claude | codex
allowed-tools: Bash, Read, Write, Edit
---

`$1` 도구로 panel 1을 **교체** 기동한다. `/dev-spawn`과 차이: 기존 pane을 강제 종료하고 새 도구로 다시 띄우며, panel 0의 직전 dispatch를 tmux named buffer(`panel1-last-dispatch`)에서 꺼내 새 세션에 그대로 인계한다 (단순 INIT_MSG가 아니라 진행 중이던 cycle 지시 그대로). 절차를 **순서대로** 정확히 수행해라. 한 단계라도 실패하면 즉시 중단하고 사용자에게 원인·복구 방법을 보고해라.

**상태 저장소**: `panel1-last-dispatch` tmux named buffer. tmux 서버 메모리에만 존재, 파일 시스템에 흔적 없음. send-to-pane.sh가 panel 1로 보낼 때마다 자동으로 동일 이름 버퍼에 덮어쓰므로 명시적 cleanup 불필요.

## 1. 인자 검증

`$1`이 `claude` 또는 `codex`가 아니면 즉시 중단:

> 사용법: `/dev-swap claude` 또는 `/dev-swap codex`

## 2. panel 1 존재 확인

`.harness/panel1.id`가 없으면 교체할 대상이 없다 — 중단:

> "panel 1이 아직 기동되지 않았다. `/dev-spawn $1` 먼저 실행해라."

```bash
[ -f .harness/panel1.id ] || { echo "no panel1.id"; exit 1; }
```

## 3. 기존 pane 종료 (idempotent)

pane이 살아있으면 `tmux kill-pane`이 SIGHUP을 pane 안 모든 프로세스(codex/claude/bash 무관)에 전달해 정리한다. 이미 죽었으면 no-op. **버퍼는 pane과 무관하게 tmux 서버에 남아있으므로 kill해도 last-dispatch가 안 날아간다.**

```bash
OLD_PID="$(bash .claude/bin/resolve-pane.sh panel1 2>/dev/null || cat .harness/panel1.id)"
if tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -qx "$OLD_PID"; then
  tmux kill-pane -t "$OLD_PID"
fi
```

## 4. panel 0 ID 저장 + 새 pane 분할

```bash
tmux display-message -p '#{pane_id}' > .harness/panel0.id
tmux set-option -p -t "$(cat .harness/panel0.id)" @fa_role panel0
tmux split-window -h -P -F '#{pane_id}' > .harness/panel1.id
tmux set-option -p -t "$(cat .harness/panel1.id)" @fa_role panel1
```

## 5. 도구 기동 명령 전송 (로깅 스킵)

`SKIP_DISPATCH_LOG=1`로 내부 sends가 last-dispatch 버퍼를 덮어쓰지 못하게 한다.

```bash
PANEL1=$(cat .harness/panel1.id)
case "$1" in
  claude) CMD="claude --dangerously-skip-permissions --model sonnet --effort max" ;;
  codex)  CMD="codex --dangerously-bypass-approvals-and-sandbox --enable codex_hooks" ;;
esac
SKIP_DISPATCH_LOG=1 bash .claude/bin/send-to-pane.sh "$PANEL1" "$CMD"
```

## 6. 기동 대기 + 신뢰 다이얼로그 처리

```bash
sleep 4
if [ "$1" = "codex" ]; then
  tmux send-keys -t "$PANEL1" Enter
  sleep 2
fi
```

## 7. 역할 인계 메시지 전송

`panel1-last-dispatch` 버퍼가 존재하면 헤더와 합성해 한 번에 paste, 없으면 fallback INIT_MSG. 헤더에 두 가지를 명시해야 한다:
1. 직전 dispatch가 이 메시지의 `---` 아래 첨부돼있다
2. 직전 도구가 작업 중간(파일 일부 생성/테스트 일부 통과)에서 끊겼을 수 있으니, **먼저 git status·기존 파일·테스트 결과로 현재 진척 상태를 확인하고 미완료 부분만 채워라**

합성은 tmux 버퍼 위에서 처리: `show-buffer`로 직전 dispatch 꺼내 헤더와 stdin merge → `load-buffer`로 임시 버퍼(`panel1-swap-msg`)에 적재 → `paste-buffer -p -d`로 진짜 bracketed paste 후 단일 Enter 제출. `-d`가 임시 버퍼 자동 삭제.

```bash
PANEL1=$(cat .harness/panel1.id)
HEADER='[panel 1 교체 알림] 너는 panel 1로 새로 교체된 세션이다. 직전 panel 1 도구는 사용자에 의해 종료됐고 너로 대체됐다.

먼저 `.claude/panel1-rules.md`를 읽어 panel 1 역할 규칙을 파악해라.

이 메시지의 아래 `---` 구분선 다음에는, panel 0이 직전 도구한테 보냈던 **마지막 dispatch 전문**이 그대로 첨부돼있다. 단, 직전 도구가 그 지시 일부를 이미 처리했을 수 있다 (예: 파일 N개 작성 후 토큰 만료/수동 종료). 처음부터 다 다시 만들지 말고:

1. `git status`로 unstaged 변경사항 확인
2. dispatch가 요구하는 파일·테스트가 이미 존재하는지 read로 점검
3. 존재하면 내용이 dispatch 사양과 부합하는지 확인 (부합하면 스킵, 부족하면 보강)
4. 누락된 부분만 새로 작성
5. 마지막에 dispatch의 acceptance 명령(또는 동등한 검증)을 한 번 돌려 GREEN 확인 후 `[panel1 완료]` 보고

---

'

if tmux show-buffer -b panel1-last-dispatch 2>/dev/null >/tmp/panel1-last-dispatch.$$; then
  # $()는 trailing newline을 strip한다. 그래서 캡처 → printf '%s%s\n'로
  # 정확히 한 개 \n을 다시 붙여 paste-buffer 후 cursor가 빈 라인에 놓이게
  # 한다 (이후 plain Enter 한 번이 깨끗한 submit으로 동작).
  DISPATCH=$(cat /tmp/panel1-last-dispatch.$$)
  rm -f /tmp/panel1-last-dispatch.$$
  printf '%s%s\n' "$HEADER" "$DISPATCH" | tmux load-buffer -b panel1-swap-msg -
  tmux paste-buffer -t "$PANEL1" -b panel1-swap-msg -p -d
  sleep 1
  tmux send-keys -t "$PANEL1" Enter
else
  FALLBACK='너는 panel 1이다. .claude/panel1-rules.md → docs/STATE.md → docs/plan.md 순으로 읽고 현재 단계를 구현해라. (직전 dispatch 버퍼 없음 — STATE.md "수행 중" 라인을 기준으로 현재 cycle을 추론해라.)'
  SKIP_DISPATCH_LOG=1 bash .claude/bin/send-to-pane.sh "$PANEL1" "$FALLBACK"
fi
```

## 8. STATE.md의 도구 라인 갱신

Edit 도구로 `- 도구: (claude|codex)` 라인을 `- 도구: $1`로 교체.

## 9. 보고

한 문장으로만:

> `panel 1 교체 완료 (도구: $1, 직전 dispatch 인계됨). 대기 모드.`

이후 행동하지 말고 턴을 마쳐라. Stop hook 알림 들어올 때 깨어나서 처리한다.
