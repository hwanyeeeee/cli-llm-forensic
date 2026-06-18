from clfx.web.api import scan_to_engine, sources_payload


def test_scan_builds_engine_from_fixture():
    eng = scan_to_engine(["tests/fixtures/dot-claude"])
    assert len(eng.events) > 0
    assert any("origin:" in t for e in eng.events for t in e.tags)


def test_scan_enriches_secrets():
    # enrich가 돌았으면 secret/pii 태그 또는 마스킹(‹…›)이 존재해야 함(CLFXTEST 픽스처).
    eng = scan_to_engine(["tests/fixtures/dot-claude"])
    tagged = any(("secret" in e.tags or "pii" in e.tags) for e in eng.events)
    masked = any("‹" in (e.preview or "") for e in eng.events)
    assert tagged or masked


def test_sources_payload_shape():
    p = sources_payload()
    assert "sources" in p and isinstance(p["sources"], list)
    assert all({"path", "label", "exists"} <= set(s) for s in p["sources"])


def test_sources_payload_only_existing(monkeypatch):
    # 없는 후보(exists=False)는 화면에 안 보여야. discover_sources는 함수-지역 import라 원본을 패치.
    monkeypatch.setattr("clfx.discover.discover_sources",
        lambda: [{"path": "/a/.claude", "label": "wsl", "exists": True},
                 {"path": "/b/.claude", "label": "wsl", "exists": False}])
    out = sources_payload()
    assert [s["path"] for s in out["sources"]] == ["/a/.claude"]
    assert all(s["exists"] for s in out["sources"])


def test_scan_progress_is_file_count_based():
    from clfx.web.api import scan_to_engine
    calls = []
    eng = scan_to_engine(["tests/fixtures/dot-claude"], on_progress=lambda d,t,ev,cur: calls.append((d,t)))
    assert eng.events
    total = calls[-1][1]
    assert total > 0
    assert calls[-1][0] == total            # 최종 done==total(파일 전부 처리)
    assert all(d <= t for d,t in calls)     # done은 total 이하 단조


def test_claudesource_on_file_fires_per_file(tmp_path):
    from clfx.sources.claude import ClaudeSource
    import json as _j
    root = tmp_path / ".claude"; (root/"projects"/"p").mkdir(parents=True)
    (root/"history.jsonl").write_text(_j.dumps({"display":"x"})+"\n", encoding="utf-8")
    (root/"projects"/"p"/"a.jsonl").write_text("", encoding="utf-8")
    seen=[]
    src=ClaudeSource(str(root), on_file=lambda p: seen.append(p))
    list(src.history_records()); list(src.transcript_records())
    assert len(seen) == 2                   # history + a.jsonl 각 1회
    assert len(src.jsonl_files()) == 2 and len(src.transcript_files()) == 1


def test_scan_to_engine_reports_progress():
    from clfx.web.api import scan_to_engine
    calls = []
    eng = scan_to_engine(["tests/fixtures/dot-claude"], on_progress=lambda d,t,ev,cur: calls.append((d,t,ev)))
    assert eng.events
    assert calls and calls[-1][0] == calls[-1][1]          # done==total 마지막
    assert calls[-1][2] > 0                                 # 누적 events>0


def test_scan_merge_is_input_order_deterministic():
    from clfx.web.api import scan_to_engine
    # 같은 두 루트를 여러 번 스캔 → events의 (source.file,line) 시퀀스가 동일(run-to-run 결정적, I2)
    roots = ["tests/fixtures/dot-claude", "tests/fixtures/dot-claude"]
    seq1 = [(e.source.file, e.source.line) for e in scan_to_engine(roots).events]
    seq2 = [(e.source.file, e.source.line) for e in scan_to_engine(roots).events]
    assert seq1 == seq2 and len(seq1) > 0


def test_scan_equivalent_to_sequential():
    # 병렬·단일패스 결과 == 기존 순차(parse_source_tagged+enrich): 이벤트 전량·순서·태그 동일(무손실·I2 증명).
    from clfx.web.api import scan_to_engine
    from clfx.cli import parse_source_tagged
    from clfx.sources.claude import ClaudeSource
    from clfx.analyze.attribution import enrich
    root = "tests/fixtures/dot-claude"
    src = ClaudeSource(root); ref = parse_source_tagged(src, root); enrich(ref, src)
    got = scan_to_engine([root]).events
    assert len(got) == len(ref) and len(ref) > 0
    for a, b in zip(got, ref):
        assert (a.ts, a.actor, a.action, a.target, a.preview, a.source.file, a.source.line, sorted(a.tags)) \
            == (b.ts, b.actor, b.action, b.target, b.preview, b.source.file, b.source.line, sorted(b.tags))


