# clfx MVP — 설계 스펙

날짜: 2026-06-17
범위: cli-llm-forensic 코어 도구(`clfx`) MVP — 파싱 → 분석 → 질의 3단계.
근거 문서: `docs/설계.md`, `docs/event-schema.md`, `docs/논문대비-신규발견.md`, `docs/스테이징-데이터셋-가이드.md`.

## 1. 목표

AI 코딩 에이전트(Claude Code)가 디스크에 남긴 기록을 파싱·분석하고 자연어로 질의하는 사후(post-incident) 포렌식 도구. **시연 종착점 = A(사용자 직접 붙여넣기) / B(에이전트 자율 접근) 두 사건을 parse→analyze→query로 재구성하고 `actor`로 행위 주체를 규명한다.**

차별점(`설계.md §기존 연구와 우리`): ① 실제로 돌아가는 자동화, ② 논문이 안 깐 아티팩트 파싱(§A 붙여넣기 분리저장, §B `projects/` 내부 레코드 타입).

## 2. 확정 결정

| 축 | 결정 | 이유 |
|---|---|---|
| 언어/런타임 | **Python 3** | 검증 명령 전부 python3, jsonl/json·정규식·base64 stdlib, pytest TDD. stdlib 위주 + 최소 의존성. |
| 질의 구현 | **결정적 엔진 + 얇은 LLM 어댑터** | 증거 주장(누가·무엇·언제·유출)은 재현 가능·완전·인용이어야 함. LLM RAG는 누락·환각·비결정 → 근거로 못 씀. 검색·귀속·탐지=결정적, LLM=편의층. |
| 테스트 데이터 | **커밋된 합성 픽스처** | 결정적(빨강/초록 안정)·진짜 시크릿 없음(CLFXTEST 가짜)·팀원/머신 비의존. |
| 에이전트 범위 | **Claude Code만** | MVP=A/B 재구성. `~/.claude/projects/*.jsonl`+`history.jsonl`+`paste-cache`. 파서 인터페이스는 어댑터로 추상화해 Codex/Gemini 나중에 끼움. |

## 3. 아키텍처

Python 3 CLI `clfx`. 3 서브커맨드 = 3단계 파이프라인.

```
clfx parse   ~/.claude        -o events.jsonl      # 1단계
clfx analyze events.jsonl     -o analyzed.jsonl    # 2단계 (tags·mask·귀속)
clfx query   analyzed.jsonl   "누가 .env 읽었어?"   # 3단계
```

### 모듈 경계 (각자 한 가지 책임, 독립 테스트)

| 모듈 | 책임 | 의존 |
|---|---|---|
| `sources/claude.py` | Claude 파일 레이아웃 읽기: `projects/*.jsonl`·`history.jsonl`·`paste-cache/`. raw 레코드 + `source{file,line}` 산출. Codex/Gemini 추가를 위한 reader 인터페이스 형태로. | stdlib만 |
| `paste.py` | §A paste 사슬 해소: `display→pastedContents→(content \| contentHash→paste-cache/<hash>.txt)` 3단계 + 이미지 base64 디코드(`message.content[]`의 `type:image`). | sources |
| `event.py` | Event 스키마 dataclass + jsonl (de)serialize. `event-schema.md`가 단일 진실원천 — 필드 복제 금지. | — |
| `parser.py` | raw 레코드 → Event. §A(paste)·§B(`toolUseResult`·`permission-mode`·`agent-name`·`isSidechain`·`thinking`) 매핑. 구조상 명확한 `actor` 채움(paste→user, read/`toolUseResult`→agent, prompt→user). | sources·paste·event |
| `analyze/secrets.py` | 시크릿·PII 정규식 탐지 → `tags`에 `secret`/`pii` 추가, `preview` 가림(`‹secret›`). | event |
| `analyze/attribution.py` | `actor` 귀속 단일 진실원천. `permission-mode`(bypassPermissions)·`isSidechain`로 검증/주석. | event |
| `analyze/timeline.py` | `ts` 정렬 타임라인. | event |
| `query/engine.py` | **결정적**: `search(kw)`·`on_date(d)`·`who_did(action,target)`·`secrets()`·`timeline(range)` → `Event[]` + 각 `source(file:line)`. | event |
| `query/llm.py` | **얇은 어댑터**: (a) NL→질의 의도 매핑, (b) 검색집합 산문 요약(문장마다 source 인용). ollama 등 로컬. 없거나 죽으면 구조적 digest로 fallback. | engine |
| `cli.py` | argparse 3 서브커맨드 배선. | 전부 |

