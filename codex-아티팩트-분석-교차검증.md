# 교차검증 보고: `codex-아티팩트-상세분석.md`

검증자: panel0(Claude Opus 5) × panel1(Codex CLI 0.147.0) 상호 반박 2라운드
측정 시각: 2026-08-20 20:10~20:35 +09:00
측정 대상: `/home/best1pjh/.codex` (WSL), `C:\Users\best1\.codex` (Windows), 저장소 `clfx/`
표본: rollout **344 파일 / 138,785 라인 / JSON parse error 0** 전수 + SQLite read-only 사본

---

## 0. 총평

문서의 **SQLite 계층 분석(§6)·수집 원칙(§11·§14·§19·§20)·코드 고정지점(§8.2)은 실측과 일치**한다.
치명적 결함은 두 가지이며, 둘 다 **"이 도구를 문서대로 구현하면 대부분의 Codex 세션에서 0 이벤트가 나온다"** 는 결과로 이어진다.

| 심각도 | 결함 | 영향 |
|---|---|---|
| **BLOCK-1** | 스키마 **버전 분기**를 전혀 다루지 않음. 문서는 0.147.0 한 버전만 관측하고 그것을 "Codex 스키마"로 서술 | 로컬 344개 rollout 중 **323개(94%)가 구스키마**. 문서대로 짠 파서는 명령증거의 ~10%, 쓰기증거의 ~3%만 회수 |
| **BLOCK-2** | item 이름의 **계층 혼동** (§0.2·§9.1 매핑표) | camelCase 이름은 SQLite projection 것. raw JSONL에 그 이름으로 파싱하면 0건 |
| 주의 | 문서의 "로컬 실측" 환경(`C:\Users\irise\.codex`, 17 세션)이 **이 머신에 존재하지 않음** | 수치·인벤토리 전부 재측정 필요 |

---

## 1. BLOCK-1 — 스키마 버전 분기 (문서 전면 미반영)

로컬 rollout의 `session_meta.cli_version`은 **29개 버전**(0.63.0 ~ 0.147.0)에 걸쳐 있다.
행위 증거가 기록되는 위치가 버전마다 다르다.

| 증거 종류 | 0.63.0 ~ 0.146.0 (323파일, 94%) | 0.147.0 (21파일) |
|---|---|---|
| 사용자 발화 | `event_msg.user_message` (2,231) | `item_completed` → `item.type="UserMessage"` (83) |
| 에이전트 응답 | `event_msg.agent_message` (7,101) | `item.type="AgentMessage"` (423) |
| 명령 실행 | `function_call name=exec_command|shell_command|run`(12,445), `custom_tool_call name=exec`(6,393), `event_msg.exec_command_end`(1,254, 0.118~0.125만) → **20,092** | `item.type="CommandExecution"`(2,281) + `custom_tool_call name=exec`(2,011, **동일 실행의 중복 뷰**) |
| 파일 쓰기 | `custom_tool_call name=apply_patch`(1,797), `event_msg.patch_apply_end`(1,702) → **3,499** | `item.type="FileChange"`(66) |
| MCP 호출 | `event_msg.mcp_tool_call_end` (85) | **0건** — 0.147.0에서 MCP 호출 기록 위치 미확인 |
| envelope `ordinal` | **없음** (323파일 전부) | **있음** (17,998라인 전부) |

정량 영향 — 문서 §9.1 매핑표(0.147 item 계층)만 구현했을 때 회수율.
분모 정의: **raw record 합산, 중복 실행 dedup 전**. panel0·codex 독립 재집계 일치.
- 명령 증거 `2,281 / (20,092 + 2,281) = **10.2%**`
- 쓰기 증거 `66 / (3,499 + 66) = **1.85%**`

(초안의 9.9%/3.4%는 codex R3-1이 REFUTE. `custom_tool_call exec`를 legacy에 몰아넣었고 쓰기 분모에서 `patch_apply_end`를 빠뜨린 오류 — 재집계로 정정.)

