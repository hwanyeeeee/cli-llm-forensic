# clfx 웹 대시보드 (Stage 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `analyzed.jsonl` 하나를 로컬 브라우저에서 포렌식 뷰로 보는 read-only 웹 대시보드.

**Architecture:** stdlib `http.server` 백엔드가 기존 `QueryEngine`을 호출(검색·귀속·탐지·질의 전부 엔진 위임 — JS 재구현 금지)하고, vanilla JS 단일 페이지가 결과를 표시만 한다. 새 CLI `clfx serve`로 기동. 의존성 0 추가.

**Tech Stack:** Python 3 stdlib (`http.server`, `urllib`, `json`), vanilla JS/HTML/CSS (빌드 없음), pytest.

---

## 공통 계약 (Cross-cutting)

- **엔진 무수정**: `clfx/query/engine.py`(QueryEngine)·`clfx/analyze/*`·`clfx/event.py`는 건드리지 않는다. `Event.to_dict()`는 이미 존재(`asdict` 기반, `source`→`{file,line}`).
- **재사용 심볼** (이미 구현됨, import만):
  - `clfx.query.engine.QueryEngine(events)` — `.search(kw)`, `.on_date(day)`, `.who_did(action, target_substr)`, `.secrets()`, `.timeline(start=None,end=None)` 전부 `[Event]` 반환.
  - `clfx.query.llm.route_intent(q) -> {"op": ..., ...}` — op ∈ {who_did, secrets, on_date, timeline, search}. who_did는 `action`/`target`, on_date는 `day`, 전부 `summarize`(bool) 포함. search는 `kw`.
  - `clfx.query.llm.summarize(events, llm=None) -> {"text","citations","mode"}` — llm=None이면 mode="digest".
  - `clfx.event.Event.from_dict(d)` / `Event.to_dict()`.
- **op 디스패치 단일화 (DRY)**: 질의 op→engine 메서드 매핑을 `api.query_payload` 한 곳에 둔다. 기존 `cli.py:cmd_query`의 동일 디스패치 if/elif를 `query_payload` 호출로 교체한다(중복 제거). `cmd_query`의 **출력 형식·기존 테스트는 그대로 통과해야 한다** — 내부 디스패치만 바꾼다.
- **read-only**: GET만. POST/PUT/DELETE 없음. 데이터 변경 없음.
- **보안 경계**: `127.0.0.1` 기본 바인드. 정적 파일은 화이트리스트 3개(`/`,`/app.js`,`/app.css`)만 — 경로 traversal 차단. 원본 `~/.claude` 파일을 읽어 응답하지 않는다(source는 file:line 텍스트로만 표시).
- **YAGNI 제외**: 멀티사건, 인증, 배포, 실시간 갱신, 원본 줄 읽기, 데이터 편집, 이미지 렌더.

## File Structure

- Create `clfx/web/__init__.py` — 빈 패키지 마커.
- Create `clfx/web/api.py` — 순수 함수 `events_payload(engine)`, `query_payload(engine, q)`. HTTP 무관, dict 반환. **여기가 op 디스패치 단일 진실원천.**
- Create `clfx/web/server.py` — `make_handler(engine)`(BaseHTTPRequestHandler 팩토리), `load_engine(path)`, `serve(path, host, port)`. api.py를 호출+직렬화만.
- Create `clfx/web/static/index.html`, `clfx/web/static/app.css`, `clfx/web/static/app.js` — 표시 전용 프론트.
- Modify `clfx/cli.py` — `cmd_query`를 `query_payload` 기반으로 리팩토링; `cmd_serve` + `serve` 서브파서 추가.
- Test `tests/test_web_api.py` — api.py 순수 함수.
- Test `tests/test_web_server.py` — 서버 엔드포인트 통합(임시 포트).

---

### Task 1: web 패키지 + `events_payload`

**Files:**
- Create: `clfx/web/__init__.py`
- Create: `clfx/web/api.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: 빈 패키지 마커 생성**

`clfx/web/__init__.py` 를 빈 파일로 생성.

```bash
mkdir -p clfx/web/static && : > clfx/web/__init__.py
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_web_api.py`:

```python
from clfx.event import Event, Source
from clfx.query.engine import QueryEngine
from clfx.web.api import events_payload, query_payload