### Event 스키마 (참조 — 단일 진실원천은 `event-schema.md`)

```
Event { ts, agent, session, actor, action, target, preview, tags[], source{file,line} }
  actor:  user | agent
  action: prompt | read | bash | write | paste | response
  source: 모든 Event가 원본 파일·줄로 추적 가능해야 함(증거능력)
```

## 4. 데이터 흐름

```
Claude 파일
  → [parse]   → events.jsonl     (구조적 actor 포함, tags 빈 배열)
  → [analyze] → analyzed.jsonl   (시크릿/PII tags·masked preview·귀속 확정)
  → [query]   → 답 + source 인용
```

파일을 단계마다 분리(events.jsonl → analyzed.jsonl)해 멱등·추적 가능. analyze는 parse 출력을 읽어 enrich.

`actor` 책임 분리: parser는 레코드 타입으로 **구조상 명확한** actor를 채운다(paste→user, `toolUseResult`/read→agent). `attribution.py`는 귀속의 단일 진실원천으로, `permission-mode`·`isSidechain`로 검증/주석한다. MVP의 A/B는 둘 다 레코드 타입에서 명확.

## 5. 핵심 원칙

1. **LLM은 검색을 안 한다.** 결정적 엔진이 찾은 집합만 요약/표현. LLM이 증거를 "찾으면" 신뢰 깨짐.
2. **요약 테스트 = 산문 일치가 아님.** "인용한 source가 전부 실재 + 검색 집합이 정확"으로 채점 → 비결정 산문도 검증 가능. ollama 죽어도 데모 안 깨짐(엔진 단독 동작).

## 6. 테스트 전략 (TDD 2층)

| 층 | 입력 | 목적 | 시점 |
|---|---|---|---|
| 단위 (커밋 픽스처) | `tests/fixtures/*.jsonl` (합성, 작음) | 파서·분석·질의 빨강/초록 | 지금 |
| 통합·평가 (스테이징셋) | 팀원 clfx-victim + ground-truth | precision/recall·주체 귀속 정확도 | 도구 완성 후 |

픽스처 구성 (`논문대비-신규발견.md` §A/§B 구조 그대로):
- **history.jsonl 픽스처**: 붙여넣기 3종 — ① `pastedContents.content` 직접 ② `contentHash`만(+ 짝 `paste-cache/<hash>.txt`) ③ 이미지(작은 1×1 base64 PNG inline).
- **projects/*.jsonl 픽스처**: `type:user`(+`toolUseResult.file.content`), `permission-mode:bypassPermissions`, `file-history-snapshot`, `agent-name`/`isSidechain`, `thinking`, `assistant`.
- **시크릿**: 스테이징 가이드와 동일한 CLFXTEST-001~008 토큰 → 픽스처서 잡은 탐지가 데이터셋서도 그대로 작동(일관).
- **노이즈** 레코드 1~2개(오탐 측정용, 예: `app.py`).

빌더: `conftest.py`에 `make_history(pastes=[...])`·`make_transcript(records=[...])` → 파라미터라이즈 + 골든 픽스처 몇 개 회귀용. 시크릿 토큰은 CLFXTEST 가짜라 커밋 안전.

질의 테스트:
- 엔진: 합성 Event 넣고 `search`/`on_date`/`who_did`/`secrets`/`timeline` 결과 정확 + 인용 정확 assert. 완전 결정적.
- 어댑터 (a) 의도매핑: 고정 문구 셋 → 기대 질의(mock LLM 또는 룰 우선).
- 어댑터 (b) 요약: 인용 source 전부 실재 + 근거 집합 일치 assert.

## 7. 3단계 MVP (각 단계 빨강→초록)

1. **파싱** — `sources/claude.py`+`paste.py`+`parser.py`+`event.py`.
   accept: 픽스처 → Event[], 모든 Event `source` 추적, paste 3사슬·§B 타입 전부 잡힘.
2. **분석** — `analyze/secrets.py`+`attribution.py`+`timeline.py`.
   accept: CLFXTEST 8개 탐지·preview 가림, A=user/B=agent 귀속, 타임라인 정렬.
3. **질의** — `query/engine.py`(결정적)+`query/llm.py`(얇게).
   accept: `who_did`/`secrets`/`on_date` 정확+인용 실재, LLM 없이도 엔진 동작.

## 8. 범위 밖 (나중 레이어)

삭제 기록 복구, ext4.vhdx 추출, Windows 이벤트로그 교차, Codex/Gemini 파서, 실시간 차단. (`설계.md §지금 안 하는 것`)
