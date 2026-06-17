"""stdlib http.server 기반 로컬 대시보드 서버. api.py를 호출+직렬화만 한다.
GET 전용(read-only). 127.0.0.1 바인드, 정적 파일 화이트리스트."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from clfx.event import Event
from clfx.query.engine import QueryEngine
from clfx.web.api import (events_payload, query_payload,
                          activity_payload, files_payload, keywords_payload,
                          sources_payload, scan_to_engine)

def _static_dir():
    """정적 파일 디렉터리. PyInstaller onefile은 sys._MEIPASS에 추출되므로 그 경로 우선."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "clfx", "web", "static")
    return os.path.join(os.path.dirname(__file__), "static")


_STATIC = _static_dir()
_ROUTES = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css"}
_CT = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}


class ServerState:
    """교체가능 엔진 보유(스캔 시 state.engine 교체). 전역 상태 회피용 가변 컨테이너.
    scan = 진행상황(POST /api/scan 처리 스레드가 갱신, GET /api/scan/progress 폴링이 읽음)."""
    def __init__(self, engine):
        self.engine = engine
        self.scan = {"total": 0, "done": 0, "events": 0, "current": None, "finished": True, "error": None}


def make_handler(state):
    """ServerState(가변 엔진) 주입 핸들러 팩토리. 스캔으로 state.engine 교체 가능(요청 시점 읽기)."""

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
            if u.path == "/api/sources":
                try:
                    self._json(sources_payload())
                except Exception as e:               # 서버는 안 죽는다
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/scan/progress":
                self._json(state.scan); return
            if u.path == "/api/events":
                try:
                    self._json(events_payload(state.engine))
                except Exception as e:               # 서버는 안 죽는다
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/query":
                q = (parse_qs(u.query).get("q") or [""])[0]
                if not q:
                    self._json({"error": "q required"}, 400)
                    return
                try:
                    self._json(query_payload(state.engine, q))
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

                    eng = scan_to_engine(roots, on_progress=_prog)
                    state.engine = eng                       # 엔진 교체
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
