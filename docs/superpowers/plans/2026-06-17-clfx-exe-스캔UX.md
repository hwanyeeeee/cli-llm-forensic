# clfx exe + 인앱 스캔 UX 구현 플랜

> **For agentic workers:** 이 plan은 panel1이 Task 단위로 구현한다. 각 Task는 TDD(빨강→초록) + 잦은 커밋. panel0이 Task별 codex 교차리뷰.

**Goal:** `clfx.exe`를 인자 없이 실행하면 브라우저가 자동으로 열리고, 스캔 화면에서 자동탐지된 소스(Windows/WSL `.claude`)를 골라 [스캔]하면 인메모리 parse+analyze 후 대시보드가 뜬다.

**Architecture:** 신규 `clfx/discover.py`(소스 자동탐지). `web/server.py`를 **상태 보유**(엔진 교체 가능)로 바꾸고 `GET /api/sources`·`POST /api/scan` 추가, analyzed 없이 起動 가능(빈 모드). `web/api.py`에 `sources_payload`·`scan_to_engine`. UI는 데이터 없을 때 스캔 화면. `packaging/launcher.py`가 서버 起動+`webbrowser.open`, PyInstaller `--onefile`로 단일 exe.

**Tech Stack:** Python 3 stdlib only(http.server·urllib·json), PyInstaller(빌드 전용), vanilla JS. 엔진=결정적 단일진실. 증거 외부전송 0.

**불변식 체크리스트(plan.md I1~I5) 적용:** ts는 norm_ts/ts_key(I1) · 집계 결정적(I2) · 마스크 인식(I3) · 테스트 환경무관(I4) · actor/origin 분리(I5). 스캔은 기존 parse_source→analyze 파이프라인 재사용이라 I1~I3는 그 경로가 이미 보장.

---

## 스코프 / 비스코프

- **스코프**: 자동탐지, 빈-서브 모드, /api/sources·/api/scan, 스캔 UI, launcher, PyInstaller onefile, _MEIPASS 정적경로.
- **비스코프(별도 plan)**: 복구·해시 ①②(B plan), MCP ⑧(C plan), 디스크 carving. 스캔은 기존 Event 소스(history/transcript/uploads 등 parser가 이미 읽는 것)만 대상.

## 데이터 흐름

```
clfx.exe → launcher.py: serve(empty) + webbrowser.open(127.0.0.1:PORT)
브라우저 → GET / (스캔화면; 엔진 비었으면 app.js가 스캔패널 렌더)
        → GET /api/sources → [{path,label,exists,events_hint?}]
사용자 체크 → POST /api/scan {roots:[...]} → 서버: parse_source(각 root)+analyze → QueryEngine 교체 → {ok,count,by_origin}
        → app.js: /api/events·activity·files·keywords 다시 fetch → 대시보드 렌더(소스 토글 포함)
```

---

## Task 1: 소스 자동탐지 `clfx/discover.py`

**Files:**
- Create: `clfx/discover.py`
- Test: `tests/test_discover.py`

자동탐지 규칙(환경 비의존·테스트 가능하게 베이스경로 주입): Windows `%USERPROFILE%\.claude`, WSL `\\wsl.localhost\<distro>\home\<user>\.claude`(Windows에서 실행 시), 그리고 현재 OS의 `~/.claude`. label은 `_origin_label`(cli.py와 동일 규칙) 재사용 — 중복정의 금지, cli에서 import.

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_discover.py
from clfx.discover import discover_sources

def test_discovers_existing_claude_dirs(tmp_path, monkeypatch):
    win = tmp_path / "winhome" / ".claude"; win.mkdir(parents=True)
    wsl = tmp_path / "wslhome" / ".claude"; wsl.mkdir(parents=True)
    # 후보 생성기를 주입(환경 비의존)
    cands = [str(win), str(wsl), str(tmp_path / "nope" / ".claude")]
    out = discover_sources(candidates=cands)
    paths = {o["path"]: o for o in out}
    assert paths[str(win)]["exists"] is True
    assert paths[str(tmp_path / "nope" / ".claude")]["exists"] is False
    assert all("label" in o for o in out)        # origin 라벨 부여
