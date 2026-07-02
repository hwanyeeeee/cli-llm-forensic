"""Phase 1 계측 하네스 — timings는 별도 필드에만(I6), 증거 페이로드 미오염."""
import json
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

from clfx.query.engine import QueryEngine
from clfx.web.api import forensic_scan, scan_to_engine
from clfx.web.server import make_handler, ServerState

FORENSIC_TIMING_KEYS = {"walk_tmp_s", "resolve_s", "hash_s", "attribution_s", "retention_s"}


def _server_with(state):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _get(httpd, path):
    port = httpd.server_address[1]
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
        return r.status, r.read().decode("utf-8")


def _post(httpd, path, obj):
    port = httpd.server_address[1]
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req) as r:
        return r.status, r.read().decode("utf-8")


def test_forensic_scan_returns_timings():
    out = forensic_scan([], roots=[], tmp_dirs=[])
    t = out["timings"]
    assert set(t) == FORENSIC_TIMING_KEYS
    assert all(isinstance(v, float) and v >= 0.0 for v in t.values())


def test_artifacts_payload_has_no_timings():
    # I6: /api/artifacts(증거 계약)에 timings 미노출 — 서버가 pop.
    state = ServerState(QueryEngine([]))
    httpd = _server_with(state)
    try:
        code, _ = _post(httpd, "/api/scan", {"roots": ["tests/fixtures/dot-claude"]})
        assert code == 200
        _, body = _get(httpd, "/api/artifacts")
        assert "timings" not in json.loads(body)
    finally:
        httpd.shutdown()


def test_scan_to_engine_attaches_parse_timings():
    eng = scan_to_engine(["tests/fixtures/dot-claude"])
    t = eng.parse_timings
    assert set(t) == {"parse_wall_s", "enrich_s"}
    assert all(isinstance(v, float) and v >= 0.0 for v in t.values())


def test_scan_to_engine_empty_roots_parse_timings():
    eng = scan_to_engine([])
    assert eng.parse_timings == {"parse_wall_s": 0.0, "enrich_s": 0.0}


def test_scan_progress_exposes_timings():
    state = ServerState(QueryEngine([]))
    httpd = _server_with(state)
    try:
        code, _ = _post(httpd, "/api/scan", {"roots": ["tests/fixtures/dot-claude"]})
        assert code == 200
        _, body = _get(httpd, "/api/scan/progress")
        t = json.loads(body)["timings"]
        assert {"parse_wall_s", "enrich_s", "walk_tmp_s", "resolve_s", "hash_s",
                "attribution_s", "retention_s", "mcp_s"} <= set(t)
    finally:
        httpd.shutdown()


import time as _time

from clfx.event import Event, Source


def _mini_engine():
    return QueryEngine([
        Event("2026-06-11T09:00:00Z", "claude", "s1", "agent", "read", "a.txt",
              "x", Source("h.jsonl", 1), []),
    ])


def test_request_timing_logged_to_stderr(capsys):
    httpd = _server_with(ServerState(_mini_engine()))
    try:
        _get(httpd, "/api/stats")
        err = ""
        for _ in range(50):                      # 핸들러 스레드 print 플러시 대기(비플레이키)
            err += capsys.readouterr().err
            if "[clfx.timing] GET /api/stats" in err:
                break
            _time.sleep(0.02)
        assert "[clfx.timing] GET /api/stats" in err
        assert "ms" in err and "B" in err
    finally:
        httpd.shutdown()
