# Codex CLI 데이터 저장·행위 아티팩트 상세 분석

> 목적: 기존 CLI 에이전트 포렌식 도구가 Codex CLI의 저장 데이터, 파일 접근, 임시 경로 작업 흔적, SQLite 상태, 원본 보존 및 분석 기능까지 확장 가능한지 검토하고, 실제 로컬 관측 결과를 상세히 정리한다.

## 0. 결론 요약

### 0.1 현재 도구가 Codex의 파일 접근·temp 작업까지 분석하고 있는가?

현재 상태에서는 **분석하고 있지 않다**.

현재 도구에는 이미 다음과 같은 **일반적인 분석 엔진**이 구현되어 있다.

- 파일 접근 이벤트 목록화
- 사용자/에이전트 행위자 분리
- read/write/bash/paste/response/MCP 이벤트 검색
- 파일 경로 실제 존재 여부 및 stat 확인
- 참조 파일과 temp 파일의 SHA-256 동일성 비교
- temp 전수 인벤토리, mtime/atime/보존기간 계산
- 파일 작성 주체와 transcript의 JOIN
- 시크릿/PII 탐지 및 preview 마스킹
- 활동량·키워드·타임라인·자연어 질의
- MCP 설정과 transcript 사용 흔적 비교
- 취득 파일 해시 매니페스트와 read-only attestation

하지만 이 기능들은 현재 모두 Claude 전용 입력 계층에 연결되어 있다.

- 입력 클래스는 clfx.sources.claude.ClaudeSource 하나뿐이다.
- CLI parse/scan 경로가 ClaudeSource를 직접 생성한다.
- 자동탐지는 .claude 디렉터리만 찾는다.
- MCP 분석은 .claude.json과 .mcp.json 구조를 전제로 한다.
- temp 루트 계산 및 30일 보존기간 상수도 Claude 실측을 기준으로 한다.
- 웹 UI 문구와 소스 선택 화면도 ~/.claude와 WSL/Windows origin을 중심으로 구성되어 있다.

따라서 Codex의 원본을 현재 도구에 넣어도 Codex 이벤트가 생성되지 않으며, 파일 목록·temp 해시·주체귀속·MCP·attestation까지 연결되지 않는다.

### 0.2 Codex에 대해 실제로 확인된 파일 접근·작업 흔적은 무엇인가?

Codex는 Claude의 단순 transcript와 다른 형태로 다음 구조화 항목을 보유한다.

| Codex 항목 | 관측된 의미 | 파일 행위 분석 가능성 |
|---|---|---|
| commandExecution | 실행 명령, cwd, 결과, 종료코드, 상태, 프로세스 식별자, 실행시간 | 명령 기반 파일 읽기·쓰기·검색·프로그램 실행 재구성 가능 |
| fileChange | 변경 대상 path, add/update/delete 종류, diff, 상태 | 에이전트가 생성·수정·삭제한 파일과 변경 내용을 재구성 가능 |
| userMessage | 사용자 텍스트 및 localImage 입력 파트 | 사용자 prompt·이미지 첨부 연결 가능 |
| agentMessage | 에이전트의 최종/commentary 텍스트 | 에이전트 응답 및 행위 설명 연결 가능 |
| reasoning | 내부 reasoning의 content/summary 구조 | 일부 기록은 opaque/encrypted 형태로 보존되므로 평문화 보장 불가 |
| webSearch | 검색 action, query, 결과 구조 | 검색 행위·검색어·결과 연결 가능 |
| imageView | 이미지 경로와 이미지 열람 이벤트 | 이미지 파일 접근/열람 연결 가능 |

다만 commandExecution은 운영체제의 모든 파일 open syscall을 기록한 커널 감사로그가 아니다. 명령 문자열과 명령 실행 결과를 기록한 실행 증거다. 예를 들어 명령 내부에 파일 읽기 명령이 있어야 확인할 수 있으며, 프로세스가 내부적으로 수행한 모든 파일 접근까지 보장하지 않는다.

### 0.3 현재 도구의 모든 기능을 Codex 기반으로 업데이트할 수 있는가?

**가능하다.** 다만 ClaudeSource를 CodexSource로 단순 복사하는 수준은 부족하다.

필요한 핵심 작업은 다음과 같다.

1. CODEX_HOME과 CODEX_SQLITE_HOME을 찾는 Codex discovery 추가
2. sessions/**/*.jsonl 원본 reader 추가
3. Codex JSONL envelope와 response_item/event_msg 구조 파서 추가
4. thread_history_1.sqlite/state_5.sqlite를 보조 projection으로 읽는 SQLite reader 추가
5. commandExecution/fileChange/userMessage/agentMessage를 기존 Event 또는 확장 Event로 정규화
6. Codex 고유 temp·sandbox·clipboard 경로를 분류하는 artifact root 추가
7. Codex config.toml 기반 MCP 설정 분석 추가
8. raw JSONL와 SQLite main/WAL/SHM를 chain-of-custody 해시 대상에 포함
9. UI의 Claude 고정 문구와 WSL/Windows origin 필터를 agent/source 필터로 확장
10. Codex fixture·정확도 테스트·회귀 테스트 추가

기존 QueryEngine, timeline, activity, keyword, secret, search, LLM digest, 파일 집계 로직은 대부분 정규화된 Event를 입력으로 받으므로 재사용 가능하다.

---

## 1. 조사 대상·환경·방법

### 1.1 조사 대상

- 제품: Codex CLI
- 관측된 버전: codex-cli 0.147.0
- 운영체제: Windows
- 관측 사용자 상태 디렉터리: C:\Users\irise\.codex
- CODEX_HOME 환경변수: 현재 shell에서 미설정
- CODEX_SQLITE_HOME 환경변수: 현재 shell에서 미설정
- 기본 적용 경로: C:\Users\irise\.codex
- 측정 snapshot 시각: 2026-08-18 11:29:25 +09:00

CODEX_HOME과 SQLite 경로는 실행 환경·사용자 설정에 따라 달라질 수 있으므로 위 경로를 일반적인 고정 경로로 간주하면 안 된다.

### 1.2 조사 방법

다음 자료를 서로 대조했다.

1. 기존 프로젝트의 설계서·event schema·Claude temp 실측 문서
2. 현재 도구의 Python 소스·웹 API·정적 UI·테스트
3. 로컬 Codex_HOME의 sessions JSONL
4. Codex가 생성한 SQLite main/WAL/SHM 파일
5. Codex temp·sandbox·clipboard 경로의 파일 목록·크기·확장자·시간
6. Codex 공식 문서의 상태 저장 위치·환경변수·history persistence 설명

분석은 원본을 수정하지 않는 read-only 조회 중심으로 진행했다. 보고서에는 인증 파일의 값, raw prompt, workspace 전체 경로의 불필요한 세부값, encrypted blob 원문을 넣지 않았다.

### 1.3 공식 문서와 로컬 실측의 구분

- 공식 문서: Codex가 어떤 위치와 환경변수를 사용하는지 설명하는 근거
- 로컬 실측: 이 컴퓨터의 현재 파일 수·DB row 수·스키마·실제 temp 파일 상태
- 추론: 파일명·경로·시간·내용 형식을 바탕으로 한 귀속 의견

공식 문서는 내부 rollout JSONL·SQLite 테이블의 전체 schema를 공개하지 않는다. 그러므로 내부 field 의미는 로컬 관측과 구조적 상관관계로 설명하며, 제품 버전이 바뀌면 재검증해야 한다.

---

## 2. 공식 저장 위치 기준

OpenAI 공식 문서 기준으로 Codex의 로컬 상태 루트는 CODEX_HOME이며 기본값은 ~/.codex이다. 이 루트에는 config, auth, logs, sessions, skills 및 기타 사용자 상태가 들어갈 수 있다.

CODEX_SQLITE_HOME은 CLI/app-server의 SQLite 기반 상태 저장 위치를 별도로 지정한다. 기본값은 CODEX_HOME이며 sqlite_home 설정이 있으면 그 설정이 우선할 수 있다.

history persistence가 활성화된 경우 history.jsonl에 로컬 session transcript가 저장될 수 있다. history persistence를 none으로 설정하거나 max_bytes를 두면 보존 범위가 달라진다.

공식 문서:

- Codex CLI: https://developers.openai.com/codex/cli/
- Advanced configuration: https://learn.chatgpt.com/docs/config-file/config-advanced
- Environment variables: https://learn.chatgpt.com/docs/config-file/environment-variables

포렌식 수집기 구현 시 다음 우선순위를 사용해야 한다.

1. 실행 환경의 CODEX_HOME 확인
2. config의 SQLite 위치 override 확인
3. CODEX_SQLITE_HOME 확인
4. 기본값 ~/.codex 적용
5. 실제 존재하는 sessions, JSONL, SQLite, WAL, SHM를 확인

---

## 3. 로컬 Codex_HOME 전체 구조

### 3.1 주요 파일·디렉터리

