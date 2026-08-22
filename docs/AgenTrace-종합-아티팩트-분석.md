# AgenTrace 종합 아티팩트 분석 — 로컬 + 모바일 원격제어

> **발표자료를 만든다면 `docs/AgenTrace-아티팩트-인계문서.md` 를 보라.** 아티팩트 파트는
> 그쪽이 최신본이다 — iOS(S1·S2)까지 4시나리오가 전부 채워져 있고 요청 구조(§2 로컬 / §3 원격)로
> 다시 짰다. 이 문서는 **도구 구현·검증(§9~§12)** 을 함께 담은 전체 기록으로 남긴다.

**과제** AgenTrace — 모바일 원격제어 포함 CLI AI 코딩 에이전트 행위 주체 식별 포렌식 도구
**작성** 2026-08-22 · 패널 제작 기준 종합본 (경진대회 마감 2026-08-23 23:00)

| 구간 | 상태 | 근거 |
|---|---|---|
| 로컬 Claude Code 아티팩트 | 완료 | 기존 구현·발표자료 |
| 로컬 Codex CLI 아티팩트 | 완료 | `docs/codex-지원-엔진스펙.md` · `codex-아티팩트-분석-교차검증.md` |
| Android × Claude 원격제어 (S3) | **완료** | `llm모바일아티팩트/docs/모바일-원격제어-실측.md` 관측 1~26 |
| Android × Codex 원격제어 (S4) | **완료** | 같은 문서 관측 27~62 |
| iOS × Claude (S1) · iOS × Codex (S2) | **추가 예정** | — |
| 도구 구현·정확도 | 완료 | `docs/Codex-정확도-측정결과.md` |

---

## 0. 한 문단 요약

CLI AI 코딩 에이전트는 로컬에 실행 흔적을 남긴다. 여기에 **모바일 원격제어**가 더해지면
**지시 주체(폰의 사람)와 실행 주체(로컬 PC의 에이전트)가 서로 다른 기기로 분리**된다.
Android 실측 결과 **관측 범위(벤더당 원격 지시 2회)에서 양 벤더 모두 "내용의 증거는 로컬 PC에만 남고,
폰에는 누가·언제·어디에 붙었는지만 남았다."**
따라서 사건 재구성의 1차 증거는 로컬이고 폰은 결속·정황 증거다. 다만 **폰만 압수해도
과거 원격 작업 디렉터리 목록이 드러나** 작업 주제가 추론된다(Codex, 26건 실측).

---

## 1. 대상·환경

### 1.1 검증 환경 (버전 고정)

| 구분 | 항목 | 버전 |
|---|---|---|
| 로컬 | Claude Code CLI | **2.1.238** |
| 로컬 | Codex CLI | **0.149.0**(원격제어 실측) / 0.147.0(로컬 파서 실측) |
| 로컬 | OS | Ubuntu 24.04.3 LTS on WSL2 · Windows 11 |
| 단말 | Galaxy A23 (SM-A235N) | Android 13 / SDK 33 · **Magisk 루팅** |
| 단말 | Claude 앱 | `1.260817.0` (minSdk 32 / targetSdk 36 · 서명 v3) |
| 단말 | ChatGPT 앱 | `1.2026.223` (minSdk 32 / targetSdk 37 · 서명 **v4**) |
| 취득 | adb | 1.0.41 / 36.0.0 · read-only (`find`/`stat`/`sha256sum`) |

> **버전 의존성**: 메시지 단위 원격 판별(§5.4·§6.6)은 해당 CLI 버전의 레코드 형식에 의존한다.
> 세션 브리지 ID·enrollment 같은 구조적 마커는 버전 의존이 낮다.
> → **1차 근거는 구조적 마커, 메시지 단위 판정은 보강 근거.**

### 1.2 취득 원칙

- 원본 **read-only**. 쓰기 경로 원천 차단, 취득 시점 SHA-256 매니페스트 기록
- SQLite는 **main + `-wal` + `-shm` 동시 취득** — 아래에서 반복 확인되듯 본체는 껍데기이고 실데이터가 WAL에 있다
- 결정성: 같은 입력 → 같은 출력(정렬 고정)

---

## 2. 로컬 아티팩트 — Claude Code

### 2.1 위치

| 경로 | 내용 | 증거 등급 |
|---|---|---|
| `~/.claude/projects/<프로젝트>/<세션UUID>.jsonl` | **세션 전사 — 1차 증거.** 프롬프트·응답·도구호출·결과 전문 | 필수 |
| `~/.claude/sessions/<pid>.json` | 실행 중 세션 상태. `bridgeSessionId` 보유 시 **원격 연결 증거** | 휘발성 보조 |
| `~/.claude/sessions/<pid>.<sha256>.key` | 메시징 소켓 인증용 추정 — 원격 마커 **아님** | 무관 |
| `~/.claude.json` | `hasUsedRemoteControl` · `remoteDialogSeen` · `remoteControlUpsellSeenCount` · `oauthAccount` | 보조 |
| `~/.claude/history.jsonl` | 프롬프트 이력 | 보조 |
| `~/.claude/file-history/` · `uploads/` · OS temp | 원본 보존·붙여넣기 캐시 | 보조 |
| `.claude.json` / `.mcp.json` | MCP 서버 설정 | 설정 증거 |

### 2.2 세션 JSONL 레코드 타입 (실측 분포 예)

`attachment` 45 · `assistant` 16 · `user` 11 · `system` 5 · `mode` 4 · `permission-mode` 4 ·
`last-prompt` 4 · **`bridge-session` 3** · `queue-operation` 2 · `atis-latch` 2 · `ai-title` 2 ·
`file-history-snapshot` 1

### 2.3 핵심 성질

- **`bridge-session` 레코드가 턴마다 반복 기록**된다(한 세션에서 5→8회 증가 관측) → 세션 수명 중 **어느 구간이 브리지 상태였는지**를 턴 단위로 재구성 가능
- 그 레코드가 `ownerAccountUuid`·`ownerOrganizationUuid`를 품는다 → 세션 JSONL 단독으로 계정·조직 결속
- `type:"system"` `subtype:"bridge_status"`에 활성화 안내문과 **공유 URL 원문**이 남는다

---

## 3. 로컬 아티팩트 — Codex CLI

### 3.1 위치

우선순위: `CODEX_HOME` env → config `sqlite_home` → `CODEX_SQLITE_HOME` → 기본 `~/.codex`.
**SQLite root가 CODEX_HOME과 분리될 수 있다**(실증).

