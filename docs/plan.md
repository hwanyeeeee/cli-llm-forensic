---
target: cli
build: pip install -e ".[dev]"
test: pytest -q
run: pytest tests/test_e2e_ab.py -q
---

# 플랜 — clfx MVP (파싱 → 분석 → 질의)

상세 구현 플랜(Task 0~14, 실코드 포함): `docs/superpowers/plans/2026-06-17-clfx-mvp.md`.
설계 스펙: `docs/superpowers/specs/2026-06-17-clfx-mvp-design.md`. Event 단일 진실원천: `docs/event-schema.md`.

**목표:** Claude Code 기록(`~/.claude`)을 파싱·분석·자연어 질의하는 포렌식 CLI `clfx`. 시연 = A(사용자 붙여넣기)/B(에이전트 자율 read) 두 사건 재구성 + `actor` 주체 규명.
**원칙:** TDD(빨강→초록). 테스트 입력 = `tests/fixtures/`에 커밋한 합성 jsonl(CLFXTEST 시크릿, 실데이터/스테이징셋 의존 금지). 질의 = 결정적 엔진 backbone + 얇은 LLM 어댑터(요약, 없어도 동작).

## 1단계: 파싱
Task 0~6 — 스캐폴드 → `event.py`(Event/Source) → 픽스처+conftest 빌더 → `sources/claude.py`(reader) → `paste.py`(3사슬+이미지) → `parser.py`(raw→Event, §A paste·§B read/prompt/bash/write/response) → CLI `parse`.
모든 Event는 `source{file,line}` 추적. paste 3사슬(content/contentHash→paste-cache/이미지 base64)·§B 레코드 타입 전부 처리.

acceptance: pip install -e ".[dev]" >/dev/null 2>&1; pytest tests/test_event.py tests/test_fixtures.py tests/test_sources.py tests/test_paste.py tests/test_parser.py tests/test_cli_parse.py -q

## 2단계: 분석
Task 7~10 — `analyze/secrets.py`(시크릿 8종+PII 탐지·`‹secret›` 마스킹) → `analyze/attribution.py`(귀속 enrich: bypass-mode 태그·시크릿 태그·마스킹·요약) → `analyze/timeline.py`(ts 정렬) → CLI `analyze`.
CLFXTEST-001~008 전부 탐지, 노이즈(app.py) 0 오탐, A=user/B=agent 귀속.

acceptance: pytest tests/test_secrets.py tests/test_attribution.py tests/test_timeline.py tests/test_cli_analyze.py -q

## 3단계: 질의
Task 11~14 — `query/engine.py`(결정적 search/on_date/who_did/secrets/timeline → Event+source 인용) → `query/llm.py`(intent 라우팅+요약, LLM 없으면 digest fallback) → CLI `query` → A/B 재구성 e2e.
증거 주장은 결정적 엔진(안 흔들림), 요약만 LLM. 요약 채점 = 인용 source 실재 + 근거 집합 일치.

acceptance: pytest tests/test_query_engine.py tests/test_query_llm.py tests/test_cli_query.py tests/test_e2e_ab.py -q

## 4단계: 웹 대시보드 (뷰 레이어)
상세 플랜: `docs/superpowers/plans/2026-06-17-clfx-dashboard.md` (Task 1~6, 실코드 포함). 설계: `docs/superpowers/specs/2026-06-17-clfx-dashboard-design.md`.
Task 1~6 — `web/api.py`(events_payload/query_payload 순수함수, op 디스패치 단일화) → `cmd_query`를 query_payload 위임으로 리팩토링(DRY) → `web/server.py`(stdlib http.server, GET 전용, 127.0.0.1) → `web/static/`(index.html/app.css/app.js, actor 색구분·필터·질의·secret 하이라이트·source 역추적) → CLI `serve`.
원칙: 엔진(QueryEngine) 단일 진실원천 — 서버가 호출, JS 재구현 금지. 의존성 0(stdlib만). read-only 단일 analyzed.jsonl.

acceptance: pytest tests/test_web_api.py tests/test_web_server.py -q

