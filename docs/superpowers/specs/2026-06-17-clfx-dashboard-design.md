# clfx 웹 대시보드 (Stage 4) — 설계

날짜: 2026-06-17
상태: 자율 확정 (사용자 자율 위임 — 퇴근, 출근 전까지 진행. plan 로드맵 원칙 기승인).
선행: MVP green (parse 90e5d39 / analyze b60b00f / query a6a8fd2, final-verify OK).

## 목적

`analyzed.jsonl`(parse→analyze 산출물) 하나를 브라우저에서 **사후조사용으로 본다**. 발표 데모에서 A(사용자 붙여넣기)·B(에이전트 자율 읽기) 두 사건을 타임라인으로 보여주고, 시크릿/PII 노출과 그 증거(source file:line)를 클릭으로 역추적한다. CLI가 하는 일을 **시각화**할 뿐 새 분석 능력을 더하지 않는다.

## 불변 원칙 (plan 로드맵에서 승인됨)

**결정적 질의 엔진(`clfx/query/engine.py`)이 단일 진실원천.** 대시보드는 엔진을 **호출·표시만** 한다. 검색·귀속·탐지·날짜질의 로직을 JS로 재구현하지 않는다(증거 분기 방지). 증거 주장은 엔진이, 대시보드는 표현만.

## 아키텍처

```
브라우저(단일 HTML, vanilla JS)
   │  fetch
   ▼
clfx/web/server.py  (stdlib http.server, 로컬 전용)
   │  호출
   ▼
clfx/web/api.py  (순수 함수: engine/llm 호출 → dict)
   │
   ▼
QueryEngine(analyzed.jsonl)  ← 진실원천 (재사용, 무수정)
```

- **기술**: Python stdlib `http.server`만. **의존성 0 추가**(프로젝트 stdlib-only 원칙 유지). 프론트는 빌드 없는 vanilla JS 단일 파일.
- **기동**: 새 CLI 서브커맨드 `clfx serve <analyzed.jsonl> [--port 8787] [--host 127.0.0.1]`. 로컬 서버 띄우고 사용자가 브라우저로 본다.
- **왜 서버인가**: 엔진(Python)을 그대로 호출하려면 백엔드가 필요. 정적 HTML이 `analyzed.jsonl`을 직접 읽으면 검색/필터를 JS로 재구현하게 돼 원칙 위반. 서버가 engine을 호출하면 원칙이 자동 충족된다.

### 검토한 대안 (기각)

- **정적 HTML + JS가 jsonl 직접 fetch**: 서버 불필요하나 검색·질의를 JS로 재구현 → "JS 재구현 금지" 위반. 기각.
- **Flask/FastAPI + React**: 강력하나 의존성·빌드툴 폭증, 발표 데모엔 과잉. YAGNI 위반. 기각.

## 컴포넌트 (책임 분리)

### 1. `clfx/web/api.py` — 순수 API 로직 (HTTP 무관, 테스트 용이)

http를 띄우지 않고 dict만 반환 → TDD 쉽다. 서버는 이걸 호출하고 직렬화만 한다.

- `events_payload(engine) -> dict`: 전체 이벤트를 ts 정렬(`engine.timeline()`)해 직렬화. 초기 타임라인용.
  반환: `{"events": [event_dict, ...], "count": N}`. 각 event_dict는 `Event.to_dict()` 형태(ts/agent/session/actor/action/target/preview/tags/source 보존 — preview는 analyze가 이미 마스킹).
- `query_payload(engine, q) -> dict`: 자연어 질의. `route_intent(q)`로 op 판정 → 해당 engine 메서드 실행 → 결과 + (요약 요청 시) `summarize(res, llm=None)` digest.
  반환: `{"op": "...", "intent": {...}, "events": [...], "count": N, "summary": {text,citations,mode}|null}`.
- 두 함수 모두 예외를 던지지 않고 정상 dict 반환(질의 0건도 정상). 서버가 try/except로 감싸 `{"error": msg}` 변환.

### 2. `clfx/web/server.py` — stdlib http.server 핸들러

- `make_handler(engine, static_dir)` → `BaseHTTPRequestHandler` 서브클래스 팩토리(engine 주입, 전역 금지).
- 라우트(GET만, read-only — POST/PUT/DELETE 없음):
  - `GET /` → `static/index.html` 반환.
  - `GET /app.js`, `GET /app.css` → 정적 파일.
  - `GET /api/events` → `events_payload(engine)` JSON.
  - `GET /api/query?q=<urlencoded>` → `query_payload(engine, q)` JSON. q 없으면 `{"error":"q required"}` + 400.
  - 그 외 → 404 JSON.