| 경로 | 내용 | 증거 등급 |
|---|---|---|
| `sessions/YYYY/MM/DD/rollout-*.jsonl` | **1차 증거.** 지시·실행·응답 전문 | 필수 |
| `state_5.sqlite` `threads` | thread 카탈로그(`rollout_path`·`cwd`·`git_branch`·`first_user_message`) | 필수(교차) |
| `state_5.sqlite` `remote_control_enrollments` | **원격제어 등록**(§6.3) | 원격제어 1차 |
| `logs_2.sqlite` | runtime 로그. **원격 판별자 `client_name`**(§6.6) | 일반=보조 / **원격제어=1차** |
| `thread_history_1.sqlite` `thread_turns`/`thread_items` | item projection + byte offset | 보조(불완전) |
| `goals_1.sqlite` | 목표·상태·budget | 있음 |
| `memories_1.sqlite` · `queue_1.sqlite` | 파생 요약 · 큐 | 보조 / 없음 |
| `app-server-daemon/settings.json` | **`{"remoteControlEnabled": true}`** | 원격제어 1차 |
| `app-server-daemon/app-server.pid` · `.stderr.log` | 데몬 pid·프로세스 시작시각·stderr | 보조 |
| `app-server-control/app-server-control.sock` | 유닉스 제어 소켓(`srw-------`) | 보조 |
| `auth.json` | **평문 JWT**(`id_token`·`access_token`·`refresh_token`) · `account_id` | 민감·결속축 |
| `config.toml`(+`.bak`) | MCP·hooks·plugins·sandbox | 설정 증거 |
| `history.jsonl` · `session_index.jsonl` | 보조 인덱스 — **비권위**(중복·누락) | 보조 |
| `tmp/` `.tmp/` `shell_snapshots/` `thread-writer-locks/` | 실행 부산물 | 보조 |
| `packages/standalone/` | **standalone 설치본** — 원격제어 전제(§6.2) | 판정 근거 |

**주의**: DB 파일명 숫자 접미사(`_5`·`_1`·`_2`)는 schema version이 **아니다**
(`_sqlx_migrations` max = state_5:46 · thread_history_1:4 · logs_2:2). glob + `_sqlx_migrations`로 판별.

**커버리지 경고**: `state_5.threads` 341 vs `thread_items` distinct thread **21**.
projection만으로 사건을 확정하면 안 된다.

### 3.2 기록 계층이 3개다 — 이름 규칙이 전부 다르다

| 계층 | 경로 | 규칙 | 실측 |
|---|---|---|---|
| raw response_item | `payload.type` | snake_case | `reasoning` 20,857 · `function_call` 15,848 · `message` 11,305 · `custom_tool_call` 10,186 |
| raw item | `event_msg.payload.item.type` | **PascalCase** | `CommandExecution` 2,252 · `AgentMessage` 423 · `Extension` 162 · `UserMessage` 83 · `FileChange` 64 |
| SQLite projection | `thread_items.item_type` | **camelCase** | `commandExecution` · `fileChange` · `userMessage` · `webSearch` |

**같은 이름, 다른 구조** — 원형 파서 공유 금지, 정규화 계층만 공유:

| 필드 | raw | SQLite |
|---|---|---|
| `FileChange.changes` | 경로-키 **map**. value keyset `{type,content}` 22 / `{type,move_path,unified_diff}` 46 | **배열** `{path,kind,diff}` 68 entry |
| `command` | **argv 배열**(2,274/2,274) | **문자열**(2,103/2,103) |
| `cwd` | percent-encoded **`file://` URL** | 절대경로 |
| 이미지 | `local_image` | `localImage` |

### 3.3 스키마 era — 버전이 아니라 **실행 모드**에도 좌우된다

로컬 표본 rollout 344파일에 **cli_version 29종**(0.63.0~0.147.0).

| 증거 | legacy 계층 (item 레코드 없는 파일 **329개**) | item 계층 (**24개**) |
|---|---|---|
| 사용자 발화 | `event_msg.user_message` 2,231 | `item.UserMessage` 83 |
| 에이전트 응답 | `event_msg.agent_message` 7,101 | `item.AgentMessage` 423 |
| 명령 실행 | `function_call exec_command\|shell_command\|run` 12,445 + `custom_tool_call exec` 6,393 + `exec_command_end` 1,254 = **20,092** | `item.CommandExecution` 2,281 |
| 파일 쓰기 | `apply_patch` 1,797 + `patch_apply_end` 1,702 = **3,499** | `item.FileChange` 66 |
| envelope `ordinal` | 없음 | 전 라인 존재 |

**같은 0.147.0 바이너리인데 `originator`로 계층이 갈린다** —
`codex-tui`(대화형) 22파일 = item / **`codex_exec`(헤드리스) 6파일 = legacy**.
→ item 계층만 보는 분석은 **관측된 `codex exec` 세션(6파일) 전체에서 이벤트를 얻지 못한다.**

**정량 영향** — item 계층만 구현한 파서의 관측 한계. 두 가지로 표기한다.

**① 파일 기준 (안정 지표 · 패널 헤드라인용)**
→ item 계층만 구현하면 **세션 파일 329/353 = 93.2%에서 명령·쓰기 이벤트를 0건** 낸다.
비율이 아니라 이진 속성(그 파일에 `item_completed` 레코드가 있느냐)이라 코퍼스가 커져도 흔들리지 않는다.

> **판정은 버전이 아니라 레코드 유무로 해야 한다.** `cli_version`으로 era를 나누면
> legacy 파일 323개만 잡히지만, **`codex_exec` 헤드리스 6파일은 0.147을 보고하면서도
> `item_completed`를 한 건도 내지 않는다**(§3.3 originator 분기). 그 6개를 더한 329개가
> 단일 스키마 파서의 실제 0건 구간이다. 이 값은 `tests/test_panel_numbers.py`가 기계 검증한다.

**② 레코드 기준 (2026-08-22 스냅샷 · 중복제거 후)**

| 지표 | legacy | item(0.147+) | 회수율 |
|---|---:|---:|---:|
| 명령 | 21,482 | 2,789 | **11.5%** |
| 파일 쓰기 | 2,222 | 171 | **7.1%** |

