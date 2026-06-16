# Event 스키마 v1.0 — 단일 진실원천 (canonical)

날짜: 2026-06-16 (비판 검토 4건 반영 확정본)
역할: 도구(파싱→정규화 출력) ↔ 팀원 `ground-truth.json` ↔ 채점 하네스 **공통 계약**.
규칙: **이 파일이 유일 원천.** 다른 문서는 이걸 *참조*만. 양쪽이 글자 그대로 동일 enum 사용. 미정 필드 null, 추측 금지.

---

## 0. 설계 원칙 (검토 반영)

- **"에이전트가 요청함" ≠ "호스트에서 일어남"** 을 분리한다 → `evidence_class`.
- `mechanism` 단일 필드가 의도·채널·결과를 뒤섞던 문제 → **직교 축**(`actor`/`channel`/`tool_name`/`effect`)으로 분리.
- 호스트 효과(exfil·persistence)는 *관찰 채널*이 아니라 *분석 분류* → `mitre`/`detections` 태그로.
- 시각은 **UTC canonical** 저장, KST는 표시용. (KST 하드코딩 금지 — 9시간 오정렬 버그.)
- `preview`에 시크릿 평문 금지 → **마스킹**.
- 삭제/카빙 레코드는 path/record가 없을 수 있음 → nullable + `recovery`.

---

## 1. Event (정규화 출력 단위)

```jsonc
Event {
  "schema_version": "1.0",
  "event_id":   "str",        // 결정론적: sha256(source_sha256 + record + sequence)[:16]  (재파싱 시 동일)
  "sequence":   0,            // 세션 내 단조 증가(ts 충돌 시 정렬 tiebreaker)

  // ── 시각 ──
  "ts_utc":     "2026-06-16T08:35:07.524Z",   // canonical(UTC). 정렬·상관은 이걸로.
  "ts_raw":     "str",        // 아티팩트 원문 타임스탬프(가공 X)

  // ── 행위자/식별 ──
  "agent":       "claude|codex|gemini",
  "agent_version":"str|null",
  "session_id":  "str",       // 유니크 = agent + session_id 로 네임스페이스
  "host":       { "hostname":"str", "os":"windows|wsl", "wsl_distro":"str|null", "user":"str" },
  "cwd":         "str",
  "git_branch":  "str|null",

  // ── 인과(재구성 필수) ──
  "turn_id":        "str|null", // 대화 턴(message uuid)
  "tool_call_id":   "str|null", // call↔result 페어링 (네이티브 id)
  "parent_event_id":"str|null", // 직접 상위(서브에이전트·thinking→tool 등)

  // ── 무엇을(직교 축) ──
  "actor":      "user|agent|subagent|hook|system",
  "channel":    "prompt|paste|response|thinking|tool_call|tool_result|hook|mcp",
  "tool_name":  "str|null",    // "Read"|"Bash"|"Write"|"WebFetch"|MCP도구명 (channel=tool_*일 때)
  "effect":     "read|write|exec|network|none",
  "evidence_class":"agent_claim|tool_observed|host_confirmed",
  "outcome":    "success|error|denied|interrupted|blocked|unknown",

  // ── 대상 ──
  "resource_type":"file|cmd|url|mcp|process|other",
  "resource":    "str",        // ★정규화형(§3 규칙) — 매칭 키
  "resource_raw":"str",        // 원문(가공 X)

  // ── 내용(시크릿 마스킹) ──
  "content_ref": { "preview_redacted":"str(<=200, 시크릿/PII 마스킹)", "sha256":"str" },

  // ── 탐지/분류 ──
  "detections": [ { "id":"CLFXTEST-001", "kind":"secret|pii", "detector":"str", "confidence":0.0 } ],
  "mitre":      [ "T1552.001" ],   // 서브기법(.yyy) 허용

  // ── 복구/출처 ──
  "recovered":  false,
  "recovery":   { "method":"live|deleted|carved|wal|journal|shadow", "confidence":0.0, "partial":false } | null,
  "source":     { "path":"str|null", "record":0, "byte_range":[0,0]|null, "source_sha256":"str" },  // path/record는 carved면 null 허용
  "extractor":  { "name":"cli-llm-forensic", "version":"str" }
}
```

### enum 고정 (양쪽 글자 그대로)
- `actor`: **user · agent · subagent · hook · system**
- `channel`: **prompt · paste · response · thinking · tool_call · tool_result · hook · mcp**
- `effect`: **read · write · exec · network · none**
- `evidence_class`: **agent_claim**(에이전트가 요청, transcript) · **tool_observed**(도구 결과가 성공 보고, 약함) · **host_confirmed**(독립 호스트 아티팩트로 확증)
- `outcome`: **success · error · denied · interrupted · blocked · unknown**
- `resource_type`: **file · cmd · url · mcp · process · other**

새 값 필요 → *둘이 합의해 이 파일에 추가*. 임의 생성 금지.

---

## 2. `actor` × `channel` 유효 조합 (검증 규칙)

| actor | 허용 channel |
|---|---|
| user | prompt, paste |
| agent | response, thinking, tool_call, tool_result, mcp |
| subagent | response, thinking, tool_call, tool_result |
| hook | tool_call, tool_result |
| system | (호스트 아티팩트서 온 것 — channel=tool_call/result 아님, evidence_class=host_confirmed) |

> **호스트 효과(inventory 기록·exfil·bashrc 변조)** = `actor:system` + `evidence_class:host_confirmed` + `effect:write|network|exec` + 분류는 `mitre`. transcript만으론 `agent_claim`까지밖에 못 감 — host_confirmed는 별도 소스 필요.

---

