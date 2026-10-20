# Codex 정확도 측정 결과 (10단계 · 신청서 목표 ⑤)

`docs/validation/정확도-검증-시나리오.md`의 3시나리오를 **Codex 기록 형식으로 확장**해 측정한 결과다.
Claude 측정본의 대응물이며, 경진대회 패널 **③결과**에 들어간다.

- 하네스: `tests/test_accuracy_codex.py` (pytest. 별도 스크립트 없음 — 회귀에 그대로 얹힌다)
- 재현: `python3 -m pytest tests/test_accuracy_codex.py -q -s`
- 입력: 정답 라벨을 가진 **합성 rollout**. 실데이터 복사 없음, 민감값 없음, 난수 없음(결정적).
- 채점: 도구가 낸 Event를 `(source.file, source.line)`으로 정답 레코드와 1:1 대조.
  추가 읽기·재집계 없음 — 도구가 내놓은 그대로 센다.

---

## 0. era 구성 — 왜 50:50인가

**legacy 50 : item 50 (균형 구성)** 을 택했다.

실측 분포는 legacy 329파일 : item 24파일 ≒ **93:7** 이다. 그 비율을 그대로 쓰면 item era 표본이
100건 중 6건뿐이라 **item era의 정확도를 따로 낼 수 없다**(1건만 틀려도 83.3%, 통계로 의미 없음).
한쪽 era만 재거나 한쪽에 쏠린 표본으로 재면 **회수율 착시**가 생긴다.

그래서 두 era를 균형으로 넣고 **era별 정확도를 분리 집계**한다. 아래 표의 `비고` 열에 era별 수치가 있다.
전체 정확도는 이 균형 구성 기준이며, 실측 분포 가중 정확도가 아니다.

MCP 시나리오만 예외다 — 사유는 §3.

---

## 1. 결과 표

```
시나리오            건수   정확도   비고
주체 식별              100   100.0%   legacy 100.0% · item 100.0% · 왜곡 30/30
접근 파일 판정           100   100.0%   legacy 100.0% · item 100.0% · 누락 0 · 오탐 0 · redirect 후보 10/10
MCP 호출 탐지          100   100.0%   누락 0 · 오탐 0 · server/tool 60/60
```

100%는 **합성 데이터가 통제됐기 때문**이지 도구가 모든 상황에서 완전하다는 뜻이 아니다.
무엇을 못 재는지는 §5에 분리해 적었다. 그쪽이 이 문서의 본론이다.

---

## 2. 시나리오별 구성

### 2-1. 주체 식별 (100건)

각 era 50건씩, 정답 **user 40 / agent 60**.

| 레코드 | legacy 형식 | item 형식 | 정답 | 건수(era당) |
|---|---|---|---|---|
| 사용자 프롬프트 | `user_message` | `UserMessage.content[].text` | user/prompt | 13 |
| 이미지 붙여넣기 | `user_message` + `local_images` | `UserMessage.content[].local_image` | user/paste | 5 |
| 사람이 친 명령 | `exec_command_end` `source=user_shell` | `CommandExecution` `source=user_shell` | **user**/bash | 2 |
| 에이전트 응답 | `agent_message` | `AgentMessage` | agent/response | 10 |
| 에이전트 명령 | `exec_command_end` `source=unified_exec_startup` | `CommandExecution` 동일 | **agent**/bash | 10 |
| 에이전트 파일작성 | `patch_apply_end` | `FileChange` | agent/write | 5 |
| 에이전트 이미지열람 | `function_call name=view_image` | `ImageView` | agent/read | 5 |

**왜곡 케이스 30/30 적중.** 두 종류를 넣었다.

1. `unified_exec_startup` 명령 20건 — 5단계 정정 대상. 링크 실패를 '주체 불명'으로 승격시키던
   옛 규칙이면 여기가 `unknown`으로 새고, 같은 세션의 동종 레코드가 agent/unknown으로 쪼개진다.
2. 디스크 소유자 왜곡 10건 — 에이전트가 쓴 파일을 실제로 디스크에 만들어 둔다(소유자=실행계정=사람).
   owner만 보면 user로 오인되는 상황. 도구는 transcript actor로 agent를 낸다.

반대 방향의 통제로 `source=user_shell` 4건을 넣었다. 이걸 agent로 쓸어담으면 §3-3 규칙이
"전부 agent"로 퇴화한 것이므로, 왜곡 30/30과 이 4건이 **같이** 맞아야 의미가 있다.

혼동행렬: `(user→user) 40`, `(agent→agent) 60`, 오분류 0.

