"""stdlib http.server 기반 로컬 대시보드 서버. api.py를 호출+직렬화만 한다.
GET 전용(read-only). 127.0.0.1 바인드, 정적 파일 화이트리스트."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from clfx.event import Event
from clfx.query.engine import QueryEngine
from clfx.web.api import (events_payload, query_payload, stats_payload,
                          activity_payload, files_payload, keywords_payload,
                          sources_payload, scan_to_engine, forensic_scan,
                          mcp_payload)

def _static_dir():
    """정적 파일 디렉터리. PyInstaller onefile은 sys._MEIPASS에 추출되므로 그 경로 우선."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "clfx", "web", "static")
    return os.path.join(os.path.dirname(__file__), "static")


_STATIC = _static_dir()
_ROUTES = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css", "/logo.png": "logo.png",
           "/view.html": "view.html", "/view.js": "view.js", "/forensic-views.js": "forensic-views.js"}
_CT = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png"}


class ServerState:
    """교체가능 엔진 보유(스캔 시 state.engine 교체). 전역 상태 회피용 가변 컨테이너.
    scan = 진행상황(POST /api/scan 처리 스레드가 갱신, GET /api/scan/progress 폴링이 읽음)."""
    def __init__(self, engine):
        self.engine = engine
        self.scan = {"total": 0, "done": 0, "events": 0, "current": None, "finished": True, "error": None}
        # 아티팩트 포렌식 결과(POST /api/scan서 forensic_scan으로 갱신, GET /api/artifacts가 읽음).
        # FS 분석 실패해도 빈 계약 유지(스캔 응답은 성공).
        self.artifacts = {"scanned": 0, "missing": 0, "tmp_scanned": 0, "tmp_roots": [],
                          "errors": [], "hashes": [], "attribution": []}
        # 원본→동일해시 tmp 검색 인덱스(POST /api/scan서 forensic_scan 결과를 pop, GET /api/hash-search가 읽음).
        # /api/artifacts엔 싣지 않음(대용량/read-only 조회 분리). 빈 계약 유지.
        self.tmp_hash_index = {}
        # MCP 통합 결과(POST /api/scan서 mcp_payload로 갱신, GET /api/mcp가 읽음).
        # MCP 분석 실패해도 빈 계약 유지(스캔 응답은 성공).
        self.mcp = {"configs": [], "usage": [], "configured_unused": [],
                    "used_unconfigured": [], "errors": []}


def make_handler(state):
    """ServerState(가변 엔진) 주입 핸들러 팩토리. 스캔으로 state.engine 교체 가능(요청 시점 읽기)."""

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body_bytes, code, content_type):
            self.send_response(code)
            ct = content_type + ("; charset=utf-8" if (content_type.startswith("text/") or content_type == "application/json") else "")
            self.send_header("Content-Type", ct)
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
            if u.path == "/api/sources":
                try:
                    self._json(sources_payload())
                except Exception as e:               # 서버는 안 죽는다
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/scan/progress":
                self._json(state.scan); return
            if u.path == "/api/stats":               # 경량 타일 집계(events 직렬화 전 즉시 표시)
                try:
                    self._json(stats_payload(state.engine))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/events":
                try:
                    self._json(events_payload(state.engine))
                except Exception as e:               # 서버는 안 죽는다
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/query":
                qs = parse_qs(u.query)
                q = (qs.get("q") or [""])[0]
                if not q:
                    self._json({"error": "q required"}, 400)
                    return
                src = (qs.get("sources") or [""])[0]
                origins = set(s for s in src.split(",") if s) or None   # 체크된 플랫폼만(없으면 전체)
                try:
                    self._json(query_payload(state.engine, q, origins=origins))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/activity":
                by = (parse_qs(u.query).get("by") or ["day"])[0]
                try:
                    self._json(activity_payload(state.engine, by=by))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/files":
                try:
                    self._json(files_payload(state.engine))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/keywords":
                try:
                    self._json(keywords_payload(state.engine))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/artifacts":
                try:
                    self._json(state.artifacts)
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/mcp":
                try:
                    self._json(state.mcp)
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/hash-search":         # 원본 sha → 동일해시 tmp 사본 조회(read-only, 해시 hex만)
                try:
                    sha = (parse_qs(u.query).get("sha") or [""])[0].strip().lower()
                    self._json({"sha": sha, "matches": state.tmp_hash_index.get(sha, [])})
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            if u.path == "/api/scan":
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    body = json.loads(self.rfile.read(n) or b"{}")
                    roots = body.get("roots") or []
                    # 진행상황 초기화 → on_progress가 루트 완료마다 갱신 → 폴링 GET이 읽음(동기 POST 유지).
                    state.scan = {"total": len(roots), "done": 0, "events": 0,
                                  "current": None, "finished": False, "error": None}

                    def _prog(d, t, ev, cur):
                        state.scan.update(done=d, total=t, events=ev, current=cur)

                    eng, ev_root = scan_to_engine(roots, on_progress=_prog, collect_artifacts=True)
                    state.engine = eng                       # 엔진 교체
                    try:                                     # FS 실패해도 스캔 응답은 성공(빈 계약 유지)
                        full = forensic_scan(ev_root, roots=roots)
                        state.tmp_hash_index = full.pop("tmp_hash_index", {})   # /api/artifacts엔 안 실림(분리)
                        state.artifacts = full
                    except Exception:
                        state.tmp_hash_index = {}
                        state.artifacts = {"scanned": 0, "missing": 0, "tmp_scanned": 0,
                                           "tmp_roots": [], "errors": [], "hashes": [], "attribution": []}
                    try:                                     # MCP 실패해도 스캔 응답은 성공(빈 계약 유지)
                        state.mcp = mcp_payload(eng, roots)
                    except Exception:
                        state.mcp = {"configs": [], "usage": [], "configured_unused": [],
                                     "used_unconfigured": [], "errors": []}
                    import threading
                    from clfx.query.llm import prewarm
                    threading.Thread(target=prewarm, daemon=True).start()   # 모델 미리 로드(쿼리 전 워밍, fire-and-forget)
                    evs = eng.events
                    by = {}
                    for e in evs:
                        for t in e.tags:
                            if t.startswith("origin:"):
                                k = t[len("origin:"):]
                                by[k] = by.get(k, 0) + 1
                    state.scan.update(done=state.scan["total"], events=len(evs),
                                      finished=True, current=None)
                    self._json({"ok": True, "count": len(evs), "by_origin": by})
                except Exception as e:
                    state.scan.update(finished=True, error=str(e))
                    self._json({"ok": False, "error": str(e)}, 500)
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


def build_state(analyzed_path):
    """analyzed_path 있으면 load, None이면 빈 엔진. serve/테스트 공용(블록 없이 단언 가능)."""
    engine = load_engine(analyzed_path) if analyzed_path else QueryEngine([])
    return ServerState(engine)


def serve(analyzed_path=None, host="127.0.0.1", port=8787):
    state = build_state(analyzed_path)
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    print(f"clfx dashboard: http://{host}:{port}  (Ctrl+C to stop)", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