> **중복제거 근거** — `exec_command_end` 1,254개 call_id가 `function_call(exec_command)` 와
> **완전히 일치**한다(교집합 1,254 = end 전체). end는 fc의 *결과*지 별개 명령이 아니다.
> 쓰기도 `apply_patch` 1,797 ∩ `patch_apply_end` 1,702 = **1,277 중복** → union 2,222.
> 단순 합산(3,499)은 같은 쓰기를 두 번 센다. 명령 분모도 22,736 → 21,482로 줄어든다.
>
> **이 비율은 코퍼스의 현재 상태이지 도구의 속성이 아니다.** 0.147+ 사용이 늘수록 올라간다
> (실제로 측정 사이에 `FileChange` 66→171, `CommandExecution` 2,281→2,789로 증가했다).
> **패널에는 ①을 싣고, ②는 스냅샷 시각과 함께 각주로 둔다.**

→ 파서는 버전 하드코딩이 아니라 **구조 탐지(capability sniffing)** 로 판정하고,
발견된 파서를 전부 실행해 `id`/`call_id`로 병합한다. 미지 구조는 `unsupported_schema`로 표면화한다.

### 3.4 암호화·opaque

`encrypted_content` 21,507회 / **305파일**, `gAAAAA` 23,718회 / 305파일(344 중 88.7%).
→ 존재·길이·위치·session/turn 연결만 보존. 복호화 시도 안 함.

---

## 4. 행위 주체 식별 (로컬)

### 4.1 도메인

`actor = user | agent | unknown`. **subagent는 actor가 아니라 agent 인스턴스 계층**
(`meta.agent_kind`·`parent_thread_id`·`depth`·`agent_path`).
`turn_context`·`world_state`·`token_count` 같은 system record는 **Event를 만들지 않는다.**

### 4.2 근거

| 판정 | 근거 |
|---|---|
| **user** | `user_message` / `UserMessage`와 그 안의 첨부 이미지 · `CommandExecution.source == user_shell` |
| **agent** | 그 외 `CommandExecution`(에이전트 턴 스트림 안의 기록) · 도구 호출과 연결된 실행 |
| **unknown** | 세션/턴 연결 자체가 없을 때만 |

**금지** — 이름에 user가 들어가도 사람 입력이 아닌 것:
`response_item.message role=user` 2,968 · `role=developer` 815(모델 입력 뷰, Event로 만들면 과계수) ·
`turn_context.user_instructions` 786 · `session_meta.base_instructions` 349 · `history.jsonl` 2,266

실측(2026-08-22 17:20 스냅샷): agent 34,698 / user 2,392 / **unknown 0**.
`user_shell` **2건**이 명령 이벤트 22,851건 중에서 분리된다.

### 4.3 파일 작성 확신도 4등급

| 등급 | 조건 |
|---|---|
| `high` | 구조화 기록 + 같은 turn/thread + **잔존 파일 stat/hash 상관** |
| `medium` | 구조화 write 기록(FileChange·apply_patch·patch_apply_end) + completed + path |
| `low` | 미완료/타깃 없음 · command 리다이렉션 추정 |
| `unknown` | 디스크에만 존재, transcript 연결 없음 |

**shell로 만든 파일은 `FileChange`에 안 잡힌다** — redirection 명령 51건 중 21건이 same-turn
FileChange 없음(16건 exit 0), write-like 227건 대 FileChange 66건에 same-turn path 매칭 **0**.
→ 도구는 이 부류를 `action=write`로 **주장하지 않고** `meta.write_target` + `confidence=low`로 후보만 표면화한다.

### 4.4 개별 승인 여부는 판정 불가

`approval_policy`: `on-request` 1,424 / `never` 1,922.
`sandbox_policy`는 문자열이 아니라 `{type:…}` 객체: `workspace-write` 1,428 / `read-only` 88 / `danger-full-access` 1,830.
개별 승인 record는 전수 검색 **0건** → policy snapshot만 기록하고 `approved_by_user`는 **기록 금지**.

---

## 5. 모바일 원격제어 S3 — Android × Claude Code

### 5.1 경로 전체

```
[폰 Claude 앱]                        [서버]                    [로컬 PC]
 shared_prefs/…_code_remote.xml   claude.ai/code/            ~/.claude/
   recap_dismissed_at              session_<ULID>              sessions/<pid>.json  bridgeSessionId
   default_session_target                                      projects/**/<uuid>.jsonl
     (environment_id)                                            ├ bridge-session (턴마다)
                                                                 ├ promptSource="queued" ← 원격
                                                                 └ tool_use.input (실행된 명령)
```

### 5.2 폰 측 잔존물 (`com.anthropic.claude`, UID 10332)

| 파일 | 내용 |
|---|---|
| `shared_prefs/user_prefs_AccountId(...)_OrganizationId(...)_code_remote.xml` | **`recap_dismissed_at`** = `{"session_<ULID>": <epoch_ms>}` · **`default_session_target`**(환경 kind·`environment_id`·name·created_at·state) · `cowork_starter_seen` · `github_connected` |
| `…_code_remote_read_state.xml` | `pending_acks={}` |
| `…_agent_chat.xml` | `has_seen_dispatch_feature` |
| `cache/app_start/acc_<...>/org_<...>/cache.json` (195KB) | 계정 entitlement — **`claude_code_remote_control: available`** · `cowork_remote_control` · `claude_code_desktop_bypass_permissions` 등 56건. 계정 이메일·실명 평문 |
| `databases/acc_<...>_org_<...>_claude_cache.db` | 대화 캐시(§5.5) |
| `shared_prefs/user_cookies_<accountUuid>.xml` | **평문 세션 쿠키 9건**(`sessionKey` 268자, `sk-ant` 접두사 노출) |
| `app_webview/Default/Cookies` | **두 번째 평문 사본**(`encrypted_value` 길이 0) |
| `shared_prefs/trusted_device.xml` | **암호화**(Tink/AndroidKeyStore) — 같은 앱 안에서 보호 수준이 다르다 |
| 식별자군 | `device_id_prefs.xml` · Segment · `files/INSTALLATION` · datadog · sentry · `siftscience.xml` · `anthropic-device-id` |
| 시각 메타 | `app_stats.xml`(`last_resumed_at`·`creation_count`) · kronos `cached_offset`(**NTP 보정 — 단말 시계 신뢰도 근거**) |

### 5.3 결속 — 브리지 세션 ID

동일 ULID가 **접두사만 바꿔 3곳**에 나타난다:

| 측 | 위치 | 값 |
|---|---|---|
| 폰 | `code_remote.xml` `recap_dismissed_at` | `session_<ULID>` |
| 로컬 | `sessions/<pid>.json` `bridgeSessionId` | `session_<ULID>` |
| 로컬 | 세션 JSONL `bridge-session` | **`cse_<ULID>`** |