def _ev(ts, actor, action, target, preview="", tags=None, file="h.jsonl", line=1):
    return Event(ts=ts, agent="claude", session="s1", actor=actor, action=action,
                 target=target, preview=preview, source=Source(file, line),
                 tags=tags or [])


def _engine():
    return QueryEngine([
        _ev("2026-06-11T10:00:00Z", "user", "paste", ".env", "API_KEY=‹secret›", ["secret"], line=3),
        _ev("2026-06-11T09:00:00Z", "agent", "read", "id_rsa", "ssh-rsa ‹secret›", ["secret"], line=7),
        _ev("2026-06-11T11:00:00Z", "agent", "read", "app.py", "print(1)", [], line=9),
    ])


def test_events_payload_sorted_and_complete():
    p = events_payload(_engine())
    assert p["count"] == 3
    # ts 오름차순 정렬(09 < 10 < 11)
    tss = [e["ts"] for e in p["events"]]
    assert tss == sorted(tss)
    # source(file:line) 보존
    first = p["events"][0]
    assert first["source"] == {"file": "h.jsonl", "line": 7}
    # 마스킹된 preview 그대로(평문 노출 안 함)
    assert "‹secret›" in first["preview"]
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `pytest tests/test_web_api.py::test_events_payload_sorted_and_complete -v`
Expected: FAIL — `ImportError: cannot import name 'events_payload'` (또는 ModuleNotFoundError).

- [ ] **Step 4: 최소 구현**

`clfx/web/api.py`:

```python
"""웹 대시보드용 순수 API 로직. HTTP 무관 — dict만 반환해 테스트가 쉽다.
엔진(QueryEngine)이 단일 진실원천. 여기서 검색/탐지 로직을 재구현하지 않는다."""
from clfx.query.llm import route_intent, summarize


def events_payload(engine):
    """전체 이벤트를 ts 정렬해 직렬화(초기 타임라인용)."""
    evs = engine.timeline()
    return {"events": [e.to_dict() for e in evs], "count": len(evs)}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `pytest tests/test_web_api.py::test_events_payload_sorted_and_complete -v`
Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add clfx/web/__init__.py clfx/web/api.py tests/test_web_api.py
git commit -m "feat(web): events_payload — ts 정렬 직렬화 (Stage 4 Task1)"
```

---

### Task 2: `query_payload` (op 디스패치 단일화)

**Files:**
- Modify: `clfx/web/api.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_web_api.py` 에 추가:

```python
def test_query_payload_who_read_env():
    p = query_payload(_engine(), "누가 .env 읽었어?")
    # 라우팅은 엔진이 — read 동사 + .env target
    assert p["op"] == "who_did"
    assert p["intent"]["action"] == "read"
    # .env paste는 read가 아니므로 read 결과엔 안 들어감(엔진 결정)
    assert all(e["action"] == "read" for e in p["events"])
    assert p["count"] == p["intent"] and isinstance(p["events"], list) or p["count"] == len(p["events"])


def test_query_payload_secrets():
    p = query_payload(_engine(), "유출된 비밀 뭐야?")
    assert p["op"] == "secrets"
    # secret 태그 단 2건(.env paste, id_rsa read)
    assert p["count"] == 2
    assert all("secret" in e["tags"] or "pii" in e["tags"] for e in p["events"])


def test_query_payload_timeline_and_summary():
    p = query_payload(_engine(), "타임라인 요약해줘")
    assert p["op"] == "timeline"
    assert p["count"] == 3
    # 요약 요청 → digest summary, citations 실재(file:line 문자열)
    assert p["summary"] is not None and p["summary"]["mode"] == "digest"
    assert len(p["summary"]["citations"]) == 3


def test_query_payload_no_summary_when_not_requested():
    p = query_payload(_engine(), "누가 id_rsa 읽었어?")
    assert p["op"] == "who_did" and p["summary"] is None
    assert p["intent"]["target"] == "id_rsa"
```