def test_scan_bypass_collected_equals_reread():
    # 단일읽기 수집 bypass 태깅 == _bypass_sessions 재읽기 태깅(같은 read 이벤트에 bypass-mode).
    from clfx.web.api import scan_to_engine
    from clfx.cli import parse_source_tagged
    from clfx.sources.claude import ClaudeSource
    from clfx.analyze.attribution import enrich
    root = "tests/fixtures/dot-claude"
    src = ClaudeSource(root); ref = parse_source_tagged(src, root); enrich(ref, src)
    got = scan_to_engine([root]).events
    ref_b = {(e.source.file, e.source.line) for e in ref if "bypass-mode" in e.tags}
    got_b = {(e.source.file, e.source.line) for e in got if "bypass-mode" in e.tags}
    assert got_b == ref_b


def test_scan_parallel_merges_all_roots(tmp_path):
    # 병렬 scan: fixture + 빈 루트 → fixture 이벤트만, 정상 병합(빈 루트 0건).
    empty = tmp_path / "empty" / ".claude"; empty.mkdir(parents=True)
    eng = scan_to_engine(["tests/fixtures/dot-claude", str(empty)])
    assert len(eng.events) > 0
    # 엔진은 저장 시 정렬 안 함(질의 시 정렬) → 여기선 병합 완전성만 단언.
    assert any("origin:" in t for e in eng.events for t in e.tags)


_MCP_EMPTY = {"configs": [], "usage": [], "configured_unused": [],
              "used_unconfigured": [], "errors": []}


def test_serverstate_mcp_empty_contract():
    # ServerState는 engine 인자 필수. 초기 state.mcp는 빈 계약 유지(스캔 전 GET /api/mcp 안전).
    from clfx.web.server import ServerState
    from clfx.query.engine import QueryEngine
    s = ServerState(QueryEngine([]))
    assert s.mcp == _MCP_EMPTY


def test_serverstate_tmp_hash_index_empty_contract():
    # [#2b] ServerState 초기 tmp_hash_index는 빈 dict(스캔 전 GET /api/hash-search 안전).
    from clfx.web.server import ServerState
    from clfx.query.engine import QueryEngine
    s = ServerState(QueryEngine([]))
    assert s.tmp_hash_index == {}


def test_api_hash_search_route_returns_contract():
    # [#2b] GET /api/hash-search?sha=deadbeef → 200 + {"sha","matches":[]}(인덱스 비었을 때). server 라우트 배선.
    import json, threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from clfx.web.server import make_handler, ServerState
    from clfx.query.engine import QueryEngine
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ServerState(QueryEngine([]))))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/hash-search?sha=deadbeef")
        with urllib.request.urlopen(req) as r:
            code, body = r.status, r.read().decode("utf-8")
        assert code == 200
        assert json.loads(body) == {"sha": "deadbeef", "matches": []}
    finally:
        httpd.shutdown()


def test_serverstate_lazy_hash_index_fields():
    # OPT-3: ServerState는 lazy 캐시 필드(tmp_inventory, _hash_index_ready)와 lock을 갖는다.
    from clfx.web.server import ServerState
    from clfx.query.engine import QueryEngine
    s = ServerState(QueryEngine([]))
    assert s.tmp_hash_index == {}
    assert s.tmp_inventory == []
    assert s._hash_index_ready is False


def test_serverstate_scan_has_staged_fields():
    # OPT-7: ServerState.scan은 기존 키 + stage/stage_done/stage_total/overall_percent를 갖는다.
    from clfx.web.server import ServerState
    from clfx.query.engine import QueryEngine
    s = ServerState(QueryEngine([]))
    for k in ("total", "done", "events", "current", "finished", "error",
              "stage", "stage_done", "stage_total", "overall_percent"):
        assert k in s.scan