| 경로/범주 | 로컬 관측 | 포렌식 의미 | 현재 도구 반영 |
|---|---:|---|---|
| sessions/YYYY/MM/rollout-*.jsonl | 17개, 합계 약 137,343,592 bytes | 가장 중요한 raw session/rollout 증거 | 미반영 |
| session_index.jsonl | 3 lines, 341 bytes | session 검색 보조 index. 중복·부분성 관측 | 미반영 |
| history.jsonl | 731 lines, 약 460KB | 사용자 history persistence 보조 증거 | 미반영 |
| state_5.sqlite | 245,760 bytes + WAL/SHM | thread catalog, rollout path, metadata | 미반영 |
| thread_history_1.sqlite | 약 20MB + WAL/SHM | turn/item projection, command/fileChange 등 | 미반영 |
| logs_2.sqlite | 약 37MB + 약 4.5MB WAL | Codex 내부 운영/diagnostic log | 미반영 |
| goals_1.sqlite | 32KB + WAL/SHM | goal 상태·token/time budget | 미반영 |
| memories_1.sqlite | 40KB + WAL/SHM | memory pipeline stage/job | 미반영 |
| queue_1.sqlite | 28KB + WAL/SHM | queued item | 미반영 |
| config.toml | 약 1KB | 모델·sandbox·project trust·TUI·plugin/hook 설정 | 미반영 |
| config.toml.bak | 약 1.8KB | 이전 설정 및 hook 관련 흔적 | 미반영 |
| auth.json | 약 4KB | file-based credential 가능성. 값은 민감 | 미반영 |
| version.json | Codex version check 상태 | 설치/업데이트 시각·버전 | 미반영 |
| .codex/tmp | 18 files, 약 2.2KB | apply-patch runtime helper/lock | 미반영 |
| .codex/.tmp | 5,961 files, 약 71.7MB | plugin cache·backup·sync 영역으로 관측 | 미반영 |
| .codex/.sandbox | 8 files, 약 599KB | sandbox runtime log/json | 미반영 |
| .codex/.sandbox-bin | 2 exe, 약 2.0MB | sandbox 실행 보조 바이너리 | 미반영 |
| .codex/.sandbox-secrets | 1 json, 828 bytes | sandbox 관련 민감 설정 가능성 | 미반영 |

크기와 row 수는 Codex가 실행 중인 동안 변한다. 위 수치는 조사 시점의 snapshot이며, 법적·재현성 있는 보고서에는 수집 시작/종료 시각과 각 파일 SHA-256을 함께 기록해야 한다.

### 3.2 sessions raw 파일

파일명은 다음과 같은 rollout 형식이다.

    rollout-YYYY-MM-DDTHH-mm-ss-<UUID>.jsonl

로컬에서는 17개 파일 모두 state_5.sqlite의 rollout_path와 연결되며, 관측 당시 17개 path가 실제 파일로 존재했다.

가장 큰 rollout 하나가 약 90MB이며, 나머지에도 수 MB 단위 파일이 존재한다. 따라서 JSONL을 메모리에 전부 올리는 parser는 적절하지 않다. line streaming, raw byte hash, line number 보존이 필요하다.

### 3.3 session_index.jsonl의 한계

session_index.jsonl은 3 lines에 불과하고 동일 session id가 중복으로 나타난 관측이 있다. 따라서 다음처럼 취급해야 한다.

- 검색 보조 index
- authoritative session 목록 아님
- 누락·중복 가능
- 실제 session 전수 탐색은 sessions/**/*.jsonl과 state_5.sqlite를 기준으로 수행

### 3.4 history.jsonl의 한계

history.jsonl은 session_id, text, ts 형태의 짧은 history record를 가진다. 로컬 관측에서 731 lines, 이전 파싱 기준 16 unique session_id가 확인되었다.

history.jsonl은 사용자가 history persistence를 켰을 때의 보조 증거다. raw rollout과 일대일 완전 대응한다고 가정하면 안 된다. max_bytes compaction이나 persistence 설정에 의해 오래된 record가 사라질 수 있다.

---

## 4. Codex 저장 아키텍처

Codex 로컬 증거는 하나의 파일이 아니라 raw event와 SQLite projection의 조합이다.

    CODEX_HOME
    ├─ sessions/YYYY/MM/rollout-*.jsonl       ← raw rollout, 1차 증거
    ├─ history.jsonl                          ← 짧은 history 보조 index
    ├─ session_index.jsonl                    ← session 검색 보조 index
    ├─ state_5.sqlite                         ← thread catalog
    │  └─ threads.rollout_path ───────────────┐
    ├─ thread_history_1.sqlite                │
    │  ├─ thread_turns                        │
    │  └─ thread_items                        │
    ├─ logs_2.sqlite                           │
    ├─ goals_1.sqlite                          │
    ├─ memories_1.sqlite                      │
    ├─ queue_1.sqlite                         │
    ├─ config.toml / auth.json                ← 설정·인증
    ├─ tmp/arg0                               ← runtime helper
    ├─ .tmp/plugins                           ← plugin/cache
    ├─ .sandbox*                              ← sandbox runtime
    └─ Windows %TEMP%/codex-clipboard-*.png  ← local image cache

권장 증거 우선순위:

1. raw rollout JSONL
2. raw rollout과 연결된 state_5.sqlite의 thread metadata
3. thread_history_1.sqlite의 item projection
4. SQLite WAL/SHM
5. history/session index
6. logs_2.sqlite 및 sandbox/temp 보조 흔적
7. config/auth는 설정·인증 목적의 민감 증거로 별도 보호

raw JSONL과 SQLite projection이 다를 경우 raw JSONL을 단일 진실원천으로 두고, SQLite는 검색·집계 가속기와 보조 cross-check로 사용해야 한다.

---

## 5. Raw rollout JSONL 구조

### 5.1 공통 envelope

대표 rollout line은 다음 형태의 envelope를 가진다.

| 필드 | 의미 |
|---|---|
| ordinal | rollout 내부 순번 |
| timestamp | record 시각 |
| type | session_meta, turn_context, event_msg, response_item, compacted, world_state 등 |
| payload | type별 실제 record |

모든 line을 raw bytes 기준으로 SHA-256 hashing하고, parser는 line number를 보존해야 한다. JSON decode가 실패한 line도 버리지 말고 parse error 목록에 남기는 편이 포렌식에 적합하다.

### 5.2 session_meta

관측된 payload key:

- base_instructions
- cli_version
- context_window
- cwd
- history_mode
- id
- model_provider
- originator
- session_id
- source
- thread_source
- timestamp

활용:

- Codex version·provider·cwd·session id 귀속
- session 시작 시각
- history mode
- raw session 식별

주의:

- base_instructions에는 사용자 환경·프로젝트 지침이 포함될 수 있어 원문 노출을 피해야 한다.
- cwd는 사용자 경로이므로 보고서에는 필요할 때만 마스킹해 표시한다.

### 5.3 turn_context

관측된 payload key:

- approval_policy
- approvals_reviewer
- collaboration_mode
- comp_hash
- current_date
- cwd
- effort
- model
- multi_agent_version
- permission_profile
- personality
- realtime_active
- sandbox_policy
- summary
- timezone
- turn_id
- workspace_roots

활용:

- turn별 approval/sandbox 경계
- 모델·reasoning effort
- workspace root
- collaboration/subagent mode
- 시간대·현재 날짜

포렌식 의미:

- commandExecution만 보면 명령을 실행했다는 사실은 알 수 있지만, 당시 sandbox/approval policy를 함께 보지 않으면 행위의 실행 조건을 놓칠 수 있다.
- turn_context와 command/fileChange를 turn_id 및 ordinal로 JOIN해야 한다.

### 5.4 event_msg

대표 nested type:

- item_completed
- task_complete
- task_started
- thread_settings_applied
- token_count
- turn_aborted

이벤트:

- turn lifecycle
- item 완료/실패
- token usage
- abort
- thread settings

포렌식 활용:

- 명령 실행 전후의 lifecycle 확인
- 완료/중단 여부
- usage 및 시간 상관
- 실패한 작업과 정상 완료 작업 분리

### 5.5 response_item

관측된 대표 payload type:

- custom_tool_call
- custom_tool_call_output
- function_call
- function_call_output
- message
- reasoning

대표 대형 session 한 개에서 관측된 예시 분포:

| response_item payload type | 관측 count |
|---|---:|
| custom_tool_call | 640 |
| custom_tool_call_output | 640 |
| function_call | 2 |
| function_call_output | 2 |
| message | 609 |
| reasoning | 1,197 |

이 값은 한 대형 session의 대표 관측치이며 전체 17개 session의 고정 통계가 아니다.

### 5.6 compacted와 world_state

compacted는 context compaction 또는 요약 경계를 표시하는 보조 record다. world_state는 실행 환경 변화·현재 상태 관련 payload일 수 있다.

이 record를 prompt/response 이벤트로 잘못 변환하면 사용자 발화와 에이전트 행위 count가 부풀려진다. 별도 metadata event 또는 skip-with-provenance 방식이 적합하다.

### 5.7 암호화·opaque field

17개 rollout 중 15개에서 encrypted_content 문자열과 gAAAAA 패턴이 관측되었다.

이 관측이 의미하는 바:

- reasoning 또는 내부 content 일부가 opaque/encrypted blob으로 남을 수 있다.
- cwd·prompt metadata·tool metadata 일부가 보인다고 해서 reasoning 전체가 평문이라는 뜻은 아니다.
- 특정 암호 알고리즘이나 복호화 가능성을 로컬 패턴만으로 단정하면 안 된다.
- encrypted blob 원문을 보고서·UI·LLM 질의 prompt에 넣지 않는다.

정규화 시 권장:

    tags += ["codex:opaque"]
    meta["encrypted"] = true
    meta["original_length"] = N
    preview = "<opaque content>"

복호화는 별도의 키 보관·인증·버전 연구 과제다. 현재 포렌식 도구의 기본 동작은 복호화가 아니라 존재·길이·위치·session/turn 연결 보존이어야 한다.

---

## 6. SQLite 저장소 분석