> 주의: 위 `test_query_payload_who_read_env`의 마지막 assert는 헷갈리니 명확히 — `p["count"] == len(p["events"])` 만 남긴다. 아래 구현 후 그 한 줄로 교체할 것:
> ```python
>     assert p["count"] == len(p["events"])
> ```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_web_api.py -v`
Expected: FAIL — `ImportError`/`cannot import name 'query_payload'`.

- [ ] **Step 3: 구현**

`clfx/web/api.py` 에 추가:

```python
def query_payload(engine, q):
    """자연어 질의 → op 판정(route_intent) → engine 실행 → dict.
    이 디스패치가 op→engine 매핑의 단일 진실원천(cli.cmd_query도 이걸 쓴다)."""
    intent = route_intent(q)
    op = intent["op"]
    if op == "who_did":
        res = engine.who_did(intent["action"], intent.get("target", ""))
    elif op == "secrets":
        res = engine.secrets()
    elif op == "on_date":
        res = engine.on_date(intent["day"])
    elif op == "timeline":
        res = engine.timeline()
    else:
        res = engine.search(intent.get("kw", ""))
    summary = summarize(res, llm=None) if intent.get("summarize") else None
    return {"op": op, "intent": intent,
            "events": [e.to_dict() for e in res], "count": len(res),
            "summary": summary}
```

그리고 `test_query_payload_who_read_env` 의 마지막 줄을 위 주의대로 `assert p["count"] == len(p["events"])` 로 정리.

- [ ] **Step 4: 테스트 통과 확인**

Run: `pytest tests/test_web_api.py -v`
Expected: PASS (4 test).

- [ ] **Step 5: 커밋**

```bash
git add clfx/web/api.py tests/test_web_api.py
git commit -m "feat(web): query_payload — op 디스패치 단일화 (Stage 4 Task2)"
```

---

### Task 3: `cmd_query` 를 `query_payload` 기반으로 리팩토링 (DRY)

**Files:**
- Modify: `clfx/cli.py` (cmd_query 함수)

- [ ] **Step 1: 기존 query 테스트가 통과 중인지 확인(회귀 기준선)**

Run: `pytest tests/test_cli_query.py -q`
Expected: PASS (현재 전부 통과). 이 Task는 동작 불변·내부만 변경.

- [ ] **Step 2: cmd_query 리팩토링**

`clfx/cli.py` 상단 import에 추가:

```python
from clfx.web.api import query_payload
```

`cmd_query` 를 다음으로 교체(출력 형식 동일, 디스패치는 query_payload 위임):

```python
def cmd_query(args):
    try:
        eng = QueryEngine(_read_events(args.analyzed))
        p = query_payload(eng, args.question)
        for e in p["events"]:
            src = e["source"]
            print(f"[{e['ts'] or '?'}] {e['actor']}/{e['action']} {e['target']}  "
                  f"({src['file']}:{src['line']})")
            if e["preview"]:
                print(f"    {e['preview'][:200]}")
        if p["summary"]:
            print("\n--- 요약 ---")
            print(p["summary"]["text"])
        print(f"\n({p['count']} events)")
    except Exception as e:
        print(f"clfx query: {e}", file=sys.stderr)
        return 1
    return 0
```

기존 `route_intent`/`summarize` import가 cmd_query에서만 쓰였다면 남겨도 무해하나, 미사용이면 제거(린트). `QueryEngine` import는 유지.

- [ ] **Step 3: 회귀 테스트 통과 확인**

Run: `pytest tests/test_cli_query.py tests/test_web_api.py -q`
Expected: PASS (전부). 출력 형식 불변이므로 기존 CLI query 테스트 그대로 통과.

- [ ] **Step 4: 커밋**

```bash
git add clfx/cli.py
git commit -m "refactor(cli): cmd_query를 query_payload 위임으로 (op 디스패치 DRY, Stage 4 Task3)"
```

---

### Task 4: 서버 핸들러 + serve

**Files:**
- Create: `clfx/web/server.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: 실패하는 통합 테스트 작성**

`tests/test_web_server.py`:

