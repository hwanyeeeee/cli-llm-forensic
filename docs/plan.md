---
target:
build:
test:
device:
---

# 플랜

(메인 세션이 Claude Code **plan mode**에서 승인된 계획을 여기에 작성한다.
panel 1 개발 세션은 이 파일과 `STATE.md`를 읽고 현재 단계를 수행한다.)

## 1단계: <제목>
<상세 설명>

acceptance:

## 2단계: <제목>
<상세 설명>

acceptance:

## 3단계: <제목>
<상세 설명>

acceptance:

<!--
스키마 요약:

frontmatter (모두 optional):
- target: ios | android | web | cli — UI 검증 도구 분기에 사용
- build: 빌드 명령 (각 단계 acceptance에서 인용 가능)
- test: 테스트 명령
- device: 에뮬레이터 ID 또는 디바이스 시리얼

각 단계의 acceptance: (optional, 한 줄 Bash):
- exit 0 → panel 0이 단계 진행
- exit ≠ 0 → 단계 유지 + 수정 지시 (3회 실패 시 막힘)
- 비어있으면 panel 0이 본문 + git diff 휴리스틱으로 자동 판정

복잡한 검증은 `.claude/bin/verify-*.sh` 또는 프로젝트 스크립트로 분리.
모바일 예: acceptance: ./gradlew assembleDebug && bash .claude/bin/verify-android.sh app/build/outputs/apk/debug/app-debug.apk
-->