- `serve(analyzed_path, host, port)`: jsonl 로드 → `QueryEngine` → `ThreadingHTTPServer` 기동, URL 출력.
- 보안 경계: `127.0.0.1` 기본 바인드(외부 노출 안 함). 정적 파일은 화이트리스트 3개만(경로 traversal 차단). 원본 `~/.claude` 파일 줄을 읽어 보여주지 **않는다**(source는 file:line 텍스트로만 표시 — 실데이터 경로 노출/유출 위험 차단).

### 3. `clfx/web/static/index.html` + `app.css` + `app.js` — 프론트(표시 전용)

- **타임라인**: `/api/events` 로드 → ts 순 이벤트 카드 리스트. **actor 색구분**: user=파랑 좌측보더, agent=빨강 좌측보더 (A=user paste / B=agent read 스토리 시각화).
- **질의/검색 박스**: 한 입력창. 입력 → `/api/query?q=` → 결과로 타임라인 교체 + (요약 있으면) 상단 요약 패널. "전체로" 버튼으로 `/api/events` 복귀.
- **필터바**: actor(user/agent)·action(prompt/read/bash/write/paste/response)·tags(secret/pii/bypass-mode) 토글. **클라이언트측 표시 토글만**(이미 받은·이미 분류된 이벤트를 보이기/숨기기 — 로직 재구현 아님). 전문 검색은 토글이 아니라 질의 박스(engine 위임).
- **secret/PII 하이라이트**: 이벤트 카드에 tags 뱃지(secret=빨강, pii=주황, bypass-mode=보라). preview는 이미 `‹secret›` 마스킹됨(서버가 평문 안 보냄).
- **이벤트 클릭 → 상세 패널**: 전체 preview, `source.file:line`, tags, session, actor/action/ts. 증거 역추적 시연(이 이벤트는 저 파일 저 줄에서 왔다).

## 데이터 흐름

1. `clfx serve analyzed.jsonl` → 서버 기동, `http://127.0.0.1:8787` 출력.
2. 브라우저 `/` → index.html → `app.js`가 `/api/events` fetch → 타임라인 렌더.
3. 질의 입력 → `/api/query?q=누가 .env 읽었어?` → 서버 route_intent+engine → JSON → 타임라인 교체.
4. 필터 토글 → 클라이언트가 현재 이벤트 집합 표시 필터(서버 왕복 없음).
5. 이벤트 클릭 → 상세 패널(받은 데이터 내, 왕복 없음).

## 에러 처리

- `serve` 시작: jsonl 없음/깨진 줄 → stderr 메시지 + exit 1. (포렌식: 부분 로드보다 명확한 실패.)
- 포트 사용중(`OSError: address in use`) → 명확한 메시지 + exit 1.
- `/api/query` q 누락 → 400 `{"error":"q required"}`.
- API 내부 예외 → 500 `{"error": "<msg>"}` (서버 안 죽음).
- 프론트 fetch 실패 → 화면 상단 에러 배너.

## 테스트 전략 (TDD)

- `tests/test_web_api.py` — 핵심. http 없이 `api.py` 순수 함수 검증:
  - `events_payload`: ts 정렬 보존, source(file:line) 보존, count 일치, preview 마스킹 유지.
  - `query_payload`: "누가 .env 읽었어?"→who_did read·target=.env, "유출된 비밀"→secrets, "타임라인"→timeline, 일반어→search. 각 결과의 op·count·source 검증. 요약 요청 시 summary.mode=="digest"·citations 실재.
  - 결정성: 같은 입력 같은 출력.
- `tests/test_web_server.py` — 가벼운 통합: `ThreadingHTTPServer`를 임시 포트로 띄워 `urllib`로 `/api/events`·`/api/query?q=`·`/`(200)·미존재(404)·q누락(400) 1회씩. 픽스처 analyzed.jsonl 사용.
- 프론트 JS는 자동 테스트 안 함(YAGNI, 발표 데모용 표시 레이어). 대신 서버 통합테스트가 엔드포인트 계약을 고정.

## 범위 경계 (YAGNI — 제외)

멀티 사건 뷰, 인증/계정, 원격 배포, 실시간 갱신(폴링/웹소켓), 원본 파일 줄 읽기, 데이터 편집/쓰기, 이미지(base64) 렌더. 전부 후속. 이번은 **로컬·read-only·단일 `analyzed.jsonl`·발표 데모/사건 리뷰**용.

## Event 직렬화 메모

`Event.to_dict()`가 이미 존재한다(`asdict` 기반, `source`→`{file,line}` 자동 변환, `to_json()`도 이걸 사용 — 단일 진실원천 충족). API는 `e.to_dict()`를 그대로 쓴다. 새 직렬화 코드 불필요.
