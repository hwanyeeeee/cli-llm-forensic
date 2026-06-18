# 문서 색인

처음 오면 이 파일부터. 새 문서를 만들면 여기 한 줄 추가한다.

프로젝트: AI 코딩 에이전트(Claude Code · Codex · Gemini CLI)가 남긴 기록을 파싱·분석하고 자연어로 질의하는 포렌식 도구.

## 먼저 읽기 (둘 다)
1. **`설계.md`** — 무엇을·왜·어떻게 만드는지. 전체 그림.
2. **`event-schema.md`** — 파싱·분석 결과의 출력 형태. 도구와 데이터셋이 같이 쓰는 형식.
3. **`역할분담.md`** — 누가 뭘 하나.

## 코어 개발자
- 위 1~3 + **`논문대비-신규발견.md`** (파서가 다뤄야 할, 논문에 없던 새 기록들).
- 토대 논문: SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6725750

## 팀원
- **`스테이징-데이터셋-가이드.md`** — 정답 아는 사건 데이터 만들기.
- **`정확도-검증-시나리오.md`** — 주체식별·접근파일·MCP호출 정확도 자동 검증(각 100건).
- **`논문대비-신규발견.md`** — 자기 PC에서 표 채우기(교차확인).
- **`발표-가이드라인.md`** — 발표 자료.

## 전체 목록

| 문서 | 내용 |
|---|---|
| `설계.md` | 도구 설계 — 무엇·왜·어떻게 |
| `event-schema.md` | 출력 레코드 형태 |
| `역할분담.md` | 코어=도구 / 팀원=데이터셋·검증·발표 |
| `논문대비-신규발견.md` | 논문에 없던 새 기록 + 다른 PC 교차확인 |
| `스테이징-데이터셋-가이드.md` | 통제 데이터셋 만들기 (팀원) |
| `정확도-검증-시나리오.md` | 정확도 자동 검증 3시나리오(주체식별·접근파일·MCP호출, 각 100건) — 합성 transcript→1:1 비교 (발표용) |
| `발표-가이드라인.md` | 발표 흐름·주의 (팀원) |
| `superpowers/specs/2026-06-17-clfx-mvp-design.md` | clfx MVP 설계 스펙 (파싱·분석·질의 확정안) |
| `superpowers/plans/2026-06-17-clfx-mvp.md` | clfx MVP 상세 구현 플랜 (Task 0~14 TDD, 실코드 포함) |
| `superpowers/specs/2026-06-17-clfx-dashboard-design.md` | clfx 웹 대시보드(Stage 4) 설계 — stdlib 서버+vanilla JS 뷰 |
| `superpowers/plans/2026-06-17-clfx-dashboard.md` | clfx 웹 대시보드 상세 구현 플랜 (Task 1~6 TDD, 실코드 포함) |
| `사용법.md` | clfx 데모·시연 사용법 (parse→analyze→query→serve + A/B 흐름) |
| `교수님-피드백.md` | 교수님 피드백 9건(원본복구·해시대조·주체왜곡·월별그래프·키워드파이·프롬프트요약·MCP·범용화) |
| `실측-temp-원본보존-원리.md` | Claude 원본보존(uploads/file-history)·temp 경로(/tmp·claude-1000)·30일 소실 실측 |
| `exe-패키징-UI-가이드.md` | 팀원 전달 — PyInstaller 단일exe+내장서버, UI는 web/static/ HTML, UI↔엔진 계약 |
| `UI-변경사항.md` | 팀원 UI 개편 내역(3컬럼·히트맵·도넛·코파일럿·시크릿 표시 제외 정책) |
| `superpowers/specs/2026-06-17-clfx-피드백확장-design.md` | 교수님 피드백 8건 확장 설계(수집·분석·시각화·exe, brainstorming+UI 통합) |
| `superpowers/plans/2026-06-17-clfx-피드백확장-A-분석시각화.md` | A단계 구현 플랜(③④⑤⑥⑦ + 신규 API, Task 1~7 TDD) |
| `superpowers/plans/2026-06-17-clfx-exe-스캔UX.md` | exe 인자0 실행→브라우저 자동→스캔화면 소스선택→인메모리 parse+analyze→대시보드 (자동탐지·/api/scan·launcher·PyInstaller, Task 1~5) |
| `llm-handoff.md` | LLM 파트 인계(설계원칙·현재흐름·gemma 지시준수 과제·codex 지적 7건·보안) — 담당 팀원 인수용 |
| `superpowers/plans/2026-06-18-clfx-B-아티팩트-해시귀속.md` | B단계 ①+④ 구현 플랜(read-only FS 해시대조·복제유출탐지·FS↔transcript JOIN 주체왜곡보정, Task1~6 TDD) |
| `superpowers/plans/2026-06-18-clfx-C-MCP통합-tmp보존.md` | C단계 ⑧ 구현 플랜(MCP 설정·실사용 통합·used_unconfigured 신호 + tmp 보존기간, Prefetch 보류, Task1~10 TDD) |
| `plan.md` / `STATE.md` | 개발 진행판 (개발 시작 후) |