```

- [ ] **Step 2: 실패 확인** — `pytest tests/test_discover.py -v` → ImportError.

- [ ] **Step 3: 구현**

```python
# clfx/discover.py
"""소스(.claude 루트) 자동탐지. 단일 PC의 Windows + WSL 후보를 나열한다.
판정·라벨은 cli._origin_label 재사용(단일 출처). 환경 비의존 위해 candidates 주입 가능."""
import os
from pathlib import Path
from clfx.cli import _origin_label


def _default_candidates():
    cands = []
    home = os.path.expanduser("~")
    cands.append(os.path.join(home, ".claude"))                  # 현재 OS home
    up = os.environ.get("USERPROFILE")                           # Windows home(있으면)
    if up:
        cands.append(os.path.join(up, ".claude"))
    # WSL distros (Windows에서 실행 시 보임). 없으면 조용히 스킵.
    wsl_root = Path(r"\\wsl.localhost")
    try:
        if wsl_root.exists():
            for distro in wsl_root.iterdir():
                # \\wsl.localhost\<distro>\home\<user>\.claude
                home_dir = distro / "home"
                if home_dir.exists():
                    for user in home_dir.iterdir():
                        cands.append(str(user / ".claude"))
                root_claude = distro / "root" / ".claude"
                cands.append(str(root_claude))
    except OSError:
        pass
    # 중복 제거(순서 보존)
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c); out.append(c)
    return out


def discover_sources(candidates=None):
    """반환: [{"path","label","exists"}] — label=origin(wsl/windows/other), exists=디렉터리 존재."""
    cands = candidates if candidates is not None else _default_candidates()
    out = []
    for c in cands:
        out.append({"path": c, "label": _origin_label(c), "exists": os.path.isdir(c)})
    return out
```

- [ ] **Step 4: 통과 확인** — `pytest tests/test_discover.py -v` → PASS.
- [ ] **Step 5: 커밋** — `git add clfx/discover.py tests/test_discover.py && git commit -m "feat(discover): .claude 소스 자동탐지(Windows+WSL)"`

---

## Task 2: 인메모리 스캔 `web/api.py`

**Files:**
- Modify: `clfx/web/api.py`
- Test: `tests/test_web_scan.py`

`scan_to_engine(roots)` = 각 root를 parse_source→origin 태깅→리스트 병합→analyze(enrich)→`QueryEngine` 반환. cli.cmd_parse의 origin 태깅 로직과 **동일 규칙**(중복 방지 위해 헬퍼 공유: cli에 `parse_roots(roots)->events` 추출 후 api·cli 양쪽서 사용).

- [ ] **Step 1: cli에 공유 헬퍼 추출(리팩토링) + 실패 테스트**

`clfx/cli.py`에 추가(cmd_parse가 이걸 호출하게 변경, DRY):
```python
def parse_roots(roots):
    """여러 .claude 루트 → origin 태깅된 Event 리스트(병합). parse/scan 공용."""
    from clfx.parser import parse_source
    from clfx.sources.claude import ClaudeSource
    evs = []
    for root in roots:
        tag = f"origin:{_origin_label(root)}"
        for e in parse_source(ClaudeSource(root)):
            if tag not in e.tags:
                e.tags.append(tag)
            evs.append(e)
    return evs
```
cmd_parse는 `evs = parse_roots(args.root)` 로 단순화.

```python
# tests/test_web_scan.py
from clfx.web.api import scan_to_engine

def test_scan_builds_engine_from_fixture():
    eng = scan_to_engine(["tests/fixtures/dot-claude"])
    assert len(eng.events) > 0
    assert any("origin:" in t for e in eng.events for t in e.tags)
```

- [ ] **Step 2: 실패 확인** — ImportError(scan_to_engine).

- [ ] **Step 3: 구현** (`clfx/web/api.py`)

```python
from clfx.cli import parse_roots
from clfx.analyze.attribution import enrich      # analyze가 쓰는 enrich 함수(실제 이름에 맞춰 import)
from clfx.query.engine import QueryEngine

def scan_to_engine(roots):
    """선택 루트들을 parse+analyze(인메모리) → QueryEngine. 디스크 analyzed.jsonl 불요."""
    events = parse_roots(roots)
    analyzed = enrich(events)                     # secret 태그·마스킹·bypass 귀속 (analyze 단계)
    return QueryEngine(analyzed)