모든 주요 SQLite는 WAL journal mode로 관측되었고, 조사 시 integrity_check는 ok였다. SQLite main 파일만 복사하면 최신 commit이 빠질 수 있으므로 main, -wal, -shm을 같은 시점에 확보해야 한다.

### 6.1 state_5.sqlite

테이블:

- _sqlx_migrations
- backfill_state
- external_agent_config_imports
- remote_control_enrollments
- threads
- thread_dynamic_tools
- thread_sections
- thread_spawn_edges

threads 주요 column:

- id
- rollout_path
- created_at
- updated_at
- source
- model_provider
- cwd
- title
- sandbox_policy
- approval_mode
- tokens_used
- has_user_event
- archived
- archived_at
- git_sha
- git_branch
- git_origin_url
- cli_version
- first_user_message
- agent_nickname
- agent_role
- memory_mode
- model
- reasoning_effort
- agent_path
- created_at_ms
- updated_at_ms
- thread_source
- preview
- recency_at
- recency_at_ms
- history_mode
- name
- is_pinned
- thread_section_id
- section_position
- section_entered_at_ms

2026-08-18 snapshot:

- threads: 17
- archived: 0
- model_provider: openai 1종
- source: cli 16, exec 1
- 17개 rollout_path가 실제 파일로 확인
- cwd/title/first_user_message/preview가 모두 채워진 상태

has_user_event가 0으로 나타난 관측이 있어 단일 flag를 사실의 근거로 사용하면 안 된다. 실제 userMessage item과 raw JSONL을 함께 확인해야 한다.

### 6.2 thread_history_1.sqlite

테이블:

- _sqlx_migrations
- thread_turns
- thread_items
- thread_history_projection_state

thread_turns 주요 column:

- thread_id
- turn_id
- rollout_ordinal
- status
- error_json
- started_at
- completed_at
- duration_ms
- first_user_item_id
- final_agent_item_id
- rollout_byte_offset
- rollout_end_ordinal
- rollout_end_byte_offset

thread_items 주요 column:

- thread_id
- turn_id
- item_id
- rollout_ordinal
- created_at_ms
- item_json
- item_type
- updated_at_ordinal

2026-08-18 11:29 snapshot:

- distinct history thread id: 6
- turns: 254
- projected items: 3,524
- turn status: completed 235, failed 3, inProgress 1, interrupted 15

item_type 분포:

| item_type | count |
|---|---:|
| agentMessage | 461 |
| commandExecution | 929 |
| contextCompaction | 14 |
| fileChange | 130 |
| imageView | 26 |
| reasoning | 1,581 |
| userMessage | 255 |
| webSearch | 128 |
| 합계 | 3,524 |

state_5.sqlite에는 17개 thread가 있지만 thread_history_1.sqlite projection은 현재 6개 thread id만 포함하는 상태가 관측되었다. 이 차이는 다음 가능성을 열어 둔다.

- projection이 모든 thread를 아직 backfill하지 않았음
- 오래된 thread history가 별도 보존정책으로 제외됨
- state catalog와 history projection의 갱신 시점이 다름
- DB rotation 또는 migration 이후 일부 projection만 남음

따라서 도구는 SQLite item만으로 전체 사건을 확정하면 안 된다. state threads의 rollout_path를 따라 raw JSONL 17개를 전수 파싱하고 SQLite는 보조 인덱스로 사용해야 한다.

### 6.3 thread item별 세부 구조

#### agentMessage

key:

- id
- memoryCitation
- phase
- text
- type

phase 관측:

- commentary
- final_answer

#### commandExecution

key:

- aggregatedOutput
- command
- commandActions
- cwd
- durationMs
- exitCode
- id
- pluginId
- processId
- scriptPath
- source
- status
- type

분석 가능한 증거:

- 실행 명령 원문
- 실행 당시 cwd
- 종료코드
- 성공/실패 상태
- 명령 결과 output
- 프로세스 id 및 실행시간
- script/플러그인 관련 metadata
- commandActions 내부 구조

주의:

- commandExecution의 command는 실행 의도·실행 요청의 증거다.
- 이것만으로 모든 하위 프로세스 syscall을 재현할 수는 없다.
- output에 파일 내용·토큰·개인정보가 포함될 수 있으므로 preview 마스킹이 필요하다.

#### fileChange

key:

- changes
- id
- status
- type

changes 내부에서 관측:

- path
- diff
- kind

kind 분포:

- add: 11
- update: 118
- delete: 1

fileChange item은 130개이고 changes entry는 144개였다. 9개 item은 여러 change entry를 포함했다.

이는 현재 도구의 write 이벤트로 정규화하기 좋은 구조다. 단, diff 전체를 preview로 표시하면 민감정보가 그대로 노출될 수 있으므로 path·kind·diff summary를 기본값으로 하고 raw diff는 별도 보호 옵션으로 두는 편이 안전하다.

#### userMessage

content는 array이며 localImage와 text part가 관측되었다.

- text part: 255회 수준의 관측
- localImage part: 23회
- 일부 user message는 2개 이상 part를 포함

text는 prompt, localImage는 paste 또는 image 입력으로 변환 가능하다.

#### reasoning

content와 summary가 array 구조로 관측되었다. 내부 reasoning은 사용자에게 보이는 일반 response와 구분해야 한다. opaque/encrypted content가 섞이는 경우에는 별도 tag로 보존하고 자연어 질의 대상에서 기본 제외한다.

#### webSearch

action, id, query, results, type key를 가진다. search query와 result metadata를 event action mcp 또는 별도의 web_search action으로 정규화할 수 있다.

#### imageView

id, path, type key를 가진다. path가 Windows Temp 또는 clipboard cache를 가리키면 이미지 첨부·열람과 연결된다.

### 6.4 logs_2.sqlite

테이블:

- _sqlx_migrations
- sqlite_sequence
- logs

logs column:

- id
- ts
- ts_nanos
- level
- target
- feedback_log_body
- module_path
- file
- line
- thread_id
- process_uuid
- estimated_bytes

snapshot:

- rows: 14,968
- non-empty feedback_log_body: 14,968
- thread_id가 채워진 row: 일부
- distinct thread id: 9
- level: DEBUG 3,867, ERROR 16, INFO 2,880, TRACE 7,926, WARN 279
- body는 JSON이 아닌 plain text로 관측
- target 63종, module/file 64종 수준

body 문자열에 command/file/path/tmp/temp/sandbox/tool 같은 단어가 포함되는 row가 존재한다. 그러나 logs는 안정된 forensic event schema가 아니며 내부 diagnostic 메시지다. 현재 도구가 로그 body를 읽지 않는 것은 타당하다. Codex adapter에서 logs를 선택적으로 보조 증거로 가져오려면:

- raw body 원문을 Event preview로 직접 넣지 않기
- target/module/level/ts/thread_id 중심의 metadata event 생성
- body는 별도 보안 export에서만 제공
- 버전별 schema 변화에 대비한 parser version 기록

### 6.5 goals_1.sqlite

테이블:

- thread_goals
- thread_goal_continuation_deferrals

thread_goals column:

- thread_id
- goal_id
- objective
- status
- token_budget
- tokens_used
- time_used_seconds
- created_at_ms
- updated_at_ms

현재 thread_goals row는 0이었다. 하지만 empty DB라는 사실은 기능이 사용되지 않았다는 뜻일 뿐, Codex 전체에서 goal artifact가 없다는 뜻은 아니다.

### 6.6 memories_1.sqlite

테이블:

- jobs
- stage1_outputs

stage1_outputs에는 raw_memory, rollout_summary, rollout_slug, usage_count, last_usage, selected_for_phase2 같은 memory pipeline column이 있다.

현재 stage1_outputs/jobs row는 0이었다. 향후 memory 기능을 사용하는 session에서는 개인 정보·요약 정보가 저장될 수 있으므로 별도 민감 artifact로 분류해야 한다.

### 6.7 queue_1.sqlite

queued_items column:

- id
- thread_id
- payload_json
- queue_order
- created_at_ms
- updated_at_ms

현재 queued_items row는 0이었다. 실행 중인 Codex를 live capture하면 queue와 WAL이 변할 수 있다.

### 6.8 raw rollout·state catalog·history projection 연결성 재검증

2026-08-18 11:53:03 +09:00 전후에 read-only 연결로 다시 확인한 결과는 다음과 같다.

| 연결 단계 | 관측값 | 해석 |
|---|---:|---|
| state_5.sqlite threads | 17 | catalog에 등록된 thread 수 |
| threads.rollout_path가 채워진 row | 17 | 모든 catalog row가 raw 경로를 가짐 |
| rollout_path 실제 파일 존재 | 17 | 이 snapshot에서는 raw 파일 누락 없음 |
| raw 파일 안에 thread id 문자열 존재 | 17 | state id와 raw rollout의 직접 연결 확인 |
| cwd가 채워진 thread | 17 | 작업 디렉터리 metadata 연결 가능 |
| thread_history projection distinct thread | 6 | history projection은 catalog 전체의 부분집합 |

따라서 Codex 수집기의 authoritative 경로는 state catalog의 thread id·rollout_path를 기준으로 잡고, raw JSONL을 먼저 보존·파싱해야 한다. thread_history의 item이 없는 thread라도 raw rollout이 존재하면 분석 대상에서 제외하면 안 된다. SQLite projection은 빠른 검색과 보조 metadata에 사용하되, raw를 대체하지 않는다.

권장 JOIN 키는 다음 순서다.

1. thread_id ↔ state_5.sqlite.threads.id ↔ raw JSONL의 session/thread metadata
2. rollout_path ↔ 파일 SHA-256·파일 크기·수집 시각
3. turn_id·rollout_ordinal ↔ thread_history.thread_turns/thread_items
4. rollout_byte_offset·rollout_end_byte_offset ↔ raw line/byte provenance