def test_lazy_hash_search_finds_unique_size_file(tmp_path, monkeypatch):
    # OPT-3 완전성: scan-time 인덱스는 dup-size만 — server lazy 전수 인덱스는 unique-size도 찾는다.
    import os, hashlib
    monkeypatch.setattr(os, "name", "posix")
    from clfx.web.server import ServerState, _ensure_hash_index
    from clfx.query.engine import QueryEngine
    from clfx.web.api import forensic_scan
    from clfx.analyze import artifacts as A
    tdir = tmp_path / "tmp"; tdir.mkdir()
    (tdir / "uniq").write_bytes(b"unique-size-content-zzz")   # 단독 크기
    (tdir / "dup1").write_bytes(b"SAME\n")
    (tdir / "dup2").write_bytes(b"SAME\n")
    full = forensic_scan([], roots=[], tmp_dirs=[str(tdir)])
    s = ServerState(QueryEngine([]))
    # POST /api/scan가 하던 것: tmp_inventory 저장 + lazy 캐시 리셋.
    s.tmp_inventory = full["tmp_inventory"]
    s.tmp_hash_index = {}
    s._hash_index_ready = False
    # scan-time 인덱스(dup만)에는 uniq sha가 없다.
    uniq_sha = hashlib.sha256(b"unique-size-content-zzz").hexdigest()
    assert uniq_sha not in full["tmp_hash_index"]
    # lazy 전수 인덱스 구축 후엔 uniq를 찾는다.
    idx = _ensure_hash_index(s)
    assert s._hash_index_ready is True
    assert uniq_sha in idx
    assert [m["path"] for m in idx[uniq_sha]] == [str(tdir / "uniq")]
    # 레퍼런스 전수 인덱스와 동일(무손실).
    ref = A.build_tmp_hash_index(A.build_tmp_inventory([str(tdir)]))
    assert idx == ref
    # 두 번째 호출은 캐시 재사용(같은 객체).
    assert _ensure_hash_index(s) is idx


def test_scan_pops_inventory_and_resets_lazy_cache(tmp_path):
    # OPT-3: POST /api/scan는 tmp_inventory/tmp_hash_index를 artifacts에서 pop(payload 비노출) +
    #        lazy 캐시 리셋. 여기선 핸들러 동치 로직을 ServerState로 직접 검증.
    import json, threading, urllib.request
    from http.server import ThreadingHTTPServer
    from clfx.web.server import make_handler, ServerState
    from clfx.query.engine import QueryEngine
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ServerState(QueryEngine([]))))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        # 빈 roots 스캔 → forensic_scan([], roots=[]) → 머신 tmp는 도출되지만 결정성 위해 결과만 검사.
        body = json.dumps({"roots": []}).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/scan", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            assert r.status == 200
        # /api/artifacts에 tmp_hash_index/tmp_inventory가 새어나오지 않아야.
        req2 = urllib.request.Request(f"http://127.0.0.1:{port}/api/artifacts")
        with urllib.request.urlopen(req2) as r:
            art = json.loads(r.read().decode("utf-8"))
        assert "tmp_hash_index" not in art
        assert "tmp_inventory" not in art
    finally:
        httpd.shutdown()


def test_events_route_sends_cached_bytes(tmp_path):
    # OPT-8: GET /api/events는 캐시된 bytes를 그대로 전송 — events_payload와 바이트 동일.
    import json, threading, urllib.request
    from http.server import ThreadingHTTPServer
    from clfx.web.server import make_handler, ServerState
    from clfx.web.api import scan_to_engine, events_payload
    eng = scan_to_engine(["tests/fixtures/dot-claude"])
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ServerState(eng)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/events")
        with urllib.request.urlopen(req) as r:
            raw = r.read()
        assert raw == json.dumps(events_payload(eng), ensure_ascii=False).encode("utf-8")
    finally:
        httpd.shutdown()


# ── B-1/B-2: chain-of-custody attestation (ServerState + /api/attestation) ──
_ATTEST_EMPTY = {"acquired": [], "acquired_count": 0, "stat_only_count": 0,
                 "all_read_only": True, "modes_seen": [], "write_delete_rename_ops": 0,
                 "note": "(스캔 전)"}


def test_serverstate_attestation_empty_contract():
    # ServerState 초기 attestation은 empty-but-valid 계약(스캔 전 GET /api/attestation 안전).
    from clfx.web.server import ServerState
    from clfx.query.engine import QueryEngine
    s = ServerState(QueryEngine([]))
    assert s.attestation == _ATTEST_EMPTY


