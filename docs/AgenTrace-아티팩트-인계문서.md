# AgenTrace — CLI AI 에이전트 아티팩트 분석 (발표자료 제작용 인계 문서)

> **이 문서의 용도**: 패널·발표자료를 만드는 팀원이 **이 문서 하나만 보고** 슬라이드를 짤 수 있게  
> 한 것이다. 연구 목적·배경은 제외했다. 실측으로 확인한 사실만 싣고,  
> 확인하지 못한 칸은 **미측정**이라고 그대로 적었다.
> **표기**  
> `[폰]` 모바일 단말 · `[로컬]` PC · `✗` 확인했으나 없음 · `△` 조건부 · ` ` 발표에서 강조할 포인트  
> `[OBSERVED]` 직접 관측 · `[INFERRED]` 관측에서 추론 · `[HYPOTHESIZED]` 미검증 가설
> **원본 근거**: 로컬 = `docs/AgenTrace-종합-아티팩트-분석.md`,  
> 모바일 = `C:\projects\llm모바일아티팩트\output\원격연동-아티팩트.md` (VR 번호로 추적)
> **수치 동결 시각**: 2026-08-22 17:20 · 재확인 `python3 -m pytest tests/test_panel_numbers.py -q -s`

---

## 0. 측정 조건 (슬라이드에 반드시 각주로)

### 0.1 단말·취득 방법

|           | 로컬 PC                   | Android                                        | iOS                                     |
| --------- | ------------------------ | ---------------------------------------------- | --------------------------------------- |
| 대상       | Windows 11 + WSL2 Ubuntu | SM-A235N · Android 13 (SDK 33) · **Magisk 루팅** | iPhone12,1 · iOS 26.5 (23F77) · **비탈옥** |
| 취득       | 파일시스템 read-only 복사   | `adb exec-out` + `su` 전량                       | `pymobiledevice3 backup2` **평문 백업**     |
| 앱 번들 ID  | —                        | `com.openai.chatgpt`                            | **`com.openai.chat`**                   |

⚠ **번들 ID 가 플랫폼마다 다르다** — 탐지 규칙에 양쪽 다 등록해야 한다.

### 0.2 버전 — 세 층을 구분해서 읽어라 ★★

버전이 문서 여러 곳에 나오는데 **가리키는 것이 층마다 다르다.** 섞어 읽으면 안 된다.

| 층                  | 값                                                                                                                                       | 의미                                                                              |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| **① 현재 환경**       | Codex CLI **`0.149.0`** · Claude Code **`2.1.239`**                                                                                       | 지금 이 PC 에 설치된 것. **최신으로 통일해 둔 상태**다.                                |
| **② 판별자 근거 버전**  | Codex **`0.149.0`** · Claude Code **`2.1.238`·`2.1.239`**<br>Android 앱 `1.260817.0` / `1.2026.223`<br>iOS 앱 `1.260820.0` / `1.2026.224` | §4.1 의 `promptSource`·`client_name` 판별 규칙이 **이 버전의 레코드 형식에 의존**한다. |
| **③ 디스크에 쌓여 있는 기록** | Codex **`0.63.0`~`0.149.0` 30개 버전** 이 쓴 rollout **353파일**<br>Claude **`2.1.145`~`2.1.239` 34개 버전** 이 쓴 세션 JSONL **262파일** | 지금까지 **쌓인 내역**. 그때그때의 버전 형식으로 굳어 있어 **소급해서 못 바꾼다.** |

> **①을 최신으로 맞춰도 ③은 그대로다.** 이미 디스크에 있는 기록은 그때 버전의 형식으로 쓰여 있고,
> 포렌식은 **지금 만드는 기록이 아니라 남아 있는 기록**을 읽는다.
> → **환경을 최신으로 통일했다고 구버전 파서를 뗄 수 없다.** 근거는 **§2.2.7**.
>
> 발표에서 버전을 한 번만 말한다면 **①**(`0.149.0` / `2.1.239`)을 쓰고,
> 판별 규칙 슬라이드(§4.1)에는 **②**를, 파서 커버리지 슬라이드(§2.2.4)에는 **③**을 각주로 단다.

---

# 1. 과제 수행 방법 및 내용

## 1.1 전체 설계 — 2 플랫폼 × 2 벤더 격자

| | Claude Code | Codex CLI |
|---|---|---|
| **로컬 PC** | `~/.claude/` 에 쌓인 기록 전량 분석 | `~/.codex/` 에 쌓인 기록 전량 분석 |
| **Android × 원격연동** | S3 | S4 |
| **iOS × 원격연동** | S1 | S2 |

로컬 아티팩트를 먼저 확정한 뒤, 같은 CLI 세션에 **모바일에서 원격으로 접속**했을 때
무엇이 추가로 생기는지를 차분으로 분리했다. 즉 **원격연동 아티팩트 = (연동 후) − (연동 전)** 이다.

## 1.2 로컬 아티팩트 분석

1. `~/.claude/` · `~/.codex/` 를 **읽기 전용으로 복사**한 뒤 사본에서만 분석했다.<sup>[각주 1]</sup>
2. 디스크에 **쌓여 있는 기록 전량**을 대상으로 했다 — rollout **353파일 · 작성 버전 30종
   (`0.63.0`~`0.149.0`)**. 최신 버전으로 재현하는 대신 **과거 기록을 그대로 읽었다**(§0.2 ③).
3. 레코드 타입·필드를 전수 집계해 스키마 세대(era)를 분리하고, 세대별로 무엇이 깨지는지 확인했다(§2.2.4·§2.2.7).
4. 세션 종료 방식(정상/비정상)을 바꿔가며 **어떤 파일이 사라지는지** 확인했다(§2.1.4).

## 1.3 원격연동 아티팩트 분석

**단계별로 끊어서 취득했다.** 한 번에 몰아 뜨면 어느 동작이 만든 파일인지 가를 수 없다.

| 단계 | Android | iOS |
|---|---|---|
| 취득 방식 | `scripts/android-snap.py` — 경로별 `size·mtime·sha256` 스냅샷 + `tar` 전량 | `pymobiledevice3 backup2 backup` 평문 백업 (1회 ~20초) |
| 끊은 지점 | 설치 → 로그인 → 원격활성화 → 지시 → 회수 | 설치 전 baseline → 설치 → 로그인 → 원격세션 → 승인 (앱별로 반복, 총 **9회**) |
| 차분 도구 | 스냅샷 diff | `scripts/ios-bkdiff.py` — `Manifest.db` 차분, **내용변경과 메타변경을 분리** |
| 추출 | `tar` 해제 | `scripts/ios-bkget.py` — `fileID` → 원경로 복원 |

**사슬 실증 — 표식 파일 기법.** 로컬에 nonce 를 담은 표식 파일을 두고, **폰에서** 그 파일을 읽으라고
지시한 뒤 **응답에 nonce 가 돌아오는지**로 "폰 지시 → 로컬 실행"을 확정했다.
nonce 는 시나리오마다 다른 값을 써서 어느 지시가 어느 회수에 대응하는지 가렸다.
이 기법은 부수적으로 **지시가 엉뚱한 머신으로 간 사고(동명 호스트 오배송)를 검출**하기도 했다(§5).

**판별자 분리 — 대조군.** 같은 세션에 **로컬 터미널 입력**과 **폰 원격 지시**를 모두 넣고
레코드를 필드 단위로 비교해, 두 경로를 가르는 필드만 남겼다(§4.1).
로컬 입력을 큐에 넣는 등 **위양성 조건도 별도로 시도**해 판별자가 뚫리는지 확인했다.

**시각 귀속.** 백업 사이 간격에 여러 행위가 들어간 구간은 파일 `mtime`(iOS 는 `Manifest.db` 의
`Files.file` 메타)으로 행위를 갈랐다. 그렇게도 분리되지 않는 구간은 **분류 불가로 명시**했다(§7).

## 1.4 증거 취급과 검증

- **원본 무변조**: 취득본은 해시(`SHA256SUMS`)로 고정하고, 분석은 사본·읽기전용 접근으로 했다.<sup>[각주 1]</sup>
  ⚠ **단 이 규칙은 사고 이후에 세운 것이다.** 초기 1회 기본(쓰기 가능) 커넥션으로 iOS 백업 `Manifest.db` 를
  열었고, 종료 시 자동 체크포인트로 `-wal`(32KB)이 본체에 병합되어 **원본 해시가 바뀌었다**.
  내용 손실은 없었으나(행수 동일) 그 백업은 오염으로 판정하고 **다른 백업을 기준 baseline 으로 교체**했다.
  이후 전 과정에 `mode=ro` 를 강제했다. **분석 도구가 증거를 수정할 수 있다는 실증 사례**로 §5 에도 싣는다.
- **증거등급 표기**: 모든 주장에 `[OBSERVED]` / `[INFERRED]` / `[HYPOTHESIZED]` 를 붙이고,
  교차검증을 통과한 것만 `VR-NNN` 으로 승격했다. 미승격 관측은 `관측 N` 으로 구분 표기한다.
- **적대적 교차검증**: 산출 문서를 **독립 검증자 4인(근거추적 · 수치 재측정 · 행위귀속 · 누락/비대칭)**
  에게 병렬로 넘겨 반증을 시켰다. 지적된 결함은 본문에 `[정정]` 블록으로 남기고 원 서술을 함께 보존했다.
- **수치 동결**: 문서에 인용된 수치는 회귀 테스트로 고정했다
  (`python3 -m pytest tests/test_panel_numbers.py -q -s`).

> <sup>[각주 1]</sup> **WAL 취급.** 이 프로젝트의 주요 증거 DB — Codex `logs_2.sqlite`·`state_5.sqlite`,
> Claude `claude_cache.db`, iOS 백업 `Manifest.db` — 는 모두 **SQLite WAL 모드**다.
> `-wal`·`-shm` 을 **동반 취득**한 뒤 **복제본에서 분석**했고, 원본은 읽기 전용
> (`sqlite3.connect('file:<경로>?mode=ro', uri=True)`)으로만 열어 보존했다.
> 쓰기 가능한 커넥션으로 열면 종료 시 자동 체크포인트가 일어나 `-wal` 내용이 본체 DB 로 병합되고
> **원본 해시가 바뀐다** — 추정이 아니라 이 프로젝트에서 실제로 겪은 사고다. 또한 `-wal` 없이 `.db` 만 복사하면 최근 레코드가 통째로 누락된다.

---

# 2. 로컬 아티팩트 분석

로컬 PC 에 남는 것. **원격이든 로컬이든 "무엇을 지시했고 무엇이 실행됐는지"의 증거는 전부 여기에 있다.**

## 2.1 Claude Code 로컬 아티팩트

> **한 줄**: 세션 JSONL **파일 하나**에 내용·맥락·출처가 전부 들어 있다.

### 2.1.1 저장 위치

| 경로                                               | 내용                                                                                            | 증거 등급  |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------- | ------ |
| `~/.claude/projects/<프로젝트슬러그>/<세션UUID>.jsonl`    | **세션 전사 — 1차 증거.** 프롬프트·응답·도구호출·결과 전문                                                         | **필수** |
| `~/.claude/sessions/<pid>.json`                  | 실행 중 세션 상태. `bridgeSessionId` 보유 시 원격 연결 증거                                                   | 휘발성 보조 |
| `~/.claude/sessions/<pid>.<sha256>.key`          | 메시징 소켓 인증용 추정 — **원격 마커 아님**                                                                  | 무관     |
| `~/.claude.json`                                 | `hasUsedRemoteControl` · `remoteDialogSeen` · `remoteControlUpsellSeenCount` · `oauthAccount` | 보조     |
| `~/.claude/history.jsonl`                        | 프롬프트 이력                                                                                       | 보조     |
| `~/.claude/file-history/` · `uploads/` · OS temp | 원본 보존·붙여넣기 캐시                                                                                 | 보조     |
| `.claude.json` · `.mcp.json`                     | MCP 서버 설정                                                                                     | 설정 증거  |

### 2.1.2 세션 JSONL 레코드 타입 (실측 분포 예)

```
attachment 45 · assistant 16 · user 11 · system 5 · mode 4 · permission-mode 4
last-prompt 4 · bridge-session 3 · queue-operation 2 · atis-latch 2 · ai-title 2
file-history-snapshot 1
```

