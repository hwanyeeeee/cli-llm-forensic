---
target: cli
build: pip install -e ".[dev]"
test: python3 -m pytest tests/ -q
run: python3 scripts/bench.py tests/fixtures/dot-claude --repeat 1
---

# 플랜 — 성능개선 Phase 1 (계측 하네스)

- 상세 플랜: `docs/superpowers/plans/2026-07-02-clfx-성능개선-P1-계측.md` (Task 1~6 TDD, 실코드 포함)
- 스펙: `docs/superpowers/specs/2026-07-02-clfx-성능개선-design.md` (§1 계측, 불변식 §0 I1~I6)
- **절대 원칙**: 무손실(분석 출력 byte-동일)·완전성(skip/cap 0)·read-only·I6(timings는 별도 필드/stderr만 — 증거 페이로드 미오염, 등가성 비교 제외)

## 1단계: 스캔 타이밍 (플랜 Task 1~2)
forensic_scan `timings`(walk_tmp/resolve/hash/attribution/retention, 서버 pop → /api/artifacts 미노출) + scan_to_engine `engine.parse_timings`(parse_wall/enrich) + `/api/scan/progress` timings 합류(mcp_s 포함) + 스캔 완료 stderr `[clfx.timing] scan {...}`.

acceptance: python3 -m pytest tests/test_timings.py tests/test_web_scan.py tests/test_web_server.py -q

## 2단계: 서버 요청 로그 + LLM 질의 timings (플랜 Task 3~4)
do_GET/do_POST `_timed` 래핑(stderr `[clfx.timing] GET /path Nms MB`) + query_payload `timings`(intent/search/llm/total ms, llm_network_ms) + OllamaLLM.last_timing.

acceptance: python3 -m pytest tests/test_timings.py tests/test_web_api.py tests/test_query_llm.py tests/test_llm_ollama.py -q

## 3단계: 프런트 marks + bench/baseline (플랜 Task 5~6)
app.js performance.mark(clfx-boot-start/stage1/stage2)+FETCH_TIMINGS+perfReport + scripts/bench.py(단계별 median 표) + docs/perf-baseline.md 템플릿 + INDEX.md 색인.

acceptance: python3 -m pytest tests/test_web_perf_js.py tests/test_web_app_js.py tests/test_bench.py -q && python3 scripts/bench.py tests/fixtures/dot-claude --repeat 1 >/dev/null

## 완료 후 (panel0/사용자)
- 전체 회귀 `python3 -m pytest tests/ -q` green → final-verify → 커밋 검증.
- 실데이터 bench 양 환경(Windows exe 경로 / WSL 네이티브) 실행 → `docs/perf-baseline.md` 기입 → 병목 순위표 → Phase 2 플랜(케이스 파일+백로그).