```python
import json
import threading
import urllib.request
import urllib.parse
from http.server import ThreadingHTTPServer

from clfx.event import Event, Source
from clfx.query.engine import QueryEngine
from clfx.web.server import make_handler


def _engine():
    return QueryEngine([
        Event("2026-06-11T09:00:00Z", "claude", "s1", "agent", "read", "id_rsa",
              "ssh-rsa ‹secret›", Source("h.jsonl", 7), ["secret"]),
        Event("2026-06-11T10:00:00Z", "claude", "s1", "user", "paste", ".env",
              "API_KEY=‹secret›", Source("h.jsonl", 3), ["secret"]),
    ])


def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(_engine()))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def _get(httpd, path):
    port = httpd.server_address[1]
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def test_events_endpoint():
    httpd = _server()
    try:
        code, body = _get(httpd, "/api/events")
        assert code == 200
        data = json.loads(body)
        assert data["count"] == 2
        assert data["events"][0]["ts"] == "2026-06-11T09:00:00Z"  # ts 정렬
    finally:
        httpd.shutdown()


def test_query_endpoint():
    httpd = _server()
    try:
        q = urllib.parse.quote("유출된 비밀 뭐야?")
        code, body = _get(httpd, f"/api/query?q={q}")
        assert code == 200
        data = json.loads(body)
        assert data["op"] == "secrets" and data["count"] == 2
    finally:
        httpd.shutdown()


def test_query_missing_q_is_400():
    httpd = _server()
    try:
        code, body = _get(httpd, "/api/query")
        assert code == 400
        assert json.loads(body)["error"]
    finally:
        httpd.shutdown()


def test_index_served():
    httpd = _server()
    try:
        code, body = _get(httpd, "/")
        assert code == 200 and "<html" in body.lower()
    finally:
        httpd.shutdown()


def test_unknown_path_404():
    httpd = _server()
    try:
        code, _ = _get(httpd, "/nope")
        assert code == 404
    finally:
        httpd.shutdown()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_web_server.py -v`
Expected: FAIL — `cannot import name 'make_handler'`.

- [ ] **Step 3: 서버 구현**

`clfx/web/server.py`:

```python
"""stdlib http.server 기반 로컬 대시보드 서버. api.py를 호출+직렬화만 한다.
GET 전용(read-only). 127.0.0.1 바인드, 정적 파일 화이트리스트."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from clfx.event import Event
from clfx.query.engine import QueryEngine
from clfx.web.api import events_payload, query_payload

_STATIC = os.path.join(os.path.dirname(__file__), "static")
_ROUTES = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css"}
_CT = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


def make_handler(engine):
    """engine 주입 핸들러 클래스 팩토리(전역 상태 금지)."""

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body_bytes, code, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)

        def _json(self, obj, code=200):
            self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       code, "application/json")

        def _static(self, fname):
            path = os.path.join(_STATIC, fname)
            try:
                with open(path, "rb") as f:
                    body = f.read()
            except OSError:
                self._json({"error": "not found"}, 404)
                return
            ext = os.path.splitext(fname)[1]
            self._send(body, 200, _CT.get(ext, "application/octet-stream"))

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in _ROUTES:
                self._static(_ROUTES[u.path])
                return
            if u.path == "/api/events":
                try:
                    self._json(events_payload(engine))
                except Exception as e:               # 서버는 안 죽는다
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/query":
                q = (parse_qs(u.query).get("q") or [""])[0]
                if not q:
                    self._json({"error": "q required"}, 400)
                    return
                try:
                    self._json(query_payload(engine, q))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            self._json({"error": "not found"}, 404)

        def log_message(self, *a):
            pass  # 콘솔 조용히

    return Handler


def load_engine(analyzed_path):
    """analyzed.jsonl → QueryEngine. 깨진 줄/없는 파일은 예외를 그대로 올린다
    (포렌식: 부분 로드보다 명확한 실패)."""
    with open(analyzed_path, encoding="utf-8") as f:
        events = [Event.from_dict(json.loads(l)) for l in f if l.strip()]
    return QueryEngine(events)


def serve(analyzed_path, host="127.0.0.1", port=8787):
    engine = load_engine(analyzed_path)
    httpd = ThreadingHTTPServer((host, port), make_handler(engine))
    print(f"clfx dashboard: http://{host}:{port}  (Ctrl+C to stop)", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
```