최초 snapshot(11:29:25)의 projection은 254 turns·3,524 items였고, 이후 재검증에서는 255 turns·3,597 items로 증가했다. 이는 SQLite와 WAL이 live 상태에서 계속 갱신될 수 있음을 보여준다. 수집 보고서에는 각 DB의 관측 시각을 row 수와 함께 기록해야 하며, 서로 다른 시각의 main/WAL/SHM 수치를 하나의 snapshot처럼 합치면 안 된다.

---

## 7. Codex 파일 접근과 에이전트 작업 행위

### 7.1 현재 로컬에서 확인된 구조화 파일 행위

Codex projection에는 다음이 있다.

#### 실행 행위

commandExecution 약 929 item이 확인되었다.

가능한 필드:

    command
    cwd
    aggregatedOutput
    exitCode
    status
    durationMs
    processId
    scriptPath
    source

이것으로 다음 행위를 분석할 수 있다.

- shell command 실행
- 파일 목록 조회
- 파일 내용 조회
- grep/rg/search
- SQLite query
- patch/helper 실행
- 테스트·빌드·프로그램 실행
- 성공/실패·종료코드·실행시간

#### 파일 변경 행위

fileChange 약 130 item, changes entry 144개가 확인되었다.

가능한 행위:

- 새 파일 추가
- 기존 파일 수정
- 파일 삭제
- 여러 파일을 한 번에 변경
- diff를 통한 변경 전후 관계 분석

#### prompt/response 행위

- userMessage → 사용자 prompt
- agentMessage → 에이전트 response/commentary/final answer
- localImage → 이미지 첨부
- imageView → 이미지 열람
- webSearch → 외부 검색

### 7.2 temp 문자열과 실제 temp artifact의 구분

commandExecution의 명령 문자열에는 tmp/temp/.codex/AppData Temp 경로가 포함될 수 있다. 한 관측에서 command text에 tmp/temp/.codex/AppData Local Temp marker가 나타났다.

그러나 이 수치는 현재 조사 과정에서 실행한 command도 포함할 수 있고, 문자열이 있다고 해서 실제 파일이 생성되었다는 뜻은 아니다. 다음을 분리해야 한다.

| 층위 | 증거 | 의미 |
|---|---|---|
| 명령 의도 | commandExecution.command | LLM/도구가 요청한 명령 |
| 명령 결과 | aggregatedOutput/exitCode/status | 명령 실행 결과 |
| transcript 변경 | fileChange.diff/path | Codex가 기록한 변경 |
| 디스크 잔존 | 실제 temp 파일 stat/hash/content | 현재 파일시스템에 남은 산물 |
| OS syscall | Windows auditing/ETW/Sysmon 등 | 실제 프로세스 수준 파일 접근 |

현재 Codex artifact만으로는 네 층위를 자동으로 동일시하면 안 된다.

### 7.3 현재 thread projection에서 확인된 temp path 연결

관측된 fileChange path에서 temp marker가 발견되지 않았다. 이는 현재 projection에 temp 파일을 직접 변경한 fileChange가 없다는 뜻이며, temp에 명령 산물이 없다는 증명은 아니다.

commandExecution JSON에는 codex-arg/apply-patch/temp marker가 일부 존재했다. 명령이 temp를 언급한 경우에도:

- 현재 파일 존재 여부 확인
- mtime/atime
- content hash
- 해당 command의 turn_id/session_id
- 인접 fileChange
- raw JSONL line/ordinal

을 함께 확인해야 한다.

### 7.4 Codex temp 디렉터리 실측

#### C:\Users\irise\.codex\tmp

관측:

- arg0 하위 작업 디렉터리 6개
- 정규 파일 18개
- .lock 6개
- applypatch.bat 6개
- apply_patch.bat 6개
- 총 크기 약 2.2KB

해석:

- Codex apply-patch 실행을 위한 Windows helper/wrapper와 lock 흔적으로 보인다.
- 파일명은 runtime helper를 강하게 시사하지만, 각 파일이 어느 session/turn에서 생성되었는지 직접적인 session id 연결은 없다.
- mtime, commandExecution, fileChange, process/log를 JOIN해야 task 단위 귀속이 가능하다.
- 이 경로는 일반 프로젝트 산출물이나 fileChange diff와 같은 의미로 취급하면 안 된다.

#### C:\Users\irise\.codex\.tmp

관측:

- 정규 파일 약 5,961개
- 총 크기 약 71.7MB
- 상위 디렉터리: plugins, plugins-backup 계열
- root-level sync marker/lock/SHA 파일 존재
- 확장자: md, json, yaml, py, png, svg, js, mjs, sh, ps1, html, toml 등 다수

해석:

- plugin/cache/synchronization artifact 성격이 강하다.
- 파일이 많고 코드·문서·이미지가 섞여 있으므로 설치된 skill/plugin의 재료 또는 cache로 분류할 수 있다.
- 해당 파일이 곧 LLM이 이번 session에서 스스로 작성한 결과라는 의미는 아니다.
- plugin cache 내부의 파일 변경을 Codex 작업 산출물로 귀속하려면 rollout/session/time correlation이 필요하다.

#### C:\Users\irise\.codex\.sandbox

관측:

- 파일 8개
- JSON 2개
- log 6개
- 약 599KB

해석:

- sandbox runtime·정책·실행 진단 증거 가능성
- commandExecution의 sandbox_policy와 시간상관 가능
- 파일 내용에는 sandbox 경로·권한·실행 오류가 포함될 수 있으므로 별도 보호 분석 필요

#### C:\Users\irise\.codex\.sandbox-bin

관측:

- executable 2개
- 약 2.0MB

해석:

- sandbox 실행 보조 바이너리로 보인다.
- 실행 자체는 commandExecution/process/log와 조합해야 한다.
- 파일 존재만으로 LLM이 해당 바이너리를 실행했다고 판단하면 안 된다.

#### C:\Users\irise\.codex\.sandbox-secrets

관측:

- JSON 1개
- 828 bytes

해석:

- 이름상 sandbox secret 또는 capability 설정 가능성이 높다.
- 원문 열람·보고서 출력 금지.
- file hash, ACL, mtime, key 목록 정도의 최소 metadata만 보존하는 것이 안전하다.

#### Windows %TEMP%

관측:

- codex-clipboard-*.png 20개
- 크기 약 17KB~676KB 범위
- thread_history에는 localImage user content가 관측됨
- imageView path 중 일부가 Temp marker를 가짐

해석:

- 사용자가 Codex에 붙여넣거나 전달한 이미지의 local clipboard cache일 가능성이 높다.
- prompt input evidence로는 중요하지만, LLM이 스스로 작업해서 만든 temp 산물과는 구분해야 한다.
- 이미지 metadata와 session/userMessage/imageView 시간상관을 통해 어느 session의 입력인지 연결해야 한다.

#### 시간·보존 재검증

기준 시각은 2026-08-18 11:29:25 +09:00이고, “30일 초과”는 LastWriteTime이 2026-07-19 11:29:25보다 이른 파일로 계산했다. 파일의 생성 시각·삭제 이력·실제 보존정책을 뜻하는 것은 아니다.

| 경로 | 파일 수 | 총 크기 | 가장 이른 mtime | 가장 늦은 mtime | 30일 초과 mtime |
|---|---:|---:|---|---|---:|
| C:\Users\irise\.codex\tmp | 18 | 2,220 bytes | 2026-08-14 13:27:01 | 2026-08-18 10:55:51 | 0 |
| C:\Users\irise\.codex\.tmp | 5,961 | 71,708,370 bytes | 2026-06-09 16:38:50 | 2026-08-03 08:03:37 | 667 |
| C:\Users\irise\.codex\.sandbox | 8 | 599,088 bytes | 2026-04-08 22:06:22 | 2026-08-13 14:21:25 | 6 |
| %TEMP%\codex-clipboard-*.png | 20 | 2,460,863 bytes | 2026-08-13 14:13:35 | 2026-08-18 03:59:06 | 0 |

추가 결론:

- .codex\.tmp와 .codex\.sandbox에는 현재 기준 30일보다 오래된 잔존물이 있으므로 Codex temp를 30일 자동 삭제 대상으로 단정할 수 없다.
- .codex\tmp와 clipboard PNG는 이번 snapshot에서 모두 최근 mtime이었다. 이것은 “30일 보존정책”의 증명이 아니라 현재 관측된 잔존 범위다.
- mtime은 복사·압축해제·cache 갱신으로 바뀔 수 있다. 생성 시각, 삭제된 파일, 과거 버전은 별도 USN Journal/Windows auditing/백업이 없으면 복원할 수 없다.
- .codex\.tmp의 plugin/cache 파일과 .sandbox-bin은 존재·시간·hash를 artifact로 보존할 수 있지만, 그 자체만으로 LLM이 해당 파일을 직접 작성했다고 귀속하면 안 된다.

### 7.5 commandExecution·fileChange 재검증 통계

live projection을 한 번 더 읽은 상세 scan에서는 다음 관측이 나왔다. 아래 marker 수는 서로 겹칠 수 있는 문자열 출현 수이며, syscall 횟수나 파일 생성 수가 아니다.

| 항목 | 관측 |
|---|---:|
| thread_items 상세 scan | 3,601 |
| commandExecution | 968 |
| commandExecution status=completed | 823 |
| commandExecution status=failed | 145 |
| exitCode=0 | 823 |
| exitCode=1 | 133 |
| exitCode=-1 | 10 |
| exitCode=124 | 2 |
| fileChange | 131 |
| fileChange path의 temp/.codex/clipboard marker | 0 |