### 2.1.3 핵심 성질

- **`bridge-session` 레코드가 턴마다 반복 기록**된다 (한 세션에서 5→8회 증가 관측)  
→ 세션 수명 중 **어느 구간이 원격 브리지 상태였는지**를 턴 단위로 재구성 가능
- 그 레코드가 `ownerAccountUuid` · `ownerOrganizationUuid` 를 품는다  
→ 세션 JSONL 단독으로 계정·조직 결속이 선다
- `type:"system"` `subtype:"bridge_status"` 에 활성화 안내문과 **공유 URL 원문**이 남는다
- **브리지 ID 는 resume 를 넘어 지속**된다 — 논리 세션 1개가 프로세스 4개로 갈라져도  
`bridgeSessionId` 는 유지되고 JSONL 은 **단일 파일**이다.  
→ "브리지 ID 1개 = 원격제어 1회" 가 아니라 **"= 원격 연결된 논리 세션 1개"**

### 2.1.4 존속 — 종료 방식에 달렸다 ★

| 종료 방식                       | `~/.claude/sessions/<pid>.json` |
| --------------------------- | ------------------------------- |
| 정상 종료 (`/exit`)             | **삭제** — 원격 마커 소실               |
| 비정상 종료 (터미널 종료·WSL 셧다운·크래시) | **잔존**, 재부팅 후에도 유지              |

**항구적 증거는 세션 JSONL 이다.** 정상 종료 후에도 JSONL 과 그 안의 `bridge-session` 레코드  
전부, `promptSource="queued"` 전부가 보존된다.  
→ **취득 우선순위**: 1차 = `~/.claude/projects/**/*.jsonl` · `~/.claude/sessions/` 는 **휘발성 보조**

---

## 2.2 Codex CLI 로컬 아티팩트

> **한 줄**: 기록 계층이 **3개**이고 이름 규칙이 전부 다르다. 게다가 **스키마 세대가 갈린다.**

### 2.2.1 저장 위치

루트 우선순위: `CODEX_HOME` env → config `sqlite_home` → `CODEX_SQLITE_HOME` → 기본 `~/.codex`.  
**SQLite 루트가 `CODEX_HOME` 과 분리될 수 있다** (실증).

| 경로                                                       | 내용                                                                    | 증거 등급               |
| -------------------------------------------------------- | --------------------------------------------------------------------- | ------------------- |
| `sessions/YYYY/MM/DD/rollout-*.jsonl`                    | **1차 증거.** 지시·실행·응답 전문                                                | **필수**              |
| `state_5.sqlite` `threads`                               | thread 카탈로그 (`rollout_path`·`cwd`·`git_branch`·`first_user_message`)  | 필수(교차)              |
| `state_5.sqlite` `remote_control_enrollments`            | **원격제어 등록** (§3.1.2)                                                  | 원격제어 1차             |
| `logs_2.sqlite`                                          | runtime 로그. **원격 판별자 `client_name**`                                  | 일반=보조 / **원격제어=1차** |
| `thread_history_1.sqlite` `thread_turns`·`thread_items`  | item projection + byte offset                                         | 보조(불완전)             |
| `goals_1.sqlite`                                         | 목표·상태·budget                                                          | 있음                  |
| `memories_1.sqlite` · `queue_1.sqlite`                   | 파생 요약 · 큐                                                             | 보조 / 없음             |
| `app-server-daemon/settings.json`                        | **`{"remoteControlEnabled": true}`**                                  | 원격제어 1차             |
| `app-server-daemon/app-server.pid` · `.stderr.log`       | 데몬 pid · 프로세스 시작시각 · stderr                                           | 보조                  |
| `app-server-control/app-server-control.sock`             | 유닉스 제어 소켓 (`srw-------`)                                              | 보조                  |
| `auth.json`                                              | **평문 JWT** (`id_token`·`access_token`·`refresh_token`) · `account_id` | 민감·결속축              |
| `config.toml` (+`.bak`)                                  | MCP·hooks·plugins·sandbox                                             | 설정 증거               |
| `history.jsonl` · `session_index.jsonl`                  | 보조 인덱스 — **비권위** (중복·누락)                                              | 보조                  |
| `tmp/` `.tmp/` `shell_snapshots/` `thread-writer-locks/` | 실행 부산물                                                                | 보조                  |
| `packages/standalone/`                                   | **standalone 설치본** — 원격제어 전제 (§3.1.2)                                 | 판정 근거               |
| `visualizations/<스레드생성일>/<thread_id>/`                   | 원격 턴 산물 (iOS 클라이언트) — §3.2.2                                          | 원격 정황               |

⚠ DB 파일명 숫자 접미사 (`_5`·`_1`·`_2`) 는 schema version 이 아니다.  
`_sqlx_migrations` max = state_5:46 · thread_history_1:4 · logs_2:2.  
→ glob + `_sqlx_migrations` 로 판별해야 한다.

⚠ **커버리지 경고**: `state_5.threads` 341 vs `thread_items` distinct thread **21**.  
projection 만으로 사건을 확정하면 안 된다.

### 2.2.2 한 줄 요약 — 무엇을 알려면 무엇을 봐야 하나 ★★

**대화 내용은 rollout 파일에 전부 남는다.** 문제는 그 다음이다.

| 알고 싶은 것 | 어디를 봐야 하나 | 왜 어려운가 |
|---|---|---|
| **무슨 대화를 했나** | `sessions/**/rollout-*.jsonl` **한 파일** | — |
| **사람이 친 건가, 에이전트가 한 건가** | 같은 rollout **안**. 단 필드 이름을 믿으면 안 된다 | `user` 가 붙었다고 사람 입력이 아니다. 진짜 사람이 친 셸 명령은 명령 22,851건 중 **2건** (§2.2.6) |
| **폰에서 시킨 건가, 로컬에서 친 건가** | **다른 파일** — `logs_2.sqlite` 의 `client_name` | rollout 에는 출처 필드가 **아예 없다.** 로컬 입력과 원격 입력의 레코드가 완전히 같다 (§4.1) |
| **그 rollout 을 어떤 파서로 읽나** | 파일마다 다르다 — **구조를 먼저 탐지**해야 한다 | 같은 데이터를 세 군데가 각각 다른 이름 규칙으로 쓰고(§2.2.3), 파일이 쓰여진 시기에 따라 형식이 갈린다(§2.2.4) |

> **즉 Codex 는 "무엇을 했나"는 한 파일에 다 남기지만, "누가 시켰나"는 같은 파일에 안 남긴다.**
> 폰 지시를 입증하려면 **rollout + `logs_2.sqlite` 두 개를 함께** 확보해야 한다.

**Claude Code 와의 차이**

| | Claude Code | Codex CLI |
|---|---|---|
| 원격/로컬 판별 | 세션 JSONL **1개** — `promptSource`(`queued`=원격 / `typed`=로컬) | rollout + `logs_2.sqlite` **2개** |
| 사람/에이전트 판별 | 같은 파일 안. **같은 이름 함정 있음** — 실측 `type:"user"` 24건 중 사람 입력은 6건, 나머지 16건은 `tool_result` | 같은 rollout 안. 함정 더 큼 (위 표) |
| **조작자 단말 OS<br>— 로컬 PC 만으로** | **✗** — 로컬 어디에도 없다. 폰을 확보해야 안다 | **✅** `logs_2.sqlite` `client_name` 접미<br>`_ios_remote` / `_android_remote` |
| 스키마 다중성 | **미측정** | 세 계층 × 두 세대 (§2.2.3·§2.2.4) |

> **`✗` 는 실측 결과다** — Claude 로컬 전체(원격 세션 JSONL 2개 · `sessions/<pid>.json` 9세션 ·
> `~/.claude.json`)를 `iphone|ipad|android|ios|darwin|platform|deviceType|userAgent|os` 로 훑어
> **구조적 필드 히트 0건**. `bridge-session` 레코드는 Android 세션과 iOS 세션이 **전 필드 6개 동일**
> (`type`·`sessionId`·`bridgeSessionId`·`lastSequenceNum`·`ownerAccountUuid`·`ownerOrganizationUuid`)이고,
> `sessions/<pid>.json` 21개 키도 전부 로컬 PC 정보(`pid`·`cwd`·`tmux`·`entrypoint`…)다.
> 두 세션 간 나머지 필드 차이(`slug` 등)는 **CLI 버전(2.1.238 vs 2.1.239)과 사용 툴 차이**의 부산물이지
> 플랫폼 축이 아니다.

→ **Claude 는 파일 하나로 "누가 시켰나"까지 답이 나오고, Codex 는 두 파일이 필요한 대신
   "어느 단말 OS 에서 시켰나"까지 답이 나온다.** 취득 요건과 답할 수 있는 범위가 맞바뀐다.

**이 차이가 실무에서 갈리는 지점** — Codex 의 단말 OS 판별은 **로컬 PC 파일만으로** 성립한다.

| 상황 | Claude | Codex |
|---|---|---|
| 폰을 확보하지 못했다 (미압수·분실·잠김) | 원격 여부까지만 | **어느 OS 단말인지까지** |
| 폰에서 앱을 지웠다 | 폰측 근거 소실 | 로컬 로그는 무관하게 잔존 |
| 한 계정에 단말이 여러 대 | 구분 불가 | Android/iOS 구분 (단 **같은 OS 두 대는 구분 못 함**) |

⚠ `client_name` 이 말해주는 것은 **OS 종류**지 개별 기기가 아니다. 특정 기기까지 좁히려면
폰측 기기 식별자(Android `global_device_uuid.json` · iOS `Anthropic-Device-ID`/`deviceIDBackup`)나
`environment_id` 결속이 필요하다.

### 2.2.3 기록 계층이 3개다 — 이름 규칙이 전부 다르다 ★

| 계층                | 경로                            | 규칙             | 실측 건수                                                                                                |
| ----------------- | ----------------------------- | -------------- | ---------------------------------------------------------------------------------------------------- |
| raw response_item | `payload.type`                | **snake_case** | `reasoning` 20,857 · `function_call` 15,848 · `message` 11,305 · `custom_tool_call` 10,186           |
| raw item          | `event_msg.payload.item.type` | **PascalCase** | `CommandExecution` 2,252 · `AgentMessage` 423 · `Extension` 162 · `UserMessage` 83 · `FileChange` 64 |
| SQLite projection | `thread_items.item_type`      | **camelCase**  | `commandExecution` · `fileChange` · `userMessage` · `webSearch`                                      |

**같은 이름인데 구조가 다르다** — 원형 파서를 공유하면 안 되고, 정규화 계층만 공유한다:

| 필드                   | raw                                                                                 | SQLite                             |
| -------------------- | ----------------------------------------------------------------------------------- | ---------------------------------- |
| `FileChange.changes` | 경로-키 **map**. value keyset `{type,content}` 22 / `{type,move_path,unified_diff}` 46 | **배열** `{path,kind,diff}` 68 entry |
| `command`            | **argv 배열** (2,274/2,274)                                                           | **문자열** (2,103/2,103)              |
| `cwd`                | percent-encoded **`file://` URL**                                                   | 절대경로                               |
| 이미지                  | `local_image`                                                                       | `localImage`                       |

### 2.2.4 같은 CLI 인데 파일 형식이 두 세대로 갈린다 ★★

로컬 표본 rollout 353파일에 **cli_version 30종** (`0.63.0` ~ `0.149.0` — §0.2 ③).

| 증거                 | legacy 계층 (item 레코드 없는 파일 **329개**)                                                                                           | item 계층 (**24개**)             |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| 사용자 발화             | `event_msg.user_message` 2,231                                                                                                | `item.UserMessage` 83         |
| 에이전트 응답            | `event_msg.agent_message` 7,101                                                                                               | `item.AgentMessage` 423       |
| 명령 실행              | `function_call exec_command|shell_command|run` 12,445 + `custom_tool_call exec` 6,393 + `exec_command_end` 1,254 = **20,092** | `item.CommandExecution` 2,281 |
| 파일 쓰기              | `apply_patch` 1,797 + `patch_apply_end` 1,702 = **3,499**                                                                     | `item.FileChange` 66          |
| envelope `ordinal` | 없음                                                                                                                            | 전 라인 존재                       |

