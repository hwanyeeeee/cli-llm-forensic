# Codex cross-family 리뷰어 (ephemeral) 설계

- 날짜: 2026-06-15
- 대상 repo: Dev-harness (템플릿 — 파생 프로젝트로 sync 전파)
- 상태: 설계 승인됨, 구현 플랜 대기

## 1. 배경 · 문제

현재 하네스는 2-pane ping-pong:

- **panel0** (Claude): plan 작성, 오케스트레이트, **리뷰**, panel1 지시.
- **panel1** (Claude): 코드 구현.

리뷰가 약한 고리다. panel0(Claude)이 panel1(Claude)의 코드를 검수 — **같은 모델 계열**. `panel0-rules.md §6` 리뷰는 `acceptance:` 명령 + 가끔 `code-reviewer` 서브에이전트(역시 Claude)뿐이다.

AWS 블로그 실험(https://aws.amazon.com/ko/blogs/tech/codex-claudecode-harness/) 결론: **Codex = 도달성 버그헌터(리뷰 적합), Claude = 안정적 편집 파트너(구현 적합)**. Codex는 실행경로·재현경로가 명확한 실제 버그를 cross-review로 가장 날카롭게 잡고, **review-only 핸드오프**로 배치했을 때 가장 안정적이었다. 같은 계열 리뷰가 놓치는 reachability/repro 버그를 cross-family 리뷰가 잡는다.

→ cross-family(Codex) 리뷰어가 빠진 조각.

## 2. 목표 · 비목표

**목표**: 사람 손 최소 + 직접 테스트해도 런타임 에러 없이 동작하는 결과물. (속도는 비목표 — 시간 안 따짐.)

**비목표**:
- 새 pane 추가 (라우팅 self-heal이 2-pane 하드코딩이라 비용 큼 — 회피).
- Codex가 코드를 편집하는 것 (블로그 분리 원칙 위반).
- 리뷰 속도 최적화.

## 3. 확정된 결정

| 결정 | 선택 | 근거 |
|---|---|---|
| 리뷰어 형태 | **ephemeral `codex exec` 호출** (pane 아님) | spec+diff는 디스크 파일이라 warm 컨텍스트 불필요. fresh eyes가 anchoring 없이 더 잘 잡음. 블로그 "stateless 핸드오프 = 가장 안정적". 라우팅 무변경. |
| Codex 권한 | **read-only** (`codex exec --sandbox read-only`) | 리뷰어가 편집하면 codex-리뷰/claude-편집 분리 붕괴. |
| 출력 통제 | `codex exec` 커스텀 프롬프트 (vs `codex review`) | 고정 포맷 강제 → bash 파싱 가능. |
| 게이트 엄격도 | **단계별 + 심각도 차등** | BLOCK(correctness/런타임/도달버그)만 차단, NIT는 log만. 오류엔 막고 nit엔 안 도는 균형. |
| cross-step 기억 | **`review-log.md` 파일** (warm pane 대체) | 재시작/swap에도 생존, 사람이 읽음, 감사 가능. |
| review-log 수명 | **plan 완료 후 보존** | 감사용. 초기화 안 함. |

## 4. 아키텍처

### 4-1. 토폴로지 (2-pane 유지)

```
panel0 (Claude)              panel1 (Claude)
오케스트레이트·plan·리뷰디스패치   구현·수정
   │  send-to-pane ───────────►  │
   │  ◄─────────── Stop hook 알림 │
   │
   └─ Bash: codex exec (read-only, headless, 일회성)
            ▲ 새 pane 아님. panel0이 게이트마다 호출.
```

`register-pane.sh` / `resolve-pane.sh` / `notify-main.sh` **무변경.**

### 4-2. 루프 (단계당)

```
panel1 구현 → Stop hook → panel0 깨어남 ([panel1 완료])
  │
  ├─ acceptance: 명령 실행 (기존 §6 싼 게이트)
  │    fail → 실패로그 첨부해 panel1에 같은 단계 재지시 → 종료
  │    pass ↓
  │
  ├─ codex-review.sh <단계#> 호출
  │    입력: 단계 spec + acceptance + `git diff` + review-log.md
  │    출력: 고정포맷 findings (stdout), exit 0=BLOCK없음 / 1=BLOCK있음
  │
  ├─ BLOCK 있음 → findings를 review-log에 append
  │              → panel1에 수정 지시 (BLOCK 항목만) → 같은 단계 → 종료
  │    (다음 깨어남에 재리뷰. Claude가 편집 — 블로그 원칙.)
  │
  └─ BLOCK 없음 → NIT는 review-log에 append (차단 안 함)
                → 해당 단계 [x], 위치 다음 단계, 재시도 0 → 다음 지시 → 종료

모든 단계 [x] 도달 →  최종 real-run 검증 (§4-4)
                      clean → ## 완료 (idle)
                      런타임 에러 → codex가 실패 리뷰 → panel1 수정 (단계 재개)
```

**iteration cap**: 같은 단계에서 BLOCK→수정→재리뷰가 3 라운드 연속 진도 없음 → `## ⚠ 막힘` idle → 사용자 escalate. 기존 §4-2 `재시도` 메커니즘 재활용 (리뷰 라운드도 재시도로 카운트).

### 4-3. 심각도 차등

Codex 출력 = findings 한 줄씩, 고정 포맷 (bash 파싱):

```
<SEVERITY> <file>:<line> | <problem> | <fix>
```

- `BLOCK` — correctness / 런타임 에러 / 도달가능 버그. **차단.**
- `NIT` — 스타일 / 리팩토링 / 사소. review-log만, 차단 안 함.

panel0: `grep -c '^BLOCK'` > 0 → 수정 루프. 0 → 진행. codex-review.sh가 이 판정을 exit code로 반환 (0/1).

### 4-4. 최종 real-run 검증 게이트

모든 단계 `[x]` 후, `## 완료` 선언 전에 프로그램을 **실제 실행**한다. plan.md frontmatter의 `run:` 명령 사용 (없으면 `test`로 폴백). target 분기는 기존 §6 재활용:

- `cli` → `run:` 명령을 샘플 입력으로 실행, exit 0 + stderr에 예외 없음 확인.
- `web` → 기존 Playwright MCP 경로.
- `android`/`ios` → 기존 `verify-android.sh` / `verify-ios.sh`.

런타임 에러 발견 → codex가 실패 출력을 리뷰 → panel1에 수정 지시 → 단계 재개. clean → `## 완료`.

이게 "내가 직접 테스트해도 에러 없음"을 보장하는 게이트.

## 5. 컴포넌트

### 5-1. `.claude/bin/codex-review.sh` (NEW)

- **무엇**: ephemeral cross-family 리뷰어.
- **사용법**: `codex-review.sh <단계#>` (panel0이 Bash로 호출).
- **동작**:
  1. `docs/plan.md`에서 `<단계#>`의 본문 spec + `acceptance:` 추출 (기존 awk/sed 인라인 파싱 패턴).
  2. `git diff` (또는 단계 범위 diff) 캡처.
  3. `.harness/review-log.md` 읽어 cross-step 컨텍스트 합성.
  4. spec + diff + review-log + 고정 출력포맷 지시를 프롬프트로 합쳐 `codex exec --sandbox read-only "<prompt>"` 호출 (정확한 플래그는 구현 시 확정 — 비인터랙티브 + 쓰기 금지 보장).
  5. findings를 stdout에 고정포맷으로 출력.
- **exit code**: `0` = BLOCK 없음, `1` = BLOCK 있음, `2` = codex 사용불가/에러(sentinel).
- **의존**: `codex` CLI, `git`, `docs/plan.md`.
- **degradation**: codex 없음/에러 → exit 2 + stderr 사유. panel0이 폴백 처리(§6).

### 5-2. `.harness/review-log.md` (NEW, runtime state)

- **무엇**: append-only findings/결정 로그. `.harness/`는 이미 gitignored → 자동 제외.
- **포맷**: 단계별 섹션, 각 finding 타임스탬프 없이(`Date.now` 회피) 단계#·SEVERITY·file:line·problem·결정(수정됨/보류) 기록.
- **읽기**: codex-review.sh (cross-step 기억). **쓰기**: panel0 (findings append).
- **수명**: plan 완료 후 **보존** (감사).

### 5-3. `.claude/panel0-rules.md §6` (EDIT — 가장 큰 변경)

기존 "리뷰" 섹션을 교체:
- acceptance 통과 후 `codex-review.sh` 호출 분기.
- BLOCK/NIT 처리 규칙 (§4-2, §4-3).
- 최종 real-run 게이트 (§4-4).
- iteration cap = 리뷰 라운드 (§4-2).
- codex 폴백: exit 2면 기존 `code-reviewer` 서브에이전트로 폴백, 루프 유지.
- 기존 "상세 리뷰 트리거(5파일+ / 명시요청 → code-reviewer 서브에이전트)"는 codex 폴백 경로로 흡수.

### 5-4. `docs/plan.md` frontmatter (EDIT)

`run:` 키 추가 — 최종 end-to-end 실행 명령. 없으면 `test`로 폴백. 평면 키, 기존 파싱 패턴 동일.

### 5-5. `.claude/panel1-rules.md` (EDIT — 최소)

한 줄 추가: 수정 지시가 codex 리뷰 findings에서 올 수 있다 (panel1은 받은 지시대로 구현하면 됨, 동작 동일). 무변경도 허용.

## 6. 가드레일

- **Codex read-only 필수.** 리뷰어가 파일 쓰면 분리 원칙 붕괴. sandbox read-only로 강제 + 프롬프트로 "리뷰만, 편집 금지" 명시.
- **하드스톱 금지.** codex 사용불가 → 서브에이전트 폴백 → 루프 계속.
- **무한루프 방지.** BLOCK 재리뷰 3라운드 무진도 → `## ⚠ 막힘` idle.
- **NIT 루프 방지.** NIT는 절대 차단 안 함, log만.

## 7. 마이그레이션 · 백업

- Dev-harness = git repo (private GitHub remote, 초기 커밋 있음).
- **feature 브랜치** `feat/codex-reviewer`에서 작업. `main` = 롤백 지점. git이 백업. (선택: `git tag pre-codex-reviewer`.)
- 현재 `main`에 미커밋 변경 있음(라우팅 self-heal infra: register-pane.sh, resolve-pane.sh 등) — 브랜치가 들고 감, 관련 infra라 OK.
- 검증 통과 → `main` 머지.
- **파생 프로젝트 안 깨짐**: 기존 drift-detection(`/dev-diff`/`/dev-pull`)이 "N개 파일 drift" 알림만. 각자 준비되면 pull. 강제 전파 아님.

## 8. 검증 플랜

[[project_redesign_validated]] 패턴 — 작은 CLI 프로젝트(wc류 5단계)를 새 루프로 end-to-end:

1. codex 리뷰가 acceptance 통과 후 발화하는지.
2. 심은 BLOCK 버그(예: 도달가능 off-by-one)가 잡힘 → review-log 기록 → panel1 수정 → 재리뷰 clean.
3. NIT(스타일)는 log되지만 차단 안 됨.
4. 최종 real-run(`run:`)이 실제 실행되고 런타임 에러를 잡는지.
5. codex 강제 비활성화 시 서브에이전트 폴백으로 루프 유지되는지.
6. review-log가 plan 완료 후 보존되는지.

## 9. 리스크 · 열린 항목

- `codex exec`의 정확한 read-only 플래그/출력 안정성 — 구현 시 실측 확정. 폴백 경로가 안전망.
- codex 출력 포맷 일탈 시 파싱 실패 → "리뷰 불확정"으로 처리, 서브에이전트 폴백 또는 재시도 (구현 시 정책 확정, 기본 폴백).
- 단계 범위 diff 산정 — 단계 경계 추적 방법(마지막 커밋 vs working tree). 기본: 직전 게이트 이후 working tree diff.