def sources_payload():
    from clfx.discover import discover_sources
    return {"sources": discover_sources()}
```
주: `enrich`의 실제 함수명/시그니처는 `clfx/analyze/attribution.py`(또는 cmd_analyze가 호출하는 것)를 확인해 맞춰라. cmd_analyze와 동일 변환을 거쳐야 디스크 경로와 결과가 일치한다.

- [ ] **Step 4: 통과 확인** — `pytest tests/test_web_scan.py -v` → PASS.
- [ ] **Step 5: 커밋**

---

## Task 3: 서버 상태화 + 라우트 `web/server.py`

**Files:**
- Modify: `clfx/web/server.py`, `clfx/cli.py`(serve analyzed 선택적)
- Test: `tests/test_web_server.py`(확장)

서버가 **교체가능한 엔진 1개**를 보유. analyzed 없이 起動 가능(엔진=빈 QueryEngine([])). `GET /api/sources`, `POST /api/scan`(body {roots}) → scan_to_engine으로 엔진 교체 → {ok,count,by_origin}.

- [ ] **Step 1: 실패 테스트**(확장)

```python
def test_scan_route_populates_engine():
    # 빈 엔진으로 서버 핸들러 만들고 /api/scan POST → 200 + count>0, 이후 /api/events 채워짐
    from clfx.web.server import make_handler, ServerState
    state = ServerState(QueryEngine([]))
    Handler = make_handler(state)
    # ... http.server TestServer로 POST /api/scan {"roots":["tests/fixtures/dot-claude"]} ...
    # assert resp json ok==True and count>0
    # 이후 GET /api/events count>0
```

- [ ] **Step 2: 실패 확인**

- [ ] **Step 3: 구현** — `make_handler`가 `ServerState`(엔진 보유 가변객체)를 받게:

```python
class ServerState:
    def __init__(self, engine):
        self.engine = engine

def make_handler(state):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            u = urlparse(self.path)
            eng = state.engine
            if u.path == "/api/sources":
                self._json(sources_payload()); return
            # 기존 /api/events·query·activity·files·keywords 는 eng(state.engine) 사용
            ...
        def do_POST(self):
            u = urlparse(self.path)
            if u.path == "/api/scan":
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                roots = body.get("roots") or []
                try:
                    state.engine = scan_to_engine(roots)   # 엔진 교체
                    evs = state.engine.events
                    by = {}
                    for e in evs:
                        for t in e.tags:
                            if t.startswith("origin:"):
                                by[t[7:]] = by.get(t[7:], 0) + 1
                    self._json({"ok": True, "count": len(evs), "by_origin": by})
                except Exception as e:
                    self._json({"ok": False, "error": str(e)}, 500)
                return
            self._json({"error": "not found"}, 404)
    return H
```
`serve(analyzed_path=None, ...)`: analyzed_path 주어지면 load해서 ServerState(엔진), 없으면 ServerState(QueryEngine([])). `load_engine`은 기존 재사용.

`clfx/cli.py` serve 서브파서: `rp.add_argument("analyzed", nargs="?", default=None)` (선택적). cmd_serve가 None이면 빈 상태로 serve.

- [ ] **Step 4: 통과 확인** — `pytest tests/test_web_server.py -q`
- [ ] **Step 5: 커밋**

---

## Task 4: 스캔 화면 UI `web/static/`

**Files:**
- Modify: `clfx/web/static/index.html`, `app.js`(, `app.css`)

데이터 없을 때(부트 시 /api/events count==0) **스캔 화면** 표시: /api/sources fetch → 후보를 체크박스(라벨·경로·존재여부)로 → [스캔] → POST /api/scan {roots:선택} → 진행표시 → 완료 시 EVENTS 재로드(/api/events 등) → 대시보드 렌더. "다시 스캔" 버튼 상시.

- [ ] **Step 1: index.html** — 스캔 오버레이 컨테이너 추가:
```html
<div id="scan-screen" hidden>
  <div class="scan-card">
    <h2>포렌식 스캔</h2>
    <p>분석할 소스를 선택하세요 (이 PC의 Claude 기록).</p>
    <div id="scan-sources"></div>
    <button id="scan-go">스캔 시작</button>
    <div id="scan-status"></div>
  </div>