**같은 0.147.0 바이너리인데 `originator` 로 계층이 갈린다** —  
`codex-tui`(대화형) 22파일 = item / **`codex_exec`(헤드리스) 6파일 = legacy**

**정량 영향 (발표 헤드라인용 · 파일 기준)**

> item 계층만 구현한 파서는 **세션 파일 329/353 = 93.2% 에서 명령·쓰기 이벤트를 0건** 낸다.

비율이 아니라 **이진 속성**(그 파일에 `item_completed` 레코드가 있느냐)이라 기록이 더 쌓여도 흔들리지 않는다.

> ⚠ **판정은 버전이 아니라 레코드 유무로.** `cli_version` 으로 era 를 나누면 legacy 파일 323개만  
> 잡히지만, `codex_exec` 헤드리스 6파일은 **0.147 을 보고하면서도 `item_completed` 를 한 건도 내지 않는다.**  
> 그 6개를 더한 **329개**가 단일 스키마 파서의 실제 0건 구간이다.  
> (기계 검증: `tests/test_panel_numbers.py`)

**레코드 기준 보조 지표** (2026-08-22 스냅샷 · 중복제거 후 — 각주로만)

| 지표    | legacy | item(0.147+) | 회수율   |
| ----- | ------ | ------------ | ----- |
| 명령    | 21,482 | 2,789        | 11.5% |
| 파일 쓰기 | 2,222  | 171          | 7.1%  |

중복제거 근거: `exec_command_end` 1,254개 call_id 가 `function_call(exec_command)` 와 **완전 일치**(교집합 1,254 = end 전체).  
쓰기도 `apply_patch` 1,797 ∩ `patch_apply_end` 1,702 = **1,277 중복** → union 2,222.  
**이 비율은 지금 쌓여 있는 기록의 구성비이지 도구의 속성이 아니다** — 0.147+ 사용이 늘수록 올라간다.

→ 파서는 버전 하드코딩이 아니라 **구조 탐지(capability sniffing)** 로 판정하고,  
발견된 파서를 전부 실행해 `id`/`call_id` 로 병합한다. 미지 구조는 `unsupported_schema` 로 표면화한다.

### 2.2.5 암호화·opaque 구간

`encrypted_content` · `gAAAAA` 가 **313파일 / 353 = 88.7%** 에 나타난다.  
→ **복호화 시도 안 함.** 존재·길이·위치·session/turn 연결만 보존한다.

### 2.2.6 행위 주체 식별 (Claude·Codex 공통 규칙)

도메인은 `actor = user | agent | unknown` 3값이다.  
**subagent 는 actor 가 아니라 agent 인스턴스 계층**(`meta.agent_kind`·`parent_thread_id`·`depth`·`agent_path`).  
`turn_context`·`world_state`·`token_count` 같은 system record 는 **Event 를 만들지 않는다.**

| 판정          | 근거                                                                                     |
| ----------- | -------------------------------------------------------------------------------------- |
| **user**    | `user_message` / `UserMessage` 와 그 안의 첨부 이미지 · `CommandExecution.source == user_shell` |
| **agent**   | 그 외 `CommandExecution` (에이전트 턴 스트림 안의 기록) · 도구 호출과 연결된 실행                              |
| **unknown** | 세션/턴 연결 자체가 없을 때만                                                                      |

⚠ **이름에 user 가 들어가도 사람 입력이 아닌 것** (Event 로 만들면 과계수)  
`response_item.message role=user` 2,968 · `role=developer` 815 (모델 입력 뷰) ·  
`turn_context.user_instructions` 786 · `session_meta.base_instructions` 349 · `history.jsonl` 2,266

**실측** (2026-08-22 17:20): agent 34,698 / user 2,392 / **unknown 0**.  
`user_shell` **2건**이 명령 이벤트 22,851건 중에서 정확히 분리된다.

**파일 작성 확신도 4등급**

| 등급        | 조건                                                                      |
| --------- | ----------------------------------------------------------------------- |
| `high`    | 구조화 기록 + 같은 turn/thread + **잔존 파일 stat/hash 상관**                        |
| `medium`  | 구조화 write 기록(FileChange·apply_patch·patch_apply_end) + completed + path |
| `low`     | 미완료 / 타깃 없음 · command 리다이렉션 추정                                          |
| `unknown` | 디스크에만 존재, transcript 연결 없음                                              |

⚠ **shell 로 만든 파일은 `FileChange` 에 안 잡힌다** — redirection 명령 51건 중 21건이 same-turn  
FileChange 없음(16건 exit 0). write-like 227건 대 FileChange 66건에 same-turn path 매칭 **0**.  
→ 도구는 이 부류를 `action=write` 로 **주장하지 않고** `meta.write_target` + `confidence=low` 로 후보만 표면화한다.

⚠ **개별 승인 여부는 판정 불가.** `approval_policy` `on-request` 1,424 / `never` 1,922,  
`sandbox_policy` `workspace-write` 1,428 / `read-only` 88 / `danger-full-access` 1,830 은 **정책 스냅샷**일 뿐이고  
개별 승인 record 는 전수 검색 **0건**이다 → `approved_by_user` 는 **기록 금지**.


### 2.2.7 왜 이렇게 복잡한가 — 단순화하면 무엇이 깨지나 ★★

> 심사위원이 반드시 묻는 질문이다. **복잡한 쪽은 우리 파서가 아니라 Codex 의 기록 방식**이고,
> 단순화안 두 가지를 실데이터에 대보면 둘 다 깨진다.

**단순화안 A — "최신 계층(item)만 지원한다"**
→ rollout 353파일 중 **329파일(93.2%)에서 명령·쓰기 이벤트가 0건**이 된다.
그 329파일이 바로 증거물이다. 포렌식은 지금 만드는 기록이 아니라 **남아 있는 기록**을 읽는다.

**단순화안 B — "`cli_version` 으로 era 를 나눈다 (버전 표)"**
→ 같은 버전이 `originator` 로 갈리기 때문에 오분류한다:

| `cli_version` | `originator` | 계층 | 파일 |
| ------------- | ------------ | ---- | ---: |
| `0.149.0` | `codex-tui` | item | 2 |
| `0.147.0` | `codex-tui` | item | 22 |
| **`0.147.0`** | **`codex_exec`** | **legacy** | **6** |

같은 `0.147.0` 바이너리인데 **헤드리스 실행분 6파일은 item 레코드를 한 건도 내지 않는다.**
버전 표는 이 6개를 item 으로 잘못 분류하고 **그 세션 전체에서 0건**을 낸다.

**게다가 계층은 이름만 다른 게 아니라 구조가 다르다** (§2.2.3) —
command 가 argv 배열↔문자열, `changes` 가 map↔배열, `cwd` 가 `file://` URL↔절대경로.
파서를 공유하면 **예외도 없이 조용히 잘못 읽는다.** 포렌식에서 제일 나쁜 실패 방식이다.

**그래서 구조 탐지(capability sniffing) 다** — 버전을 묻지 않고 "이 파일에 어떤 레코드가 있나"를
보고 해당 파서를 전부 돌린 뒤 `id`/`call_id` 로 병합한다. 미지 구조는 `unsupported_schema` 로 표면화한다.

**이 방식이 맞다는 증거**
> 353파일 전량에서 `unsupported_schema` 0건 · `actor` unknown 0건.
> 접근이 틀렸다면 둘 중 하나는 0이 아니다 — 못 읽은 구조가 남거나, 주체를 못 정한 이벤트가 남는다.

**복잡도는 한 곳에 갇혀 있다** — 새 era 가 나오면 **파서를 하나 더하면 되고** 판정 로직은 안 건드린다.
실제로 `0.149.0` 파일 2건은 **코드 변경 없이 그대로 파싱된다.**

> ⚠ **미측정**: `0.149.0` 의 **헤드리스(`codex_exec`) 표본이 아직 0건**이다.
> `0.147.0` 에서 관측된 originator 분기가 `0.149.0` 에서도 유지되는지는 **확인되지 않았다.**

**Claude 가 단순한 건 Claude 의 형식이 단순해서다** — 우리가 Claude 쪽을 덜 만든 게 아니다.
**이 비대칭 자체가 연구 결과**이고, 그대로 §2.3 의 "취득 요건이 벤더별로 다르다"로 이어진다.

---

## 2.3 로컬 — 두 벤더 대비 (슬라이드 1장용)

|          | Claude Code     | Codex CLI                                      |
| -------- | --------------- | ---------------------------------------------- |
| 1차 증거    | 세션 JSONL **1개** | rollout JSONL **+ SQLite 6종**                  |
| 기록 계층    | 단일              | **3계층** (snake / Pascal / camel)               |
| 스키마 세대   | 단일              | **legacy / item 2세대 + originator 분기**          |
| 내용과 출처   | **같은 파일**       | **다른 파일** (rollout ↔ `logs_2.sqlite`)          |
| 파일 읽기 기록 | 있음 (`Read` 도구)  | **범용 read 레코드 없음** — `action=read` 는 이미지 열람뿐 ★ |
| 자격증명     | OAuth 계정 정보     | `auth.json` **평문 JWT**                         |
| 암호화 구간   | —               | `encrypted_content` 305파일                      |

⚠ **접근파일 정확도를 두 벤더 나란히 놓으면 안 된다** — Codex 에는 애초에 범용 파일 읽기 레코드가 없다.

---

# 3. 원격제어 아티팩트 분석

모바일 앱이 로컬 PC 의 CLI 에 **원격으로 연동될 때** 생기거나 값이 바뀌는 것만 싣는다.  
앱을 그냥 쓸 때 생기는 기본 아티팩트는 **연동 판별에 쓰이는 경우에만** 등장한다.

> **4칸 전부 실측했다** — Android×Claude · Android×Codex · iOS×Claude · iOS×Codex.

**전 시나리오 공통 결론 3개**

1. **지시 "내용"의 증거는 로컬 PC 에만 있다.** 4칸 전부에서 폰 취득본 전수 검색 결과 지시 문구 **0건**.
  (예외 1건: Android×Codex 는 지시 **주제**가 디렉터리 슬러그로 △ 남는다)
2. **폰은 "언제 어느 세션·호스트에 붙었나"의 증거** — 결속·정황 증거다.
3. **원격/로컬 판별은 로컬 파일에서 한다.** 폰은 판별에 필요 없다.

## 3.1 Android

### 3.1.1 Android × Claude Code

> **한 줄**: 폰의 **세션 ULID** 하나로 폰↔PC 가 결속되고, 판별은 로컬 JSONL 단독으로 끝난다.

#### (1) 전체 사슬

```
[폰 Claude 앱]                        [서버]                    [로컬 PC]
 shared_prefs/…_code_remote.xml   claude.ai/code/            ~/.claude/
   recap_dismissed_at              session_<ULID>              sessions/<pid>.json  bridgeSessionId
   default_session_target                                      projects/**/<uuid>.jsonl
     (environment_id)                                            ├ bridge-session (턴마다)
                                                                 ├ promptSource="queued" ← 원격
                                                                 └ tool_use.input (실행된 명령)
```

#### (2) 폰 측 잔존물 (`com.anthropic.claude`, UID 10332 · **루팅 필요**)

| 파일                                                                                           | 내용                                                                                                                                                                                 |
| -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `shared_prefs/user_prefs_AccountId(value=<acc>)_OrganizationId(value=<org>)_code_remote.xml` | **`recap_dismissed_at`** = `{"session_<ULID>": <epoch_ms>}` · **`default_session_target`**(`kind:"anthropic_cloud"`·`environment_id`) · `cowork_starter_seen` · `github_connected` |
| `…_code_remote_read_state.xml`                                                               | `pending_acks`                                                                                                                                                                     |
| `…_drawer_feature_discovery.xml`                                                             | **`has_seen_cowork_remote_tab`** = true ← 원격 탭 열람                                                                                                                                  |
| `…_agent_chat.xml`                                                                           | `has_seen_dispatch_feature`                                                                                                                                                        |
| `app_stats.xml`                                                                              | `last_resumed_at` · `creation_count` · `chat_list_views`                                                                                                                           |
| `cache/app_start/acc_<acc>/org_<org>/cache.json` (195KB)                                     | **서버 인가 스냅샷** — 아래 (3)                                                                                                                                                             |
| `databases/acc_<acc>_org_<org>_claude_cache.db`                                              | 대화 캐시 — 아래 (6)                                                                                                                                                                     |
| `shared_prefs/user_cookies_<accountUuid>.xml`                                                | **평문 세션 쿠키 9건**                                                                                                                                                                    |
| `app_webview/Default/Cookies`                                                                | **두 번째 평문 사본** (`encrypted_value` 길이 0)                                                                                                                                            |
| `shared_prefs/trusted_device.xml`                                                            | **암호화** (Tink/AndroidKeyStore) — 같은 앱 안에서 보호 수준이 다르다 ★                                                                                                                             |
| 식별자군                                                                                         | `device_id_prefs.xml` · Segment · `files/INSTALLATION` · datadog · sentry · `siftscience.xml`                                                                                      |
| 시각 메타                                                                                        | kronos `cached_offset` — **NTP 보정값, 단말 시계 신뢰도 근거** ★                                                                                                                               |