→ **문자열 일치 검색으로는 못 잇는다. ULID 본문으로 매칭해야 한다.**

시각 대조(2회 독립 재현, 부호 일관):

| 회차 | 폰 `recap_dismissed_at` | 로컬 원격 프롬프트 | 차이 |
|---|---|---|---|
| 1차 | 16:37:29.694 | 16:37:28.721 | **+0.973초** |
| 2차 | 16:51:32.221 | 16:51:29.946 | **+2.275초** |

**2회 모두** 폰 값이 뒤 → 단말 시계 오차가 아니라 "프롬프트 전송 → 폰이 recap 갱신" 순서의 반영.

> **한계**: `recap_dismissed_at`은 **세션당 값 1개**다. 2차 지시가 1차 값을 덮어썼다.
> 폰 단독으로는 "몇 번 지시했는지"를 알 수 없다 — 횟수·순서는 로컬 JSONL에만 있다.

### 5.4 원격/로컬 메시지 판별 — 로컬 JSONL 단독 가능

| | **원격 (폰)** | 로컬 타이핑 (유휴) | 로컬 타이핑 (작업 중) |
|---|---|---|---|
| `user` 레코드 | 생성 | 생성 | **미생성** |
| `promptSource` | **`queued`** | `typed` | (없음) |
| `origin.kind` | `human` | `human` | `human`(attachment 내부) |
| `queue-operation` | enqueue → **`dequeue`** | 없음 | enqueue → **`remove`** |
| 본문 전달 | `user.message.content` | `user.message.content` | **`attachment.queued_command.prompt`** |

**판별 규칙:**

| 조건 | 판정 |
|---|---|
| `type=user` ∧ `promptSource="queued"` ∧ `origin.kind="human"` | **원격 입력** |
| `type=user` ∧ `promptSource="typed"` | 로컬 직접 입력 |
| `type=attachment` ∧ `attachment.type="queued_command"` | 로컬 큐 입력 |
| `promptSource="system"` ∧ `origin.kind="task-notification"` | 시스템 생성 |

위양성 검증 완료 — 로컬 조건 5회(유휴 4·작업 중 1) 어느 쪽도 `queued`+`human` 조합을 만들지 못했다.
단 표본이 작고(원격 2·로컬 5) **v2.1.238 레코드 형식에 의존**한다.

### 5.5 폰은 원격 지시 **내용**을 저장하지 않는다

폰 취득본 전수 문자열 검색:

| 검색어 | 히트 |
|---|---|
| 세션 ULID | `code_remote.xml` **1건** |
| `environment_id` | `code_remote.xml` **1건** |
| 지시 문구 / 표식 파일명 | **0건** |

`claude_cache.db` 행수 변화 0(대화 15→15, 메시지 22→22).
→ **원격 Code 세션의 대화 내용은 단말에 저장되지 않는다.** 일반 대화와 저장 경로가 완전히 다르다.

**대조 — 일반 대화는 폰에 남는다**: 로그인만 해도 대화 목록 **15건**(제목·최대 3.8KB 요약·모델·설정)이
평문 SQLite로 내려앉고, 대화를 열면 본문 22건이 캐시된다(`tool_use.input` 25.7KB 포함).
단 **활성 분기만** 남는다(`index` 0~87 중 22건 — 편집·재생성으로 버려진 형제 분기는 없음).

> **오해 방지**: 단말 캐시 15건은 "사용자가 폰에서 본 것"이 아니라 **로그인 시 서버가 밀어준 최근 목록**이며
> 그 범위는 사용자 행위가 아니라 **서버 페이지 크기**가 정한다. 스크롤해도 늘지 않는다(15 = 상한).

### 5.6 존속 — 종료 방식에 달렸다

| 종료 방식 | `sessions/<pid>.json` |
|---|---|
| 정상 종료(`/exit`) | **삭제** — 원격 마커 소실 |
| 비정상 종료(터미널 종료·WSL 셧다운·크래시) | **잔존**, 재부팅 후에도 유지 |

**항구적 증거는 세션 JSONL이다.** 정상 종료 후에도 JSONL과 그 안의 `bridge-session` 레코드
8건 전부, `promptSource="queued"` 모두 보존된다.

→ **취득 우선순위**: 1차 = `~/.claude/projects/**/*.jsonl`, `~/.claude/sessions/`는 **휘발성 보조**.

**브리지 ID는 resume를 넘어 지속된다** — 논리 세션 1개가 프로세스 4개로 갈라져도
`bridgeSessionId`는 유지되고 JSONL은 **단일 파일**이다.
→ "브리지 ID 1개 = 원격제어 1회"가 아니라 **"= 원격 연결된 논리 세션 1개"**.

### 5.7 사슬 완성

| 시각(KST) | 내용 |
|---|---|
| 16:51:29.946 | 원격 프롬프트 `/tmp/AGENTRACE-MARKER.txt 읽어서 nonce줄 그대로 답해줘`(`queued`+`human`) |
| 16:51:34.187 | `tool_use` **Bash `cat /tmp/AGENTRACE-MARKER.txt`** |
| 16:51:37.951 | `tool_result` — nonce 포함 |
| 16:51:41.119 | 답변 `nonce: dc70739f05d5cf342a327e1ec577c561` |

표식 파일 SHA-256 `b8f370de…`. **폰 지시 1건이 로컬에서 어떤 명령으로 실행됐는지 단일 표식으로 특정된다.**

---

## 6. 모바일 원격제어 S4 — Android × Codex (ChatGPT 앱)

### 6.1 경로 전체

```
[폰 ChatGPT 앱]                          [서버]                          [로컬 PC]
 files/datastore/                   android.chat.openai.com/       ~/.codex/
  …_codex_remote_hosts.json           backend-api/codex/            app-server-daemon/settings.json
    saved_hosts[] · 작업디렉터리 26건    remote/control                state_5.sqlite remote_control_enrollments
    last_connection_used_at (⚠오지시)                                logs_2.sqlite  client_name ← 원격 판별
  …_codex_remote_control_            wss://chatgpt.com/backend-      sessions/**/rollout-*.jsonl (내용)
    enrollments.json                  api/wham/remote/control/       auth.json (평문 JWT)
    ECDSA P-256 공개키만               server{,/enroll,/refresh}
```

**폰과 로컬이 서로 다른 엔드포인트를 쓴다** — 네트워크 탐지 규칙은 양쪽을 따로 등록해야 한다.

### 6.2 전제 조건 — 벤더별로 다르다