**정정 요구**: 파서는 `session_meta.cli_version`으로 era를 판정하고 **legacy(≤0.146) / item(0.147+) 두 경로**를 모두 구현해야 한다. `ordinal`은 optional — 없으면 line number를 provenance로 쓴다.

**중복 뷰 주의**: 0.147.0은 같은 실행이 `custom_tool_call name=exec`(2,011)와 `item.CommandExecution`(2,281) 양쪽에 남는다. 정규화 시 dedup 하지 않으면 명령 건수가 부풀려진다.

---

## 2. BLOCK-2 — item 이름 계층 (3개 계층, 이름 규칙 전부 다름)

| 계층 | 경로 | 이름 규칙 | 실측 값 |
|---|---|---|---|
| raw · response_item | `payload.type` | snake_case | `reasoning`(20,857) `function_call`(15,848) `function_call_output`(15,847) `message`(11,305) `custom_tool_call`(10,186) `custom_tool_call_output`(10,185) `web_search_call`(256) `agent_message`(182) `tool_search_call/output`(8/8) `ghost_snapshot`(2) |
| raw · event_msg item | `payload.item.type` (`item_completed`일 때) | **PascalCase** | `Reasoning`(3,176) `CommandExecution`(2,252) `AgentMessage`(423) `Extension`(162) `UserMessage`(83) `SubAgentActivity`(78) `FileChange`(64) `CollabAgentToolCall`(22) `ContextCompaction`(18) `ImageView`(16) |
| SQLite projection | `thread_items.item_type` | **camelCase** | `reasoning` `commandExecution` `agentMessage` `webSearch` `userMessage` `subAgentActivity` `fileChange` `collabAgentToolCall` `imageView` `contextCompaction` |

문서 §5(rollout)·§6(SQLite)·§7.1("projection에는"이라 명시)은 계층을 지켰다. **틀린 곳은 §0.2 표와 §9.1 매핑표** — 계층 표기 없이 camelCase 이름을 "Codex 원본"으로 제시한다.

### 같은 이름, 다른 구조 — 파서 공유 금지

| 필드 | raw rollout | SQLite thread_items |
|---|---|---|
| `FileChange.changes` | **경로-키 객체(map)**. value keyset 2종: `{type,content}` 22건(add) / `{type,move_path,unified_diff}` 46건(update·move) | **배열** 68 entry. keyset `{path,kind,diff}`, `kind`는 `{type}` 22 / `{type,move_path}` 46 |
| `CommandExecution.command` | **argv 배열** `["/bin/bash","-lc","…"]` (2,274/2,274건 list) | **문자열** (2,103/2,103건 str) + `aggregatedOutput`·`exitCode`·`durationMs`·`processId`·`scriptPath`·`pluginId`·`commandActions` |
| `cwd` | percent-encoded **`file://` URL** (2,274/2,274건, 디코딩 필요) | **절대경로 문자열** (2,103/2,103건) |
| `UserMessage.content` | `local_image` 12 / `text` 84 (+ `text_elements[].byte_range` 플레이스홀더) | `localImage` 12 / `text` 83 — 이름·건수 모두 다름 |
| `webSearch` | 존재하지 않음 → `Extension` + `kind:"web.search"` (+ `event_msg.web_search_end`) | `webSearch` 로 존재 |

→ 문서 §9.1의 `changes[].path`, `localImage`, `webSearch`는 **SQLite 계층에만** 맞는 표기다.
→ 두 계층의 **원형 파서는 공유 불가**하되, `path/kind/diff|content` 정규화 계층은 공유 가능하다(codex R2-3 정정).

---

## 3. 환경 불일치 — 문서의 "실측"이 이 머신 것이 아님