**과계수 0 별도 검증** — `test_paired_call_and_end_are_one_event_not_two`.
`function_call(exec_command)` + `exec_command_end`가 같은 `call_id`로 묶이면 레코드는 2개지만
Event는 1개여야 한다. 각각 세면 명령 실행 건수가 2배로 부풀어 보고서가 틀린다.
6 레코드 → 3 Event 확인.

### 2-2. 접근 파일 판정 (100건)

접근 70(write 40 · read 30) + decoy 30. 각 era 35건씩.

- write: legacy `patch_apply_end` 20 + item `FileChange` 20
- read: legacy `function_call name=view_image` 15 + item `ImageView` 15
  (**Codex에는 범용 파일 읽기 레코드가 없다.** read로 잡히는 건 이미지 열람뿐이고,
  일반적인 파일 읽기는 shell 명령으로 일어나 `action=bash`가 된다. §5-2 참조)
- decoy 30: 디스크에 파일은 만들되 transcript엔 한 번도 등장시키지 않는다 → 잡으면 오탐

결과: **누락 0 · 오탐 0 · action(read/write) 일치 100%**.

### 2-3. MCP 호출 탐지 (100건)

MCP 60 + 비-MCP 40.

- MCP 60: legacy `mcp_tool_call_end`. 6 server × 10 tool = 60 쌍 전부 서로 다르다.
  `mcp_usage_from_events` 집계도 교차 확인 — 60 rows, 총 count 60.
- 비-MCP 40: item `Extension kind=web.search` **10**, item `CommandExecution` 10,
  item `FileChange` 5, legacy `exec_command_end` 10, legacy `agent_message` 5.

**web.search를 MCP로 세지 않는 것**이 이 시나리오의 핵심 함정이다. 0.147 표본에는 MCP 사용이
아예 없고 `Extension.kind=web.search` 162건뿐이라, 이걸 MCP로 집계하면 "쓰지도 않은 외부 연동"이
보고서에 생긴다. 오탐 0으로 확인.

`agent_message` 5건은 본문에 `mcp__` 문자열을 넣어 두었다 — 텍스트 매칭으로 MCP를 세면
여기서 걸린다. 도구는 `action=="mcp"` Event만 세므로 영향 없음.

---

## 3. MCP는 왜 era 균형이 아닌가

**item era(0.147)에는 MCP 레코드 형식 자체가 없다.** `_ITEM_TYPES` 어디에도 MCP 항목이 없고,
`Extension`은 `kind=web.search`만 받는다. 실측 표본에서도 MCP 사용은 0건이다.

그래서 양성 60건은 legacy `mcp_tool_call_end` 형식으로만 만들었고, **오탐 쪽 40건에 item era를
넣어** 두 era를 모두 태웠다. 즉 item era에 대해 측정된 것은 **오탐률(0)** 이고,
**회수율은 측정 대상이 존재하지 않아 미정의**다. 이건 도구의 결함이 아니라 기록 형식의 공백이다.

향후 Codex가 item era에서 MCP를 기록하기 시작하면 파서는 그 형식을 모른다 →
`unsupported_schema`로 표면화된다(조용히 누락되지 않음). 그때 이 시나리오를 확장하면 된다.

---

## 4. 측정 중 발견한 결함 1건 (수정 완료)

시나리오 1의 과계수 검증을 짜다가 `meta.source`가 사라지는 경로를 찾았다.

**증상**: `exec_command_end`가 앞선 `function_call(exec_command)`과 같은 `call_id`로 병합되면,
`codex_parser.py`의 `if ident not in self.by_id:` 분기를 건너뛰어 **`source`가 Event에 실리지 않는다.**
`source`는 `exec_command_end`에만 있고 `function_call` 쪽엔 없다.

**실데이터 규모**: WSL·Windows 두 코퍼스의 `exec_command_end` **1,254건 전부**가 이 병합 경로다.
1,254건 모두 `source=unified_exec_startup`을 갖고 있었는데 전부 유실되고 있었다.

이건 5단계 BLOCK #2("`source`를 `meta.source`로 보존해라. **merge 시에도 덮어써 잃지 않게**")가
절반만 닫힌 상태였다. 비병합 경로만 고쳐졌었다.

**수정**: `_update(...)`에 `source=payload.get("source")`를 넘겨 분기 밖에서도 싣는다.
`_update`는 `None`을 걸러내므로 source 없는 레코드에는 아무 일도 없다.

**실데이터 효과** (`~/.codex` 37,090 이벤트, 이벤트 수·actor 분포 불변):

| command_execution `meta.source` | 수정 전 | 수정 후 |
|---|---|---|
| `unified_exec_startup` | 2,784 | **4,038** (+1,254) |
| `user_shell` | 1 | 1 |
| 없음(None) | 12,445 | **11,191** (−1,254) |