command/cwd/output/scriptPath를 합친 문자열에서 확인된 marker는 codex 262회, temp 93회, clipboard 21회, tmp 16회, AppData\Local\Temp 12회, POSIX /tmp 11회, apply-patch 13회였다. command 문자열에 경로가 포함된 것은 명령 의도 또는 출력의 증거이지 OS가 실제로 그 파일을 열었다는 증명이 아니다. 현재 관측에서 fileChange path에는 temp marker가 없으므로 “Codex가 temp 파일을 fileChange로 직접 보고했다”는 연결은 확인되지 않는다.

이 통계를 이용한 안전한 판정 단계는 다음과 같다.

1. commandExecution의 turn_id/session_id와 command/cwd를 보존한다.
2. 같은 turn의 aggregatedOutput·exitCode·status를 함께 읽는다.
3. raw JSONL ordinal/byte offset과 thread_history item을 연결한다.
4. 실제 파일이 남아 있으면 mtime·size·SHA-256·ACL을 별도로 취득한다.
5. 실제 프로세스 파일 open/read/write가 필요하면 ETW/Sysmon/Windows auditing을 추가 수집한다.

---

## 8. 기존 도구의 기능별 지원 범위

현재 구현 기준 주요 파일:

- clfx/cli.py
- clfx/discover.py
- clfx/event.py
- clfx/parser.py
- clfx/sources/claude.py
- clfx/analyze/artifacts.py
- clfx/analyze/attribution.py
- clfx/analyze/secrets.py
- clfx/analyze/keywords.py
- clfx/analyze/mcp.py
- clfx/query/engine.py
- clfx/query/llm.py
- clfx/web/api.py
- clfx/web/server.py
- clfx/web/static/*

### 8.1 기능별 판정표

| 기능 | 현재 구현 | Codex 현재 적용 | 업데이트 가능성 | 필요한 변경 |
|---|---|---|---|---|
| 자동 source discovery | .claude 후보 및 WSL/Windows 검색 | Codex 미탐지 | 가능 | CODEX_HOME/CODEX_SQLITE_HOME/기본 .codex 탐지 |
| JSONL parse | Claude history/projects JSONL | Codex 미파싱 | 가능 | Codex envelope parser |
| SQLite read | 없음 | 미분석 | 가능 | read-only SQLite adapter 및 WAL 처리 |
| Event 정규화 | 일반 Event dataclass | agent 필드만 codex 문자열 허용 | 가능 | Codex event mapper, metadata 확장 |
| 사용자 prompt | Claude user content | Codex userMessage 미연결 | 가능 | text/localImage mapping |
| agent response | Claude assistant text | Codex agentMessage 미연결 | 가능 | phase/text mapping |
| shell/command | Claude Bash | Codex commandExecution 미연결 | 가능 | command→bash/command event |
| file read | Claude toolUseResult.file | Codex command/output 기반만 존재 | 부분 가능 | read intent parser, syscall 한계 표기 |
| file write | Claude Write/Edit | Codex fileChange 미연결 | 가능 | changes[] path/kind/diff mapping |
| image input/view | Claude image/paste | Codex localImage/imageView 미연결 | 가능 | clipboard path 및 imageView mapping |
| web search | Claude/MCP 일부 | Codex webSearch 미연결 | 가능 | web_search action 또는 mcp tag |
| secrets/PII | preview 문자열 scan/mask | Codex preview 미생성 | 가능 | command output/diff/user text scan |
| keyword | Event preview 기반 | Event가 없어서 미작동 | 높음 | normalize 후 기존 함수 재사용 |
| timeline/activity | Event timestamp 기반 | Event가 없어서 미작동 | 높음 | ordinal/timestamp adapter |
| files panel | read/write/paste/upload Event 집계 | Codex source 없음 | 높음 | normalized file events |
| attribution | transcript actor + fs stat JOIN | Codex actor mapping 없음 | 가능하나 조건부 | command/fileChange와 path/time JOIN |
| hash cluster | 참조/temporary path SHA-256 | Codex roots 미전달 | 가능 | Codex roots 및 raw artifact roots 추가 |
| tmp inventory | Claude root에서 OS tmp 추정 | .codex internal tmp 미포함 | 가능 | Codex-specific root classifier |
| tmp retention | RETENTION_DAYS=30 | Codex 보존정책 근거 없음 | 부분 가능 | Codex는 측정값·정책 unknown 분리 |
| hash search | temp hash index | temp inventory가 Codex를 못 찾음 | 가능 | inventory 범위 확장 |
| MCP | Claude config parser | Codex config.toml 미분석 | 가능 | TOML mcp_servers adapter |
| attestation | JSONL/ref/tmp hash + roio audit | Codex JSONL/DB 미포함 | 가능 | JSONL+SQLite+WAL/SHM manifest |
| natural-language query | deterministic engine + local Ollama fallback | Codex events 없음 | 높음 | normalized Event만 공급 |
| web dashboard | Claude 문구·origin filter | Codex 표시 없음 | 가능 | agent/source filter, artifact labels |
| CLI parse/analyze | ClaudeSource 직접 hard-code | Codex 입력 불가 | 가능 | source registry/agent option |
| packaging | PyInstaller launcher | backend만 확장하면 재사용 | 가능 | Codex fixture·설정 문서 포함 |

### 8.2 현재 코드에서 확인한 Claude 고정 지점

다음 지점은 Codex 업데이트 때 반드시 수정해야 한다.

- cli.py가 ClaudeSource를 직접 import
- parse_roots가 .claude root만 받음
- cmd_analyze의 _NullSource.agent가 claude
- web/api.py의 scan_to_engine가 ClaudeSource를 직접 생성
- discover.py의 _default_candidates가 .claude만 탐색
- artifacts.py의 _wsl_base_of, tmp_roots docstring과 path 규칙이 Claude root 전제
- artifacts.py의 RETENTION_DAYS = 30 주석이 Claude tmp 실측 기반
- mcp.py가 형제 .claude.json과 project .mcp.json을 찾음
- UI case-target 기본값이 ~/.claude
- UI source 안내가 Claude Code 기록으로 고정
- UI source filter는 WSL/Windows origin만 구분
- 테스트 fixture와 대부분 Event의 agent가 claude

Event dataclass 주석에는 claude | codex | gemini가 이미 적혀 있지만, 이는 입력 adapter가 존재한다는 뜻이 아니다.

---

## 9. 파일 접근 기록을 Codex에 매핑하는 설계

### 9.1 최소 호환 mapping

기존 event-schema를 최대한 유지하려면 다음처럼 정규화할 수 있다.

| Codex 원본 | Event.agent | Event.actor | Event.action | Event.target | Event.preview |
|---|---|---|---|---|---|
| userMessage text | codex | user | prompt | 빈 문자열 또는 message id | text 일부 |
| userMessage localImage | codex | user | paste | image path/id | image metadata |
| agentMessage | codex | agent | response | phase/type | text 일부 |
| commandExecution | codex | agent | bash | command | redacted output 또는 command summary |
| fileChange add/update/delete | codex | agent | write | changes[].path | kind/diff summary |
| imageView | codex | agent | read 또는 paste | image path | image view metadata |
| webSearch | codex | agent | mcp 또는 web_search | search/query label | query/result summary |
| reasoning opaque | codex | agent | response 또는 reasoning | item id | opaque marker only |

현재 action enum을 바꾸지 않는 최소 구현은 commandExecution을 bash로 표현하는 것이다. 하지만 bash와 Codex commandExecution을 구별하려면 다음 tag를 추가해야 한다.

    codex:item_type=commandExecution
    codex:source=agent
    codex:exit=0
    codex:status=completed

### 9.2 권장 Event 확장

파일 접근·SQLite join을 정확히 표시하려면 tags만으로는 부족하다. 다음 optional metadata를 추가하는 것이 좋다.

    meta = {
      "agent": "codex",
      "raw_type": "commandExecution",
      "turn_id": "...",
      "item_id": "...",
      "rollout_ordinal": 123,
      "rollout_byte_offset": 456789,
      "sqlite_db": "...",
      "sqlite_table": "thread_items",
      "exit_code": 0,
      "status": "completed",
      "confidence": "high"
    }

기존 출력과의 호환을 유지하려면 meta를 optional로 두고, 기존 Event 9개 필드는 그대로 둔다.

### 9.3 source(file:line) 보존

기존 도구는 source.file/source.line을 중심으로 UI citation을 만든다. Codex는 다음 우선순위를 사용해야 한다.

1. raw rollout JSONL file + line
2. raw rollout file + ordinal/byte offset
3. SQLite database + table + thread_id/item_id
4. log database + row id

SQLite row만 source로 사용하면 raw line으로 역추적하기 어려우므로 rollout_path와 ordinal/byte offset을 함께 보존해야 한다.

### 9.4 read 행위의 confidence

Codex는 Claude처럼 별도의 read tool result가 항상 동일하게 남는다고 가정하면 안 된다.

권장 분류:

- high: fileChange path 또는 명시적인 file-read tool result가 있음
- medium: commandExecution command에 cat/Get-Content/rg/sqlite 등 명시적 read operation이 있음
- low: output에 파일명이 보이나 command intent가 불명확함
- unknown: temp 파일이 존재하지만 session 연결이 없음

UI와 보고서에서 “파일을 읽었다”와 “파일 경로가 명령에 등장했다”를 구분해야 한다.

---

## 10. Codex temp·sandbox 분석 설계

### 10.1 root 분류

Codex용 artifact root는 최소 다음 범주로 나눠야 한다.

| 범주 | 후보 | 기본 의미 |
|---|---|---|
| codex_state | CODEX_HOME | 설정·세션·상태 |
| codex_rollout | CODEX_HOME/sessions | raw transcript |
| codex_runtime_tmp | CODEX_HOME/tmp | helper/lock/runtime |
| codex_cache_tmp | CODEX_HOME/.tmp | plugin/cache/sync |
| codex_sandbox | CODEX_HOME/.sandbox* | sandbox runtime |
| user_temp | TEMP/TMP | OS 공용 temp |
| codex_clipboard | TEMP/codex-clipboard-* | 이미지 입력 cache |
| generic_tmp | C:\tmp, /tmp, /var/tmp | 다른 프로세스와 공유되는 temp |

현재 artifacts.tmp_roots는 Codex internal tmp/.tmp/.sandbox를 자동으로 추가하지 않으므로 변경이 필요하다.

### 10.2 “LLM 스스로 작업” 귀속 규칙

파일이 Codex 경로 아래에 있다는 이유만으로 에이전트 작업 산물로 확정하지 않는다. 다음 JOIN 점수를 사용한다.

1. raw rollout의 session/turn/ordinal과 timestamp 근접성
2. commandExecution command가 해당 경로를 직접 언급하는지
3. fileChange path/diff가 동일 경로를 지시하는지
4. processId/scriptPath와 runtime helper의 시간상관
5. SHA-256 또는 content fingerprint 일치
6. sandbox log의 task/process reference
7. 파일명/포맷이 Codex runtime 고유 패턴인지

권장 결과:

    actor = agent, confidence = high
    actor = agent, confidence = medium
    actor = unknown, reason = no transcript link
    artifact_class = runtime_helper | plugin_cache | clipboard_input | sandbox_log

### 10.3 cache와 self-work 구분

- .codex/.tmp/plugins: plugin/cache로 분류. self-work 단정 금지.
- .codex/tmp/arg0/apply_patch.bat: Codex runtime helper로 분류. 특정 task 귀속은 별도 JOIN.
- TEMP/codex-clipboard-*.png: user input/clipboard evidence로 분류. agent output과 분리.
- .sandbox logs/exe/secrets: runtime boundary evidence. 실행·접근의 직접 증거가 아니므로 process/log correlation 필요.

### 10.4 보존기간 계산

Claude 문서에서 실측된 30일을 Codex에 그대로 적용하면 안 된다.

Codex 공식 문서는 CODEX_HOME 아래 state/history 위치와 history persistence 설정을 설명하지만, internal .tmp/tmp/sandbox 파일의 보존기간을 일반 정책으로 보장하지 않는다.

따라서 Codex retention 결과는 다음처럼 표현해야 한다.

- observed_age_days
- current_mtime
- current_atime
- cleanup_policy = unknown 또는 관측된 정책
- likely_cache
- session_link
- deletion_risk = high/medium/low

RETENTION_DAYS=30 같은 단일 상수는 Claude/Codex source별로 분리해야 한다.

---

## 11. SQLite 및 WAL 수집 설계

### 11.1 수집 대상

Codex SQLite는 main만 수집하면 안 된다.

    state_5.sqlite
    state_5.sqlite-wal
    state_5.sqlite-shm

같은 방식으로 goals, logs, memories, queue, thread_history의 main/WAL/SHM를 모두 수집한다.

### 11.2 read-only 연결

분석기는 SQLite read-only 연결을 사용하고, 원본 DB에 VACUUM, checkpoint, WAL merge, schema write를 수행하지 않아야 한다.

권장 순서:

1. 실행 중 Codex의 live 상태를 기록
2. main/WAL/SHM 파일을 함께 확보
3. 확보본을 대상으로 read-only 연결
4. PRAGMA integrity_check 결과 기록
5. schema/table/row count 기록
6. raw rollout_path와 join
7. main/WAL/SHM 각각 hash 기록

### 11.3 raw JSONL 우선 정책

projection이 17개 thread 중 6개만 포함하는 관측이 있었으므로 다음 정책을 적용한다.

- raw JSONL은 누락되지 않는 한 1차 증거
- state threads는 session catalog
- thread_history item은 빠른 검색용 projection
- projection에만 있는 item과 raw에만 있는 item을 reconciliation report에 표시
- mismatch를 자동 삭제·덮어쓰기하지 않음

### 11.4 SQLite item과 raw line 연결

가능한 연결 키:

- thread_id
- turn_id
- item_id
- rollout_ordinal
- rollout_byte_offset
- rollout_path

이 키를 normalized Event.meta에 보존하면 UI에서 “SQLite item → raw rollout line” 역추적이 가능하다.

---

## 12. MCP·config 분석 확장

현재 mcp.py는 Claude 구조를 전제로 한다.

- 형제 ~/.claude.json
- project .mcp.json
- mcpServers
- claudeAiMcpEverConnected
- pluginUsage

Codex는 사용자 config.toml과 project .codex/config.toml layers를 사용하므로, Codex adapter에서는 다음을 별도로 읽어야 한다.

- config.toml의 mcp_servers 관련 table
- project .codex/config.toml
- profile config
- plugin/skill이 제공하는 MCP metadata
- raw rollout의 custom_tool_call/custom_tool_call_output

MCP 결과 schema는 기존 API와 호환되게 유지할 수 있다.

    {
      "configs": [],
      "usage": [],
      "configured_unused": [],
      "used_unconfigured": [],
      "errors": [],
      "agent": "codex"
    }

마스킹 규칙은 그대로 재사용하되 TOML parser와 Codex custom tool field 경로를 추가해야 한다. auth.json·env value·URL query token·Bearer token은 원문을 출력하지 않는다.

---

## 13. 현재 도구 기능을 Codex에 연결하는 구현안

### 13.1 source registry

현재 direct import를 source registry로 바꾼다.

    SOURCES = {
        "claude": ClaudeSource,
        "codex": CodexSource,
    }

각 source는 최소 다음 interface를 제공한다.

    agent
    root
    jsonl_files()
    transcript_files()
    history_records()
    transcript_records()
    parse_file(path)
    artifact_roots()

### 13.2 CodexSource

추가 파일 후보:

    clfx/sources/codex.py
    clfx/sources/codex_sqlite.py

CodexSource 책임:

- CODEX_HOME root validate
- sessions/**/*.jsonl enumerate
- session_index/history enumerate
- rollout JSONL raw byte hash
- session metadata extraction
- state/thread_history SQLite optional load
- raw line/source citation
- Codex temp/sandbox root expose