## 3. 매칭 계약 (★팀원 채점의 핵심 — 이게 없으면 점수 무의미)

도구 Event ↔ ground-truth `attack_event` "일치" 정의:

1. **resource 정규화**(`resource_type`별):
   - `file` → realpath + `$HOME` 상대화 + 소문자 드라이브 + forward-slash. (`/mnt/c/..`·`C:\..`·`\\wsl$\..` 동일화)
   - `cmd` → `shlex` 토큰화 후 **argv[0] + 대상(파일/호스트/URL)** 만 비교(원문 문자열 비교 금지 — 공백·플래그순서 변동).
   - `url` → scheme+host+path (query 무시 옵션).
2. **매칭 키** = `(effect, resource_type, normalized_resource)` + `ts_utc`가 incident window 내 (정렬·tiebreak용, 단독 기준 아님).
3. **할당** = window 내 **1:1**(한 Event는 ground-truth 1개에만). precision/recall 분모 명시.
4. **시크릿 탐지 채점** = ground-truth `expected_detections`의 id가 Event `detections[].id`에 있나 → recall. `noise_files`가 secret로 태깅되면 → false positive(precision).
5. **재구성등급**(논문) = ground-truth `attack_events` 중 도구가 매칭한 비율 → 완전/부분/불가.

---

## 4. ground-truth.json 정렬 (스테이징 가이드와 동일 어휘)

`attack_events`는 위 enum을 **그대로** 사용:

```jsonc
"attack_events": [
  { "ts_utc":"...", "actor":"agent",  "channel":"tool_call", "tool_name":"Read",
    "effect":"read",  "resource_type":"file", "resource":"~/victim-proj/.env",
    "evidence_class":"agent_claim", "expect_detections":["CLFXTEST-001","CLFXTEST-002","CLFXTEST-003","CLFXTEST-004"] },
  { "ts_utc":"...", "actor":"agent",  "channel":"tool_call", "tool_name":"Bash",
    "effect":"exec",  "resource_type":"cmd",  "resource":"cat ~/victim-proj/config.py", "evidence_class":"agent_claim" },
  { "ts_utc":"...", "actor":"system", "channel":"hook",      "tool_name":null,
    "effect":"write", "resource_type":"file", "resource":"/tmp/inventory.txt",
    "evidence_class":"host_confirmed", "mitre":["T1074.001"] },
  { "ts_utc":"...", "actor":"system", "channel":"hook",      "effect":"network",
    "resource_type":"file", "resource":"/tmp/clfx-sink/results.b64",
    "evidence_class":"host_confirmed", "mitre":["T1567"] },
  { "ts_utc":"...", "actor":"system", "channel":"hook",      "effect":"write",
    "resource_type":"file", "resource":"~/.bashrc", "evidence_class":"host_confirmed", "mitre":["T1546"] }
]
```

> `system` 이벤트는 `evidence_class:host_confirmed` — 즉 도구가 *호스트 아티팩트*(inventory 파일·bashrc·exfil 파일)로 확증해야 매칭. transcript만으론 안 됨. 이게 "에이전트가 요청 vs 실제 일어남" 구분.

---

## 5. canonical 예시 (둘이 눈에 박기)

에이전트가 `.env`를 자율로 읽은 1건:
```json
{
  "schema_version":"1.0","event_id":"a1b2c3d4e5f6a7b8","sequence":42,
  "ts_utc":"2026-06-16T08:35:07.524Z","ts_raw":"2026-06-16T08:35:07.524+09:00",
  "agent":"claude","agent_version":"2.1.178","session_id":"019caed9-...",
  "host":{"hostname":"DEV-PC","os":"wsl","wsl_distro":"Ubuntu-24.04","user":"dev"},
  "cwd":"~/victim-proj","git_branch":"main",
  "turn_id":"msg_77","tool_call_id":"toolu_01ab","parent_event_id":"e_turn77",
  "actor":"agent","channel":"tool_call","tool_name":"Read","effect":"read",
  "evidence_class":"agent_claim","outcome":"success",
  "resource_type":"file","resource":"~/victim-proj/.env","resource_raw":"/home/dev/victim-proj/.env",
  "content_ref":{"preview_redacted":"STRIPE_SECRET_KEY=‹SECRET:CLFXTEST-001›\nAWS_ACCESS_KEY_ID=‹SECRET:CLFXTEST-002›","sha256":"d4f1.."},
  "detections":[{"id":"CLFXTEST-001","kind":"secret","detector":"stripe","confidence":0.99}],
  "mitre":["T1552.001"],
  "recovered":false,"recovery":null,
  "source":{"path":"~/.claude/projects/-victim-proj/019caed9.jsonl","record":42,"byte_range":null,"source_sha256":"9f97.."},
  "extractor":{"name":"cli-llm-forensic","version":"0.1"}
}
```

---

## 6. 범위 메모 (v1 실용 — 과설계 회피)

- 서명/HMAC custody·Hungarian 할당 등은 v1 범위 밖(스트레치). v1은 SHA256(+md5는 보조 교차검증만, 단독 금지) + greedy 1:1로 충분.
- `host_confirmed`(Sysmon/EVTX/$MFT 상관)는 **네이티브 Windows 한정**·스트레치. WSL2 호스트층은 사각(이게 도구 존재이유) — v1은 transcript `agent_claim` + 로컬 호스트흔적(inventory·bashrc) 중심.
- 필드 많아 보이나 핵심 필수 = `event_id·ts_utc·agent·actor·channel·effect·evidence_class·resource(+type)·detections·source`. 나머지는 있으면 채우고 없으면 null.

확정: 이 v1으로 양쪽 시작. 변경은 이 파일 PR로만.