## 5단계: 교수님 피드백확장 A (분석·시각화)
상세 플랜: `docs/superpowers/plans/2026-06-17-clfx-피드백확장-A-분석시각화.md` (Task 1~7). 설계: `docs/superpowers/specs/2026-06-17-clfx-피드백확장-design.md`.
Task 1~7 — `analyze/keywords.py`(키워드 빈도+수사사전+패턴) → `engine.activity(by)`(활동량 actor분리) → `engine.files()`(접근파일 actor분리) → `query/llm.py` OllamaLLM(gemma4:12b)+make_llm → `web/api.py`(activity/files/keywords payload+요약 LLM 연결) → `web/server.py`(/api/activity·files·keywords 라우트) → CLI query 요약 연결.
원칙: 엔진 결정적 집계 단일 진실원천, 모든 집계 actor 분리(④), UI(팀원 be9a39b) fetch만. secret 탐지·마스킹 유지(강조X). C단계(MCP)·B단계(복구·해시)·exe는 별도 plan.

acceptance: pytest tests/test_keywords.py tests/test_engine_aggregates.py tests/test_web_aggregates.py tests/test_llm_ollama.py tests/test_web_server.py -q

## 6단계: exe + 인앱 스캔 UX
상세 플랜: `docs/superpowers/plans/2026-06-17-clfx-exe-스캔UX.md` (Task 1~5). 설계 근거: 피드백확장-design §아키텍처(exe).
Task 1~5 — `discover.py`(소스 자동탐지 Windows+WSL) → `web/api.py` `scan_to_engine`/`sources_payload`(인메모리 parse+analyze, `parse_roots` 공유) → `web/server.py` 상태화(엔진 교체)+`/api/sources`·`/api/scan`+빈모드 起動 → 스캔 UI(데이터 없으면 소스 체크박스→스캔→대시보드) → `packaging/launcher.py`+PyInstaller `--onefile`(_MEIPASS 정적경로).
원칙: 인자0 실행→브라우저 자동→소스 선택→대시보드. 스캔=기존 parse→analyze 재사용(I1~I3 보장). UI/launcher는 manual+serve 검증, 코어는 pytest.

acceptance: pytest tests/test_discover.py tests/test_web_scan.py tests/test_web_server.py -q

## 불변식 체크리스트 (plan 작성·구현 공통)

5단계 codex가 6건 BLOCK을 잡았는데 5건이 plan의 실코드 결함이었다(타입 혼재·비결정·마스크 누출·환경의존 테스트). 이미 배운 불변식을 새 코드에 안 옮긴 탓. **plan을 쓸 때와 각 Task 구현 시 아래 표를 self-check한다. 픽스처가 이걸 강제하면 codex 전에 acceptance가 먼저 잡는다.**

| # | 불변식 | 위반 시 증상 | 방어 |
|---|---|---|---|
| I1 | **ts를 만지면 무조건 `norm_ts`/`ts_key`** (raw `e.ts` 슬라이스·startswith·비교 금지) | history발 epoch-ms int ts에서 TypeError/AttributeError | 표시·버킷=`norm_ts(e.ts)`, 정렬·범위=`ts_key`. event.py 단일 출처. |
| I2 | **집계는 결정적 정렬** (set 순회 결과를 순서에 쓰지 말 것, 동점 tie-break 명시) | PYTHONHASHSEED마다 출력 순서 바뀜 → 증거 비재현 | `dict.fromkeys`로 dedup, 정렬키 `(-count, term)` 등 전순서. |
| I3 | **텍스트 소비자는 마스크 인식** (`‹secret›`·`‹pii›` 스팬 토큰화/검색 전 제거) | redaction 마커가 키워드·매칭으로 새서 secret 강조 | `re.sub(r"‹[^›]*›"," ",text)` 선처리. |
| I4 | **테스트는 환경무관 결정적** (ollama·네트워크·시계 등 외부의존 monkeypatch) | ollama 떠있는 머신서만 깨지는 테스트 | 외부 어댑터는 None/스텁 주입, 산출(인용·집계)만 단언. |
| I5 | **actor는 user/agent로 분리** (집계·시각화 전부, owner/ACL 신뢰 금지) | 에이전트 행위가 사용자로 오인(④ 왜곡) | by_actor 계열 유지. 귀속은 transcript↔아티팩트 JOIN(B단계). |

**픽스처 규약**: 공용 픽스처/conftest 빌더는 **ISO str·epoch-ms int ts를 섞어** 생성한다(I1 상시 검증). 새 집계/질의 Task는 이 mixed-ts 입력에 대한 회귀를 반드시 포함한다.