> 테스트가 `/` 를 200으로 기대하므로 Task 5 전에는 `test_index_served`가 실패한다. **Task 4 커밋 시점엔 index.html이 아직 없으니** 이 테스트만 일시적으로 xfail이 아니라 — 순서를 지켜 Task 5에서 static 파일을 만든 뒤 전체 통과시킨다. Task 4 Step 4의 실행은 `test_index_served` 제외하고 통과 확인한다.

- [ ] **Step 4: 정적 의존 테스트 제외하고 통과 확인**

Run: `pytest tests/test_web_server.py -v -k "not index_served"`
Expected: PASS (events/query/400/404 4건). `test_index_served`는 Task 5에서 통과.

- [ ] **Step 5: 커밋**

```bash
git add clfx/web/server.py tests/test_web_server.py
git commit -m "feat(web): http.server 핸들러 + serve (api 위임, read-only, Stage 4 Task4)"
```

---

### Task 5: 프론트 (index.html / app.css / app.js)

**Files:**
- Create: `clfx/web/static/index.html`
- Create: `clfx/web/static/app.css`
- Create: `clfx/web/static/app.js`
- Test: `tests/test_web_server.py::test_index_served` (Task 4에서 작성됨)

- [ ] **Step 1: index.html 작성**

`clfx/web/static/index.html`:

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>clfx — 포렌식 대시보드</title>
  <link rel="stylesheet" href="/app.css">
</head>
<body>
  <header>
    <h1>clfx 포렌식 대시보드</h1>
    <form id="q-form">
      <input id="q" type="text" placeholder="자연어 질의: 누가 .env 읽었어? / 유출된 비밀 / 타임라인 요약해줘" autocomplete="off">
      <button type="submit">질의</button>
      <button type="button" id="reset">전체</button>
    </form>
    <div id="filters">
      <span>actor:</span>
      <label><input type="checkbox" class="f-actor" value="user" checked> user</label>
      <label><input type="checkbox" class="f-actor" value="agent" checked> agent</label>
      <span>tags:</span>
      <label><input type="checkbox" class="f-tag" value="secret" checked> secret</label>
      <label><input type="checkbox" class="f-tag" value="pii" checked> pii</label>
      <label><input type="checkbox" class="f-tag" value="bypass-mode" checked> bypass</label>
    </div>
  </header>
  <div id="banner" class="hidden"></div>
  <div id="summary" class="hidden"></div>
  <main>
    <section id="timeline"></section>
    <aside id="detail" class="hidden"></aside>
  </main>
  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: app.css 작성 (actor 색구분 — A/B 시각화)**

`clfx/web/static/app.css`:

```css
* { box-sizing: border-box; }
body { font: 14px/1.5 system-ui, sans-serif; margin: 0; color: #1a1a1a; background: #f6f7f9; }
header { padding: 12px 16px; background: #fff; border-bottom: 1px solid #ddd; position: sticky; top: 0; }
h1 { font-size: 18px; margin: 0 0 8px; }
#q-form { display: flex; gap: 8px; }
#q { flex: 1; padding: 6px 10px; border: 1px solid #ccc; border-radius: 6px; }
button { padding: 6px 12px; border: 1px solid #ccc; border-radius: 6px; background: #fff; cursor: pointer; }
#filters { margin-top: 8px; font-size: 13px; color: #555; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
main { display: flex; gap: 16px; padding: 16px; align-items: flex-start; }
#timeline { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.card { background: #fff; border: 1px solid #e2e2e2; border-left-width: 5px; border-radius: 6px; padding: 8px 12px; cursor: pointer; }
/* actor 색구분: user(A)=파랑, agent(B)=빨강 */
.card.user { border-left-color: #2563eb; }
.card.agent { border-left-color: #dc2626; }
.card .meta { font-size: 12px; color: #666; }
.card .target { font-weight: 600; }
.card .preview { color: #444; white-space: pre-wrap; word-break: break-all; max-height: 3em; overflow: hidden; }
.badge { display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 10px; margin-left: 6px; color: #fff; }
.badge.secret { background: #dc2626; }
.badge.pii { background: #ea580c; }
.badge.bypass-mode { background: #7c3aed; }
#detail { width: 360px; background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 12px; position: sticky; top: 110px; }
#detail .src { font-family: ui-monospace, monospace; background: #f0f0f0; padding: 2px 6px; border-radius: 4px; }
#detail pre { white-space: pre-wrap; word-break: break-all; background: #fafafa; padding: 8px; border-radius: 4px; }
#summary { background: #fffbe6; border: 1px solid #f0d000; margin: 0 16px; padding: 10px 14px; border-radius: 6px; white-space: pre-wrap; }
#banner { background: #fee; border: 1px solid #dc2626; color: #dc2626; margin: 0 16px; padding: 10px 14px; border-radius: 6px; }
.hidden { display: none; }
.count { font-size: 12px; color: #888; padding: 0 16px; }
```

