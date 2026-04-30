# Dev-harness

새 프로젝트(앱/웹) 개발마다 복사해서 쓰는 **tmux 2-panel 개발 하네스**.

- **panel 0 (메인 세션)** — 플랜 작성, 코드 리뷰, 직접 수정, panel 1 지시
- **panel 1 (개발 세션)** — `claude` 또는 `codex`로 실제 코드 생성

메인이 panel 1을 tmux로 제어하고, panel 1의 Stop hook이 자동으로 메인에 "작업 완료" 알림을 보내 루프가 돈다. 사용자는 플랜만 잘 세우면 자리 비워도 OK.

## 사용법

1. 이 폴더를 새 프로젝트 디렉터리로 복사
   ```bash
   cp -r /mnt/c/projects/Dev-harness ~/proj/MyApp
   cd ~/proj/MyApp
   ```
2. tmux 세션 시작 후 해당 폴더에서 `claude` 실행 (이게 panel 0)
3. 기능 요청 → 메인이 `docs/plan.md`와 `docs/STATE.md`를 작성
4. 플랜 검토 후 panel 0에서 아래 중 하나 입력
   ```
   /dev-spawn claude
   /dev-spawn codex
   ```
5. 이후 자리 비워도 됨. 돌아와서 `docs/STATE.md`만 열어보면 현황이 보임
   - `## 완료` — 플랜 끝까지 도달
   - `## ⚠ 막힘` — 같은 단계 3회 실패, 사용자 개입 필요
   - `## ❓ 결정 필요` — 플랜에 없는 설계 결정 대기 중

## 구조

```
CLAUDE.md                # claude(panel 0/1) 자동 로드 — 역할 분기 부트스트랩
AGENTS.md                # codex(panel 1) 자동 로드 — 정체성·인프라 가드
.claude/
  settings.json          # Stop hook 등록 + tmux/adb/xcrun 권한
  commands/dev-spawn.md  # /dev-spawn claude|codex
  hooks/notify-main.sh   # panel 1 Stop hook → panel 0 알림
  bin/send-to-pane.sh    # tmux paste-mode 우회 헬퍼
  bin/verify-android.sh  # APK 설치·기동·logcat 크래시 검사 (모바일 acceptance용)
  bin/verify-ios.sh      # 시뮬레이터 설치·기동·log 크래시 검사
.codex/
  hooks.json             # codex Stop hook 등록 (claude와 동일 역할)
  hooks/notify-main.sh   # stdin JSON의 cwd를 꺼내 .claude/hooks/notify-main.sh 재사용
docs/
  plan.md                # 상세 플랜 (메인이 작성)
  STATE.md               # 현재 상황 한 화면 요약 (메인이 갱신)
.harness/                # 런타임 상태 (gitignore)
  panel0.id, panel1.id   # tmux pane ID
```

## 도구 중간 전환

토큰 소진 등으로 도구를 바꾸고 싶으면 panel 1 종료 후 `/dev-spawn` 다른 플래그로 재실행. 새 도구가 STATE.md + plan.md를 읽고 이어서 작업한다.

## 검증 — plan.md `acceptance:`

각 단계의 plan.md 본문에 `acceptance:` 라인을 박으면 panel 0이 그 명령을 실행해 exit code로 단계 진행/유지 판정. 비어있으면 본문 + git diff 휴리스틱.

- **CLI / Node**: `acceptance: node --test` 같은 한 줄.
- **웹 / Electron / Tauri**: `.mcp.json`의 **Playwright MCP** (panel 0이 호출). 첫 사용 전 `npx playwright install chromium`.
- **Android**: `acceptance: ./gradlew assembleDebug && bash .claude/bin/verify-android.sh app/build/outputs/apk/debug/app-debug.apk` — 헬퍼가 APK 설치·기동·logcat 크래시 검사·스크린샷 (`.harness/artifacts/`).
- **iOS**: `acceptance: bash .claude/bin/verify-ios.sh build/MyApp.app` — 헬퍼가 시뮬레이터 부팅·설치·기동·log 검사.
- **데스크톱 네이티브**: `screencapture`(macOS), PowerShell(Windows) 등 OS별 명령 직접.

에뮬레이터/디바이스는 사이클 시작 전 사용자가 켜둬야 함 (`emulator -avd <name> &` 또는 `xcrun simctl boot`). 헬퍼들은 *훅 아님 · 자동 아님* — `acceptance:` 라인에 명시할 때만 실행.

frontmatter (optional):
```yaml
---
target: android
build: ./gradlew assembleDebug
test: ./gradlew testDebugUnit
device: emulator-5554
---
```
panel 0이 `target`·`build`·`device`를 검증 분기·로그 컨텍스트로 활용.
