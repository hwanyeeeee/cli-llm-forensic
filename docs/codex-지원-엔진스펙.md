# Codex 지원 엔진 스펙 (확정 사실 + 합의된 설계)

근거: panel0(Opus 5) × panel1(Codex gpt-5.6-sol xhigh) 상호반박 **R1~R4**.
원본 산출물 `.harness/codex-verify-*.md`, 문서 검증 결과 `codex-아티팩트-분석-교차검증.md`.
측정: 2026-08-20, WSL `~/.codex` rollout **344파일 / 138,785라인 / JSON error 0** 전수 + SQLite read-only 사본.

**이 문서는 확정 사실과 합의 결정만 담는다. 추측은 § 9(미해결)에만 둔다.**

---

## 1. 취득 대상 (discovery)

우선순위: `CODEX_HOME` env → config `sqlite_home` → `CODEX_SQLITE_HOME` → 기본 `~/.codex`.
**SQLite root가 CODEX_HOME과 분리될 수 있다** (실증: `codex doctor --json` 으로 3종 override 확인).

| 대상 | 역할 | 증거 등급 |
|---|---|---|
| `sessions/YYYY/MM/DD/rollout-*.jsonl` | **1차 증거. authoritative** | 필수 |
| `state_5.sqlite` `threads` (`rollout_path`) | thread 카탈로그 | 필수(교차) |
| `thread_history_1.sqlite` `thread_turns`/`thread_items` | item projection + byte offset | 보조(불완전) |
| `goals_1.sqlite` | 목표·상태·budget 직접 증거 | **있음** |
| `logs_2.sqlite` | runtime 상관·오류 진단 | 보조(스키마 불안정) |
| `memories_1.sqlite` | 파생 요약 | 보조 |
| `queue_1.sqlite` | 현재 0 rows | 없음(live 시 잠재) |
| `history.jsonl` `session_index.jsonl` | 보조 인덱스 | **비권위**(중복·누락) |
| `config.toml`(+`.bak`) | MCP·hooks·plugins·sandbox | 설정 증거 |
| `tmp/` `.tmp/` `shell_snapshots/` `thread-writer-locks/` | 실행 부산물 | 보조 |
| Windows 전용: `attachments/` `dictation-history/` `browser/` `computer-use/` `.codex-global-state.json` `sqlite/*.db` | 입력·부가 흔적 | 보조 |

**주의**: DB 파일명 숫자 접미사(`_5` `_1` `_2`)는 schema version이 **아니다**
(`_sqlx_migrations` max = state_5:46, thread_history_1:4, logs_2:2). glob + `_sqlx_migrations`로 판별.
SQLite는 main/**WAL**/SHM 동시 확보 후 read-only 사본으로만 연다 (6개 DB 전부 `journal_mode=wal`).

**커버리지 경고**: `state_5.threads` 341 vs `thread_items` distinct thread **21**. projection만으로 사건 확정 금지.

---

## 2. 스키마 era 분기 (최우선 구현 사항)

로컬 표본에 **cli_version 29종**(0.63.0~0.147.0). 행위 증거 위치가 era마다 다르다.

| 증거 | legacy ≤0.146.0 (323파일, 94%) | item era 0.147.0 (21파일) |
|---|---|---|
| 사용자 발화 | `event_msg.user_message` 2,231 | `item.UserMessage` 85 |
| 에이전트 응답 | `event_msg.agent_message` 7,101 | `item.AgentMessage` 423 |
| 명령 실행 | `function_call name=exec_command\|shell_command\|run` 12,445 + `custom_tool_call name=exec` 6,393 + `event_msg.exec_command_end` 1,254 = **20,092** | `item.CommandExecution` 2,281 (+ code-mode `custom_tool_call exec` 2,011) |
| 파일 쓰기 | `custom_tool_call name=apply_patch` 1,797 + `event_msg.patch_apply_end` 1,702 = **3,499** | `item.FileChange` 66 |
| MCP | `event_msg.mcp_tool_call_end` 85 | **0건 — 위치 미확인(§9)** |
| envelope `ordinal` | 없음 | 전 라인 존재 (단, 1파일에서 중복 2건 → 단독키 불가) |

**item era만 구현 시 회수율: 명령 10.2%, 쓰기 1.85%** (raw record 합산, dedup 전).

### era 판정 = **structural sniffing 우선** (R6-3 확정)

`cli_version` 하드코딩 switch **금지**. 0.148+에서 또 바뀌면 같은 사고가 반복된다.