</div>
```
- [ ] **Step 2: app.js boot 분기** — `/api/events` count==0 이면 `showScan()` (대시보드 숨기고 #scan-screen 표시). count>0 이면 기존 대시보드.
- [ ] **Step 3: showScan()** — `jget('/api/sources')` → 각 source 체크박스 렌더(exists=false는 비활성+회색). 기본 exists=true 체크.
- [ ] **Step 4: scan-go 핸들러** — 선택 roots로 `fetch('/api/scan',{method:'POST',body:JSON.stringify({roots})})` → 응답 ok면 #scan-status에 "N건(소스별)" 표시 후 `boot()` 재호출(대시보드 로드). 실패면 에러 표시.
- [ ] **Step 5: "다시 스캔"** — 헤더에 버튼 → showScan() 재호출.
- [ ] **Step 6: 수동 검증** — `python -m clfx.cli serve`(인자 없이) → 브라우저 스캔화면 → 픽스처/실제 소스 선택 → 대시보드. 커밋.

---

## Task 5: launcher + PyInstaller `packaging/`

**Files:**
- Create: `packaging/launcher.py`, `packaging/build.md`(빌드 명령)
- Modify: `clfx/web/server.py`(_MEIPASS 정적경로)

- [ ] **Step 1: _MEIPASS 정적경로** — server.py `_STATIC` 결정:
```python
import sys, os
def _static_dir():
    base = getattr(sys, "_MEIPASS", None)        # PyInstaller onefile 임시 추출 경로
    if base:
        return os.path.join(base, "clfx", "web", "static")
    return os.path.join(os.path.dirname(__file__), "static")
_STATIC = _static_dir()
```
테스트: 비-frozen 환경서 기존 경로 반환(회귀 green).

- [ ] **Step 2: launcher.py**
```python
"""clfx.exe 엔트리 — 빈 서버 起動 + 브라우저 자동 오픈. 인자 0."""
import threading, webbrowser, time
from clfx.web.server import serve   # analyzed 없이 빈 모드

def main():
    host, port = "127.0.0.1", 8770
    t = threading.Thread(target=lambda: serve(None, host=host, port=port), daemon=True)
    t.start()
    time.sleep(1.0)
    webbrowser.open(f"http://{host}:{port}")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
```
(serve가 블로킹이면 메인스레드서 serve, 브라우저 오픈을 타이머 스레드로 — 둘 중 동작하는 형태로. 포트 사용중이면 +1 재시도.)

- [ ] **Step 3: PyInstaller 빌드 명령** (`packaging/build.md`):
```
pip install pyinstaller
pyinstaller --onefile --name clfx \
  --add-data "clfx/web/static;clfx/web/static" \    # Windows는 ; 구분(WSL/Unix는 :)
  packaging/launcher.py
# 산출: dist/clfx.exe
```
- [ ] **Step 4: 수동 검증** — `dist/clfx.exe` 실행 → 브라우저 자동 오픈 → 스캔 → 대시보드. (Windows에서.) 커밋.

---

## Self-Review (작성자 점검)

1. **spec 매핑**: exe(결정1)·단일PC 양 소스(결정3)·actor/origin 분리 — 커버. 복구/해시/MCP는 비스코프(B/C).
2. **placeholder 스캔**: `enrich` 실제 함수명 = Task2서 attribution.py 확인 필수(명시함).
3. **타입 일관**: ServerState.engine은 QueryEngine. /api/scan→교체. 기존 라우트가 state.engine 참조하도록 Task3서 전부 치환.
4. **I1~I5**: 스캔은 기존 parse→analyze 재사용이라 ts/마스크/결정성 보장. origin 태깅은 parse_roots(공유). 신규 ts 슬라이스 없음.

## 실행 핸드오프
- 권장: subagent-driven(Task별 panel1 구현 → panel0 codex 리뷰). 기존 하네스 루프 유지.
- acceptance(단계 전체): `pytest tests/test_discover.py tests/test_web_scan.py tests/test_web_server.py -q` + 전체 `pytest -q` green + `python -m clfx.cli serve`(인자0) 스캔→대시보드 수동확인.