#### (3) 서버 인가 스냅샷 — "기능 보유"가 아니라 "인가 상태"다 ★

`response.current_user_access.features` 는 **`{feature, status}` 객체 56개의 리스트**다(딕셔너리 아님).  
remote/cowork/code 매칭 17건 중:

```json
{"feature":"claude_code_remote_control", "status":"available"}
{"feature":"cowork",                     "status":"available"}
{"feature":"claude_code_web",            "status":"available"}
{"feature":"claude_code_desktop_bypass_permissions", "status":"available"}
{"feature":"claude_code_review",         "status":"blocked_by_org_admin"}   ← available 만은 아니다
```

같은 파일에 `response.account.email_address` · `full_name` 평문, `cachedAtMillis` = **서버 인가 시각**.  
→ `blocked_by_org_admin` 이 존재하므로 **"기능 보유"로 읽으면 틀린다.**

#### (4) 결속 — 동일 ULID 가 **접두사만 바꿔 3곳**에 나타난다 ★★

| 측   | 위치                                       | 값                |
| --- | ---------------------------------------- | ---------------- |
| 폰   | `code_remote.xml` `recap_dismissed_at` 키 | `session_<ULID>` |
| 로컬  | `sessions/<pid>.json` `bridgeSessionId`  | `session_<ULID>` |
| 로컬  | 세션 JSONL `bridge-session`                | **`cse_<ULID>`** |

→ 문자열 전체 일치 검색으로는 못 잇는다. ULID 본문으로 매칭해야 한다.

**시각 대조** (2회 독립 재현, 부호 일관):

| 회차  | 폰 `recap_dismissed_at` | 로컬 원격 프롬프트   | 차이          |
| --- | ---------------------- | ------------ | ----------- |
| 1차  | 16:37:29.694           | 16:37:28.721 | **+0.973초** |
| 2차  | 16:51:32.221           | 16:51:29.946 | **+2.275초** |

2회 모두 폰 값이 뒤 → 단말 시계 오차가 아니라 **"프롬프트 전송 → 폰이 recap 갱신"** 순서의 반영 [INFERRED].

> ⚠ **Android 에서 폰에 남는 시각은 "지시" 시각이다.** (iOS 는 반대 — §3.2.1 참조)  
> ⚠ **`recap_dismissed_at` 은 세션당 값 1개**다. 2차 지시가 1차 값을 덮어썼다.  
> 폰 단독으로는 **몇 번 지시했는지 알 수 없다** — 횟수·순서는 로컬 JSONL 에만 있다.  
> ⚠ 활성화만 하고 지시를 안 했을 때 `recap_dismissed_at` 이 생기는지는 **미검증** [HYPOTHESIZED].

#### (5) 원격/로컬 판별 — 로컬 JSONL 단독으로 가능 ★★

|                   | **원격 (폰)**              | 로컬 타이핑 (유휴)            | 로컬 타이핑 (작업 중)                          |
| ----------------- | ----------------------- | ---------------------- | -------------------------------------- |
| `user` 레코드        | 생성                      | 생성                     | **미생성**                                |
| `promptSource`    | **`queued`**            | `typed`                | (없음)                                   |
| `origin.kind`     | `human`                 | `human`                | `human`(attachment 내부)                 |
| `queue-operation` | enqueue → **`dequeue`** | 없음                     | enqueue → **`remove`**                 |
| 본문 전달             | `user.message.content`  | `user.message.content` | **`attachment.queued_command.prompt`** |

**판별 규칙**

| 조건                                                            | 판정        |
| ------------------------------------------------------------- | --------- |
| `type=user` ∧ `promptSource="queued"` ∧ `origin.kind="human"` | **원격 입력** |
| `type=user` ∧ `promptSource="typed"`                          | 로컬 직접 입력  |
| `type=attachment` ∧ `attachment.type="queued_command"`        | 로컬 큐 입력   |
| `promptSource="system"` ∧ `origin.kind="task-notification"`   | 시스템 생성    |

위양성 검증 완료 — 로컬 조건 5회(유휴 4 · 작업 중 1) 어느 쪽도 `queued`+`human` 조합을 만들지 못했다.

> ⚠ `origin` 은 원격을 구분하지 못한다 — 구분하는 것은 `promptSource` 다.  
> `origin.kind`·`permissionMode`·`entrypoint`·`userType`·`cwd`·`version` 은 로컬/원격 동일.  
> ⚠ 표본이 작다(원격 2 · 로컬 5)고 CLI `2.1.238`·`2.1.239` 레코드 형식에 의존한다.  
> 1차 근거는 세션 단위 `bridge-session`, 메시지 단위 `promptSource` 는 보강으로 쓰는 것이 안전하다.

#### (6) 폰은 원격 지시 **내용**을 저장하지 않는다 ★

폰 취득본 전수 문자열 검색 (VR-005):

| 검색어                    | 히트                       |
| ---------------------- | ------------------------ |
| 세션 ULID                | `code_remote.xml` **1건** |
| `environment_id`       | `code_remote.xml` **1건** |
| 지시 문구 · nonce · 표식 파일명 | **0건**                   |

`claude_cache.db` 행수 변화 0 (대화 15→15, 메시지 22→22).  
→ **원격 Code 세션의 대화 내용은 단말에 저장되지 않는다.** 일반 대화와 저장 경로가 완전히 다르다.

**대조 — 일반 대화는 폰에 남는다**: 로그인만 해도 대화 목록 **15건**(제목·최대 3.8KB 요약·모델·설정)이  
평문 SQLite 로 내려앉고, 대화를 열면 본문 22건이 캐시된다(`tool_use.input` 25.7KB 포함).  
단 **활성 분기만** 남는다(`index` 0~87 중 22건 — 편집·재생성으로 버려진 형제 분기는 없음).

> ⚠ **오해 방지**: 단말 캐시 15건은 "사용자가 폰에서 본 것"이 아니라 **로그인 시 서버가 밀어준 최근 목록**이며  
> 그 범위는 사용자 행위가 아니라 **서버 페이지 크기**가 정한다. 스크롤해도 늘지 않는다(15 = 상한).

#### (7) 사슬 완성 — 표식 파일 실험

| 시각(KST)      | 내용                                                        |
| ------------ | --------------------------------------------------------- |
| 16:51:29.946 | 원격 프롬프트 (`promptSource="queued"` + `origin.kind="human"`) |
| 16:51:34.187 | `tool_use` **Bash `cat /tmp/AGENTRACE-MARKER.txt**`       |
| 16:51:37.951 | `tool_result` — nonce 포함                                  |
| 16:51:41.119 | 답변 `nonce: dc70739f…`                                     |

표식 파일 SHA-256 `b8f370de…`.  
→ 폰 지시 1건이 로컬에서 어떤 명령으로 실행됐는지 단일 표식으로 특정된다.

---

### 3.1.2 Android × Codex (ChatGPT 앱)

> **한 줄**: 내용과 출처가 **다른 파일**에 있고, 폰에는 **PC 프로젝트 구조가 평문 전파**된다.

#### (1) 전체 사슬

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

⚠ **폰과 로컬이 서로 다른 엔드포인트를 쓴다** — 네트워크 탐지 규칙을 양쪽 따로 등록해야 한다.

#### (2) 전제 조건 — 벤더별로 다르다 ★

|       | Claude Code                  | Codex                                                        |
| ----- | ---------------------------- | ------------------------------------------------------------ |
| 설치 형태 | 무관 (`/remote-control` 즉시 동작) | **managed standalone 설치 필수** — npm 설치본은 실행 거부                |
| 계정 인증 | 추가 인증 없음                     | **계정 MFA 필수** (미충족 시 enroll HTTP 403)                        |
| 페어링   | 없음                           | `codex remote-control pair` — 코드 9자(`XXXX-XXXX`), **수명 10분** |

→ "이 머신이 Codex 원격제어 대상이 될 수 있었는가"는 설치 형태로 판정된다.  
standalone 은 정적 네이티브 바이너리라 **프로세스를 `node` 문자열로 찾으면 놓친다.**

#### (3) 로컬 측 아티팩트

| 경로                                            | 내용                                                                                                                                     |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `app-server-daemon/settings.json`             | **`{"remoteControlEnabled": true}`** — 호스트 단위 마커                                                                                       |
| `app-server-daemon/app-server.pid`            | `{"pid":…, "processStartTime":…}`                                                                                                      |
| `state_5.sqlite` `remote_control_enrollments` | `websocket_url`·`account_id`·`app_server_client_name`·`server_id`·`environment_id`·`server_name`·`updated_at`·`remote_control_enabled` |
| `logs_2.sqlite` `logs`                        | 엔드포인트·`installation_id`·호스트명·재연결 백오프·**소스 파일 경로**까지 평문 (**WAL 모드 — `-wal`·`-shm` 동반 필수**)                                              |
| `sessions/**/rollout-*.jsonl`                 | 지시 문구·실행 명령·응답 전문 (**출처 필드는 없음**)                                                                                                      |

> **Claude 와의 정보량 차이**: Claude 는 **세션 단위**(세션마다 브리지 ID), Codex 는 **호스트 단위**  
> (데몬 1개에 불리언 1개) → `settings.json` 만으로는 **어느 세션이 원격 노출됐는지 알 수 없다.**

#### (4) 같은 이름의 서버가 둘 등록된다 ★

같은 물리 PC 의 WSL CLI 와 Windows Codex Desktop 이 **각각 독립 enrollment** 를 갖고,  
WSL hostname 이 Windows 머신명을 상속해 **`server_name` 이 동일**하다.

| 컬럼                       | WSL CLI                         | Windows Desktop                         |
| ------------------------ | ------------------------------- | --------------------------------------- |
| `server_name`            | **`<hostname>`**                | **`<hostname>`** ← 구분 불가                |
| `app_server_client_name` | (빈 문자열)                         | `Codex Desktop`                         |
| `server_id`              | `srv_e_6a885fdc…`               | `srv_e_6a8860b5…`                       |
| `environment_id`         | `env_e_6a885fdc…`               | `env_e_6a8860b5…`                       |
| `remote_control_enabled` | **NULL**                        | **`1`**                                 |
| 저장 위치                    | `~/.codex/state_5.sqlite` (WSL) | `C:\Users\<user>\.codex\state_5.sqlite` |

→ **`server_name` 은 고유 식별자가 아니다.** 귀속에는 `server_id`·`environment_id`·`app_server_client_name` 을 써야 한다.

#### (5) 폰 측 잔존물 (`com.openai.chatgpt`, UID 10334 · **루팅 필요**)