SQLite reader 책임:

- read-only connection
- WAL presence check
- schema fingerprint
- row count
- thread/item extraction
- raw rollout join
- malformed JSON/unknown item type error report

### 13.3 parser 분리

현재 parser.py의 Claude-specific logic을 그대로 Codex에 넣지 않고 다음처럼 나눈다.

    parse_claude_record(...)
    parse_codex_record(...)
    normalize_record(...)

공통 부분:

- timestamp normalization
- Event source
- preview clipping
- tags
- secret scan hook

Codex 전용 부분:

- envelope.payload
- response_item
- event_msg
- turn_context
- commandExecution
- fileChange
- localImage
- reasoning opaque

### 13.4 API scan pipeline

현재 scan_to_engine은 다음을 hard-code한다.

    srcs = [ClaudeSource(r) for r in roots]

이를 source kind에 따라 분기한다.

    sources = build_sources(selected_roots, agent="codex")
    parse all raw files
    normalize events
    enrich actor/tags
    build reference resolution
    build temp inventory
    forensic scan
    mcp scan
    attestation
    QueryEngine

Claude와 Codex를 동시에 선택할 경우 agent tag와 root tag를 모두 보존해야 한다.

### 13.5 QueryEngine 재사용

다음은 normalized Event만 있으면 거의 그대로 재사용 가능하다.

- search
- on_date
- who_did
- secrets
- bypass
- timeline
- activity
- files
- keyword_stats
- deterministic digest
- local Ollama summary

단, bypass는 Codex의 approval_policy/sandbox_policy/permission_profile을 기존 bypass-mode tag로 동일시하면 안 된다. Codex policy는 별도 tag와 별도 query를 두는 것이 정확하다.

예:

    codex:approval_policy=on-request
    codex:sandbox=workspace-write
    codex:permission=...

### 13.6 artifact forensic 확장

기존 hash_clusters, attribution_join, tmp_retention은 구조적으로 재사용 가능하다. 변경점:

- events_with_root에 Codex root 추가
- Event action mapping 추가
- CODEX_HOME internal roots 추가
- Codex clipboard files를 input artifact로 분류
- state/thread_history/main/WAL/SHM를 acquisition manifest에 추가
- retention policy source별 분리
- Codex fileChange path와 command target을 구분
- unknown/no-link temp artifact를 unknown으로 유지

### 13.7 UI 확장

현재 UI는 다음이 Claude 고정이다.

- case-target 기본값 ~/.claude
- “Claude Code 기록” 안내
- 탐지된 .claude source가 없다는 문구
- source filter가 WSL/Windows origin만 제공

변경안:

- agent selector: Claude / Codex / Gemini
- source selector: agent + origin + root
- artifact class badge: rollout / SQLite / command / fileChange / cache / clipboard / sandbox
- “파일을 읽음”과 “명령에 파일 경로가 등장” 구분
- temp artifact confidence 표시
- encrypted/opaque 표시
- raw JSONL source citation
- SQLite projection과 raw rollout citation 동시 표시

