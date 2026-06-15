---
description: 이 하네스를 /mnt/c/projects/<name>로 새 프로젝트로 복제 (런타임 상태 정리, 실행권한 복원)
argument-hint: <new-project-name>
allowed-tools: Bash, Edit
---

`$1` 이름으로 하네스를 `/mnt/c/projects/$1` 에 복제한다. 아래 단계를 **순서대로** 수행하고, 한 단계라도 실패하면 즉시 중단하고 사용자에게 원인을 보고해라.

## 1. 인자 검증

비어있거나 영숫자/점/밑줄/하이픈 외 문자가 있으면 중단.

```bash
NAME="${1:-}"
if [ -z "$NAME" ]; then
  echo "사용법: /dev-start <new-project-name>"; exit 1
fi
if ! [[ "$NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "이름에 영숫자/점/밑줄/하이픈만 허용: $NAME"; exit 1
fi
```

## 2. 타겟 경로 충돌 확인

```bash
TARGET="/mnt/c/projects/$NAME"
if [ -e "$TARGET" ]; then
  echo "이미 존재하는 경로라 덮어쓰지 않는다: $TARGET"; exit 1
fi
```

## 3. 복사

소스는 현재 하네스 루트. `cp -a`로 권한·시간 속성 보존.

WSL이 `/mnt/c` 경로에서 가끔 negative-cache 글리치를 일으켜 직접 `cp -a SRC TGT`가 실패하므로, **타겟 디렉터리를 먼저 만든 뒤 `SRC/.`로 내용물만 부어 넣는다.** WSL `mkdir`이 글리치로 실패하면 `cmd.exe mkdir`로 즉시 우회 (Windows side는 항상 성공).

```bash
SOURCE="${CLAUDE_PROJECT_DIR:-/mnt/c/projects/Dev-harness}"
mkdir -p "$TARGET" 2>/dev/null || cmd.exe /c "mkdir C:\\projects\\$NAME" >/dev/null
cp -a "$SOURCE/." "$TARGET/"
```

## 4. 런타임 잔재 + 부트스트랩 도구 제거

세션마다 고유한 파일과 캐노니컬 하네스에서만 의미 있는 부트스트랩 커맨드 삭제. `.gitkeep`은 보존.

```bash
rm -f "$TARGET/.harness/panel0.id" \
      "$TARGET/.harness/panel1.id" \
      "$TARGET/.harness/notify.log" \
      "$TARGET/.claude/commands/dev-start.md"
```

## 5. 실행 권한 복원

Windows 경유로 복사된 적이 있었을 경우 대비.

```bash
chmod +x "$TARGET/.claude/hooks/notify-main.sh" \
         "$TARGET/.claude/hooks/managed-file-warn.sh" \
         "$TARGET/.claude/bin/send-to-pane.sh" \
         "$TARGET/.claude/bin/verify-android.sh" \
         "$TARGET/.claude/bin/verify-ios.sh" \
         "$TARGET/.claude/bin/dev-sync.sh" \
         "$TARGET/.codex/hooks/notify-main.sh" 2>/dev/null || true
```

## 5-b. 하네스 링크 기록

새 프로젝트가 어느 하네스에서 왔는지를 적어둔다. `dev-sync.sh` 가 양방향 sync 시 이 파일을 읽어 하네스 루트를 찾는다.

```bash
echo "$SOURCE" > "$TARGET/.dev-harness-root"
```

## 6. 프로젝트명 치환

Edit 도구로 다음을 교체:

- `$TARGET/CLAUDE.md` 1번째 줄: `# Dev-harness` → `# $NAME`
- `$TARGET/README.md` 전체를 스텁 1줄로 덮어쓰기: `# $NAME\n`
  (원본 README는 하네스 안내라 새 프로젝트에선 무의미)

## 7. 템플릿 오염 확인 (경고만)

소스의 `docs/plan.md`나 `docs/STATE.md`가 실제 작업 내용으로 변질된 상태면 경고만 출력 (복사는 이미 끝났으므로 되돌리지 않음).

```bash
# plan.md 템플릿 ~1.1KB. 2KB 넘으면 오염 의심 (헤드룸 ~860B = 슬롯 채워지면 트립)
if [ "$(wc -c < "$TARGET/docs/plan.md")" -gt 2000 ]; then
  echo "⚠ plan.md가 템플릿보다 큼 — 소스 오염 가능성. 새 프로젝트에서 수동 초기화 필요할 수 있음."
fi
# STATE.md 템플릿 ~700B. 1200B 넘으면 오염 의심 (헤드룸 ~500B = 한 사이클 분량)
if [ "$(wc -c < "$TARGET/docs/STATE.md")" -gt 1200 ]; then
  echo "⚠ STATE.md가 템플릿보다 큼 — 소스 오염 가능성."
fi
```

## 8. 보고

한 문장:

> `/mnt/c/projects/$NAME 에 복제 완료. 해당 폴더에서 tmux 세션 열고 claude 실행 → /dev-spawn 로 시작.`

끝나면 **턴 마쳐라**. 추가 행동 없이 종료.