| | Claude Code | Codex |
|---|---|---|
| 설치 형태 | 무관(`/remote-control` 즉시 동작) | **managed standalone 설치 필수** — npm 설치본은 실행 거부 |
| 계정 인증 | 추가 인증 없음 | **계정 MFA 필수**(미충족 시 enroll HTTP 403) |
| 페어링 | 없음 | `codex remote-control pair` — `manualPairingCode` 9자(`XXXX-XXXX`), **수명 10분** |

→ **"이 머신이 Codex 원격제어 대상이 될 수 있었는가"는 설치 형태로 판정된다.**
관측 버전(0.149.0)에서 npm 설치본은 실행이 거부됐다. standalone은 정적 네이티브 바이너리라
프로세스를 `node` 문자열로 찾으면 놓친다.

### 6.3 로컬 측 아티팩트

| 경로 | 내용 |
|---|---|
| `app-server-daemon/settings.json` | **`{"remoteControlEnabled": true}`** — 호스트 단위 마커 |
| `app-server-daemon/app-server.pid` | `{"pid":…, "processStartTime":…}` |
| `state_5.sqlite` `remote_control_enrollments` | `websocket_url` `account_id` `app_server_client_name` `server_id` `environment_id` `server_name` `updated_at` `remote_control_enabled` |
| `logs_2.sqlite` `logs` | 엔드포인트·식별자·재연결 백오프·**소스 파일 경로**까지 평문 |
| `sessions/**/rollout-*.jsonl` | 지시 문구·실행 명령·응답 전문 |

**Claude와의 정보량 차이**: Claude는 **세션 단위**(세션마다 브리지 ID), Codex는 **호스트 단위**
(데몬 1개에 불리언 1개) → `settings.json`만으로는 **어느 세션이 원격 노출됐는지 알 수 없다.**

### 6.4 같은 이름의 서버가 둘 등록된다 ★

같은 물리 PC의 WSL CLI와 Windows Codex Desktop이 **각각 독립 enrollment**를 갖고,
WSL hostname이 Windows 머신명을 상속해 **`server_name`이 동일**하다.

| 컬럼 | WSL CLI | Windows Desktop |
|---|---|---|
| `server_name` | **`Hwansktop`** | **`Hwansktop`** ← 구분 불가 |
| `app_server_client_name` | (빈 문자열) | `Codex Desktop` |
| `server_id` | `srv_e_6a885fdc…` | `srv_e_6a8860b5…` |
| `environment_id` | `env_e_6a885fdc…` | `env_e_6a8860b5…` |
| `remote_control_enabled` | **NULL** | **`1`** |
| 저장 위치 | `~/.codex/state_5.sqlite`(WSL) | `C:\Users\<user>\.codex\state_5.sqlite` |

→ **`server_name`은 고유 식별자가 아니다.** 귀속에는 `server_id`·`environment_id`·`app_server_client_name`을 써야 한다.

### 6.5 폰 측 잔존물 (`com.openai.chatgpt`, UID 10334)

| 파일 | 내용 |
|---|---|
| `files/datastore/user-<opaqueId>__<uuid>_codex_remote_hosts.json` | `saved_hosts[]`(`slingshot:<environment_id>:8765`) · `selected_host_id` · **`remembered_working_directories_by_host`** · `last_connection_used_at_millis_by_host` · `has_ever_set_up_remote` |
| `files/datastore/user-…_codex_remote_control_enrollments.json` | `account_user_id` · `client_id` · `key_id` · **`public_key_spki_der_base64`** · `algorithm: ecdsa_p256_sha256` · **`protection_class: os_protected_nonextractable`** |
| `shared_prefs/com.auth0.authentication.storage.xml` | **평문 JWT** `access_token`(2,001자) · `id_token`(1,625자) · `refresh_token` — 페이로드에 **이메일·실명·사진 URL** |
| `files/datastore/global_cookie_storage.json` | 쿠키 23건 평문 |
| `databases/user-…_conversations.db` | 대화 캐시(본체 49KB + **WAL 276KB**) |
| `databases/user-…_websocket_topic_data.db` | 토픽 오프셋 5행 — **원격제어와 무관**(검증됨) |

**작업 디렉터리 유출 ★** — `remembered_working_directories_by_host`에 절대경로가 평문으로 남는다
(WSL 26건 · Windows 7~8건). 경로에 연구 주제·학회명·날짜가 들어 있어 **내용 추론까지 가능**하다.
Codex가 지시 문구를 디렉터리명으로 슬러그화하는 성질(`Documents\Codex\<날짜>\<슬러그>`)과 결합하면
**경로 목록만으로 과거 원격 지시의 주제를 추론할 수 있다.**

**장치 개인키만 비추출 ★** — `protection_class: os_protected_nonextractable`.
AndroidKeyStore(TEE/StrongBox)에 있고 파일에는 공개키만 있다.
→ **확인된 범위에서 유일하게 "루팅해도 못 뽑는" 아티팩트.** "루팅=전량 획득"은 과장이다.

### 6.6 원격 판별자 — `client_name` (별도 로그 DB)

| connection_id | `client_name` | 정체 |
|---|---|---|
| 1 | `codex_app_server_daemon` | 데몬 자신 |
| 3 | `codex-tui` + `codex_app_server_daemon` 혼재 | (연결 재사용) |
| **4** | **`codex_chatgpt_android_remote`** | **폰(ChatGPT Android)** |
| 5 | `codex-tui` | 로컬 터미널 |

`turn/start` RPC의 `connection_id`를 `client_name`에 **조인**해 판정한다.

> **구현 주의**: 최근 RPC 몇 건만 표본으로 보면 `codex-tui`의 `plugin/list` 노이즈에 묻혀
> `codex_chatgpt_android_remote`를 놓친다. 해법은 `turn/start` 필터가 아니라
> **연결별로 묶는 것**이다 — connection 0에 tui 노이즈가 아무리 많아도 connection 4는 오염되지 않는다.
> `turn/start`의 `connection_id`는 그 위에서 "실제로 턴을 몬 연결"을 고르는 데 쓴다.

### 6.7 rollout JSONL에는 원격 표시가 **없다** ★

같은 스레드의 로컬 입력과 원격 입력 레코드를 전문 대조한 결과 —
레코드 키·`payload` 키·`passthrough` 구조·`turn_context` 필드가 **전부 동일**.
**출처를 구분하는 필드가 하나도 없다.**

| 필요한 것 | 파일 |
|---|---|
| 지시 문구·실행 명령·응답 | `~/.codex/sessions/**/rollout-*.jsonl` |
| **원격/로컬 출처** | `~/.codex/logs_2.sqlite`(`client_name`) |

