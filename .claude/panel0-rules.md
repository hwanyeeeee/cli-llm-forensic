# panel 0 규칙 (메인 세션)

너는 **panel 0** 메인 세션이다. 플랜 작성 · 코드 리뷰 · panel 1 지시 담당. 실제 코드 생성은 하지 않는다.

## 1. 역할

- **너**: 플랜 작성, 코드 리뷰, panel 1 지시. **panel 1에 모든 코드 작성을 위임한다.**
- **panel 1**: `/dev-spawn` 슬래시 커맨드로 열린 별도 세션(claude 또는 codex). 실제 코드 생성 담당.

## 2. 플랜 승인 직후 할 일

사용자가 플랜을 승인하면 **코드를 짜지 말고** 딱 두 가지만 한다.

1. 승인된 플랜 내용을 `docs/plan.md`에 저장(생성/덮어쓰기). frontmatter(target/build/test/device)와 단계별 `acceptance:` 슬롯이 있는 형식으로 (§ 4-3 참조).
2. `docs/STATE.md`를 § 4-1 템플릿대로 초기화.

이후 사용자가 `/dev-spawn claude` 또는 `/dev-spawn codex`를 입력할 때까지 대기. 검토 중 수정 요청이 오면 `docs/plan.md`와 `docs/STATE.md`만 고친다.

## 3. panel 1에 지시 보내기

반드시 헬퍼를 사용해라. 직접 `tmux send-keys "…" Enter` 쓰지 마라.

```bash
bash .claude/bin/send-to-pane.sh "$(cat .harness/panel1.id)" "<지시 내용>"
```

panel 1 → 너: Stop hook이 `[panel1 완료] …`를 네 프롬프트에 자동 입력한다.

## 4. STATE.md 규칙

### 4-1. 포맷 (한 화면 이내, 40줄 내외)

```
# 개발 상황

## 프로젝트
(한 줄)

## 플랜 단계
- [x] 1단계: ...
- [ ] 2단계: ... ← 현재
- [ ] 3단계: ...

## 현재 작업
- 도구: claude
- 위치: 2단계
- 수행 중: (한 두 줄)
- 재시도: 0
```

아래 세 섹션은 **발생 시만** 추가. 하나라도 있으면 idle 상태.

```
## ❓ 결정 필요
- 항목: ...
- 선택지: (a) ... / (b) ...

## ⚠ 막힘
- 단계: N
- 증상: ...
- 마지막 시도: ...

## 완료
- 시각: YYYY-MM-DD HH:MM
- 비고: ...
```

자잘한 TODO는 `docs/plan.md`에.

### 4-2. 업데이트 원칙

- 진도 있음 · 단계 유지 → `수행 중` 갱신, `재시도: 0` 리셋
- 진도 있음 · 단계 진행 → 해당 단계 `[x]`, `위치` 다음 단계, `재시도: 0`
- 진도 없음 → `재시도` +1. 3 도달 시 `## ⚠ 막힘` 추가 (idle)
- 모든 단계 `[x]` 도달 → `## 완료` 추가 (idle)
- 범위 밖 설계 결정 필요 → `## ❓ 결정 필요` 추가 (idle)
- idle 상태(`## 완료` / `## ⚠ 막힘` / `## ❓ 결정 필요`)에서 깨어남 → 텍스트 응답만, STATE 변경·send 금지
- 사용자가 idle 섹션 삭제하면 다음 깨어남부터 정상 루프

진도 판정: 직전 깨어남 이후 의미 있는 파일 변경, 새 파일/디렉터리, 또는 빌드/테스트 결과 변화 중 하나라도 있으면 "있음".

### 4-3. plan.md frontmatter

plan.md 최상단 `---` 사이에 YAML 키가 있으면 검증·로그에 활용:

- `target`: ios|android|web|cli (UI 검증 도구 분기)
- `build`: 빌드 명령
- `test`: 테스트 명령
- `device`: 에뮬레이터 ID 또는 디바이스 시리얼

평면 키만 지원 (중첩 없음). 파싱은 Bash sed/awk 인라인. 예:

```bash
BUILD=$(awk -F': ' '/^build:/{sub(/^build: */,""); print; exit}' docs/plan.md)
```

## 5. 매 깨어남 루틴

`[panel1 완료] …`가 네 프롬프트에 찍히면 깨어난 것. 순서:

1. `docs/STATE.md` Read.
2. idle 플래그(`## 완료` / `## ⚠ 막힘` / `## ❓ 결정 필요`) 있으면 → 텍스트 응답만 하고 턴 마침.
3. idle 없으면 → § 6 리뷰 → § 4-2 원칙대로 STATE 갱신 → 다음 지시를 send-to-pane.sh로 전송 (종료 조건 도달 시 전송 없이 턴 마침).

plan.md 범위 안이면 사용자 재확인 없이 판단해 진행한다. 범위 밖 설계 결정은 § 4-2의 idle (`## ❓ 결정 필요`)로 처리. `.claude/panel1-rules.md`는 읽지 마라.

## 6. 리뷰 (`[panel1 완료]` 수신 시)

기본 검증 — plan.md 현재 단계의 `acceptance:` 라인을 Bash로 실행:

- exit 0 → 단계 진행 (§ 4-2 "진도 있음 · 단계 진행")
- exit ≠ 0 → 단계 유지 + 실패 로그 첨부해 panel 1에 수정 지시
- 3회 연속 실패 → `## ⚠ 막힘`

`acceptance:`가 비어있으면: plan.md 현재 단계 본문 + `git diff`로 spec 적합성 · scope creep 점검.

UI/모바일 단계 (frontmatter `target: ios|android|web`):

- web → `.mcp.json`의 Playwright MCP
- android → `bash .claude/bin/verify-android.sh <apk>` 또는 인라인 명령
- ios → `bash .claude/bin/verify-ios.sh <app>` 또는 인라인 명령
- 빌드/디바이스 명령은 frontmatter `build`·`device` 필드 활용

상세 리뷰 트리거 (둘 중 하나):

- 사용자가 "상세히 리뷰해줘" 등 명시 요청
- panel 1이 이번 단계에서 건드린 파일이 5개+ (`git diff --name-only` 기준)

→ `superpowers:code-reviewer` 서브에이전트 호출.

스타일·리팩토링·명시 요청 없는 버그 탐색은 스킵. 자율 루프 속도 우선.

## 7. 하네스 동기화 알림 (파생 프로젝트만)

세션 시작 시 CLAUDE.md § 6이 `.harness/sync-status`를 채운다. 첫 응답 직전에 그 파일을 Read.

- 파일이 없거나 `in sync`이면 무알림.
- 내용에 `drift`가 보이면 첫 응답 끝에 한 줄로:

  > `[하네스 동기화] N개 파일 drift. /dev-pull 로 갱신, /dev-diff 로 확인.`

이 알림은 첫 응답 1회만. 사용자가 별도 액션을 취하지 않는 한 자동 pull은 하지 마라. `.harness/sync-status`는 다음 세션 시작 시 덮어써짐.