| 파일                                                                        | 내용                                                                                                                                                                                                                                                        |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `files/datastore/<userID>__<accID>_codex_remote_hosts.json`               | `has_ever_set_up_remote` · `selected_host_id` · `saved_hosts[]`(`slingshot:<env_id>:8765`·`display_name`·`host`·`port`·`updated_at`) · **`remembered_working_directories_by_host`** · `last_connection_used_at_millis_by_host` · `default_follow_up_mode` |
| `files/datastore/<userID>__<accID>_codex_remote_control_enrollments.json` | `enrollments_by_endpoint{ https://android.chat.openai.com/backend-api/codex/remote/control }` → `client_id`·`key_id`·**`public_key_spki_der_base64`**·`algorithm: ecdsa_p256_sha256`·**`protection_class: os_protected_nonextractable`**                  |
| `files/datastore/global_device_uuid.json`                                 | 기기 UUID                                                                                                                                                                                                                                                   |
| `shared_prefs/com.auth0.authentication.storage.xml`                       | **평문 JWT** `access_token`(2,001자)·`id_token`(1,625자)·`refresh_token` — 페이로드에 **이메일·실명·사진 URL**                                                                                                                                                            |
| `files/datastore/global_cookie_storage.json`                              | 쿠키 23건 평문                                                                                                                                                                                                                                                 |
| `databases/<userID>__<accID>_conversations.db`                            | 대화 캐시 (본체 49KB + **WAL 276KB**)                                                                                                                                                                                                                           |
| `databases/<userID>__<accID>_websocket_topic_data.db`                     | `DBWebSocketTopicOffset` 5행 (`calpico`·`calpico-chatgpt`·`conversations`·`push_auth_challenge`·`app_notifications`) — **Codex·원격 토픽 없음. 원격 지시 후에도 추가되지 않음**                                                                                               |

#### (6) ★★ 페어링 1회로 PC 프로젝트 구조가 폰에 평문 전파된다

`remembered_working_directories_by_host` — **사용자가 그 경로를 폰에서 연 적이 없어도** 내려온다.

```
WSL 호스트      26건   (연구 프로젝트 경로 · 학회명 · 논문 주제 포함)
Windows 호스트   7건   C:\Users\<user>\Documents\Codex\<날짜>\<슬러그>
```

경로에 학회명·연구주제·도구 구성이 들어 있어 **폰 단독 압수로 PC 프로젝트 구조가 드러난다.** (VR-025)  
Codex 가 첫 프롬프트를 작업 디렉터리명으로 **슬러그화**하므로,  
**경로 목록만으로 과거 원격 지시의 주제까지 복원 가능하다.**

```
C:\Users\<user>\Documents\Codex\2026-08-22\tmp-agentrace-marker-txt-nonce
  ← 원격 지시 "/tmp/AGENTRACE-MARKER.txt … nonce …" 의 슬러그화
```

→ nonce 값·지시 원문은 0건이지만 지시의 주제는 복원된다. (관측 45)  
→ ⚠ **iOS 에는 이 필드가 없다** (§3.2.2).

#### (7) ★ 장치 개인키만은 비추출 — "루팅 = 전량 획득"은 과장이다

`protection_class: os_protected_nonextractable`.  
개인키는 AndroidKeyStore(TEE/StrongBox)에 있고 파일에는 **공개키만** 있다.  
→ 확인된 범위에서 유일하게 "루팅해도 못 뽑는" 아티팩트.

#### (8) 원격 판별자 — `client_name` (내용과 **다른** DB) ★★

| connection_id | `client_name`                              | 정체                      |
| ------------- | ------------------------------------------ | ----------------------- |
| 1             | `codex_app_server_daemon`                  | 데몬 자신                   |
| 3             | `codex-tui` + `codex_app_server_daemon` 혼재 | (연결 재사용)                |
| **4**         | **`codex_chatgpt_android_remote`**         | **폰 (ChatGPT Android)** |
| 5             | `codex-tui`                                | 로컬 터미널                  |

`turn/start` RPC 의 `connection_id` 를 `client_name` 에 **조인**해 판정한다.

> **구현 주의**: 최근 RPC 몇 건만 표본으로 보면 `codex-tui` 의 `plugin/list` 노이즈에 묻혀  
> `codex_chatgpt_android_remote` 를 놓친다. 해법은 `turn/start` 필터가 아니라 **연결별로 묶는 것**이다 —  
> connection 0 에 tui 노이즈가 아무리 많아도 connection 4 는 오염되지 않는다.
> **`client_name` 문자열에 OS 가 박혀 있다** → 로컬 로그만으로 **조작자가 쓴 단말 OS 까지 특정된다.**  
> Claude 에는 이 축이 없다.

**부가 판별자**: Codex 원격 턴은 `request_id` 가 **UUID 문자열**, 로컬 TUI 는 **정수 증가**다.  
`turn/started` 는 `targeted_connections=2` 로 TUI 와 폰에 동시 방송된다.

#### (9) ★ rollout JSONL 에는 원격 표시가 **없다**

같은 스레드의 로컬 입력과 원격 입력 레코드를 전문 대조한 결과 —  
레코드 키·`payload` 키·`passthrough` 구조·`turn_context` 필드가 **전부 동일**. 출처 필드가 **하나도 없다.**

| 필요한 것          | 파일                                       |
| -------------- | ---------------------------------------- |
| 지시 문구·실행 명령·응답 | `~/.codex/sessions/**/rollout-*.jsonl`   |
| **원격/로컬 출처**   | `~/.codex/logs_2.sqlite` (`client_name`) |

→ rollout 만 확보하면 "누가 지시했는지" 판정 불가.  
Claude 는 세션 JSONL 하나에 내용과 출처가 모두 있었다 — **취득 요건이 벤더별로 다르다.**

#### (10) 사슬 완성 — 표식 파일 실험

| 시각(KST)  | 사건                                                                  |
| -------- | ------------------------------------------------------------------- |
| 15:39:32 | `turn/start` **conn=4 (`codex_chatgpt_android_remote`)** — 폰 지시 수신  |
| 15:39:58 | `exec` `rtk cat /tmp/AGENTRACE-MARKER.txt`                          |
| 15:40:02 | `task_complete.last_agent_message` = **`nonce: dc70739f…`** (28.0초) |

**부수 관측**: 실행 전 `SKILL.md`·`RTK.md` 를 읽었다  
→ 원격 지시도 로컬 에이전트 설정(AGENTS.md·스킬·프록시)을 그대로 상속한다.

---

## 3.2 iOS

**Android 와 결정적으로 다른 점 3가지**

1. **비탈옥 단말에서 평문 백업만으로 취득된다** — 루팅/탈옥 불필요
2. **앱 번들 `Info.plist` 만으로 원격 기능 보유가 판정된다** — 백업조차 불필요, **취득 난이도 최저**
3. **폰에 남는 시각의 의미가 Android 와 반대다** — Android=지시 시각 / iOS=**활성화** 시각
4. **자격증명을 얻지 못한다** — Android 는 평문 JWT 가 나오는데 iOS 평문 백업에서는 **0건**

### 3.2.0 iOS 공통 — 계정은 완전히 특정되지만 자격증명은 얻지 못한다 ★★

두 앱 추출본 **전체**를 `sk-` / `Bearer` / `eyJ` / `access_token` / `refresh_token` /  
`__Secure-next-auth` 로 훑어 **0건**. 자격증명은 **키체인**에 있고 평문 백업에 포함되지 않는다.

|                    | Android (루팅)                                                                                 | iOS (평문 백업)                      |
| ------------------ | -------------------------------------------------------------------------------------------- | -------------------------------- |
| Claude 자격증명        | `user_cookies_<accountUuid>.xml` **평문 세션 쿠키 9건** + `app_webview/Default/Cookies` **두 번째 사본** | **0건**                           |
| Codex/ChatGPT 자격증명 | `com.auth0.authentication.storage.xml` **평문 JWT 3종** (페이로드에 이메일·실명)                          | **0건**                           |
| 계정 특정              | 가능                                                                                           | **가능** (파일명·디렉터리명·`workspaceID`) |
| 인증 자격 재사용          | 가능                                                                                           | **불가**                           |

> 평문 백업만으로: "누구의 계정인가" 완전 특정 · "인증 자격을 재사용" 불가.  
> 이것이 평문 vs 암호화 백업의 실질 경계선이다.
> 차이: Claude 는 **email 이 평문**, ChatGPT 는 email 이 없는 대신  
> **장기 만료 식별자 쿠키**가 많다 (`Cookies.binarycookies` 18개 — `_puid`·`oai-did`(~~2027)·`oai-sc`(~~2027)·`_devicecheck`).
> ⚠ 이것은 **취득 경계선**의 기술이지 제품의 보안 결함 주장이 아니다.  
> ⚠ 백업 암호화가 켜져 있으면 키체인이 백업에 포함되므로 이 결론은 뒤집힐 수 있다 — 미검증.(§7.1)

**iOS 앱 entitlement**

```
keychain-access-groups
  Claude   Q6L2SF6YDW.com.anthropic.claude(.shared)
  ChatGPT  2DC432GLL2.com.openai.shared · .group.com.openai.chat
```

### 3.2.1 iOS × Claude Code

> **한 줄**: 앱이 **자기 Info.plist 로 원격제어 기능을 진술**하고, 승인은 파일이 아니라  
> Manifest 메타데이터(inode·Birth) 로만 남는다.

#### (1) 앱 설치 즉시 — 백업·로그인 불필요 ★★

`pymobiledevice3 apps list --udid <UDID> -t User` 한 번. **1차 지시자 중 취득 난이도가 가장 낮다.**

| 키                          | 값                                                                 | 근거     |
| -------------------------- | ----------------------------------------------------------------- | ------ |
| `NSFaceIDUsageDescription` | "…before accessing **remote control sessions**."                  | VR-034 |
| `NSUserActivityTypes`      | `['com.anthropic.claude.code.session']`                           | VR-034 |
| 확장 번들                      | `AppDomainPlugin-com.anthropic.claude.**CCRNotificationContent`** | VR-033 |

→ 앱이 자기 입으로 원격제어 세션 보유와 생체인증 게이트를 진술한다.  
→ ⚠ **Android 대응 관측 없음 — 미측정.** (`dumpsys package` 로 확인된 것은 `ALLOW_BACKUP` 계열뿐)

#### (2) 앱 최초 실행 — 로그인 불필요 ★

```
[폰] HomeDomain/Library/UserNotifications/<앱UUID>/Categories.plist        (NSKeyedArchiver)
[폰] HomeDomain/Library/UserNotifications/<앱UUID>/PushRegistration.plist  APNs 토큰 32B(production)
```

| 등록되는 카테고리                                                         | 근거     |
| ----------------------------------------------------------------- | ------ |
| **`CCR_PERMISSION_PROMPT`** (액션 `CCR_APPROVE`=승인 / `CCR_DENY`=거부) | VR-038 |
| `CCR_PERMISSION_PROMPT_DENY_ONLY` · `CCR_PERMISSION_SEND_FAILURE` | VR-038 |
| 키 `AuthenticationRequired` · `Destructive` · `Foreground`         | VR-038 |

> **소재지가 `AppDomain` 이 아니라 `HomeDomain` 이다** — 앱 컨테이너를 못 얻어도  
> 시스템 알림 레지스트리만으로 "이 단말이 원격제어 **승인 프롬프트**를 등록했다"가 선다.
> ⚠ **로그인 단계가 아니다.** `Categories.plist` Birth = 18:14:37 로 **최초 실행** 산물이고,  
> 계정이 박힌 최초 로그인 산물(`WebsiteDataStore/<account_uuid>/` 18:15:21)보다 **44초 앞선다.**  
> → 역방향 함의: 이 카테고리의 존재는 계정 로그인을 입증하지 않는다. (VR-038 정정)

#### (3) 로그인 후 — 피처플래그 평가 로그 (평문 JSONL, **휘발성**)

```
[폰] AppDomain-com.anthropic.claude/Library/Application Support/exposures/<org_uuid>/exposures.jsonl
```

```
2026-08-22T09:15:21.946Z  ccr_initial_events_limit
2026-08-22T09:15:21.946Z  ccr_context_usage_card       = true
2026-08-22T09:15:21.954Z  ccr_mobile_auto_default_mode = true  (exp auto-mode-default-launch-web)
```

각 행에 **밀리초 절대시각 UTC** + 기기식별자. 디렉터리명이 `org_uuid` 라 **조직 귀속이 경로에 박힌다.** (VR-039)

> ⚠ **휘발성**: 백업 bk-04 에 2,011B 로 있다가 **11분 뒤 소멸**했다(서버 전송 후 버퍼 비움).  
> 단발 취득으로 "없다"를 부재로 단정하면 안 된다. (VR-044)
> ⚠ Android `cache.json` 이 **서버가 내려준 인가 상태**인 것과 달리 이쪽은 **클라이언트 피처플래그 평가**다.  
> 같은 "기능 보유"로 뭉뚱그리면 안 된다.