1. record별 capability 탐지: `item_completed`+`item.type` / legacy `user_message`·`agent_message` / response·custom call / `ordinal` 유무
2. 한 파일에 여러 view가 공존할 수 있으므로 **발견된 파서를 전부 실행**하고 `id`/`call_id`로 병합
3. `cli_version`은 capability matrix와 대조해 **불일치 warning**만 생성 — record를 버리는 gate가 아니다
4. unknown envelope/item/kind는 raw provenance·count·keyset을 보존하고 `unsupported_schema`로 **표면화**(조용한 0건 금지)
5. 0.148 fixture 확보 시 capability golden test에 추가. "0.148 지원" 표기는 fixture 통과 후에만

### 이름 계층 3단 (계층마다 규칙 다름 — 파서 공유 금지)

| 계층 | 경로 | 규칙 | 예 |
|---|---|---|---|
| raw response_item | `payload.type` | snake_case | `function_call` `custom_tool_call` `message` `reasoning` `web_search_call` |
| raw item | `event_msg.payload.item.type` | **PascalCase** | `CommandExecution` `FileChange` `UserMessage` `Extension` `ImageView` `SubAgentActivity` |
| SQLite | `thread_items.item_type` | **camelCase** | `commandExecution` `fileChange` `userMessage` `webSearch` |

동일 이름 다른 구조:

| 필드 | raw | SQLite |
|---|---|---|
| `FileChange.changes` | path-키 **map**. value `{type,content}` 22 / `{type,move_path,unified_diff}` 46 | **배열** `{path,kind,diff}` 68 entry |
| `command` | argv **배열** (2,274/2,274) | **문자열** (2,103/2,103) |
| `cwd` | percent-encoded `file://` URL | 절대경로 |
| 이미지 | `local_image` 12 / `text` 84 | `localImage` 12 / `text` 83 |

→ **원형 파서는 계층별 분리, 정규화 계층은 공유.**

---

## 3. 행위자(actor) 판별 — 확정 규칙

### 3-1. actor 도메인 = `user | agent | unknown` (subagent·system 아님)

subagent는 행위자 종류가 아니라 **agent 인스턴스 계층** → `actor=agent` + typed meta.
`system`(turn_context/world_state/token_count)은 **Event를 만들지 않으므로** actor가 필요 없다 — turn-context side store로 보존.

**선결 과제 — 조용한 user 폴백 제거**: 현재 3곳이 `actor not in ("user","agent") → "user"` 로 흡수한다.
포렌식에서 최악의 실패 유형(파서 버그가 user 행위로 둔갑).

| 위치 | 현재 |
|---|---|
| `clfx/query/engine.py:87` | activity 집계 폴백 |
| `clfx/query/engine.py:110` | files `by_actor` 폴백 |
| `clfx/analyze/keywords.py:88` | keyword `by_actor` 폴백 |

확정안: 공용 `actor_bucket()`로 검증 일원화. `{user, agent, unknown}` 3버킷 반환, 도메인 밖 문자열은 unknown + **warning count**.
UI는 unknown을 중립색 경고 카드/필터로 노출하고 **user·agent 어느 쪽에도 합산하지 않는다**.
영향 범위: `query/engine.py`, `analyze/keywords.py`, `web/api.py`, `web/static/{index.html,app.js,app.css}`,
`tests/test_engine_aggregates.py`, `tests/test_keywords.py` (exact `by_actor={user,agent}` 단언).

### 3-2. actor=user 확정 근거 (이것만)

- legacy `event_msg.user_message`, item era `item.UserMessage`
- 그 안의 이미지(`local_image` / legacy `local_images` 35·`images` 1) → `action=paste`

**actor=user 금지 목록** (이름에 user가 들어가도 사람 입력 아님):
- `response_item.message role=user` 2,968 / `role=developer` 815 — 모델 입력 뷰. **별도 Event 생성 시 과계수**
- `session_meta.instructions|base_instructions` 349, `turn_context.user_instructions` 786 — 자동 주입
- `history.jsonl` 2,266 — 보조 인덱스, 중복 가능

### 3-3. command origin

`CommandExecution.source` 값 도메인 (raw 0.147): `unified_exec_startup` 2,293 / `user_shell` 1.
SQLite: `unifiedExecStartup` 2,124 / `userShell` 1. `pluginId`·`scriptPath`는 **2,125/2,125 전부 empty**.

