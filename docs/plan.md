---
target: cli
build: pip install -e ".[dev]"
test: python3 -m pytest tests/ -q
run: python3 -m clfx.cli parse ~/.codex --out /tmp/codex-events.jsonl
---

# 플랜 — Codex 아티팩트 지원 (다중 소스 엔진)

- 기준서: `docs/codex-지원-엔진스펙.md` (R1~R7 교차검증 확정 사실)
- 검증 근거: `codex-아티팩트-분석-교차검증.md` · 원본 `.harness/codex-verify-*.md`
- 패널 산출: `docs/패널-구성안.md` (마감 2026-08-23 23:00)
- **절대 원칙**: read-only · 무손실(unknown 구조도 provenance 보존, 조용한 0건 금지) · 결정성 · 기존 413 테스트 green 유지

## 1단계: actor 정합성 선결 (Codex 무관, 현재 코드 결함)

`actor not in ("user","agent") → "user"` 조용한 폴백 5곳 제거. 공용 `actor_bucket()` 도입 →
`{user, agent, unknown}` 3버킷 + 도메인 밖 값은 unknown + warning count. unknown은 user·agent 어느 쪽에도 합산 금지.

수정: `query/engine.py:87,110` · `analyze/keywords.py:88` · `query/llm.py:198,276` · `web/api.py:_stats_build`
테스트 갱신: `test_engine_aggregates.py` · `test_keywords.py` · `test_web_api.py:31-33`

acceptance: python3 -m pytest tests/test_engine_aggregates.py tests/test_keywords.py tests/test_web_api.py tests/test_query_llm.py -q

## 2단계: UI unknown 노출 (12지점)

`web/static/app.js` — 92 · 137 · 158-160 · 235-236 · 255-264 · 272-280 · 286-289 · 297 · 336-345 · 359 · 447-448 · 508 · 519-520.
unknown을 중립색 경고 카드/필터로 노출. timeline·heatmap·keyword·파일집계에서 숨김/agent흡수 제거.

acceptance: python3 -m pytest tests/test_web_app_js.py tests/test_web_api.py -q

## 3단계: CodexSource + discovery + source registry

`clfx/sources/codex.py` — CODEX_HOME → config `sqlite_home` → CODEX_SQLITE_HOME → `~/.codex` 순 해석,
`sessions/**/rollout-*.jsonl` 스트리밍(raw byte SHA-256, line 보존, 90MB급 대비 메모리 미적재).
`discover.py` 4계열 후보에 `.codex` 추가. `cli.py`·`web/api.py`·`wsl_helper.py`의 ClaudeSource 하드코딩 → registry.

acceptance: python3 -m pytest tests/test_codex_source.py tests/test_discover.py tests/test_cli.py -q

## 4단계: 파서 — structural sniffing + 2 era

capability 탐지(`item_completed` / legacy `user_message`·`agent_message` / response·custom call / `ordinal`) →
**발견된 파서 전부 실행 후 id·call_id 병합**. `cli_version`은 warning만, gate 아님.
legacy: `function_call(exec_command|shell_command|run)`+`function_call_output`(+`exec_command_end`) call_id 병합 ·
`custom_tool_call(exec|apply_patch)` · `patch_apply_end` · `mcp_tool_call_end` · `web_search_end`.
item era: `item_completed` → PascalCase 10종. 미지 구조는 `unsupported_schema`로 표면화.

acceptance: python3 -m pytest tests/test_codex_parser.py -q

## 5단계: actor·confidence 귀속 + Event.meta

actor=user는 `user_message`/`UserMessage`+내부 이미지만. `response_item.message role=user/developer`·
`user_instructions`·`base_instructions`·`history.jsonl`은 Event 생성 안 함(과계수 차단).
`CommandExecution.source=userShell`→user, model tool call 연결→agent, 연결실패→unknown.
subagent = actor=agent + `meta.agent_kind/parent_thread_id/depth/agent_path`.
파일작성 confidence 4등급. `approved_by_user` 기록 금지(policy snapshot만).
`Event.meta` optional dict — 비면 `to_dict()` 생략(기존 JSON byte shape 보존). `action`에 `search`·`spawn` 추가.

acceptance: python3 -m pytest tests/test_codex_actor.py tests/test_event.py -q

## 6단계: SQLite 보조 + attestation

main/WAL/SHM 동시 사본 → read-only. `state_5.threads`(rollout_path) 교차 + **커버리지 경고**(threads N vs projection M).
`thread_turns.rollout_byte_offset` provenance 활용. DB는 glob + `_sqlx_migrations`로 판별(숫자 접미사 ≠ version).
attestation 해시 대상에 rollout JSONL + DB main/WAL/SHM 포함.

acceptance: python3 -m pytest tests/test_codex_sqlite.py tests/test_attestation.py -q

## 7단계: Codex temp/config 분석 + UI 소스 필터

temp classifier — `tmp/` `.tmp/` `shell_snapshots/` `thread-writer-locks/` + Windows `attachments/`·clipboard.
**보존기간 상수 금지** — `observed_age_days/min/max/count`만, policy=unknown.
`config.toml` TOML 파서(`mcp_servers`·`hooks`·`plugins`). **`web.search`를 MCP로 합치지 않는다.**
UI: Claude 고정 문구 → agent/source 필터로 확장.

acceptance: python3 -m pytest tests/test_codex_artifacts.py tests/test_mcp.py tests/test_web_api.py -q

## 8단계: fixture + 회귀 + real-run

legacy era·item era fixture 각 1개(민감값 제거 합성). capability golden test.
전체 회귀 green + Codex 실 스캔 real-run.

acceptance: python3 -m pytest tests/ -q

## 9단계: exe 패키징 검증 (Codex 경로)

Phase 2a에서 만든 PyInstaller exe는 Codex 지원 이전 산출물(dist/AgenTrace.exe, 2026-07-03)이다.
`codex_sqlite`가 3곳 전부 **함수 내부 지연 import**(`cli.py:56` · `wsl_helper.py:48` · `web/api.py:325`)이고
`web/api.py`는 `except Exception`으로 감싸져 있어, 번들 누락 시 **경고 한 줄만 남기고 SQLite 지원이 조용히 사라진다**.

- exe 재빌드(`packaging\build-exe.bat`) 후 Codex 소스 스캔이 CLI 경로와 **동일 이벤트 수**를 내는지 등가 확인
- `codex_parser` · `codex_sqlite` 번들 포함 확인. 누락 시 `--hidden-import` 추가
- attestation에 rollout JSONL + DB main/-wal/-shm 해시가 exe 경로에서도 들어오는지
- `requires-python >=3.11` 변경이 빌드에 영향 없는지 (빌드 환경 Windows Python 3.12.10 · PyInstaller 6.21.0)

acceptance: python3 -m pytest tests/test_wsl_delegate.py tests/test_codex_sqlite.py -q