- [ ] **Step 3: app.js 작성 (fetch + 렌더 + 필터 + 상세)**

`clfx/web/static/app.js`. 검색/질의/탐지는 전부 서버 위임. JS는 표시·표시토글만.

```javascript
let CURRENT = [];  // 현재 표시 중인 이벤트 집합(서버가 준 것)

const $ = (s) => document.querySelector(s);
const timeline = $("#timeline");
const banner = $("#banner");
const summaryBox = $("#summary");
const detail = $("#detail");

function badge(t) { return `<span class="badge ${t}">${t}</span>`; }

function card(e, i) {
  const tags = (e.tags || []).map(badge).join("");
  const prev = e.preview ? `<div class="preview">${escapeHtml(e.preview)}</div>` : "";
  return `<div class="card ${e.actor}" data-i="${i}">
    <div class="meta">${e.ts || "?"} · ${e.actor}/${e.action} ${tags}</div>
    <div class="target">${escapeHtml(e.target || "")}</div>
    ${prev}
  </div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function activeFilters() {
  const actors = [...document.querySelectorAll(".f-actor:checked")].map(c => c.value);
  const tags = [...document.querySelectorAll(".f-tag:checked")].map(c => c.value);
  return { actors, tags };
}

function render() {
  const { actors, tags } = activeFilters();
  // 클라이언트측 표시 토글만(이미 분류된 필드 보이기/숨기기 — 로직 재구현 아님)
  const shown = CURRENT.filter(e =>
    actors.includes(e.actor) &&
    ((e.tags || []).length === 0 || (e.tags || []).some(t => tags.includes(t)) || !(e.tags || []).some(t => ["secret","pii","bypass-mode"].includes(t)))
  );
  timeline.innerHTML = shown.map((e) => card(e, CURRENT.indexOf(e))).join("")
    || '<div class="count">표시할 이벤트 없음</div>';
}

function showDetail(e) {
  detail.classList.remove("hidden");
  detail.innerHTML = `<h3>이벤트 상세</h3>
    <div>${e.ts || "?"} · <b>${e.actor}/${e.action}</b></div>
    <div>target: ${escapeHtml(e.target || "")}</div>
    <div>tags: ${(e.tags || []).join(", ") || "-"}</div>
    <div>session: ${escapeHtml(e.session || "")}</div>
    <div>출처: <span class="src">${escapeHtml(e.source.file)}:${e.source.line}</span></div>
    <pre>${escapeHtml(e.preview || "")}</pre>`;
}

async function load(url) {
  banner.classList.add("hidden");
  try {
    const r = await fetch(url);
    const data = await r.json();
    if (data.error) throw new Error(data.error);
    CURRENT = data.events || [];
    if (data.summary && data.summary.text) {
      summaryBox.classList.remove("hidden");
      summaryBox.textContent = "요약: " + data.summary.text;
    } else {
      summaryBox.classList.add("hidden");
    }
    render();
  } catch (err) {
    banner.classList.remove("hidden");
    banner.textContent = "에러: " + err.message;
  }
}

$("#q-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const q = $("#q").value.trim();
  if (q) load("/api/query?q=" + encodeURIComponent(q));
});
$("#reset").addEventListener("click", () => { $("#q").value = ""; load("/api/events"); });
document.querySelectorAll(".f-actor, .f-tag").forEach(c => c.addEventListener("change", render));
timeline.addEventListener("click", (ev) => {
  const c = ev.target.closest(".card");
  if (c) showDetail(CURRENT[+c.dataset.i]);
});