def test_api_attestation_route_returns_contract():
    # GET /api/attestation → 200 + empty 계약(스캔 전). server.py 라우트 배선 증명.
    import json, threading, urllib.request
    from http.server import ThreadingHTTPServer
    from clfx.web.server import make_handler, ServerState
    from clfx.query.engine import QueryEngine
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ServerState(QueryEngine([]))))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/attestation")
        with urllib.request.urlopen(req) as r:
            code, body = r.status, r.read().decode("utf-8")
        assert code == 200
        got = json.loads(body)
        assert set(got) == set(_ATTEST_EMPTY)
        assert got == _ATTEST_EMPTY
    finally:
        httpd.shutdown()


def test_scan_populates_attestation(tmp_path):
    # 스캔 후 /api/attestation: jsonl 증거 취득 → acquired_count>0, all_read_only True.
    # acquired_hashes/stat_only는 /api/artifacts엔 노출되지 않아야(Issue-1, payload 분리).
    import json, threading, urllib.request
    from http.server import ThreadingHTTPServer
    from clfx.web.server import make_handler, ServerState
    from clfx.query.engine import QueryEngine
    import os as _os
    # 자기완결 fixture root(.claude/history.jsonl + transcript) — 콘텐츠 취득(jsonl) 보장.
    root = tmp_path / ".claude"; (root / "projects" / "p").mkdir(parents=True)
    (root / "history.jsonl").write_text(
        json.dumps({"display": "hi", "timestamp": "2026-06-15T01:00:00Z", "project": "p"}) + "\n",
        encoding="utf-8")
    (root / "projects" / "p" / "t.jsonl").write_text(
        json.dumps({"type": "user", "timestamp": "2026-06-15T01:00:00Z", "sessionId": "s",
                    "message": {"content": [{"type": "text", "text": "hello world"}]}}) + "\n",
        encoding="utf-8")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ServerState(QueryEngine([]))))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        body = json.dumps({"roots": [str(root)]}).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/scan", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            assert r.status == 200
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/attestation") as r:
            att = json.loads(r.read().decode("utf-8"))
        assert att["acquired_count"] > 0
        assert att["all_read_only"] is True
        assert att["write_delete_rename_ops"] == 0
        assert set(att["modes_seen"]).issubset({"r", "rb"})
        # jsonl 증거파일이 acquired에 들어감(sha 64-hex).
        paths = [a["path"] for a in att["acquired"]]
        assert paths == sorted(paths)
        import re as _re
        assert all(_re.fullmatch(r"[0-9a-f]{64}", a["sha256"]) for a in att["acquired"])
        # Issue-1: acquired_hashes/stat_only는 /api/artifacts엔 안 실림.
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/artifacts") as r:
            art = json.loads(r.read().decode("utf-8"))
        assert "acquired_hashes" not in art
        assert "stat_only" not in art
    finally:
        httpd.shutdown()


def test_load_engine_uses_ro_open(tmp_path, monkeypatch):
    # load_engine open이 roio._ro_open("r")를 경유 — 읽기전용 강제 + audit 기록.
    import json
    from clfx import roio
    from clfx.web import server as srv
    p = tmp_path / "analyzed.jsonl"
    ev = {"ts": "2026-06-15T01:00:00Z", "agent": "claude", "session": "s",
          "actor": "user", "action": "prompt", "target": "", "preview": "hi",
          "source": {"file": "h", "line": 1}, "tags": []}
    p.write_text(json.dumps(ev) + "\n", encoding="utf-8")
    roio.reset_audit()
    eng = srv.load_engine(str(p))
    assert len(eng.events) == 1
    recs = roio.audit_records()
    assert any(r["path"] == str(p) and r["mode"] == "r" for r in recs)


def test_api_mcp_route_returns_contract():
    # GET /api/mcp 는 200 + 빈 계약(스캔 전). server.py 라우트 배선 증명.
    import json, threading
    import urllib.request, urllib.error
    from http.server import ThreadingHTTPServer
    from clfx.web.server import make_handler, ServerState
    from clfx.query.engine import QueryEngine
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ServerState(QueryEngine([]))))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/mcp")
        with urllib.request.urlopen(req) as r:
            code, body = r.status, r.read().decode("utf-8")
        assert code == 200
        assert json.loads(body) == _MCP_EMPTY
    finally:
        httpd.shutdown()
