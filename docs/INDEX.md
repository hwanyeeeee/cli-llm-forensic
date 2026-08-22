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
- **`Codex-정확도-측정결과.md`** — 그 3시나리오의 Codex 측정 결과(수치 + 못 재는 것).
- **`유출시나리오-재현.md`** — 유출 A/B 두 결론 재현 데이터셋(발표 데모·패널 ④ 화면).
- **`origin-channel-원격지시-판별.md`** — 폰 지시 vs 로컬 타이핑 판별 규칙과 실측 분포.
- **`원격제어-마커.md`** — "이 머신에 원격제어가 설정된 적 있나"(상태). 위 문서는 행동, 이건 상태.
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
| `Codex-정확도-측정결과.md` | Codex 정확도 측정 결과 3시나리오×100건 — era 균형 근거·수치·못 재는 것(shell redirect·read 레코드 부재·item era MCP 공백) |
| `유출시나리오-재현.md` | 유출 A/B 두 결론 재현(사용자 직접 vs 에이전트 자율) — Claude·Codex 동일 결론·시연 화면 수치·공개 캡처 주의 |
| `origin-channel-원격지시-판별.md` | `meta.origin_channel` 원격/로컬 판별 — Claude promptSource·Codex logs_2 연결 조인·실데이터 분포·해상도 한계 |
| `원격제어-마커.md` | 원격제어 마커 4종(호스트·계정 **상태**) — Event 가 아닌 이유·signal 3값·승격 금지 함정 3개·`/api/remote-control` 계약 |
| `발표-가이드라인.md` | 발표 흐름·주의 (팀원) |
| `superpowers/specs/2026-06-17-clfx-mvp-design.md` | clfx MVP 설계 스펙 (파싱·분석·질의 확정안) |
| `superpowers/plans/2026-06-17-clfx-mvp.md` | clfx MVP 상세 구현 플랜 (Task 0~14 TDD, 실코드 포함) |
| `superpowers/specs/2026-06-17-clfx-dashboard-design.md` | clfx 웹 대시보드(Stage 4) 설계 — stdlib 서버+vanilla JS 뷰 |
| `superpowers/plans/2026-06-17-clfx-dashboard.md` | clfx 웹 대시보드 상세 구현 플랜 (Task 1~6 TDD, 실코드 포함) |
| `사용법.md` | clfx 데모·시연 사용법 (parse→analyze→query→serve + A/B 흐름) |
| `교수님-피드백.md` | 교수님 피드백 9건(원본복구·해시대조·주체왜곡·월별그래프·키워드파이·프롬프트요약·MCP·범용화) |
| `실측-temp-원본보존-원리.md` | Claude 원본보존(uploads/file-history)·temp 경로(/tmp·claude-1000)·30일 소실 실측 |
| `codex-지원-엔진스펙.md` | Codex 아티팩트 지원 엔진 스펙 — era 분기·3계층 이름·행위자 판별·Event 확장 확정안 (R1~R4 교차검증 근거) |
| `AgenTrace-아티팩트-인계문서.md` | **★ 팀원 인계 최종본 (발표자료 제작용)** — §2 로컬(Claude·Codex) + §3 원격제어 4시나리오(Android·iOS × Claude·Codex) 전량. 판별자 한 장·오판 함정 12건·한계·경로 색인·슬라이드 구성 제안 포함 |
| `AgenTrace-종합-아티팩트-분석.md` | **패널 제작 기준 종합본** — 로컬(Claude·Codex) + Android 원격제어(S3·S4) + 오판 함정 + 도구 검증. iOS 예정 |
| `모바일-원격제어-분석-계획.md` | 모바일 원격제어 4시나리오(iOS·Android × Claude·Codex) 인계 문서 — 통제실험 절차·취득 방법·산출 규격 |
| ~~`패널-제작-계획.md`~~ *(보류 — 패널 제작 범위 밖)* | 패널 마감 역산 작업계획 — 신청서 정합성·모바일 실측 착수안·구성 재설계 |
| ~~`패널-구성안.md`~~ *(보류 — 패널 제작 범위 밖)* | 경진대회 A1 패널 확정 구성 — 제약·그림 4개·수치 표기 규칙·글자량 상한 |
| `exe-패키징-UI-가이드.md` | 팀원 전달 — PyInstaller 단일exe+내장서버, UI는 web/static/ HTML, UI↔엔진 계약 |
| `UI-변경사항.md` | 팀원 UI 개편 내역(3컬럼·히트맵·도넛·코파일럿·시크릿 표시 제외 정책) |
| `superpowers/specs/2026-06-17-clfx-피드백확장-design.md` | 교수님 피드백 8건 확장 설계(수집·분석·시각화·exe, brainstorming+UI 통합) |
| `superpowers/plans/2026-06-17-clfx-피드백확장-A-분석시각화.md` | A단계 구현 플랜(③④⑤⑥⑦ + 신규 API, Task 1~7 TDD) |
| `superpowers/plans/2026-06-17-clfx-exe-스캔UX.md` | exe 인자0 실행→브라우저 자동→스캔화면 소스선택→인메모리 parse+analyze→대시보드 (자동탐지·/api/scan·launcher·PyInstaller, Task 1~5) |
| `llm-handoff.md` | LLM 파트 인계(설계원칙·현재흐름·gemma 지시준수 과제·codex 지적 7건·보안) — 담당 팀원 인수용 |
| `superpowers/plans/2026-06-18-clfx-B-아티팩트-해시귀속.md` | B단계 ①+④ 구현 플랜(read-only FS 해시대조·복제유출탐지·FS↔transcript JOIN 주체왜곡보정, Task1~6 TDD) |
| `superpowers/plans/2026-06-18-clfx-C-MCP통합-tmp보존.md` | C단계 ⑧ 구현 플랜(MCP 설정·실사용 통합·used_unconfigured 신호 + tmp 보존기간, Prefetch 보류, Task1~10 TDD) |
| `superpowers/specs/2026-07-02-clfx-성능개선-design.md` | 성능개선 설계 — 계측 우선 2-페이즈 + sqlite3 케이스 파일 + 표적 백로그(gzip·인덱스·LLM 스트리밍), 불변식 I1~I6 |
| `superpowers/plans/2026-07-02-clfx-성능개선-P1-계측.md` | Phase 1 계측 하네스 구현 플랜(스캔 timings·요청 로그·LLM timings·프런트 marks·bench.py, Task 1~6 TDD) |
| `perf-baseline.md` | Phase 1 성능 측정 결과(단계별 median·병목 순위표) — Phase 2 착수 순서의 근거 |
| `superpowers/plans/2026-07-03-clfx-성능개선-P2a-취득계층.md` | Phase 2a 구현 플랜(O9 적응형 동시성·O10 탐지 타임아웃·O11 WSL-side 파싱 위임, Task 1~5 TDD) |
| `plan.md` / `STATE.md` | 개발 진행판 (개발 시작 후) |
