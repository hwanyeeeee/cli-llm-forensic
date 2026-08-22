# origin_channel — 원격 지시와 로컬 실행을 한 타임라인에 (13단계)

폰에서 내린 지시와 로컬 PC에서 일어난 실행을 **같은 타임라인 위에서 구분**하기 위한 최소 필드.

- 근거: `/mnt/c/projects/llm모바일아티팩트/output/패널-인계-모바일원격제어.md` §4
  (Android SM-A235N 루팅 실측 · 관측 63건 · Claude Code 2.1.238 · Codex 0.149.0)
- 구현: `clfx/parser.py`(Claude) · `clfx/codex_sqlite.py`(Codex)
- 고정 테스트: `tests/test_origin_channel.py`
- **로컬 아티팩트만 다룬다.** 폰 단말 파싱은 이 저장소 범위 밖.

---

## 1. 도메인과 '없음'의 의미

`meta.origin_channel ∈ {remote, local, unknown}`.

**판별 못 하면 `unknown`이다. `local`로 폴백하지 않는다.** 1단계에서 없앤 조용한 user 폴백과
같은 실패 유형(모르는 걸 아는 것처럼 표시)이라 같은 규칙을 적용한다.

필드가 **없는 것**과 `unknown`은 다르다:

| 상태 | 뜻 |
|---|---|
| 필드 없음 | **판정 대상 레코드가 아니다.** 관측 자체가 없다 |
| `unknown` | **봤는데 못 가렸다.** 근거가 반쪽이거나 상충한다 |
| `local` | 로컬 타이핑/로컬 클라이언트라는 **양성 근거**가 있다 |

어느 쪽도 "로컬이었다"를 뜻하지 않는다. 보고서에서 필드 부재를 local로 읽으면 안 된다.
`test_no_local_verdict_without_positive_evidence`가 이 불변식을 고정한다.

---

## 2. Claude — 세션 JSONL 한 파일로 끝난다

| 근거 | 값 |
|---|---|
| 원격 | `promptSource="queued"` ∧ `origin.kind="human"` |
| 로컬 | `promptSource="typed"` ∧ `origin.kind="human"` |
| 그 외 | `unknown` |
| 부가 | `bridge-session` 레코드 → `meta.bridge_session_id` |

`origin.kind="human"`을 함께 보는 이유는 Android 실측에서 **이 조합이 위양성 검증된 조합**이기
때문이다. `origin`이 아예 없는 구버전 레코드는 근거가 반쪽이라 `unknown`으로 둔다.

**지시 레코드에만 붙인다.** 뒤따르는 `tool_use`/`toolUseResult` 실행 Event에는 채널을 찍지 않는다 —
같은 턴이라도 "그 실행이 원격에서 왔다"는 것은 추론이지 기록이 아니다
(`test_claude_execution_events_carry_no_channel`).

### 세션 ID 접두사 함정

같은 세션을 가리키는 ID가 계층마다 접두사가 다르다 — 로컬은 uuid,
브리지는 `cse_…`(로컬 상태·URL 쪽은 `session_…`). **접두사 문자열끼리 비교해 이으면 안 된다.**
잇는 키는 레코드 자신의 `sessionId`다(`test_claude_bridge_session_joins_on_session_id_not_prefix`).

브리지 세션이 열려 있다는 건 "원격으로 닿을 수 있다"까지만 말한다. 그 턴이 폰에서 왔다는
뜻이 아니므로 `bridge_session_id` 단독으로 remote 판정하지 않는다.

---

## 3. Codex — rollout에는 없다. `logs_2.sqlite`를 조인해야 한다

rollout JSONL 어디에도 원격 여부가 없다. `logs_2.sqlite`의 tracing span 텍스트에서 뽑는다.

```
app_server.request{… app_server.connection_id=4 …
                   app_server.client_name="codex_chatgpt_android_remote" …}: …
```

1. `app_server.connection_id=N` ∧ `app_server.client_name="…"` → **연결별 클라이언트**
2. 같은 span에 실린 `thread_id=…` → 연결을 **스레드**에 잇는다
3. `client_name`이 `_remote`로 끝나면 remote, 아니면 local
4. `turn/start connection_id=ConnectionId(N)` → 실제로 턴을 몬 연결(`started_turns`)

**연결 단위로 묶는 게 핵심이다.** 최근 RPC 표본만 훑으면 connection 0의 `codex-tui`
`plugin/list` 노이즈가 다수라 원격 연결이 묻힌다. 실측 이 PC 기준 tui 138행 대 원격 69행.
`test_codex_connection_join_survives_tui_noise`가 노이즈 60행 대 원격 4행으로 이걸 고정한다.

6단계에서 `logs_2`를 '보조'로 등급했지만 **원격 판별에는 1차 증거다.**

`remote_control_enrollments`에서 `environment_id`·`server_name`을 가져와 원격이 관측된
Event에만 붙인다. 등록 행은 "어느 환경에 등록됐나"까지만 말하고 채널이 살아 있음을 보증하지
않으므로(VR-023), 행의 존재 자체를 원격 실행의 근거로 쓰지 않는다.

### 한 스레드가 양쪽에 보이면 unknown

로컬 TUI로 시작한 스레드를 폰에서 `thread/resume`하면 **두 연결 모두에 찍힌다.**
어느 *턴*이 어느 쪽인지는 스레드 단위로 가릴 수 없다 → `origin_channel="unknown"`.
다만 관측을 버리지 않고 `meta.origin_channels_seen=["local","remote"]`에 남겨 unknown의
근거를 사후 감사할 수 있게 한다.