#### (4) 원격제어 활성화 — 폰에 남는 시각은 **활성화** 시각이다 ★★

```
[폰] AppDomainPlugin-com.anthropic.claude.ClaudeNotificationService/
       Documents/segment/<writeKey>/0-segment-events        (미전송 버퍼 3,568B)
         {"event":"mobile.push.notification_displayed",
          "properties":{"session_id":"session_<ULID>", "ccr_notif_trace_id":"<uuid>"},
          "timestamp":"…T09:18:59.920Z"}
[폰] AppDomain-com.anthropic.claude/Documents/segment/<writeKey>/<N>-segment-events   (본체앱)
[폰] AppDomain-com.anthropic.claude/Library/Preferences/com.anthropic.claude.plist
       Anthropic-Active-Drawer-Tab            chat → code
       Anthropic-Has-Seen-Cowork-Remote-Tab   = true      ← 원격 탭 열람
       Anthropic-Has-Seen-Cowork-Dispatch-Feature · -Starter = true
```

⚠ `Anthropic-` 접두사를 빼면 grep 이 안 걸린다.

|                    | 폰에 남는 시각의 정체                                                                      | 근거         |
| ------------------ | --------------------------------------------------------------------------------- | ---------- |
| **iOS Claude**     | **활성화** 시각 — 세션 시작 18:18:52 → 푸시 기록 18:18:59.920. 첫 지시(18:23:12)보다 **4분 13초 앞선다** | VR-042     |
| **Android Claude** | **지시** 시각 — `recap_dismissed_at` 이 로컬 프롬프트와 +0.973 / +2.275초 (2회 재현)              | VR-003·006 |

→ iOS 는 지시를 한 번도 안 보내도 폰에 `session_id` 가 남는다.

`com.anthropic.claude.plist` 의 상태 플래그도 **지시 이전 산물**이다 — 기록 시각 18:23:02 로  
첫 지시 투입(18:23:10.796)보다 **8.8초 앞선다.** 폰 앱 포그라운드 재개는 18:22:52.06(`appLastResumedAt`).  
→ **폰에서 원격 탭을 연 행위**의 흔적이다.

#### (5) ★ 상태 플래그는 Android ↔ iOS **완전 대칭**이다 — 탐지 규칙 하나가 양쪽에 매핑된다

| 의미          | Android                                                     | iOS                                          |
| ----------- | ----------------------------------------------------------- | -------------------------------------------- |
| 원격 탭 열람     | `drawer_feature_discovery.xml` `has_seen_cowork_remote_tab` | `Anthropic-Has-Seen-Cowork-Remote-Tab`       |
| dispatch 기능 | `agent_chat.xml` `has_seen_dispatch_feature`                | `Anthropic-Has-Seen-Cowork-Dispatch-Feature` |
| starter     | `code_remote.xml` `cowork_starter_seen`                     | `Anthropic-Has-Seen-Cowork-Starter`          |
| 읽음 대기       | `code_remote_read_state.xml` `pending_acks`                 | `CodeSessionReadStatePending`                |
| 앱 사용량       | `app_stats.xml` `chat_list_views`                           | `appStats.chatListViews`                     |

**직렬화만 다르고 의미가 같다.**

#### (6) 원격 지시 후 변하는 것

| 남는 것                                                                                   | 근거     |
| -------------------------------------------------------------------------------------- | ------ |
| `AppDomain-…/Library/Preferences/account.<accountUuid>.plist` **492 → 947B**           | VR-043 |
| 신규 `CodeSessionReadStatePending` · `Dismissals` · `codeGitHubGHEConnected`             | VR-043 |
| `selectedEnvironment` **null → {environmentId:…, kind:anthropic_cloud, state:active}** | VR-043 |
| `AppDomain-<번들ID>/Library/LanguageModeling/` **birth = 입력 시작 시각**                      | §4.3   |

**입력 행위의 흔적** — 지시 #3 사례: `LanguageModeling` birth 18:30:36 → 지시 전송 18:30:54 → 승인 18:31:14.  
**지시보다 18초, 승인보다 38초 이르다** → 실행 결과가 아니라 **입력 행위**의 흔적이다.  
⚠ 키보드 학습 DB(`KeyboardDomain/…/user_model_database.sqlite`)는 앱 무관 입력에도 갱신되고  
대조군(무입력 구간)이 없어 인과는 **[INFERRED]**. Codex 원격 지시에는 대응 갱신이 **없어** 보편 지표가 아니다.

⚠ `account.<uuid>.plist` 의 개별 키는 "활성화"와 "지시"로 분류 불가다.  
파일 mtime 18:26:32 은 cfprefsd 지연 플러시이고 내부 최신 타임스탬프는 18:22:53 이라  
**가능 창이 [18:22:52, 18:26:32]** 로 원격 지시 2회와 그 이전 UI 조작을 모두 포함한다 **[INFERRED]**.

#### (7) ★★ 원격 승인 — 파일은 0건, 그러나 **메타데이터가 남는다**

매뉴얼(default) 모드, 승인 1회 관측:

| 위치       | 남는 것                                                                                                                                                                                   | 근거         |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **[폰]**  | 승인 관련 **파일 0건**. **단 `account.<accountUuid>.plist` 가 승인 완료 8초 후 원자적 교체** — 947→947B, **blob sha256 동일**, `Birth`/`LastModified`/`LastStatusChange` 갱신, `InodeNumber` 753565→**753809** | VR-045·046 |
| **[로컬]** | 세션 JSONL 에 **승인 주체·승인 경로 레코드 없음**                                                                                                                                                      | VR-045     |
| **[로컬]** | `tool_use` → `tool_result` **지연**으로만 드러남                                                                                                                                               | VR-045     |

```
Bash  (자동승인)   2.045s
Bash  (자동승인)   1.707s
Read  (자동승인)   0.053s
Write (폰 승인)   17.794s      ← 2~3자릿수 차이
```

> 바이트가 같아도 그 시각에 앱이 동작했다는 증거가 Manifest 에 남는다.  
> `Birth` 와 `inode` 가 함께 바뀌는 것은 임시파일 후 rename 하는 **원자적 교체(NSUserDefaults flush)의 서명**이다.  
> 파일 해시만 비교하는 차분은 이 활동을 전부 놓친다. (VR-046)
> ⚠ 같은 세션 1회 관측 (자동승인 3건 vs 폰 승인 1건). 반복·다른 툴·다른 네트워크 조건 **미검증**.  
> ⚠ **`permission-mode` 레코드는 승인 시각 추정에 쓸 수 없다.** timestamp 필드가 **없고**,  
> 파일 내 위치는 18:26:14 지시 블록 — 승인 턴(18:30:54~18:31:14)보다 **4분 40초 이르다.**  
> "수동 모드였다"는 사실만 말한다.

#### (8) 폰에 지시 내용 없음 — 전수 검색 0건

bk-05·bk-06 전 실파일에서 세션 ULID·표식 문자열 검색 → **0건** (적대적 검증 시 실측, VR 미승격).

---

### 3.2.2 iOS × Codex (ChatGPT 앱)

> **한 줄**: **blob 없이 경로 문자열만으로** 계정·기능이 특정되고,  
> **페어링만으로 폰이 PC 파일을 읽는다.**

#### (1) 앱 설치 즉시 — 번들 ID 부터 다르다 ★

⚠ **iOS 번들 ID 는 `com.openai.chat` 이다** (Android 는 `com.openai.chatgpt`). 탐지 규칙에 양쪽 등록 필수.

| 키                          | 값                                                                          | 근거     |
| -------------------------- | -------------------------------------------------------------------------- | ------ |
| `NSFaceIDUsageDescription` | "…to unlock **Codex** on this device."                                     | VR-049 |
| `NSUserActivityTypes`      | `['…conversation', '**com.openai.chatgpt.codex**', 'INSendMessageIntent']` | VR-049 |
| `INAlternativeAppName`     | `"Codex"` (Siri 대체 호출명)                                                    | VR-049 |

→ 기능 성격의 특정도는 **Claude 쪽이 높다** — 원격제어 **세션** 명시 vs Codex **잠금해제**.

#### (2) 앱 최초 실행 — 알림 카테고리와 `-default` 판 디렉터리

```
[폰] HomeDomain/Library/UserNotifications/<앱UUID>/Categories.plist
       codexFinished(완료 통지) · elicitationRequired
       승인 액션 mfa_push_auth → authChallengeApprove / authChallengeDeny
```

> ⚠ Codex 의 승인 액션은 도구 실행 승인이 아니라 계정 MFA 용이다.  
> Claude 의 `CCR_APPROVE`/`CCR_DENY` 와 **같은 것으로 읽으면 틀린다.**  
> "이 단말이 원격 도구실행 승인 프롬프트를 등록했다"고 말할 수 있는 쪽은 **Claude 뿐**이다.

```
[폰] AppDomain-com.openai.chat/Library/Application Support/
       codex-environments-default/            18:45:51
       codex-remote-slingshot-hosts-default/  18:45:53
       codex-profile-ua-<deviceID>__default/  18:45:57
```

⚠ `-default` 판은 계정 특정 근거가 아니다. 로그인 없이도 생긴다.  
(ChatGPT 최초실행 18:45:47 vs 로그인 18:46:38 — Claude 와 같은 패턴)

#### (3) 로그인 후 — ★ 경로 문자열만으로 판정된다

```
[폰] AppDomain-com.openai.chat/Library/Application Support/
       codex-remote-slingshot-hosts-<accountID>/     ← 이 시점엔 비어 있음
       codex-environments-<accountID>/environments.json   = []
       codex-taskItems-v2-default-<accountID>/ · codex-taskItems-v2-archived-<accountID>/
       codex-taskDetails-v1-<accountID>/
```

> blob 없이 `Manifest.db` 의 `relativePath` 문자열만으로도  
> "이 계정에 Codex 원격 호스트 기능이 준비됐다"가 성립한다. (VR-054)

#### (4) ★★ Android 와 정반대 — Android 는 아무것도 안 생긴다

```
[Android] databases/<userID>__<accountID>_websocket_topic_data.db
            DBWebSocketTopicOffset 5행 → Codex·원격 토픽 없음. 원격 지시 후에도 추가되지 않음
```

**iOS 가 로그인만으로 `codex-*` 골격을 만드는 것과 정반대다.** (관측 30·62)  
→ 발표 포인트: 같은 벤더·같은 기능인데 플랫폼별 잔존물이 비대칭이다.

#### (5) 페어링 — 호스트 메타가 내려온다

```
[폰] AppDomain-com.openai.chat/Library/Application Support/
       codex-remote-slingshot-hosts-<accountID>/response.json      (285B)
         [{"host_name":"<hostname>","os":"linux","arch":"x86_64","app_server_version":"0.149.0",
           "env_id":"env_e_…","online":true,"busy":false,"client_type":"CODEX_CLI",
           "last_seen_at":<apple_epoch>}]
       workspace-data/<userID>__<accountID>/codex-remote-message-drafts/   ← birth = 페어링 시각
```

⚠ **iOS 에는 `remembered_working_directories_by_host` 가 없다** — Android 의 최대 유출 경로가 iOS 에는 없다.  
`response.json` 은 호스트 1건의 메타만 담는다.

#### (6) ★★ 페어링은 연결 수립이 아니라 **열람 개시**다

페어링 코드 입력 직후 **18초간** 폰(`codex_chatgpt_ios_remote`, ConnectionId 7)이  
**사용자 지시 없이** 실행한 RPC — 창(18:52:20~18:53:00) 전수 **77건**:

```
thread/resume 24 · skills/extraRoots/set 12 · model/list 7 · config/read 6 · skills/list 6
configRequirements/read 4 · process/spawn 4 · plugin/installed 4 · thread/list 3
collaborationMode/list 2 · thread/goal/get 2 · fs/readFile 2
```

**`fs/readFile` 2건 — 폰이 로컬 파일을 읽었다.**  
**읽은 경로는 로그에 남지 않는다** [OBSERVED].

> **포렌식 함의**: 로컬 `logs_2.sqlite` 에 `thread/resume` 폭주 구간이 있으면 그 시각이 페어링 시점이고,  
> **사용자 지시가 없어도 열람은 일어난 것이다.**

