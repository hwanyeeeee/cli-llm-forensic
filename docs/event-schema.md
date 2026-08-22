# 출력 레코드 형태 (Event)

파싱·분석 결과는 아래 한 가지 레코드로 정리한다. **한 줄 = 에이전트가 한 행동 하나.**

```jsonc
Event {
  "ts":       "시각 (UTC, ISO8601)",
  "agent":    "claude | codex | gemini",
  "session":  "세션 id",
  "actor":    "user | agent | unknown",               // 사람이 입력했나, 에이전트가 알아서 했나
  "action":   "prompt | read | bash | write | paste | response | mcp | search | spawn",
  "target":   "대상 (파일 경로 / 명령 / URL)",
  "preview":  "내용 미리보기 (시크릿은 가림)",
  "tags":     ["secret", "pii"],                      // 분석으로 붙는 표시 (없으면 빈 배열)
  "source":   { "file": "원본 jsonl 경로", "line": 42 },  // 증거 추적용
  "meta":     { }                                     // 아래 참조. 비면 직렬화에서 생략된다
}
```

`actor` 의 `unknown` 은 **"봤는데 못 가렸다"** 는 뜻이다. 판정 못 한 값을 `user` 로 흘리지 않는다.

## meta — 있을 때만 붙는 부가 필드

`meta` 는 자유 딕셔너리가 아니라 **소스가 실제로 관측했을 때만** 채운다.
필드가 없는 것과 값이 `unknown` 인 것은 다르다.

| 필드 | 값 | 언제 붙나 |
|---|---|---|
| `origin_channel` | `remote` \| `local` \| `unknown` | 원격 지시 여부. Claude=`promptSource`, Codex=`logs_2.sqlite` `client_name` 조인 |
| `origin_channels_seen` | `["local","remote"]` | `origin_channel` 이 `unknown` 인 이유(양쪽 관측)를 남긴다 |
| `prompt_source` · `origin_kind` | 원문 값 | **Claude 전용.** `origin_channel` 이 `unknown` 일 때만. 왜 못 가렸는지의 근거 — `sdk`·`system` 은 판정 실패가 아니라 사람이 낸 지시가 아니었다는 뜻이다 |
| `origin_os` | `ios` \| `android` \| `unknown` | **Codex 전용.** `client_name` 접미가 조작 단말 OS 를 담는다. `origin_channel == "remote"` 로 확정됐을 때만 단다 |
| `origin_os_seen` | `["android","ios"]` | 한 스레드를 서로 다른 OS 단말이 이어받아 `origin_os` 가 `unknown` 일 때 |
| `origin_os_candidates` | `["android"]` | 채널이 `unknown` 이라 단말을 단정할 수 없을 때. **주장이 아니라 관측 보존이다** |
| `bridge_session_id` | 원문 값 | **Claude 전용.** 같은 파일의 `bridge-session` 레코드가 이 세션을 원격 브리지에 이었을 때. 계층마다 접두사가 달라(`uuid` vs `cse_…`) 잇는 키는 레코드 자신의 `sessionId` 다 |
| `confidence` | `high` \| `medium` \| `low` \| `unknown` | 파일 작성 판정의 확신도 |
| `write_target` | 경로 | shell 리다이렉션으로 만들어졌을 **후보** — 확정 아님 |
| `sqlite_thread_id` · `cwd` · `git_branch` · `git_sha` · `model` · `approval_mode` · `sandbox_policy` | 원문 값 | Codex `state_5.sqlite` `threads` 에서 교차 부착 |
| `environment_id` · `server_name` | 원문 값 | 원격이 관측된 스레드에만. `server_name` 은 **고유 식별자가 아니다**(중복 실측) |
| `agent_kind` · `parent_thread_id` · `depth` · `agent_path` | 원문 값 | subagent 계층. **subagent 는 actor 가 아니다** |

## 규칙

- 모든 Event는 `source` 로 **원본 파일·줄을 되짚을 수 있어야** 한다 (증거능력).
  - `source.file` 이 가리키는 곳: `history.jsonl` / `projects/<…>.jsonl` / 붙여넣기 본문이 따로면 `paste-cache/<hash>.txt`. 붙여넣은 이미지(transcript 안 base64)·읽은 파일(`toolUseResult` 필드)은 그 내용이 든 transcript 줄을 가리킨다.
- 시크릿 값은 `preview` 에 그대로 넣지 말고 가린다 (예: `‹secret›`).
- **판정 못 한 값에 기본값을 주지 않는다.** 관측이 없으면 필드를 안 달고, 봤는데 못 가렸으면 `unknown` 이다. 둘 중 무엇도 `local`·`user` 를 뜻하지 않는다.
- `approved_by_user` 는 **기록하지 않는다.** 개별 승인 레코드가 존재하지 않아 정책 스냅샷(`approval_mode`)만 남는다.
- 데이터셋 정답(`ground-truth`)도 이 형식의 `actor`·`action`·`target` 을 그대로 쓴다 → 도구 출력과 1:1 비교.
- 새 필드가 필요하면 이 파일을 고치고 PR로만 바꾼다 (다른 문서에 복제 금지).
- **상태는 Event 가 아니다.** `hasUsedRemoteControl` 같은 호스트·계정 설정 플래그는 행동이
  아니라 상태라서 Event 로 만들면 같은 사실이 타임라인에 한 줄 더 늘어 과계수가 난다.
  소스 메타(원격제어 마커)로만 노출한다 → `docs/원격제어-마커.md`.