- 문서 §1.1: `C:\Users\irise\.codex`. **이 머신에 `irise` 사용자 없음**. `/mnt/c/Users` 전수 = `best1`, `Default`, `Public`, `CodexSandboxOffline`, `All Users`(→ProgramData 링크), `Default User`(→Default 링크), `desktop.ini` — 이 중 실사용자 후보는 `best1` 하나.
- 실제 CODEX_HOME은 **둘**:
  - WSL `/home/best1pjh/.codex` — rollout **344개**, `state_5.threads` **341**, `thread_history_1.thread_items` **5,820**(distinct thread **21**)
  - Windows `C:\Users\best1\.codex` — `thread_history_1.sqlite` **없음**, 대신 `sqlite/codex-dev.db`·`sqlite/codex-history-snapshots-dev.db`
- 문서 수치(17 세션 / 137MB / `.tmp` 5,961 files)는 전부 재측정 대상. 현재값: WSL `.tmp` 5,485 files·71.7MB(30일초과 2), Windows `.tmp` 6,137 files·136.8MB(30일초과 751).
- `session_index.jsonl`: WSL 1줄 / Windows 1,020 bytes — **authoritative 아님**이라는 문서 §3.3 주장은 유지.

### 문서가 놓친 증거원
- 경로: 실제 `sessions/YYYY/MM/**DD**/rollout-*.jsonl` (문서는 2단, 실제 **3단**)
- envelope type `inter_agent_communication_metadata`(182), `world_state`(244), `compacted`(201)
- `event_msg`: `patch_apply_end` `exec_command_end` `mcp_tool_call_end` `sub_agent_activity` `thread_rolled_back` `error` `agent_reasoning` `thread_goal_updated`
- Windows측 디렉터리: `attachments/` `dictation-history/` `transcription-history.jsonl` `browser/` `computer-use/` `ambient-suggestions/` `process_manager/` `packages/` `vendor_imports/` `visualizations/` `.codex-global-state.json(.bak)` `cap_sid` `chrome-native-hosts*.json` `sandbox.YYYY-MM-DD.log`
- WSL측: `shell_snapshots/` `thread-writer-locks/` `rules/` `skills/` `installation_id` `models_cache.json`
- 코드: `clfx/wsl_helper.py:19,25` 도 `ClaudeSource` 하드코딩 (§8.2 목록에 없음 — Phase 2a O11 위임 경로)

---

## 4. 확인 결과 문서가 옳았던 부분

| 문서 위치 | 판정 | 근거 |
|---|---|---|
| §5.1 envelope `{timestamp,type,payload}` | OK (+`ordinal`은 0.147.0 한정) | 344파일 전수 |
| §5.4 event_msg 대표 type / §5.5 response_item type 목록 | OK(부분집합) | 전수 분포로 확장 필요 |
| §5.7 암호화 blob | OK (비율 재현) | 전수: `encrypted_content` 21,507회 / **305파일**, `gAAAAA` 23,718회 / **305파일** (344 중 88.7%). 문서의 15/17≈88%와 비율 일치 |
| §6.1~6.3 SQLite 테이블·컬럼·item 키 구조 | OK 전부 일치 | `sqlite_master` + `table_info` 대조. `commandExecution` 13키 정확 |
| §6 WAL 동시확보 원칙 / §11.2 read-only | OK | 6개 DB 전부 `journal_mode=wal`, `integrity_check=ok` |
| §6.8·§20.4 projection ≠ 전체 history | OK, 문서보다 강함 | threads 341 vs projection thread 21 (문서는 17 vs 6) |
| §3.2 rollout 파일명 정규식 | OK | 344/344 매치, 실패 0 |
| §2 CODEX_HOME/CODEX_SQLITE_HOME/`sqlite_home` 우선순위 | OK | `codex doctor --json` 으로 override 3종 실증 |
| §8.2 Claude 고정지점 | OK 전부 실존 | `cli.py:7,63,82-93`, `web/api.py:15,237`, `discover.py:70`, `artifacts.py:21,230`, `mcp.py`, `web/static/*`, `event.py` |
| §12 config.toml `mcp_servers` | OK | Windows config에 `[mcp_servers.node_repl]`, WSL config에 `[hooks]`·`[plugins]` |
| §7.2·§10.2 4계층 분리 원칙(명령의도/결과/transcript/디스크/syscall) | OK | 유지 권고 |