- `userShell` → actor=user (직접 근거)
- model tool call과 연결됨 → actor=agent
- 연결 실패 → **unknown** (user로 폴백 금지)
- `unifiedExecStartup`은 실행 transport일 뿐 **LLM 자율성 증명 아님**

### 3-4. 승인(approval) — 개별 승인 판정 불가

`turn_context.approval_policy`: `on-request` 1,424 / `never` 1,922.
`sandbox_policy`는 **문자열 아니라 `{type:...}` 객체**: `workspace-write` 1,428 / `read-only` 88 / `danger-full-access` 1,830.
`approvals_reviewer=user` 597.

개별 승인 record는 전수 검색 결과 **0건**. → policy snapshot만 attach. `approved_by_user=true` **기록 금지**.

### 3-5. subagent 계층 (Codex 고유, Claude에 없음)

`session_meta.source.subagent.thread_spawn` 18 (depth 18/18=1, parent 18/18, agent_path 17/18, nickname 18/18),
`thread_source`: user 169 / subagent 18 / absent 162, `SubAgentActivity` 78 (started 14/interacted 62/interrupted 2),
`CollabAgentToolCall` 22, `state_5.thread_spawn_edges` 18 rows(parent 5 / child 18).

→ **actor=agent 유지 + `meta.agent_kind=subagent`, `parent_thread_id`, `depth`, `agent_path`, `agent_nickname`.**
계층을 버리면 "누가 어느 작업을 위임받았는지"를 잃는다 = 포렌식 손실.

### 3-6. 디스크 산물 작성 주체 — confidence 등급

`FileChange` 66 items / 70 paths / 18 turns.
보수적 shell redirection 탐지 `CommandExecution` 51건 중 **21건이 same-turn FileChange 없음**(16건은 exit 0).
넓은 heuristic write-like 227건 대 FileChange 66, same-turn path 매칭 **0**.
→ **shell로 만든 파일은 FileChange에 안 잡힌다**(구조적 비포착의 하한).

| 등급 | 조건 |
|---|---|
| `high` | completed FileChange(path/kind/diff) + 같은 turn/thread + 잔존 파일 stat/hash 상관 |
| `medium` | completed command(exit 0) + 명시 write target + cwd·turn·mtime 상관, FileChange 없음 |
| `low` | command/output에 path marker만, 또는 시간·basename만 상관 |
| `unknown` | 디스크 파일만 존재 / cache·tmp 소속만 확인 / 외부 프로세스 배제 불가 |

### 3-7. 사용자 제공 파일

구조화 user image path 48 refs / 47 unique — **현존 1개뿐**.
Windows `attachments/` 2 files, clipboard PNG 5 files — raw reference basename과 **교집합 0**.
→ session/item 참조가 있을 때만 user/paste 확정. 디스크 잔존물만 있으면 actor=unknown input-cache.
`ImageView` 16 = actor=agent / action=read / `meta.media=image`.

---

## 4. Event 스키마 확정안

```
Event(ts, agent, session, actor, action, target, preview, source, tags, meta?)

actor  = user | agent | unknown            ← subagent·system 없음 (§3-1)
action = prompt | read | bash | write | paste | response | mcp | search | spawn
                                             ← search·spawn 신규 2개
meta   = optional dict. 비어 있으면 to_dict()에서 생략 → 기존 JSON byte shape 보존
```

| 결정 | 내용 | 근거 |
|---|---|---|
| D1 | actor = user·agent·unknown. subagent는 meta, system은 Event 아님 | engine.py·keywords.py 폴백이 미지 actor를 user로 흡수 → 공용 `actor_bucket()`로 교체 |
| D2 | `search`·`spawn` 추가. ImageView는 `read`+meta | search는 MCP와 다름, spawn은 인과 |
| D3 | **`meta` optional dict 도입** (tags-only 반대) | ordinal·exitCode·duration·processId·depth는 typed scalar. tags는 escaping·범위질의·정렬 불가. 비용 실측: `Event(` callsite 68개지만 optional 마지막 필드면 수정 0, exact 9-key 단언은 `tests/test_event.py:22` 1개뿐 |
| D4 | provenance = `source.file` + `source.line` + raw byte offset/hash. 0.147은 `meta.ordinal` 추가 | ordinal 1파일에서 중복 2건 → 단독키 불가 |
| D5 | code-mode `custom_tool_call exec`를 **drop하지 않음** | 0.147 표본: ctc 312 vs CommandExecution 292, id 교집합 0. input이 `await tools.exec_command({...})` JS. **1 JS call → N shell exec** 구조. shell Event는 CommandExecution에서 생성, ctc는 parent/orchestration record로 연결 |
| D6 | legacy는 `call_id`로 call+output(+`exec_command_end`) **1 Event 병합** | function_call 12,445 중 output match 12,444, missing 1(status=unknown으로 보존). exec_command_end 1,254 전부 call_id 일치 |

