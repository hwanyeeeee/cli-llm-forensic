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