---

## 14. chain-of-custody와 민감정보 처리

### 14.1 hash 범위

Codex 수집 manifest에는 최소 다음을 포함한다.

- 모든 rollout JSONL
- history.jsonl
- session_index.jsonl
- state/goals/logs/memories/queue/thread_history SQLite main
- 존재하는 각 WAL/SHM
- config.toml/config.toml.bak
- 필요 시 sandbox/temp artifact

auth.json은 원문 export를 금지하되, 수집 대상 여부·파일 size·mtime·SHA-256을 별도 보호 manifest에 기록할 수 있다.

### 14.2 read-only attestation

현재 roio는 read/rb open만 허용하고 in-memory audit를 제공한다. Codex 확장 시:

- JSONL reader를 roio 경유
- SQLite connection도 read-only
- WAL checkpoint 금지
- mcp/config reader도 같은 read-only wrapper 사용
- output artifact 생성은 evidence root 바깥에 위치
- source root 안의 output overwrite 금지

attestation에는 다음을 추가한다.

    raw_rollout_count
    sqlite_main_count
    sqlite_wal_count
    sqlite_shm_count
    projection_mismatch_count
    opaque_field_count
    temp_inventory_count
    unknown_attribution_count

현재 구현의 attestation 범위도 구분해야 한다.

- clfx/roio.py의 _ro_open은 r/rb만 허용하고 audit를 메모리에 기록한다.
- write_delete_rename_ops()는 실제 syscall counter가 아니라 항상 0을 반환하는 정적 보장값이다.
- cli.py의 _write_events는 분석 결과를 out_path.tmp에 쓰고 os.replace로 최종 산출물을 교체한다. 이 출력 쓰기는 evidence root 읽기와 별도의 side effect다.
- cli.py의 _read_events, analyze/mcp.py의 config reader, web/server.py의 static file reader는 builtin open을 사용해 roio audit에 포함되지 않는다. web/server.py의 analyzed_path reader처럼 roio를 경유하는 경로도 따로 있다.

그러므로 현재의 all_read_only는 “분석 대상 evidence root를 읽는 parser 층”의 의미로 제한해야 하며, 도구 프로세스 전체가 파일 쓰기를 하지 않는다는 의미로 확대하면 안 된다. Codex adapter를 추가할 때는 evidence root와 output root를 분리하고, JSONL·SQLite·WAL/SHM·config·MCP reader를 하나의 read-only wrapper로 통일하거나, wrapper 밖의 읽기·쓰기 경로를 attestation에 명시적으로 남겨야 한다.

### 14.3 preview 마스킹

다음은 기본 preview에서 제외하거나 mask한다.

- auth.json content
- access token/API key/Bearer token
- command output의 secret
- fileChange diff의 private key/password
- reasoning encrypted/opaque blob
- clipboard image raw bytes
- sandbox secret file value

포렌식 원문은 별도 접근통제된 evidence copy에만 보관한다.

---

## 15. 테스트·검증 현황

2026-08-18 현재 도구에서 pytest를 실행한 결과:

- passed: 353
- failed: 8
- skipped: 3

실패 분류:

1. hash cluster tmp copy 관련 4건
2. attribution/reference resolution Windows path 관련 2건
3. MCP fixture 경로 관련 1건
4. staged hash progress 관련 1건

이 실패들은 Codex adapter가 없어서 발생한 직접 실패는 아니지만, Codex 확장 전에 현재 artifact layer의 Windows/WSL portability와 fixture 문제를 먼저 정리해야 한다.

Codex 추가 테스트는 최소 다음을 포함해야 한다.

### 15.1 Codex parser fixture

- session_meta
- turn_context
- userMessage text
- userMessage localImage
- agentMessage
- commandExecution
- fileChange add/update/delete
- reasoning opaque
- webSearch
- compacted
- malformed JSON line
- unknown item type

### 15.2 SQLite fixture

- state threads와 rollout_path join
- thread_history item extraction
- WAL 존재/부재
- projection 6/17처럼 partial projection
- item_json malformed
- error_json
- interrupted/failed turn

### 15.3 artifact fixture

- CODEX_HOME/tmp/arg0 helper
- CODEX_HOME/.tmp plugin cache
- TEMP/codex-clipboard image
- sandbox log/exe/json
- commandExecution path와 실제 temp file time correlation
- fileChange path와 temp hash cluster
- unknown artifact attribution

### 15.4 security fixture

- auth.json 값 비노출
- command output secret mask
- diff secret mask
- encrypted_content 원문 미노출
- report/UI XSS escape

---

## 16. 권장 개발 순서

### 단계 A: source/discovery

- Codex_HOME resolver
- CODEX_SQLITE_HOME resolver
- CodexSource
- source registry
- CLI/API source parameter

### 단계 B: raw parser

- JSONL envelope parser
- source line/ordinal/hash
- user/agent/command/fileChange normalization
- opaque handling

### 단계 C: SQLite accelerator

- state thread catalog
- thread_history item projection
- raw rollout join
- WAL/SHM integrity

### 단계 D: file/temp/artifact

- commandExecution file intent extraction
- fileChange write event
- Codex temp roots
- clipboard classification
- sandbox/cache classification
- hash/retention/attribution

### 단계 E: config/MCP/security

- config.toml parser
- project/profile config
- Codex MCP usage
- output masking
- auth metadata policy

### 단계 F: UI/packaging/test

- agent/source filter
- artifact class/confidence panel
- SQLite/raw citation
- Codex fixture/e2e
- PyInstaller resource path
- documentation and acquisition guide

---

## 17. 업데이트 가능성 최종 판정

| 질문 | 판정 | 이유 |
|---|---|---|
| Codex session prompt/response 분석 가능? | 가능 | userMessage/agentMessage/raw response_item 구조 존재 |
| Codex command/fileChange 분석 가능? | 가능 | commandExecution/fileChange projection과 raw JSONL 존재 |
| Codex 파일 접근 패널 제공 가능? | 가능, 의미 구분 필요 | command intent와 실제 OS syscall을 구분해 normalized event 생성 가능 |
| Codex temp 경로 산물 분석 가능? | 가능, 조건부 | internal tmp/cache/sandbox/clipboard root를 추가하고 시간·hash·session JOIN 필요 |
| LLM이 temp에서 스스로 작업했다고 확정 가능? | 일부 가능 | command/fileChange/process/time correlation이 있을 때만 confidence 부여 |
| Codex reasoning 원문 복구 가능? | 불확실 | encrypted/opaque field가 다수 rollout에서 관측됨 |
| 기존 timeline/activity/keyword/query 재사용 가능? | 대부분 가능 | Event normalization 이후 기존 deterministic engine 재사용 |
| 기존 hash/retention/attestation 재사용 가능? | 가능, 범위 확장 필요 | Codex root·SQLite/WAL/SHM·temp classifier 추가 |
| 기존 MCP 기능 재사용 가능? | 부분 가능 | 마스킹/usage aggregate는 재사용, config reader는 새로 필요 |
| 기존 UI에서 Codex까지 표시 가능? | 가능, 수정 필요 | Claude 고정 문구·source filter·artifact label 확장 |
| 도구 전체를 Codex 분석 기반으로 업데이트 가능? | 가능 | 핵심 엔진은 generic이지만 ingestion·source·artifact·UI·test는 작업 필요 |

핵심 판단:

> Codex 지원은 “새 parser 하나 추가”로 끝나지 않는다. raw rollout, SQLite projection, WAL/SHM, command/fileChange semantics, CODEX_HOME 내부 temp/cache, Windows clipboard, sandbox, config/MCP, UI source model을 하나의 source-aware pipeline으로 통합해야 한다.

---

## 18. 기존 Claude 분석과의 비교

