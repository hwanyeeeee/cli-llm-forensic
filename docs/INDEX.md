# 문서 색인

처음 오면 이 파일부터. 새 문서를 만들면 여기 한 줄 추가한다.

프로젝트: AI 코딩 에이전트(Claude Code · Codex CLI)가 남긴 기록을 파싱·분석하고 자연어로 질의하는 포렌식 도구.

## 폴더 구조

| 위치 | 내용 |
|---|---|
| `docs/` | 핵심 문서 — 설계·출력 형식·사용법·종합 분석·인계 최종본·개발 진행판 |
| `docs/analysis/` | 아티팩트 분석 — Codex 상세·엔진 스펙·원격 판별·원격제어 마커·원본 보존 실측 |
| `docs/validation/` | 검증 — 정확도 측정·유출 시나리오 재현·데이터셋 만들기·성능 측정 |
| `docs/team/` | 팀 운영 — 역할·인계·UI·발표·피드백 |
| `docs/archive/` | 보류 — 범위 밖으로 뺀 문서 (읽지 않아도 된다) |

## 먼저 읽기
1. **`설계.md`** — 무엇을·왜·어떻게 만드는지. 전체 그림.
2. **`event-schema.md`** — 파싱·분석 결과의 출력 형태. 도구와 데이터셋이 같이 쓰는 형식.
3. **`team/역할분담.md`** — 누가 뭘 하나.

## 코어 개발자
- 위 1~3 + **`analysis/논문대비-신규발견.md`** (파서가 다뤄야 할, 논문에 없던 새 기록들).
- Codex 작업이면 **`analysis/codex-지원-엔진스펙.md`** 먼저.
- 토대 논문: SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6725750

## 팀원
- **`AgenTrace-아티팩트-인계문서.md`** — 발표자료 제작용 인계 최종본.
- **`validation/스테이징-데이터셋-가이드.md`** — 정답 아는 사건 데이터 만들기.
- **`validation/정확도-검증-시나리오.md`** — 주체식별·접근파일·MCP호출 정확도 자동 검증(각 100건).
- **`validation/유출시나리오-재현.md`** — 유출 A/B 두 결론 재현 데이터셋(발표 데모).
- **`analysis/origin-channel-원격지시-판별.md`** — 폰 지시 vs 로컬 타이핑 판별 규칙과 실측 분포.
- **`analysis/원격제어-마커.md`** — "이 머신에 원격제어가 설정된 적 있나"(상태). 위 문서는 행동, 이건 상태.
- **`team/발표-가이드라인.md`** — 발표 자료.

## 전체 목록

### `docs/` (루트)

| 문서 | 내용 |
|---|---|
| `INDEX.md` | 이 색인 |
| `설계.md` | 도구 설계 — 무엇·왜·어떻게 |
| `event-schema.md` | 출력 레코드 형태 (단일 원천) |
| `사용법.md` | clfx 데모·시연 사용법 (parse→analyze→query→serve + A/B 흐름) |
| `AgenTrace-종합-아티팩트-분석.md` | 종합본 — 로컬(Claude·Codex) + Android 원격제어(S3·S4) + 오판 함정 + 도구 검증 |
| `AgenTrace-아티팩트-인계문서.md` | **★ 팀원 인계 최종본 (발표자료 제작용)** — 로컬(Claude·Codex) + 원격제어 4시나리오(Android·iOS × Claude·Codex). 판별자 한 장·오판 함정 12건·한계·경로 색인 |
| `plan.md` / `STATE.md` | 개발 진행판 |

### `docs/analysis/`

| 문서 | 내용 |
|---|---|
| `codex-아티팩트-상세분석.md` | Codex CLI 저장 데이터·파일 접근·임시 경로·SQLite·원본 보존 상세 분석 (로컬 관측) |
| `codex-아티팩트-분석-교차검증.md` | 위 상세분석의 교차검증 보고 — Claude × Codex 상호 반박 2라운드, rollout 344파일 전수 |
| `codex-지원-엔진스펙.md` | Codex 지원 엔진 스펙 — era 분기·3계층 이름·행위자 판별·Event 확장 확정안 |
| `논문대비-신규발견.md` | 논문에 없던 새 기록 + 다른 PC 교차확인 |
| `실측-temp-원본보존-원리.md` | Claude 원본보존(uploads/file-history)·temp 경로·30일 소실 실측 |
| `origin-channel-원격지시-판별.md` | `meta.origin_channel` 원격/로컬 판별 — Claude promptSource·Codex logs_2 조인·실데이터 분포·한계 |
| `원격제어-마커.md` | 원격제어 마커 4종(호스트·계정 **상태**) — Event 가 아닌 이유·signal 3값·`/api/remote-control` 계약 |
| `모바일-원격제어-분석-계획.md` | 모바일 원격제어 4시나리오(iOS·Android × Claude·Codex) — 통제실험 절차·취득 방법·산출 규격 |

### `docs/validation/`

| 문서 | 내용 |
|---|---|
| `정확도-검증-시나리오.md` | 정확도 자동 검증 3시나리오(주체식별·접근파일·MCP호출, 각 100건) — 합성 transcript→1:1 비교 |
| `Codex-정확도-측정결과.md` | 위 3시나리오의 Codex 측정 결과 — era 균형 근거·수치·못 재는 것 |
| `유출시나리오-재현.md` | 유출 A/B 두 결론 재현(사용자 직접 vs 에이전트 자율) — Claude·Codex 동일 결론·시연 화면 수치 |
| `스테이징-데이터셋-가이드.md` | 통제 데이터셋 만들기 (팀원) |
| `perf-baseline.md` | 성능 측정 결과(단계별 median·병목 순위표) |

### `docs/team/`

| 문서 | 내용 |
|---|---|
| `역할분담.md` | 코어=도구 / 팀원=데이터셋·검증·발표 |
| `exe-패키징-UI-가이드.md` | PyInstaller 단일exe+내장서버, UI는 web/static/ HTML, UI↔엔진 계약 |
| `UI-변경사항.md` | 팀원 UI 개편 내역(3컬럼·히트맵·도넛·코파일럿·시크릿 표시 제외 정책) |
| `llm-handoff.md` | LLM 파트 인계(설계원칙·현재흐름·gemma 지시준수 과제·보안) |
| `교수님-피드백.md` | 교수님 피드백 9건(원본복구·해시대조·주체왜곡·월별그래프·키워드파이·프롬프트요약·MCP·범용화) |
| `발표-가이드라인.md` | 발표 흐름·주의 |
| `AgenTrace발표자료.pdf` | 발표 자료 PDF |

### `docs/archive/`

| 문서 | 내용 |
|---|---|
| `패널-구성안.md` | 경진대회 A1 패널 구성 — 패널 제작은 이 저장소 범위 밖 |
| `패널-제작-계획.md` | 패널 마감 역산 작업계획 — 패널 제작은 이 저장소 범위 밖 |