---

## 4. 실데이터 분포 (이 PC, 2026-08-22)

`~/.claude.json`에 `hasUsedRemoteControl=true`가 있어 실제 원격제어 사용 이력이 있는 머신이다.

### Claude — `queued`가 실제로 잡히는가: **잡힌다**

원본 레코드 1,059파일 / 427,751줄 기준 `promptSource` 분포:

| 값 | 건수 |
|---|---|
| `typed` | 5,042 |
| `sdk` | 1,950 |
| `system` | 600 |
| **`queued`** | **250** |
| `suggestion_accepted` | 71 |

`origin.kind`와의 조합:

| 조합 | 건수 | 판정 |
|---|---|---|
| `queued` ∧ `human` | **231** | remote |
| `typed` ∧ `human` | 4,514 | local |
| `queued`, origin 없음 | 19 | unknown |
| `typed`, origin 없음 | 528 | unknown |
| `sdk`, origin 없음 | 1,950 | unknown |
| `system` ∧ (task-notification/peer/auto-continuation/없음) | 600 | unknown |
| `suggestion_accepted` ∧ `human` | 71 | unknown |

파싱 결과 Event 107,256건:

| `origin_channel` | 건수 |
|---|---|
| 필드 없음(실행 Event 등) | 98,715 |
| `local` | 5,018 |
| `unknown` | 3,277 |
| **`remote`** | **246** |

레코드 231건 → Event 246건인 것은 한 레코드의 `content` 파트마다 Event가 하나씩 나오기
때문이다(텍스트+이미지 동반 레코드 14건).

**원격 턴이 있는 세션 52개는 전부 로컬 턴도 가지고 있다.** 세션 단위로 채널을 매기면 틀린다 —
필드가 Event 단위여야 하는 실측 근거다.

`bridge_session_id`는 Event 13,254건에 붙었지만 **서로 다른 브리지 ID는 2개뿐**이고,
remote 246건 중 브리지 ID를 가진 건 **13건**이다. `~/.claude/sessions/`가 정상 종료 시
삭제되고 `bridge-session` 레코드도 드물게만 남기 때문이다(VR-009). 브리지 ID는 **보강 근거**로만
쓸 수 있고 원격 판정의 필수 조건이 될 수 없다.

### Codex — 원격 연결은 잡히지만 스레드 판정은 unknown

`logs_2.sqlite` 22,855행에서 뽑은 연결별 클라이언트:

| connection_id | client_name | 채널 | 턴 시작 |
|---|---|---|---|
| 0 | `codex-tui` | local | — |
| 1 · 43 | `codex_app_server_daemon` | local | — |
| 3 | `codex-tui` + `codex_app_server_daemon` | local | — |
| **4** | **`codex_chatgpt_android_remote`** (69행) | **remote** | **✔** |
| 5 | `codex-tui` | local | ✔ |

`remote_control_enrollments` 1행 — `environment_id=env_e_6a885fdc…`,
`server_name=Hwansktop`, `remote_control_enabled=NULL`.

스레드 판정 3건: local 2 · **unknown 1**. Event 37,090건 중 `local` 1 · `unknown` 8 ·
나머지 37,081건은 필드 없음.

> **원격제어를 실제로 썼는데 `remote`로 판정된 Codex Event가 0건이다.**
> 유일하게 폰이 건드린 스레드 `01a024ca…`가 로컬 TUI(connection 5)에서도 관측돼
> `unknown`이 됐다. 폰에서 `thread/resume`한 스레드라 양쪽에 다 찍힌 것이고,
> `origin_channels_seen=["local","remote"]`에 그 사실이 남는다.
> **이건 결함이 아니라 스레드 단위 판정의 해상도 한계다.** 턴 단위로 가르려면
> `turn/start`의 타임스탬프와 rollout 턴을 시간창으로 맞춰야 하는데, 그건 추정이라
> 지금 규칙(양성 근거만)으로는 하지 않는다.

커버리지가 낮은 것(37,090 중 9)도 정상이다. `logs_2`는 최근 로그만 보관하므로
과거 스레드는 로그에 없고, 그래서 필드가 붙지 않는다 — 관측 부재이지 local이 아니다.

---

## 5. 이 필드가 말하지 않는 것

- **실행 위치가 아니라 지시 출처다.** `remote`여도 명령은 전부 로컬 PC에서 실행됐다.
  그게 이 필드의 요점이다 — "폰에서 시켰고 여기서 돌았다".
- **Claude 실행 Event에는 채널이 없다.** 프롬프트만 채널을 안다. 턴 전체로 전파하지 않았다.
- **Codex는 턴 단위로 못 가린다.** 스레드가 최소 단위다(§3).
- **음성 결과가 미사용을 뜻하지 않는다.** `remote_control_enrollments` 0행은 enroll 실패에서도
  나오고(VR-013), `~/.claude/sessions/`는 정상 종료 시 비므로(VR-009), 비어 있음은 근거가 아니다.
- **버전 의존.** 메시지 단위 판정은 Claude Code 2.1.238, Codex 판별자는 0.149.0 관측이다.
  브리지 세션 ID·enrollment는 버전 의존이 낮아 1차 근거, 메시지 단위 판정은 보강 근거로 쓴다.