| 항목 | Claude Code | Codex CLI |
|---|---|---|
| 주 저장소 | ~/.claude history/projects JSONL | CODEX_HOME sessions rollout JSONL + SQLite |
| 사용자 입력 | history/transcript/paste-cache | userMessage + localImage + history.jsonl |
| agent read | toolUseResult.file | commandExecution 또는 tool-call/output 기반 |
| agent write | Write/Edit/MultiEdit | fileChange diff/path |
| command | Bash tool | commandExecution |
| 이미지 | image/paste cache | localImage/imageView + codex-clipboard temp |
| reasoning | transcript assistant content | reasoning item, opaque/encrypted 가능 |
| temp | /tmp, C:\tmp, Claude-specific dirs | CODEX_HOME/tmp, .tmp, sandbox, Windows Temp clipboard |
| config | .claude.json/.mcp.json | config.toml/project config/profile |
| SQLite | 핵심 저장소 아님 | state/thread_history/logs 등 핵심 projection |
| source index | projects/*.jsonl 직접 탐색 | session_index는 보조, raw sessions/state join 필요 |
| 보존기간 | Claude temp 실측 문서 있음 | Codex internal temp 정책은 별도 실측 필요 |
| 현재 clfx 지원 | parser·artifact·UI 연결 | Event 주석만 존재, 실제 adapter 없음 |

Claude의 uploads/file-history와 Codex의 fileChange는 모두 파일 증거를 제공하지만 동일한 구조가 아니다.

- Claude file-history는 원본/버전 snapshot과 transcript mapping이 핵심이다.
- Codex fileChange는 변경 diff/path projection이 핵심이다.
- Codex에서 원본 파일 전체를 복원하려면 fileChange diff, workspace 원본, Git, temp/cache, raw command output을 함께 확인해야 한다.

---

## 19. 수집 절차 권고

### 19.1 live 상태

Codex가 실행 중이면 다음이 동시에 변할 수 있다.

- rollout JSONL append
- history.jsonl append/compaction
- SQLite WAL append
- logs append
- temp helper 생성/삭제
- clipboard image 생성/정리

따라서 수집 시작/종료 시각, Codex version, 환경변수, 활성 process를 기록한다.

### 19.2 최소 보존 세트

    CODEX_HOME/
    ├─ sessions/
    ├─ history.jsonl
    ├─ session_index.jsonl
    ├─ state_5.sqlite*
    ├─ thread_history_1.sqlite*
    ├─ logs_2.sqlite*
    ├─ goals_1.sqlite*
    ├─ memories_1.sqlite*
    ├─ queue_1.sqlite*
    ├─ config.toml
    ├─ config.toml.bak
    ├─ tmp/
    ├─ .tmp/
    ├─ .sandbox/
    ├─ .sandbox-bin/
    └─ .sandbox-secrets/

추가:

- %TEMP%/codex-clipboard-*
- 실제 CODEX_SQLITE_HOME
- project .codex/config.toml
- 관련 workspace file stat/hash
- 필요 시 C:\tmp와 OS Temp

### 19.3 수집 후 검증

1. raw JSONL count와 state thread count 비교
2. state rollout_path 존재성 확인
3. thread_history distinct thread count 비교
4. WAL/SHM 존재성 확인
5. integrity_check
6. 각 파일 SHA-256
7. parse error line 목록
8. opaque/encrypted field count
9. command/fileChange count
10. temp inventory 및 access error
11. projection mismatch report
12. auth/sandbox secret 별도 보호 확인

---

## 20. 한계와 오판 방지

### 20.1 파일 존재 = LLM 작성 아님

CODEX_HOME/.tmp의 plugin cache, sandbox binary, clipboard image는 Codex와 관련 있지만, 해당 파일을 LLM이 task 중 작성했다는 직접 증거는 아니다.

### 20.2 command = syscall audit 아님

commandExecution은 명령 실행 증거다. Windows OS 수준에서 실제 파일 open/read/write를 확정하려면 Sysmon/ETW/Windows auditing 등 별도 수집원이 필요하다.

### 20.3 fileChange = 모든 write 아님

Codex가 fileChange로 보고하지 않는 외부 프로그램의 파일 수정, 사용자가 별도로 수정한 파일, shell 내부 redirection 결과가 projection에 누락될 수 있다. workspace stat, Git diff, OS file timeline을 함께 사용해야 한다.

### 20.4 SQLite projection = 전체 history 아님

17개 state thread와 6개 history projection thread의 차이가 관측되었다. projection이 비어 있거나 부분적이어도 raw rollout이 있으면 raw를 우선한다.

### 20.5 live 분석 자체가 증거를 변경할 수 있음

현재 Codex가 계속 실행 중인 상태에서 조사 명령을 수행했기 때문에 다음 값은 조사 중 증가할 수 있다.

- commandExecution
- agentMessage
- logs
- thread_history
- WAL size

최종 forensic acquisition은 live/격리/종료 상태를 명확히 구분해야 한다.

### 20.6 암호화 blob 해석 금지

gAAAAA 같은 prefix는 opaque/encrypted-looking pattern의 관측일 뿐, 알고리즘·키·복호화 가능성을 확정하는 근거가 아니다.

### 20.7 사용자 계정/ACL만으로 actor 귀속 금지

Windows Temp와 CODEX_HOME 파일의 OS owner는 사용자 계정일 수 있다. actor는 transcript command/fileChange/time/process correlation으로 판정해야 한다.

### 20.8 분석 도구 자체의 파일 접근과 증거 범위

이번 추가 점검으로 현재 도구의 “파일 접근 기록”은 두 범위로 나뉜다는 점을 명확히 했다.

| 범위 | 현재 의미 | Codex 확장 시 요구 |
|---|---|---|
| evidence read audit | roio를 거친 parser open 목록 | raw/SQLite/config/MCP/temp reader까지 동일 wrapper로 통합 |
| analysis output | JSONL 결과·웹 분석 산출물 작성 | 별도 output root, 생성 파일 manifest, evidence와 물리적 분리 |
| OS-level access | 현재 수집하지 않음 | 필요 시 ETW/Sysmon/Windows auditing |
| static/config read | 일부 builtin open으로 roio 밖 | audit 누락을 명시하거나 wrapper 경유 |

따라서 보고서에서 “파일 접근 기록을 분석했다”고 쓸 때는 commandExecution에 나타난 명령 문자열, projection의 fileChange, 실제 잔존 파일 stat/hash, OS syscall telemetry를 각각 다른 증거 계층으로 표시해야 한다. 네 계층을 하나의 “LLM 파일 접근 로그”로 합치면 과귀속이 발생한다.

---

## 21. 기존 프로젝트 참고 문서

현재 도구 및 기존 Claude 분석과의 연결:

- [기존 설계서](cli-llm-forensic-final/docs/설계.md)
- [Event schema](cli-llm-forensic-final/docs/event-schema.md)
- [기존 사용법](cli-llm-forensic-final/docs/사용법.md)
- [기존 temp·원본 보존 실측](cli-llm-forensic-final/docs/실측-temp-원본보존-원리.md)
- [논문 대비 신규 발견](cli-llm-forensic-final/docs/논문대비-신규발견.md)
- [artifact 확장 계획](cli-llm-forensic-final/docs/superpowers/plans/2026-06-18-clfx-B-아티팩트-해시귀속.md)
- [MCP/temp 계획](cli-llm-forensic-final/docs/superpowers/plans/2026-06-18-clfx-C-MCP통합-tmp보존.md)

기존 문서에서 Codex 경로가 언급되더라도 실제 parser 구현은 Claude 중심이다. 문서의 “Codex 지원 예정”과 현재 실행 가능한 기능을 혼동하면 안 된다.

---

## 22. 최종 결론

현재 도구는 파일 접근·temp·해시·보존·귀속을 분석할 수 있는 기반을 이미 갖추고 있지만, 실제 입력 adapter가 Claude에 고정되어 있어 Codex에 대해서는 해당 기능이 실행되지 않는다.

Codex는 Claude보다 더 풍부한 저장 구조를 가진다.

- raw rollout JSONL
- thread/state SQLite
- WAL/SHM
- commandExecution
- fileChange
- userMessage/localImage
- reasoning opaque/encrypted
- webSearch/imageView
- plugin/cache/sandbox/clipboard temp

따라서 Codex 분석은 단순히 “Codex JSONL을 Claude parser에 넣기”가 아니라 다음 원칙으로 구현해야 한다.

1. raw rollout JSONL을 1차 증거로 유지
2. SQLite는 projection/검색 가속기로 사용
3. main/WAL/SHM를 함께 보존
4. command intent와 OS syscall을 구분
5. fileChange와 실제 파일 stat/hash를 JOIN
6. CODEX_HOME internal tmp, plugin cache, sandbox, clipboard를 artifact class로 분리
7. temp self-work 귀속은 session/time/hash/process correlation이 있을 때만 확정
8. encrypted reasoning은 복호화하지 않고 opaque metadata로 보존
9. 기존 deterministic query/analysis 엔진은 normalized Event 위에서 재사용
10. UI와 report에 confidence와 source citation을 표시

최종 판정은 **전체 기능 업데이트 가능**이다. 다만 현재 도구가 Codex의 파일 접근·temp self-work를 이미 분석하고 있다고 말할 수는 없으며, 위 source/SQLite/artifact/UI/test 확장을 구현한 뒤에야 Codex 분석 결과를 도구 기능 전체에 연결할 수 있다.

---

## 부록 A. 조사 당시 숫자 요약

| 영역 | 관측값 |
|---|---:|
| Codex CLI | 0.147.0 |
| rollout JSONL | 17 files |
| rollout total size | 약 137.3MB |
| state threads | 17 |
| thread_history projection threads | 6 |
| thread turns | 254 |
| projected items | 3,524 |
| commandExecution | 929 |
| fileChange | 130 |
| fileChange entries | 144 |
| userMessage | 255 |
| agentMessage | 461 |
| reasoning | 1,581 |
| webSearch | 128 |
| imageView | 26 |
| logs rows | 14,968 |
| CODEX_HOME/tmp files | 18 |
| CODEX_HOME/.tmp files | 5,961 |
| sandbox files | 8 |
| sandbox-bin files | 2 |
| sandbox-secrets files | 1 |
| Windows codex clipboard PNG | 20 |
| rollout encrypted-looking files | 15/17 |

수치는 live 상태 snapshot이다. 재현 시 수집 시각·version·환경변수·각 파일 hash를 함께 기록해야 한다.

## 부록 B. 구현 완료 후 기대되는 분석 출력

    {
      "ts": "2026-08-18T...",
      "agent": "codex",
      "session": "...",
      "actor": "agent",
      "action": "write",
      "target": "workspace/path/file.py",
      "preview": "<diff summary>",
      "tags": [
        "codex:item_type=fileChange",
        "codex:kind=update",
        "origin:windows"
      ],
      "source": {
        "file": "sessions/.../rollout-....jsonl",
        "line": 1234
      },
      "meta": {
        "thread_id": "...",
        "turn_id": "...",
        "item_id": "...",
        "rollout_ordinal": 456,
        "sqlite_projection": "thread_history_1.sqlite",
        "confidence": "high"
      }
    }

이 형태를 사용하면 기존 파일 패널·timeline·query·secret mask·artifact hash·attestation 기능을 유지하면서 Codex 전용 증거 provenance와 불확실성을 함께 표시할 수 있다.