→ **rollout만 확보하면 "누가 지시했는지" 판정 불가.** Claude는 세션 JSONL 하나에 내용과 출처가
모두 있었다 — **취득 요건이 벤더별로 다르다.**

### 6.8 사슬 완성

| 시각(KST) | 사건 |
|---|---|
| 15:39:32 | `turn/start` **conn=4(`codex_chatgpt_android_remote`)** — 폰 지시 수신 |
| 15:39:58 | `exec` `rtk cat /tmp/AGENTRACE-MARKER.txt` |
| 15:40:02 | `task_complete.last_agent_message` = **`nonce: dc70739f…`**(28.0초) |

**부수 관측**: 실행 전 `SKILL.md`·`RTK.md`를 읽었다 →
**원격 지시도 로컬 에이전트 설정(AGENTS.md·스킬·프록시)을 그대로 상속한다.**

---

## 7. S3 ↔ S4 대비 (확정판)

| | Claude Code (S3) | Codex (S4) |
|---|---|---|
| 원격 모델 | 살아있는 세션에 **브리지** | 호스트 페어링 후 세션 이어받기 |
| 기존 CLI 세션 이어받기 | 가능 | 가능 |
| 전제 조건 | 세션에서 `/remote-control` | standalone 설치 + **계정 MFA** + `pair`(9자·10분) |
| 원격 지시 전달 | 세션에 프롬프트 주입 | 동일 — 로컬 TUI에 주입 |
| 로컬 마커 | `sessions/<pid>.json` `bridgeSessionId`(**세션 단위**) | `app-server-daemon/settings.json`(**호스트 단위**) + enrollment |
| 원격 판별자 | `promptSource="queued"` ∧ `origin.kind="human"` — 세션 JSONL **내부** | `client_name="codex_chatgpt_android_remote"` — **별도 로그 DB** |
| 내용+출처 단일 파일 | **예(1개)** | **아니오(2개 필요)** |
| 대상 오인 위험 | 낮음(세션 ID 고유) | **높음**(`display_name` 중복) |
| 폰에 남는 것 | 세션 ID·시각 | 호스트 목록·**작업 디렉터리 26건**·장치 공개키 |
| 폰에 지시 내용 | **없음** | **없음** |
| 정상 종료 후 | 세션 JSONL 잔존(`sessions/`는 삭제) | enrollment·rollout 잔존 |

### 공통 결론 ★

1. **"내용의 증거는 로컬 PC에만 있다"** — 관측 범위에서 두 벤더, 두 경로(신규 지시·세션 재개) 모두 그러했다
2. **폰은 "언제 어느 세션·호스트에 붙었나"의 증거** — 결속·정황 증거
3. **SQLite는 `-wal` 동시 취득 필수** — 앱·벤더 무관하게 본체는 껍데기, 실데이터는 WAL
4. **루팅 여부가 취득 결과를 이분한다** — 비루팅은 접근 불가(ChatGPT는 `adb backup`도 차단),
   루팅은 자격증명·PII가 복호화 없이 획득된다. **다만 "루팅=전량"은 아니다** —
   원격제어 장치 개인키는 AndroidKeyStore 비추출이라 오프라인 덤프로 얻을 수 없다(§6.5)

---

## 8. 오판 함정 — 이 연구의 실무 기여

| # | 유형 | 내용 |
|---|---|---|
| 1 | **위음성** | `remote_control_enrollments` **0행 ≠ 미사용** — enroll이 MFA로 거부돼도 0행. 구분은 `logs_2.sqlite`로만 |
| 2 | **위음성** | `~/.claude/sessions/`는 **정상 종료 시 삭제** — 비었다고 "원격제어 쓴 적 없음"이 아니다 |
| 3 | **위양성** | `settings.json` `true` + enrollment 행이 있어도 **채널은 죽어 있을 수 있다** — 토큰 서버측 무효화 시에도 마커는 "활성" |
| 4 | **위양성** | 폰 `last_connection_used_at`이 **실행 호스트를 오지시한다** — 실제 실행은 WSL인데 Windows 값이 갱신됨 |
| 5 | 오귀속 | `server_name` 중복 — 같은 이름의 다른 머신에 귀속될 수 있다 |
| 6 | 해석오류 | 폰 대화 캐시 15건은 **서버 페이지 크기**가 정한 상한 — "이 계정 대화가 15개"가 아니다 |
| 7 | 해석오류 | 캐시된 메시지는 **활성 분기만** — 편집·재생성으로 버려진 분기는 없다 |

> **결론 문구**: 설정 파일·DB 행은 **"설정된 적 있음"까지만** 말한다.
> **실제 가용 구간과 실행 주체는 로그로만 확정된다.**

**방법론 검증** — 표식 파일(nonce)이 설계 목적을 넘어 작동했다.
S4 1차 시도에서 지시가 **의도한 WSL이 아니라 Windows Desktop으로 갔는데**, nonce가 돌아오지
않은 것이 그 사실을 즉시 드러냈다. 이 검출이 없었다면 "Codex 원격제어로 로컬 명령 실행 확인"이라는
**오결론**을 낼 뻔했다.

---

## 9. 도구 구현·검증 결과

### 9.1 파이프라인

`원본 → read-only 취득 → 구조 탐지 파서 → 행위 주체 귀속 → 단일 Event → 분석·대시보드`

`Event(ts, agent, session, actor, action, target, preview, source{file,line}, tags, meta?)`
`action = prompt | read | bash | write | paste | response | mcp | search | spawn`

### 9.2 실측 (Codex 로컬 코퍼스)

| 항목 | 값 |
|---|---|
| rollout | **353파일** |
| 복원 이벤트 | **37,090** |
| actor | agent 34,698 · user 2,392 · **unknown 0** |
| 미지 스키마 | **0건** |
| SQLite | DB 6종 · threads 350 · turns 127 |
| 회귀 테스트 | **511건 통과**(+1 skip: iOS 미측정) |

> **이 절의 수치는 `2026-08-22 17:20` 스냅샷이다.** Codex를 쓸수록 계속 자란다 —
> 실제로 하루 사이 rollout 344→353, 이벤트 30,232→37,090으로 변했다.
> **패널에 인쇄할 값은 이 시각으로 동결하고 각주에 시각을 적는다.**
> 재확인: `python3 -m pytest tests/test_panel_numbers.py -q -s` (대조표 출력).
> `manifest N파일`은 SQLite 사이드카 체크포인트에 따라 변동하므로 **인쇄하지 않는다.**