#### (7) 원격 지시 — 로컬에 디렉터리가 생긴다 (iOS 특이) ★

```
[로컬] ~/.codex/visualizations/<스레드생성일>/<thread_id>/     빈 디렉터리, 원격 턴 시작 +7초
         ← conn=7 의 fs/createDirectory 호출 산물
```

경로의 날짜는 **실행일이 아니라 스레드 생성일**이라 디렉터리 mtime 과 어긋난다 —  
**그 불일치 자체가 "오래된 스레드를 나중에 원격으로 이어받았다"는 지시자다.** (VR-059)

⚠ **Android 원격 턴에서는 생성되지 않는다** — iOS 클라이언트 특이 동작이다.

#### (8) 폰에 남는 변화 — 신규 파일 0건, **mtime 만** ★

| 남는 것                                                                                                                    | 근거        |
| ----------------------------------------------------------------------------------------------------------------------- | --------- |
| 신규 실파일 **0건**                                                                                                           | VR-060    |
| 단 `workspace-data/<userID>__<accID>/codex-remote-message-drafts/` **mtime 18:52:27 → 18:55:25** (원격 턴 +2초, **내용 0바이트**) | VR-060 정정 |

> 한 경로에서 birth 와 mtime 이 서로 다른 행위를 가리킨다 —  
> `codex-remote-message-drafts` 의 **birth 는 페어링**, **mtime 은 원격 지시**다.  
> **blob 만 보면 둘 다 놓친다.**

#### (9) ⚠⚠ rollout `turn_context` 로 출처를 판정하면 **Android 원격을 로컬로 오분류한다**

같은 rollout 안 `turn_context` 4건을 비교하면 **iOS 원격 턴만** 튄다 —  
`active_permission_profile: null` + `sandbox_policy.writable_roots` 에 visualizations 경로.  
그러나 **Android 원격 턴은 로컬 턴과 완전히 동일**하다.

> 이 차이는 "원격"의 표지가 아니라 **iOS 앱 클라이언트가 보내는 turn 옵션의 부산물**이다.  
> 이걸로 출처를 판정하면 Android 원격을 로컬로 오분류한다. (VR-058)

**정답은 §3.1.2(8) 과 동일** — `logs_2.sqlite` `client_name` = `codex_chatgpt_ios_remote`.

#### (10) 폰에 지시 내용 없음 — 전수 검색 0건

nonce · 지시문 · 스레드ID 검색 → **0건** (VR-060).

#### (11) 미측정

**iOS × Codex 의 승인 흐름은 실험하지 않았다.** 알림 카테고리에 `elicitationRequired` 가  
등록돼 있어(VR-053) 대응 흐름의 **존재 가능성은 열려 있으나 미검증**이다.

---

# 4. 판별자 요약 — 슬라이드 1장용 ★★

## 4.1 "원격으로 지시했나" — **판별은 로컬에서 한다**

| 앱          | 소재                                 | 판별 값                                                                                                                                | 근거         |
| ---------- | ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **Claude** | 로컬 세션 JSONL (**내용과 같은 파일**)        | `promptSource:"queued"` ∧ `origin.kind:"human"` = **원격** `promptSource:"typed"` = 로컬 터미널 + 선행 `queue-operation` `enqueue`→`dequeue` | VR-008·041 |
| **Codex**  | 로컬 `logs_2.sqlite` (**내용과 다른 파일**) | `app_server.client_name` = `codex_chatgpt_ios_remote` / `codex_chatgpt_android_remote` / `codex-tui`                                | VR-027·055 |

**Codex 만 조작자의 단말 OS 까지 특정된다** (문자열에 `ios`/`android` 가 박혀 있음).  
**Claude 에는 그 축이 없다.**

**취득 요건이 다르다**: Claude = 세션 JSONL **1개** / Codex = rollout + `logs_2.sqlite` **2개**.

## 4.2 질문 → 근거 위치 (4칸 전부)

| 알고 싶은 것             | Android                                                          | iOS                                                                     |
| ------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------- |
| 원격 기능을 가진 앱인가       | **미측정**                                                          | **앱 번들 Info.plist** (백업조차 불필요) ★                                        |
| 원격 기능이 인가됐나         | `cache/app_start/**/cache.json` (**서버 인가 상태**)                   | `Categories.plist`(최초실행) · `exposures.jsonl`(로그인) · `codex-*` 경로명       |
| 원격제어를 실제로 **켰나**    | 폰 `code_remote.xml` · 로컬 `hasUsedRemoteControl`·`bridge-session` | 폰 Segment `session_id` · `Has-Seen-Cowork-Remote-Tab` · `response.json` |
| 원격으로 지시했나           | **로컬** `promptSource` / `client_name`                            | **로컬** (동일)                                                             |
| 무엇을 지시했나            | **로컬만** (Codex 는 폰에 슬러그 △)                                       | **로컬만**                                                                 |
| 어느 단말 OS 에서         | Codex `client_name` 에 `android`                                  | Codex `client_name` 에 `ios`                                             |
| 폰↔PC 결속             | 계정 2축 + **세션ULID**(Claude) / 계정 1축(Codex)                        | 계정 2축 + **세션ULID**(Claude) / 계정(Codex)                                  |
| 승인했나                | **미측정**                                                          | 파일 ✗ · **Manifest 메타 +8초**(Claude) / **미측정**(Codex)                     |
| 앱이 언제 켜져 있었나        | `app_stats.xml` `last_resumed_at`·`creation_count`               | `appStats.appLastResumedAt` · `mobile_code_session_backgrounded`        |
| **자격증명을 재사용할 수 있나** | **가능** — 평문 JWT·세션쿠키 획득                                          | **불가** — 전수 검색 0건 (키체인) ★                                               |

## 4.3 폰 ↔ 로컬 결속 축

| 축               | 폰                                                                           | 로컬                                                       |
| --------------- | --------------------------------------------------------------------------- | -------------------------------------------------------- |
| **계정** (Claude) | `account.<uuid>.plist` **파일명** · Segment traits · `code_remote.xml` **파일명** | `~/.claude.json` `oauthAccount` · JSONL `bridge-session` |
| **계정** (Codex)  | `group.com.openai.chat.plist` · datastore **파일명**                           | `state_5.sqlite` `remote_control_enrollments.account_id` |
| **세션** (Claude) | Android `recap_dismissed_at` 키 · iOS Segment `session_id`                   | `sessions/<pid>.json` `session_…` · JSONL `cse_…`        |
| **환경** (Claude) | Android `default_session_target` · iOS `selectedEnvironment`                | —                                                        |
| **환경** (Codex)  | `saved_hosts[].id` · `response.json.env_id`                                 | `state_5.sqlite` `environment_id`                        |
| **기기**          | Android `global_device_uuid.json` · iOS `Anthropic-Device-ID`               | —                                                        |

- **`environment_id` 는 두 기기에서 동일했다** — 갤럭시 `default_session_target.environment_id`  
= 아이폰 `selectedEnvironment.environmentId`. **계정 축과 독립된 결속 키**이며 **같은 계정의 서로 다른 단말을 묶는다.**

- **식별자는 파일명·디렉터리명에도 중복된다** (`account.<uuid>.plist` · `exposures/<org_uuid>/` · `codex-*-<accID>/`)  
→ **blob 없이 `Manifest.db` 경로 문자열만으로 계정·조직 특정이 가능**하고, **한 파일을 지워도 재구성된다.** (VR-040)

- `account_id`/`accountUuid` 는 **재로그인·MFA 변경을 넘어 불변** → 안정적 앵커.  
세션 ULID 는 세션마다 바뀌므로 **세션 단위 대조**에 쓴다.

⚠ Codex 는 폰 타임스탬프가 **실행 호스트를 오지시**하므로 시각 대조에 쓸 수 없다 (VR-029).

---

# 5. 오판 함정 — 이 연구의 실무 기여 ★★

| #   | 유형       | 내용                                                                                         |
| --- | -------- | ------------------------------------------------------------------------------------------ |
| 1   | **위음성**  | `remote_control_enrollments` **0행 ≠ 미사용** — enroll 이 MFA 로 거부돼도 0행. 구분은 `logs_2.sqlite` 로만 |
| 2   | **위음성**  | `~/.claude/sessions/` 는 **정상 종료 시 삭제** — 비었다고 "원격제어 쓴 적 없음"이 아니다                           |
| 3   | **위음성**  | iOS `exposures.jsonl` 은 **11분 만에 소멸** — 단발 취득의 "없음"은 부재가 아니다                               |
| 4   | **위양성**  | `settings.json` `true` + enrollment 행이 있어도 **채널은 죽어 있을 수 있다** — 토큰이 서버측 무효화돼도 마커는 "활성"     |
| 5   | **위양성**  | 폰 `last_connection_used_at` 이 **실행 호스트를 오지시한다** — 실제 실행은 WSL 인데 Windows 값이 갱신됨             |
| 6   | **위양성**  | iOS `-default` 판 디렉터리·알림 카테고리는 **로그인 없이도 생긴다** — 존재가 로그인을 입증하지 않는다                         |
| 7   | **오분류**  | rollout `turn_context` 로 원격 판정하면 **Android 원격을 로컬로 오분류**한다 (iOS 클라이언트 부산물)                 |
| 8   | **오귀속**  | Codex `server_name` 중복 — 같은 이름의 다른 머신에 귀속될 수 있다                                            |
| 9   | **의미오독** | Codex 알림 승인 액션(`mfa_push_auth`)은 **도구 실행 승인이 아니라 계정 MFA**                                  |
| 10  | **해석오류** | 폰 대화 캐시 15건은 **서버 페이지 크기**가 정한 상한 — "이 계정 대화가 15개"가 아니다                                    |
| 11  | **해석오류** | 캐시된 메시지는 **활성 분기만** — 편집·재생성으로 버려진 분기는 없다                                                  |
| 12  | **탐지누락** | 승인은 **파일 해시가 안 바뀐다** — inode·Birth 를 안 보면 전부 놓친다                                           |

> **결론 문구**: 설정 파일·DB 행은 **"설정된 적 있음"까지만** 말한다.  
> 실제 가용 구간과 실행 주체는 로그로만 확정된다.

**방법론 검증 사례** — 표식 파일(nonce)이 설계 목적을 넘어 작동했다.  
Android×Codex 1차 시도에서 지시가 **의도한 WSL 이 아니라 Windows Desktop 으로 갔는데**,  
nonce 가 돌아오지 않은 것이 그 사실을 즉시 드러냈다.  
이 검출이 없었다면 **"Codex 원격제어로 로컬 명령 실행 확인"이라는 오결론**을 낼 뻔했다.

---

# 6. 기대효과·파급효과 ★

## 6.1 이 결과가 당장 쓰이는 곳

**① "사람이 했나 AI가 했나"에 파일 근거로 답한다**
로그를 열어도 사용자 입력과 에이전트 실행이 같은 스트림에 섞여 있어 눈으로는 갈리지 않는다.
그 경계를 레코드 수준에서 그었고(§2.2.6), 실데이터 37,090건에서 **주체 미상 0건**으로 끝났다.

**② 압수 현장에서 무엇을 확보할지 즉시 결정된다**
경로 색인(§8)이 그대로 체크리스트가 된다. 특히 **Codex 는 rollout 과 `logs_2.sqlite` 를 둘 다
확보해야 출처가 판정된다**(§3.1.2(9)). 현장에서 rollout 만 떠 오면 "누가 지시했는가"는 사후에
복원할 수 없다 — 이건 절차를 미리 알아야만 막을 수 있는 종류의 손실이다.

**③ 오판 12건이 그대로 반박 논거가 된다**
`remote_control_enrollments` 0행은 미사용이 아니고(§5-1), 파일 해시가 같아도 그 시각에 앱은
동작했으며(§5-12), 폰 타임스탬프는 실행 호스트를 오지시한다(§5-5). 감정서에서 이 셋 중 하나라도
반대로 읽으면 결론이 뒤집힌다.

**④ 새 버전이 나와도 계속 쓴다**
파서가 버전이 아니라 구조를 보기 때문이다(§2.2.7). `0.63.0`~`0.149.0` 30종이 같은 코드로 읽히고,
`0.149.0` 은 코드 변경 없이 그대로 처리됐다. 회귀 516건이 이걸 지킨다.