load("/api/events");  // 초기 타임라인
```

- [ ] **Step 4: 서버 통합 테스트 전체 통과 확인**

Run: `pytest tests/test_web_server.py -v`
Expected: PASS (5 test 전부 — `test_index_served` 포함, index.html이 이제 존재).

- [ ] **Step 5: 커밋**

```bash
git add clfx/web/static/index.html clfx/web/static/app.css clfx/web/static/app.js
git commit -m "feat(web): vanilla JS 프론트 — 타임라인 actor 색구분/필터/질의/상세 (Stage 4 Task5)"
```

---

### Task 6: CLI `serve` 서브커맨드

**Files:**
- Modify: `clfx/cli.py` (cmd_serve + build_parser)
- Test: `tests/test_web_server.py` (수동 확인 보조) — 자동 테스트는 import/파서 레벨

- [ ] **Step 1: 파서 레벨 실패 테스트 추가**

`tests/test_web_server.py` 에 추가:

```python
from clfx.cli import build_parser


def test_serve_subcommand_parses():
    args = build_parser().parse_args(["serve", "x.jsonl", "--port", "9000"])
    assert args.cmd == "serve" and args.analyzed == "x.jsonl" and args.port == 9000
    assert args.host == "127.0.0.1"  # 기본 로컬 바인드
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `pytest tests/test_web_server.py::test_serve_subcommand_parses -v`
Expected: FAIL — `invalid choice: 'serve'`.

- [ ] **Step 3: cli.py 에 serve 추가**

`clfx/cli.py` 의 `cmd_query` 아래에 추가:

```python
def cmd_serve(args):
    try:
        from clfx.web.server import serve
        serve(args.analyzed, host=args.host, port=args.port)
    except FileNotFoundError as e:
        print(f"clfx serve: 파일 없음 {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"clfx serve: {e}", file=sys.stderr)
        return 1
    return 0
```

`build_parser()` 의 `return p` 직전에 추가:

```python
    rp = sub.add_parser("serve", help="analyzed.jsonl 을 로컬 웹 대시보드로 본다")
    rp.add_argument("analyzed")
    rp.add_argument("--host", default="127.0.0.1")
    rp.add_argument("--port", type=int, default=8787)
    rp.set_defaults(func=cmd_serve)
```

- [ ] **Step 4: 테스트 통과 + 전체 회귀 확인**

Run: `pytest tests/test_web_api.py tests/test_web_server.py tests/test_cli_query.py -q`
Expected: PASS (전부).

- [ ] **Step 5: 수동 스모크(선택) — 실제 기동 확인**

Run:
```bash
python3 -m clfx.cli serve clfx-out/analyzed.jsonl --port 8799 &
sleep 1
curl -s http://127.0.0.1:8799/api/events | python3 -c "import sys,json; d=json.load(sys.stdin); print('events', d['count'])"
kill %1
```
Expected: `events <N>` 출력(N>0). analyzed.jsonl 없으면 먼저 `parse`→`analyze`로 생성.

- [ ] **Step 6: 커밋**

```bash
git add clfx/cli.py tests/test_web_server.py
git commit -m "feat(cli): serve 서브커맨드 — 로컬 대시보드 기동 (Stage 4 Task6)"
```

---

## Acceptance (전체)

```bash
pytest tests/test_web_api.py tests/test_web_server.py -q
```

기존 회귀도 깨지지 않아야 한다:

```bash
pytest -q
```

## Self-Review 결과

- **Spec coverage**: 타임라인 actor 색구분(Task5 css `.card.user/.agent`)·필터(Task5 app.js activeFilters)·전문검색=질의 위임(Task2 query_payload search op)·secret/PII 하이라이트(Task5 badge)·이벤트 클릭→source(Task5 showDetail)·NL 질의(Task2)·read-only(Task4 GET만)·의존성0(stdlib)·`clfx serve`(Task6) — 전부 매핑됨.
- **Placeholder**: 없음(모든 코드 전체 기재).
- **Type 일관성**: `events_payload`/`query_payload` 시그니처가 Task1·2·3·4 전반 일치. `make_handler(engine)`·`load_engine`·`serve(path,host,port)` 일관. event dict 키(ts/actor/action/target/preview/tags/source{file,line})가 css/js와 일치.
- **DRY**: op 디스패치는 query_payload 한 곳(Task3에서 cmd_query가 위임).