### 9.3 정확도 (합성 통제 데이터, 각 100건)

| 시나리오 | 정확도 | 비고 |
|---|---|---|
| 주체 식별 | **100.0%** | legacy 100% · item 100% · 왜곡 30/30 |
| 접근 파일 판정 | **100.0%** | 누락 0 · 오탐 0 |
| MCP 호출 탐지 | **100.0%** | 누락 0 · 오탐 0 |

> **100%가 가리는 것**: ①shell redirection 파일 작성은 원리상 확정 불가(후보로만 표면화)
> ②**Codex에는 범용 파일 읽기 레코드가 없다** — `action=read`는 이미지 열람뿐이라
> Claude의 접근파일 정확도와 **나란히 놓으면 안 된다** ③개별 승인 여부 판정 불가

### 9.4 `origin_channel` — 폰 지시와 로컬 실행을 한 타임라인에

`meta.origin_channel ∈ {remote, local, unknown}`. **판별 못 하면 `unknown`, `local`로 폴백하지 않는다.**
필드 부재(판정 대상 아님)와 `unknown`(봤는데 못 가림)은 다르다 — 보고서에서 부재를 local로 읽으면 안 된다.

| | 근거 | 저장 위치 |
|---|---|---|
| Claude | `promptSource="queued"` ∧ `origin.kind="human"` = remote / `typed`+`human` = local | 세션 JSONL **1개** |
| Codex | `logs_2.sqlite` tracing span에서 `connection_id ↔ client_name` 조인 → `_remote` 접미사 | rollout + **logs_2 2개** |

**실데이터 (이 PC, 원격제어 사용 이력 있음)**

Claude — 원본 1,059파일 / 427,751줄:

| `promptSource` | 건수 | | 조합 | 판정 |
|---|---:|---|---|---|
| `typed` | 5,042 | | `queued` ∧ `human` **231** | **remote** |
| `sdk` | 1,950 | | `typed` ∧ `human` 4,514 | local |
| `system` | 600 | | origin 없는 구버전 레코드 | unknown |
| **`queued`** | **250** | | | |

→ Event 107,256건 중 **`remote` 246건** (2026-08-22 17:20 스냅샷) · `local` 5,018 · `unknown` 3,277 · 필드없음 98,715

> **원격 턴이 있는 세션 52개는 전부 로컬 턴도 가지고 있다.**
> 세션 단위로 채널을 매기면 틀린다 — 채널이 **Event 단위 필드**여야 하는 실측 근거다.

> `bridge_session_id`는 Event 13,254건에 붙었지만 서로 다른 브리지 ID는 **2개뿐**이고
> remote 246건 중 브리지 ID를 가진 건 **13건**이다(정상 종료 시 `sessions/` 삭제 때문).
> → 브리지 ID는 **보강 근거**이지 원격 판정의 필수 조건이 아니다.

Codex — `logs_2.sqlite` 22,855행:

| connection_id | client_name | 채널 | 턴 시작 |
|---|---|---|---|
| 0 · 3 · 5 | `codex-tui` | local | ✔(5) |
| 1 · 43 | `codex_app_server_daemon` | local | — |
| **4** | **`codex_chatgpt_android_remote`** (69행) | **remote** | **✔** |

> **`remote`로 판정된 Codex Event는 0건이다. 두 가지 이유가 겹쳐 있고 구분해야 한다.**
>
> ① **모집단 자체가 1건이다.** 이 PC에서 Codex 원격제어를 쓴 것은 **2026-08-22 실험 1회뿐**이다.
> `logs_2`는 08-10~08-22 12일치 22,877행을 담고 있는데 그중 원격 클라이언트 로그는
> **15:36:44~15:38:14의 90초 구간 69행**이 전부다. enrollment도 실험 중 수동 페어링
> 1행(08-21 23:25:32)뿐이다. → 검출 실패가 아니라 **검출 대상이 하나뿐**이었다.
>
> ② 그 유일한 스레드가 `thread/resume` 경로라 로컬 TUI(connection 5)에도 찍혀 `unknown`이 됐다.
> `meta.origin_channels_seen=["local","remote"]`에 관측을 남긴다.
> **결함이 아니라 스레드 단위 판정의 해상도 한계다.** 턴 단위로 가르려면 `turn/start`
> 타임스탬프와 rollout 턴을 시간창으로 맞춰야 하는데 그건 추정이라
> "양성 근거만" 규칙에서는 하지 않는다.
>
> → **Codex 판별자(`client_name`)는 실험 표본 1건에서만 검증됐다.** 반면 Claude 판별자는
> 실험과 무관한 과거 실사용 이력에서 검증됐다(아래).

**Claude와 Codex의 표본이 근본적으로 다르다** — 패널·보고서에서 두 수치를 나란히 놓을 때 반드시 밝힐 것:

| | Claude | Codex |
|---|---|---|
| 이 PC의 원격제어 사용 | **실사용 이력 다수** — `queued ∧ human` 231건이 **2026-07-31 ~ 08-22 18일**에 걸침 | **실험 1회(90초)** 가 전부 |
| 실험 이전 데이터 | **224건** (231건 중) | **0건** |
| 판별자 검증 표본 | 과거 실사용 + 통제 실험 | 통제 실험 단독 |

**이 필드가 말하지 않는 것** — 실행 위치가 아니라 **지시 출처**다. `remote`여도 명령은 전부
로컬 PC에서 실행됐다. 그게 요점이다: **"폰에서 시켰고 여기서 돌았다."**

---

## 10. iOS — 추가 예정

| # | 단말 | 에이전트 | 상태 | 계획 취득 경로 |
|---|---|---|---|---|
| S1 | iOS | Claude Code | **예정** | 암호화 백업(Finder/idevicebackup2) → `Manifest.db` 앱 도메인 → 앱 컨테이너 |
| S2 | iOS | Codex (ChatGPT 앱) | **예정** | 동일 |

### 10.1 수신 표 — Android 관측 축 6개에 S1·S2를 받아 적는다

Android에서 확립한 축을 그대로 쓴다. **Android 열은 확정값, iOS 두 열은 결과가 오면 채운다.**
값 칸이 `미측정`인 동안에는 그 축에 대해 **어떤 주장도 하지 않는다** — 빈칸을
"Android와 같다"로 읽으면 안 된다.

