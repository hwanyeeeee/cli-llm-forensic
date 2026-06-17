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
                          activity_payload, files_payload, keywords_payload)

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
            if u.path == "/api/activity":
                by = (parse_qs(u.query).get("by") or ["day"])[0]
                try:
                    self._json(activity_payload(engine, by=by))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/files":
                try:
                    self._json(files_payload(engine))
                except Exception as e:
                    self._json({"error": str(e)}, 500)
                return
            if u.path == "/api/keywords":
                try:
                    self._json(keywords_payload(engine))
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