## 5. 기타 정정
- DB 파일명 숫자 접미사(`_5`,`_1`,`_2`)는 **schema version 아님** — `_sqlx_migrations` max는 state_5=46, thread_history_1=4, logs_2=2. 하드코딩 금지, glob + `_sqlx_migrations` 확인.
- `thread_items.item_json`은 BLOB 아니라 **TEXT(JSON 문자열)**.
- `thread_turns`에 이미 `rollout_byte_offset`·`rollout_end_ordinal`·`rollout_end_byte_offset` 존재 → 문서 §9.3이 "새로 보존해야 한다"고 제안한 provenance는 **이미 Codex가 제공**한다(0.147 계열 한정).

---

## 6. 검증 절차 (재현용)

3라운드 상호반박. 각 라운드의 원본 산출물은 `.harness/`에 보존.

| 라운드 | 요청 | 산출 | 결과 |
|---|---|---|---|
| R1 | `.harness/codex-verify-request.md` (P0~P5) | `.harness/codex-verify-result.md` | OK 10 / WRONG 2 / PARTIAL 8 / UNVERIFIABLE 1 |
| R2 | `.harness/panel0-crosscheck-round2.md` (panel0이 codex 보고에 3건 반박) | `.harness/codex-verify-result-r2.md` | R2-1 CONFIRM · R2-2 CONFIRM · R2-3 PARTIAL |
| R3 | `.harness/panel0-crosscheck-round3.md` (버전분기 전수 + 보고서 사실검토) | `.harness/codex-verify-result-r3.md` | (a)(b) CONFIRM · (c) **REFUTE** + 보고서 오류 6건 지적 |

panel0 독립 선기록(편향 방지): `.harness/panel0-independent-findings.md` — codex 보고 수신 **전**에 작성.

교차검증에서 **panel0이 틀렸던 항목**: 회수율 산식(분모 오류), `custom_tool_call exec`의 버전 귀속,
raw/SQLite `command`·`cwd` 구조를 "동일 계열"로 서술, 암호화 marker 수치의 범위 미표기, `/mnt/c/Users` 목록 비전수.
전부 codex R3 지적으로 정정했다.

## 7. 문서 정정 액션 목록

| # | 대상 | 조치 |
|---|---|---|
| 1 | §1.1 | 관측 환경을 실제 측정 머신으로 교체. 단일 CODEX_HOME 전제 삭제(WSL/Windows 2곳) |
| 2 | §3.1·§3.2·§6.2·§7.4 | 모든 수치에 snapshot 시각 명시 + 현재값으로 재측정. `sessions/YYYY/MM/DD` 3단으로 수정 |
| 3 | **§5 신설** | `cli_version` era 분기 절(legacy ≤0.146 / item 0.147+) 추가 — 최우선 |
| 4 | §5.1 | `ordinal`은 0.147.0+ 한정 optional로 표기 |
| 5 | §0.2·§9.1 | 매핑표를 **계층 3열**(response_item / event_msg.item / SQLite item_type)로 재작성 |
| 6 | §9.1 | `changes[].path`·`localImage`·`webSearch`는 SQLite 계층 표기임을 명시. raw는 map·`local_image`·`Extension(kind=web.search)` |
| 7 | §9.3 | `thread_turns.rollout_byte_offset`·`rollout_end_ordinal` 이미 존재 — "신규 보존" → "기존 필드 활용"으로 |
| 8 | §3.1 | DB 파일명 숫자 접미사 = schema version 아님. glob + `_sqlx_migrations` 확인으로 |
| 9 | §8.2 | `clfx/wsl_helper.py:19,25` 추가 |
| 10 | §16 | 단계 B에 era 분기·dedup·중복뷰 처리 추가, 단계 C에 projection 커버리지 경고(threads 341 vs 21) |
