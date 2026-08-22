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

## 10단계: Codex 정확도 정량 측정

신청서 목표 ⑤. Claude는 측정본이 있고 **Codex는 없다**. `docs/정확도-검증-시나리오.md` 3시나리오를 Codex 기록 형식으로 확장.

- 주체 식별 100건 · 접근파일 판정 100건 · MCP 외부연동 호출 100건
- 합성 transcript(정답 라벨 보유) ↔ 도구 판정 1:1 비교. 실데이터 복사 금지
- legacy·item 두 era를 모두 포함해야 한다 — 한쪽만 재면 회수율 착시가 생긴다
- 산출: 시나리오별 정확도 수치 + 오분류 사례 분류(무엇을 왜 틀렸는가)

acceptance: python3 -m pytest tests/test_accuracy_codex.py -q

## 11단계: 유출 시나리오 재현 데이터셋 (A/B 두 결론)

패널 ④·발표 데모의 서사 근거. 신청서 §4 "책임 소재의 정확한 귀속", 기존 발표자료 「활용 시나리오 ③ 수사 결론」 대응.

같은 "민감파일이 외부로 나갔다"는 결과에서 **주체가 갈리는 두 사건**을 통제 데이터로 재현한다.

- **결론 A — 사용자 직접**: 사람이 민감파일을 열어 프롬프트에 붙여넣어 전송. 주체=사람, 시각·대상·원본위치 동반
- **결론 B — 에이전트 자율**: 사용자 직접 지시 없이 에이전트가 bypass(권한확인 생략) 모드에서 민감 폴더를 자율로 읽어 전송. 어느 폴더·세션에서 그 모드를 썼는지 기록 잔존

요건:
- Claude·Codex **양쪽 형식**으로 각각 생성 (도구 무관하게 같은 결론이 나오는지)
- 합성. 실데이터 복사·민감값 금지. 가짜 시크릿은 명백한 더미로(`AKIA...EXAMPLE` 등)
- 대시보드에 띄웠을 때 A/B가 색으로 갈리고 `file:line` 역추적이 되는 상태까지
- 산출: `tests/fixtures/leak-scenario/` + `docs/유출시나리오-재현.md`(사건 서술 + 도구가 낸 근거)

패널 F5 캡처를 이 데이터셋으로 대체하면 개인 프로젝트 경로 노출 없이 시연할 수 있다.

acceptance: python3 -m pytest tests/test_leak_scenario.py -q + 전체 회귀 green

## 13단계: origin_channel — 원격 지시와 로컬 실행을 한 타임라인에

근거: `/mnt/c/projects/llm모바일아티팩트/output/패널-인계-모바일원격제어.md` §4 (Android 실측 63건, Claude 2.1.238 · Codex 0.149.0)

폰에서 내린 지시와 로컬에서 일어난 실행을 **같은 타임라인 위에서 구분**하기 위한 최소 필드.
로컬 측 아티팩트만 다룬다 — 폰 단말 파싱은 이 저장소 범위 밖.

| 필드 | Claude | Codex |
|---|---|---|
| `meta.origin_channel` | 세션 JSONL `promptSource`: `queued`=remote / `typed`=local | `logs_2.sqlite` `client_name` 조인 (`codex_chatgpt_android_remote`=remote) |
| `meta.bridge_session_id` | `~/.claude/sessions/<pid>.json` | — |
| `meta.environment_id` · `meta.server_name` | — | `remote_control_enrollments` |

주의:
- Codex는 `turn/start` 의 `connection_id` 를 `client_name` 에 **조인**해야 한다. 최근 RPC 표본만 보면 `codex-tui` 의 `plugin/list` 노이즈에 묻힌다
- 판별 못 하면 `origin_channel="unknown"`. **local 로 폴백 금지** — 1단계에서 없앤 그 실패 유형이다
- Claude 세션 ID 접두사가 계층마다 다르다(`session_…` vs `cse_…`) — 문자열 동일성으로 잇지 마라

acceptance: python3 -m pytest tests/test_origin_channel.py -q + 전체 회귀 green

## 15단계: 패널 수치 고정 테스트

14단계에서 드러난 문제 — 패널에 실을 수치가 **코퍼스가 자라면서 조용히 낡는다.**
측정 사이에 `FileChange` 66→171, `CommandExecution` 2,281→2,789로 변했고
회수율 분모에 중복(call_id 교집합 1,277)이 섞여 쓰기 회수율이 4배 틀렸다.
A1은 인쇄되면 못 고친다.

- `tests/test_panel_numbers.py` — 패널·종합문서에 실린 수치를 코드·실데이터로 재계산해 단언
- 실데이터 의존 수치는 **드리프트를 허용하되 방향과 산식을 고정**한다
  (예: legacy 파일에 `item_completed` 0건은 불변, 회수율은 분모 중복제거 산식이 유지되는지)
- 합성 fixture 기반 수치(정확도 3×100건 등)는 정확히 고정
- 실데이터가 없는 환경에서는 skip 하되 **조용히 통과시키지 마라** — skip 사유를 출력

acceptance: python3 -m pytest tests/test_panel_numbers.py -q + 전체 회귀 green