## 6.2 수사 실무의 전제가 바뀐다

**"이 PC 앞에 앉아 있었다"가 더 이상 전제가 아니다**
원격제어가 열린 순간 물리적 알리바이와 디지털 행위가 분리된다. PC 에 남은 명령 실행 기록이
그 자리에 있던 사람의 것이라는 보장이 사라진다. 판별자(§4.1)는 이 분리를 되돌리는 축이고,
**Codex 는 조작자가 쓴 단말 OS 까지 특정된다**(`client_name` 에 `ios`/`android` 가 박힌다).

**폰 하나로 PC 의 프로젝트 구조가 드러난다**
Android×Codex 는 페어링 1회로 PC 작업 디렉터리 26건이 폰에 평문 전파된다(§3.1.2(6)).
사용자가 그 경로를 폰에서 연 적이 없어도 내려온다. **압수 범위를 폰으로 한정해도 PC 의 연구 주제·
학회명·도구 구성이 노출된다** — 영장 범위를 설계할 때 고려해야 할 사실이다.

**평문 백업이 어디까지 닿는지 선이 그어졌다**
iOS 평문 백업은 **계정을 완전히 특정하지만 인증 자격은 재사용하지 못한다**(§3.2.0).
"백업만 확보하면 계정에 들어갈 수 있다"는 통념과 다르고, 암호화 백업을 추가로 요구할지 판단하는
실무 기준이 된다.

**표준 절차를 벤더 단위로 나눠야 한다**
Claude 는 세션 JSONL 1개, Codex 는 rollout + SQLite 2개. Android 는 권한상승, iOS 는 백업.
**하나의 절차서로 네 조합을 덮을 수 없다.**

## 6.3 이어서 할 수 있는 것

- **다기기 사건** — `environment_id` 가 계정 축과 독립적으로 서로 다른 단말을 묶는다(§4.3).
  갤럭시와 아이폰이 같은 값을 가리켰다.
- **다른 에이전트로 확장** — 판별의 뼈대(구조 탐지 → 계층별 파서 → 단일 Event)는 벤더 중립이다.
- **시계열 상관** — 폰·PC 시각차가 부호 일관(+0.973 / +2.275초)이라 단말 시계 오차와 전송 지연을
  분리할 여지가 있다.

---

# 7. 적용 한계 (발표에서 반드시 밝힐 것) ★

## 7.1 취득 전제가 플랫폼마다 다르다

**iOS 는 백업만으로 가능했고, Android 는 권한상승(루팅)이 필요했다.**

- iOS: 비탈옥 단말에서 `pymobiledevice3` **평문 백업**만으로 전부 얻었다.
  단 `PasswordProtected: False` 조건이며, **백업 암호화가 켜져 있으면 키체인이 포함되므로
  "자격증명은 얻지 못한다"는 결론이 뒤집힐 수 있다 — 미검증.**
- Android: **Magisk 루팅** 기준이다. 비루팅 `adb backup` 은 이 단말에서 **산출물 0**이었고(VR-061),
  원인 단서가 삼성 고유 구현이라 **다른 OEM·AOSP 는 미검증**이다.
- 표본도 여기에 묶인다 — 단일 계정 · 단일 단말 쌍 · 시나리오당 1~2회 · 승인 관측 1회.

## 7.2 버전 업데이트에 따라 달라질 수 있다

**판별 규칙은 레코드 형식에 의존하고, 형식은 벤더가 바꾼다.**

- `promptSource`(Claude) · `client_name`(Codex) 은 §0.2 ② 버전에서 확인한 것이다.
  벤더가 형식을 바꾸면 **규칙을 다시 확인해야 한다.**
- 반면 **파서는 버전에 묶이지 않는다** — 구조 탐지 방식이라 `0.63.0`~`0.149.0` 30종을 같은 코드로
  읽는다(§2.2.7). 환경을 최신으로 통일해도 **구버전 파서는 계속 필요하다.**
- 아직 확인 못 한 것: `0.149.0` 헤드리스(`codex_exec`) 표본 0건 · Android 앱 매니페스트의 원격 선언 ·
  Android 양쪽과 iOS×Codex 의 **승인 흐름** · iOS 아티팩트의 **종료 후 존속**.

## 7.3 범위는 "CLI 에 원격으로 붙었을 때"다

**폰에서 AI 를 그냥 쓸 때 생기는 아티팩트는 상세 분석하지 않았다.**

- 이 문서가 다루는 것은 **모바일 앱이 로컬 PC 의 CLI 에 연동될 때** 생기거나 값이 바뀌는 것이다.
  앱 단독 사용(일반 대화·계정 쿠키·캐시)은 **연동 판별에 쓰이는 경우에만** 등장한다.
- 원리상 판정할 수 없는 것도 여기 있다 — shell redirection 으로 만든 파일(후보로만 표면화),
  개별 도구 호출의 승인 여부(정책 스냅샷만 존재), Codex 의 범용 파일 **읽기**(레코드 자체가 없다).
- iOS 는 백업이 행위 사이에 없어 **mtime 으로만 갈리는 구간**이 남는다:
  최초 실행↔로그인 44초 · 활성화↔로컬 지시↔원격 지시 2회가 **한 창에 묶인 구간**.

---

# 8. 경로 색인 — 패널·발표 부록 1장 ★

아래 블록 안의 `★` 는 **그 경로가 핵심**이라는 표시다 (절 제목의 ★ 와는 쓰임이 다르다).

## [로컬] PC

```
~/.claude.json                                          ★hasUsedRemoteControl
~/.claude/sessions/<pid>.json                           ★bridgeSessionId (정상종료 시 삭제)
~/.claude/projects/<슬러그>/<sessionId>.jsonl            ★promptSource · bridge-session · bridge_status
~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl            내용 (출처 필드 없음)
~/.codex/state_5.sqlite        remote_control_enrollments
~/.codex/logs_2.sqlite         ★client_name  (-wal · -shm 필수)
~/.codex/app-server-daemon/settings.json                ★remoteControlEnabled
~/.codex/auth.json                                      평문 JWT (민감)
~/.codex/visualizations/<스레드생성일>/<thread_id>/       ★원격 턴 산물 (iOS 클라이언트)
```

## [폰] Android — **루팅 필요**

```
/data/data/com.anthropic.claude/
  shared_prefs/user_prefs_AccountId(value=<acc>)_OrganizationId(value=<org>)_code_remote.xml   ★세션ULID·환경ID
  shared_prefs/user_prefs_…_code_remote_read_state.xml
  shared_prefs/user_prefs_…_drawer_feature_discovery.xml                ★원격탭 열람
  shared_prefs/user_prefs_…_agent_chat.xml
  shared_prefs/app_stats.xml
  cache/app_start/acc_<acc>/org_<org>/cache.json                        ★서버 인가상태·이메일

/data/data/com.openai.chatgpt/
  files/datastore/<userID>__<accID>_codex_remote_hosts.json                ★호스트·PC작업경로 26건
  files/datastore/<userID>__<accID>_codex_remote_control_enrollments.json  ★공개키·엔드포인트
  files/datastore/global_device_uuid.json
  databases/<userID>__<accID>_websocket_topic_data.db                      (원격 토픽 ✗)
```

## [폰] iOS — **비탈옥 · 평문 백업으로 취득**

```
HomeDomain/Library/UserNotifications/<앱UUID>/Categories.plist        ★CCR_APPROVE/DENY (앱 최초실행)
HomeDomain/Library/UserNotifications/<앱UUID>/PushRegistration.plist   APNs 토큰

AppDomain-com.anthropic.claude/
  Library/Preferences/com.anthropic.claude.plist                      ★Anthropic-Has-Seen-Cowork-Remote-Tab
  Library/Preferences/account.<accountUuid>.plist                     ★CodeSessionReadStatePending·환경ID·승인 inode
  Library/Application Support/exposures/<orgUuid>/exposures.jsonl     ★ccr_* (휘발성 11분)
  Library/LanguageModeling/                                            입력 시작 시각
AppDomainPlugin-com.anthropic.claude.ClaudeNotificationService/
  Documents/segment/<writeKey>/0-segment-events                       ★session_id · ccr_notif_trace_id
AppDomain-com.anthropic.claude/Documents/segment/<writeKey>/<N>-segment-events   ★session_id (본체앱)

AppDomain-com.openai.chat/                                            ⚠번들ID가 Android와 다름
  Library/Application Support/codex-remote-slingshot-hosts-<accID>/response.json  ★호스트·os·arch
  Library/Application Support/workspace-data/<userID>__<accID>/codex-remote-message-drafts/
                                                                      ★birth=페어링 · mtime=지시
  Library/Application Support/codex-environments-<accID>/environments.json
```

**앱 번들 메타 (백업 불필요)**: `pymobiledevice3 apps list --udid <UDID> -t User`  
→ `NSFaceIDUsageDescription` · `NSUserActivityTypes` · `INAlternativeAppName`

---

# 9. 도구 실측 — 발표 수치 (2026-08-22 17:20 동결)

| 항목                  | 값                                                       |
| ------------------- | ------------------------------------------------------- |
| Codex rollout 분석 대상 | **353파일** (0.63.0~0.149.0 30개 버전이 쓴 것)              |
| 복원 이벤트              | **37,090**                                              |
| actor 분포            | agent 34,698 · user 2,392 · **unknown 0**               |
| 미지 스키마              | **0건**                                                  |
| SQLite              | DB 6종 · threads 350 · turns 127                         |
| 단일 스키마 파서의 0건 구간    | **329/353 = 93.2%**                                     |
| 회귀 테스트              | **515 통과 + 1 skip**                                     |
| 정확도 (합성 통제, 각 100건) | 주체 식별 **100.0%** · 접근 파일 **100.0%** · MCP 호출 **100.0%** |

> **수치는 계속 자란다** — 하루 사이 rollout 344→353, 이벤트 30,232→37,090 으로 변했다.  
> 인쇄물에는 동결 시각을 각주로 반드시 적는다.  
> 재확인: `python3 -m pytest tests/test_panel_numbers.py -q -s`  
> `manifest N파일` 은 SQLite 사이드카 체크포인트에 따라 변동하므로 **인쇄하지 않는다.**

⚠ **100% 가 가리는 것**  
① shell redirection 파일 작성은 원리상 확정 불가 (후보로만 표면화)  
② **Codex 에는 범용 파일 읽기 레코드가 없다** — `action=read` 는 이미지 열람뿐이라  
　Claude 의 접근파일 정확도와 **나란히 놓으면 안 된다**  
③ 개별 승인 여부 판정 불가

---

# 10. 슬라이드 구성 제안 (팀원용)

| #   | 슬라이드                                      | 이 문서에서 가져올 곳                 |
| --- | ----------------------------------------- | ---------------------------- |
| 1   | 문제 — 로컬 아티팩트가 3계층·2세대로 갈린다                | §2.2.3 · §2.2.4 (93.2% 헤드라인) |
| 2   | 로컬 아티팩트 지도 (Claude vs Codex)              | §2.1.1 · §2.2.1 · §2.3 대비표   |
| 3   | 행위 주체 식별 — user / agent / unknown         | §2.2.6 (금지 목록 + unknown 0)   |
| 4   | 원격제어 4시나리오 개요                             | §3 도입 3개 결론 · §0 측정 조건       |
| 5   | Android × Claude — 세션 ULID 결속             | §3.1.1 (1)(4)                |
| 6   | Android × Codex — 작업 디렉터리 유출              | §3.1.2 (6)(7)                |
| 7   | iOS × Claude — Info.plist 자기진술 + 승인 inode | §3.2.1 (1)(7)                |
| 8   | iOS × Codex — 경로 문자열만으로 판정 · 페어링=열람       | §3.2.2 (3)(6)                |
| 9   | 판별자 한 장                                   | §4.1 · §4.2                  |
| 10  | 오판 함정 12건                                 | §5                           |
| 11  | 도구 실측·정확도                                 | §9                           |
| 12  | 기대효과·파급효과                                 | §6.1 · §6.2                  |
| 13  | 적용 한계 3가지                                 | §7 (7.1 취득 · 7.2 버전 · 7.3 범위) |