| # | 관측 축 | Android × Claude (확정) | Android × Codex (확정) | S1 iOS × Claude | S2 iOS × Codex |
|---|---|---|---|---|---|
| ① | **원격제어 마커 위치** | 폰 `code_remote.xml`(`recap_dismissed_at`·`default_session_target`) · 로컬 `sessions/<pid>.json` `bridgeSessionId` | 폰 `codex_remote_hosts.json`·`codex_remote_control_enrollments.json` · 로컬 `app-server-daemon/settings.json` + `state_5.remote_control_enrollments` | **미측정** | **미측정** |
| ② | **원격/로컬 판별자** | `promptSource="queued"` ∧ `origin.kind="human"` — 세션 JSONL **내부** | `client_name="codex_chatgpt_android_remote"` — **별도 로그 DB**(`logs_2`), `connection_id` 조인 | **미측정** | **미측정** |
| ③ | **폰↔로컬 결속축** | 동일 ULID 3표기(`session_…`/`cse_…`) · 시각차 +0.973s·+2.275s | `account_id` 일치 · `environment_id`/`server_id` | **미측정** | **미측정** |
| ④ | **폰에 지시 내용이 남는가** | **없음** — 전수 문자열 검색 0건, `claude_cache.db` 행수 변화 0 | **없음** — `DBMessageChunk` 재조립 후 검색 0건 | **미측정** | **미측정** |
| ⑤ | **자격증명 보호 수준** | 세션 쿠키 9건 평문(2곳 중복) · `trusted_device.xml`만 Tink 암호화 | JWT 3종 평문 · 쿠키 23건 평문 · **장치 개인키만 비추출**(`os_protected_nonextractable`) | **미측정** | **미측정** |
| ⑥ | **종료 후 존속** | `sessions/<pid>.json` 정상종료 시 **삭제** / 세션 JSONL·`bridge-session` **잔존** | enrollment·rollout **잔존** | **미측정** | **미측정** |

### 10.2 받을 때 같이 기록할 것

| 항목 | 이유 |
|---|---|
| iOS·앱 버전, 백업 암호화 여부, 탈옥 여부 | Android처럼 **버전 의존 결론**이 나온다(§12-3) |
| 취득 경로가 백업인지 파일시스템인지 | 같은 축이라도 **취득 한계선이 달라진다** |
| 표식 파일 nonce·SHA-256 | 사슬 완성(§5.7·§6.8)과 **오배송 검출**(§8 방법론 검증)에 필요 |
| 폰↔로컬 시각차 부호 | Android는 2회 모두 폰이 뒤였다 — iOS도 같은지 |
| 음성 결과 | "안 나왔다"도 결과다. §8 위음성 함정 1·2와 대조할 것 |

### 10.3 예상 쟁점

iOS는 `allowBackup` 개념이 없고 앱 컨테이너가 백업 포함 여부(`NSURLIsExcludedFromBackupKey`)로
갈린다 → **비탈옥 백업 경로에서 어디까지 나오는가**가 Android와 다른 한계선을 그을 것이다.

Android 결론 중 **iOS에서 뒤집힐 수 있는 것**을 미리 표시해 둔다 — 뒤집히면 §7 공통 결론을
손봐야 한다.

| Android 결론 | iOS에서 달라질 수 있는 이유 |
|---|---|
| "루팅 여부가 취득 결과를 이분한다" | iOS는 **백업이라는 중간 지대**가 있다 → 이분법 자체가 안 맞을 수 있다 |
| "폰에 지시 내용 없음" | 저장 경로가 플랫폼별 SDK에 달렸다 — 재검증 없이 이식 금지 |
| "장치 개인키만 비추출" | iOS Secure Enclave는 보호 범위가 다르다 |

---

## 11. 패널 반영 매핑

| 패널 단락 | 사용할 내용 | 그림 |
|---|---|---|
| ① 배경·목적 | 유출 주체가 사람→AI로 확장 · DLP 사각지대 · 전용 도구 부재 · **지시/실행 주체 분리** | (텍스트) |
| ② 방법·내용 | §9.1 파이프라인 · §3.2 3계층 · §4 주체 귀속 · §5~7 원격제어 경로 | `f2_hero` · **`fm_remote`** |
| ③ 결과 | §9.2 실측 · §9.3 정확도 · §5.7·§6.8 사슬 완성 · 대시보드 실화면 | `f6_metrics` · F5 캡처 |
| ④ 기대·파급 | 책임 소재 귀속 · 증거능력 · **기기 경계를 넘는 재구성** · 범용성 | (텍스트) |
| 하단 경고 | §8 오판 함정 | `fm_remote` 하단 띠 |

---

## 12. 한계

1. **iOS 미착수** — 본 문서의 모바일 결론은 Android 실측이다
2. **표본 크기 — 벤더별로 비대칭이다.** Claude는 실험과 무관한 과거 원격 사용 이력 224건이
   있어 판별자가 실사용 데이터에서 검증됐다. **Codex는 이 PC에서 원격제어를 쓴 적이 없고
   2026-08-22 실험 1회(90초)가 유일한 표본이다.** 따라서 Codex `client_name` 판별자는
   통제 실험에서만 검증된 상태이며, 다양한 실사용 패턴에서의 동작은 미검증이다
3. **버전 의존** — Claude Code 2.1.238 · Codex 0.149.0. 레코드 형식 변경 시 재검증
4. **미수집** — 세션 중 실시간 `logcat` · `dumpsys netstats`(앱 단위 집계라 호스트 구분 불가) · MITM 복호화(범위 밖)
5. **자격증명 재사용 가능성 미검증** — 탈취된 토큰이 실제로 원격제어 채널 접속에 쓰일 수 있는지는 검증하지 않았다(연구 범위 밖)
6. **취약점 주장 아님** — 평문 자격증명 저장은 안드로이드 기본 방어선(UID 격리·FBE) 안에 있다.
   본 문서는 이를 **취득 한계선**으로 기술하며 보안 취약점으로 주장하지 않는다

---

## 참조

- `docs/codex-지원-엔진스펙.md` — Codex 파서 구현 기준서
- `codex-아티팩트-분석-교차검증.md` — 원 분석문서 교차검증(7라운드)
- `docs/Codex-정확도-측정결과.md` — 정확도 측정 상세
- `docs/모바일-원격제어-분석-계획.md` — 4시나리오 계획·취득 절차
- `llm모바일아티팩트/docs/모바일-원격제어-실측.md` — Android 실측 원본(관측 63건)
- `llm모바일아티팩트/output/패널-인계-모바일원격제어.md` — 도식 인계
- 신청서 `AgenTrace_캡스톤디자인 경진대회 설계 계획서`