**남은 11,191건은 파서 유실이 아니다.** 원본 `function_call name=exec_command` 12,445건에는
`source` 필드가 애초에 없고(12,445/12,445 부재), 그중 `exec_command_end` 짝이 있는 건 1,254건뿐이다.
나머지 11,191건은 원본 어디에도 귀속 근거가 없다 → 사후 감사 가능한 source 커버리지의 상한은
**15,230건 중 4,039건(26.5%)** 이고, 수정 전은 18.3%였다.

---

## 5. 무엇을 왜 못 재는가 (100%가 가리는 것)

정확도 100%는 **넣은 것을 다 맞혔다**는 뜻이지 **넣을 수 없는 게 없다**는 뜻이 아니다.
아래는 합성으로 재현할 수 없거나, 재현해도 도구가 원리상 못 잡는 부류다.

### 5-1. shell redirection 파일 작성 — 구조적 비포착 (부속 측정 10/10)

`printf x > /path` 처럼 shell로 만든 파일은 **`FileChange`에 잡히지 않는다**(기준서 §3-6).
합성 10건(각 era 5)을 넣어 확인:

- `action=write` Event로 **주장하지 않는다** (0/10) — 직접 증거가 없으므로 올바른 침묵
- 대신 `meta.write_target`에 경로를, `meta.confidence="low"`에 등급을 남긴다 (10/10)

즉 이 부류는 "정답/오답"이 아니라 **후보로만 표면화되는 등급**이다. 시나리오 2의 100건에서는
제외하고 별도 집계했다. 보고서에 "이 파일에 썼다"고 단정하지 않는 것이 여기서는 정답이다.

실측 근거: 보수적 redirection 탐지 `CommandExecution` 51건 중 21건이 same-turn `FileChange`가
없었고(16건은 exit 0), 넓은 heuristic write-like 227건 대 `FileChange` 66건에 same-turn path
매칭이 0이었다. **shell로 만든 파일은 원리상 transcript에서 확정할 수 없다.**

### 5-2. 범용 파일 읽기 레코드 부재

Codex는 파일 읽기를 별도 레코드로 남기지 않는다. `action=read`가 붙는 건 이미지 열람
(`view_image` / `ImageView`)뿐이다. `cat`·`grep` 같은 읽기는 `action=bash`로만 남는다.

따라서 시나리오 2의 "접근 파일 판정"은 Claude 측정본과 **범위가 다르다.**
Claude는 `toolUseResult.file`로 실제 읽은 파일을 잡지만, Codex는 못 잡는다.
두 도구의 접근파일 정확도를 나란히 놓을 때 이 차이를 빼고 비교하면 안 된다.

### 5-3. 개별 승인 여부

`turn_context.approval_policy` 스냅샷은 있지만 **개별 승인 record는 전수 검색 결과 0건**이다.
"이 명령을 사람이 승인했나"는 측정 대상 자체가 없다. `approved_by_user=true`는 기록하지 않는다.

### 5-4. 병합된 `user_shell` 명령 (구조상 도달 불가, 미측정)

`function_call(exec_command)`은 정의상 모델의 tool call이므로, `source=user_shell`인
`exec_command_end`가 같은 `call_id`로 병합되는 조합은 구조상 나오지 않는다.
두 코퍼스 실측에서도 병합 1,254건 전부 `unified_exec_startup`이었다.
만약 이 조합이 나타나면 병합된 Event의 actor가 `agent`로 남는다 — 그때는 병합 시점에
actor 재평가가 필요하다. **지금은 관측된 적 없어 측정하지 않았다.**

### 5-5. 합성이 재현하지 못하는 것

- 손상·절단된 JSONL, 인코딩 깨짐 → 별도 파서 테스트 영역
- 동시 세션·subagent 계층의 실제 타이밍
- SQLite 보조 인덱스와 rollout의 불일치(실측 coverage 경고 351/348/22)

---

## 6. 패널 ③결과 표기안

```
Codex 판정 정확도 (합성 100건 × 3, legacy·item 균형)
  주체 식별      100/100   왜곡 30/30
  접근 파일      100/100   누락 0 · 오탐 0
  MCP 탐지       100/100   web.search 오탐 0
```

표기 시 반드시 같이 적을 것:
- **"합성 통제 데이터 기준"** — 실데이터 정확도가 아니다
- **shell redirection 작성은 후보(low)로만 표면화** — 접근파일 100%가 이걸 포함하지 않는다
- **item era MCP는 기록 형식 부재로 회수율 미정의**