---

## 5. Claude 대비 3분류

**(a) 그대로 재사용**: Event 기반 timeline·search·query, secret/PII scan·mask, keyword, read-only hash/stat inventory, `source(file:line)` 인용, 파일/활동 UI.

**(b) 새로 만들어야 함**: Codex home·SQLite discovery, cli_version era parser, raw 3계층 adapter, WAL-safe SQLite reader, call/output pairing, typed meta provenance, turn policy(approval/sandbox), subagent graph, web search·image 매핑, opaque 처리, Codex temp classifier.

**(c) 원리적으로 불가능**: syscall 수준 read/write 완전성, 개별 user 승인 확정, shell 산물의 유일 작성자 확정(OS telemetry 없이), encrypted reasoning 복호화, 삭제된 temp 복원, 동일 protocol role로 주입된 human/hook 텍스트 분리.

### Codex가 Claude보다 우세한 축
명령 실행(cwd·exitCode·durationMs·processId 전건), turn 경계·상태, approval/sandbox policy, subagent 계층, 웹검색, byte-offset provenance.

### Codex가 열세인 축
**파일 read 증거**(전용 read item 없음 — `commandActions` read 19건뿐), MCP(0.147 위치 미확인), reasoning 평문성(`encrypted_content` 305/344 파일), temp 산물의 actor 귀속.

---

## 6. 암호화·opaque

`encrypted_content` 21,507회 / **305파일**, `gAAAAA` 23,718회 / 305파일 (344 중 88.7%).
→ 존재·길이·위치·session/turn 연결만 보존. 복호화 시도 안 함. blob 원문은 UI·LLM 질의·보고서에 넣지 않음.

## 7. temp 보존기간 — 상수 금지

20:43 snapshot: `tmp` 3 files(0.02~3.84d), `.tmp` 5,485 files(median 8.29d / max 134.27d / 30일초과 2),
`shell_snapshots` 2 files, `thread-writer-locks` 6 files.
삭제 event·정책 설정 **관측 안 됨**. → Claude의 `RETENTION_DAYS=30` 재사용 근거 없음.
`observed_age_days/min/max/count`만 보고, policy는 `unknown`.

## 8. 우리 코드 수정 지점

`clfx/cli.py:7,63,82-93` · `clfx/web/api.py:15,237` · `clfx/discover.py:70` ·
`clfx/analyze/artifacts.py:21,230` · `clfx/analyze/mcp.py` · `clfx/web/static/*` · `clfx/event.py` ·
**`clfx/wsl_helper.py:19,25`**(O11 위임 경로 — 기존 문서 §8.2 누락분).

## 9. 미해결 (구현 전 판단 필요)

1. `on-request` turn에서 개별 command의 실제 승인 여부 — 명시 event 없음 → unknown 고정.
2. hook/plugin이 user/developer message로 주입한 텍스트와 사람 입력의 구조적 분리 필드 — 관측 안 됨.
3. shell write target의 완전한 path 추출 — shell parser + OS telemetry 없이는 heuristic 한계.
4. attachment/clipboard 잔존물의 session 귀속 — raw reference와 교집합 0.
5. **0.147의 MCP 기록 위치** — R6-2 판정 **UNVERIFIABLE**. 안정판 0.147 21파일/18,483라인 전수에서
   `Extension.kind`=`web.search` 162건뿐, `custom_tool_call.name`=`exec` 2,042건뿐,
   `function_call.name`은 agent 협업 7종뿐, MCP marker 0, `config.toml mcp_servers` 0, `thread_dynamic_tools` 0.
   → **0.147 표본에 MCP 사용 자체가 없음**. "이름이 바뀌었다"는 근거도 없음.
   닫으려면 MCP server를 실제 구성한 0.147/0.148 fresh session에서 known MCP call 1회 실행한 **fixture 필요**.
   **`web.search`를 MCP로 합치지 않는다.**
6. **0.148+ 스키마 유지 여부** — 표본 없음. §2 structural sniffing으로 대응하되 fixture 없이 "지원" 표기 금지.
