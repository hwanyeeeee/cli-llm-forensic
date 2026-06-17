import json
import threading
import urllib.request
import urllib.parse
import urllib.error
from http.server import ThreadingHTTPServer

from clfx.event import Event, Source
from clfx.query.engine import QueryEngine
from clfx.web.server import make_handler
from clfx.cli import build_parser, main


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


def test_serve_subcommand_parses():
    args = build_parser().parse_args(["serve", "x.jsonl", "--port", "9000"])
    assert args.cmd == "serve" and args.analyzed == "x.jsonl" and args.port == 9000
    assert args.host == "127.0.0.1"  # 기본 로컬 바인드


def test_serve_broken_jsonl_exits_1(tmp_path, capsys):
    # 깨진 analyzed.jsonl → load_engine 이 serve_forever 전에 즉시 예외 → stderr + exit 1 (blocking 안 함)
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{bad\n", encoding="utf-8")
    assert main(["serve", str(bad)]) == 1
    assert "clfx serve" in capsys.readouterr().err


def test_serve_missing_file_exits_1(tmp_path, capsys):
    assert main(["serve", str(tmp_path / "nope.jsonl")]) == 1
    assert "clfx serve" in capsys.readouterr().err


def test_activity_endpoint():
    httpd = _server()
    try:
        code, body = _get(httpd, "/api/activity?by=month")
        assert code == 200
        import json as _j
        d = _j.loads(body)
        assert d["by"] == "month" and isinstance(d["rows"], list)
    finally:
        httpd.shutdown()


def test_files_endpoint():
    httpd = _server()
    try:
        code, body = _get(httpd, "/api/files")
        assert code == 200
        import json as _j
        assert "files" in _j.loads(body)
    finally:
        httpd.shutdown()


def test_keywords_endpoint():
    httpd = _server()
    try:
        code, body = _get(httpd, "/api/keywords")
        assert code == 200
        import json as _j
        assert "keywords" in _j.loads(body)
    finally:
        httpd.shutdown()
