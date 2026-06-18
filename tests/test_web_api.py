from clfx.event import Event, Source
from clfx.query.engine import QueryEngine
from clfx.web.api import (events_payload, query_payload, stats_payload,
                          activity_payload, files_payload, keywords_payload)


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
    tss = [e["ts"] for e in p["events"]]
    assert tss == sorted(tss)
    first = p["events"][0]
    assert first["source"] == {"file": "h.jsonl", "line": 7}
    assert "‹secret›" in first["preview"]


def test_stats_payload_counts():
    s = stats_payload(_engine())
    assert s == {"total": 3, "user": 1, "agent": 2, "bypass": 0}


def test_query_payload_who_read_env(monkeypatch):
    import clfx.web.api as api
    monkeypatch.setattr(api, "make_llm", lambda *a, **k: None)   # ollama 비의존(결정적)
    p = api.query_payload(_engine(), "누가 .env 읽었어?")
    assert p["op"] == "who_did"
    assert p["intent"]["action"] == "read"
    assert all(e["action"] == "read" for e in p["events"])
    assert p["count"] == len(p["events"])


def test_query_origin_filter(monkeypatch):
    # 체크된 플랫폼(origin)만 답변 근거. 파싱은 전량, 답변 범위만 좁힘(무손실).
    import clfx.web.api as api
    monkeypatch.setattr(api, "make_llm", lambda *a, **k: None)
    eng = QueryEngine([
        Event("2026-06-15T01:00:00Z", "claude", "s", "user", "prompt", "", "win쪽 일",
              Source("h", 1), ["origin:windows"]),
        Event("2026-06-15T02:00:00Z", "claude", "s", "agent", "read", "f", "wsl쪽",
              Source("h", 2), ["origin:wsl"]),
    ])
    p = api.query_payload(eng, "6/15 요약", origins={"windows"})
    assert p["op"] == "on_date" and p["count"] == 1
    assert all("origin:windows" in e["tags"] for e in p["events"])
    p2 = api.query_payload(eng, "6/15 요약", origins=None)   # 전체
    assert p2["count"] == 2


def test_query_payload_secrets(monkeypatch):
    import clfx.web.api as api
    monkeypatch.setattr(api, "make_llm", lambda *a, **k: None)   # ollama 비의존(결정적)
    p = api.query_payload(_engine(), "유출된 비밀 뭐야?")
    assert p["op"] == "secrets"
    assert p["count"] == 2
    assert all("secret" in e["tags"] or "pii" in e["tags"] for e in p["events"])


def test_query_payload_timeline_and_summary(monkeypatch):
    # make_llm을 None으로 패치 → summarize digest 강제. ollama 떠있는 머신서도 결정적(mode 고정).
    import clfx.web.api as api
    monkeypatch.setattr(api, "make_llm", lambda *a, **k: None)
    p = query_payload(_engine(), "타임라인 요약해줘")
    assert p["op"] == "timeline"
    assert p["count"] == 3
    assert p["summary"] is not None and p["summary"]["mode"] == "digest"
    assert len(p["summary"]["citations"]) == 3


def test_query_payload_always_answers(monkeypatch):
    import clfx.web.api as api
    monkeypatch.setattr(api, "make_llm", lambda *a, **k: None)   # I4: ollama 떠도 결정적(digest)
    p = api.query_payload(_engine(), "누가 id_rsa 읽었어?")
    assert p["op"] == "who_did"
    assert p["summary"] is not None and p["summary"]["mode"] == "digest" and p["summary"]["text"]
    assert p["intent"]["target"] == "id_rsa"


def test_query_payload_llm_none_skips_make_llm(monkeypatch):
    # llm=None 주입(CLI 경로) → make_llm 호출조차 안 함(ollama/네트워크 무관). 호출되면 터짐.
    import clfx.web.api as api
    def boom(*a, **k): raise AssertionError("make_llm 호출되면 안 됨")
    monkeypatch.setattr(api, "make_llm", boom)
    p = api.query_payload(_engine(), "누가 id_rsa 읽었어?", llm=None)
    assert p["op"] == "who_did" and p["summary"]["mode"] == "digest"


def test_query_payload_cli_summary_uses_make_llm(monkeypatch):
    # CLI 요약 intent → answer(make_llm). ollama 비의존 위해 make_llm→None 패치 → digest.
    import clfx.web.api as api
    monkeypatch.setattr(api, "make_llm", lambda *a, **k: None)
    p = api.query_payload(_engine(), "타임라인 요약해줘", answer_only_summary=True)
    assert p["intent"]["summarize"] is True
    assert p["summary"] is not None and p["summary"]["mode"] == "digest"


def test_query_payload_cli_nonsummary_skips_llm(monkeypatch):
    # CLI 비요약 질의 → LLM 호출 금지(make_llm 미호출) + summary None.
    import clfx.web.api as api
    def boom(*a, **k): raise AssertionError("비요약 CLI는 make_llm 호출 금지")
    monkeypatch.setattr(api, "make_llm", boom)
    p = api.query_payload(_engine(), "누가 id_rsa 읽었어?", answer_only_summary=True)
    assert p["op"] == "who_did" and p["summary"] is None


def test_query_payload_vague_question_gives_overview(monkeypatch):
    # 막연한 대화형 질문(특정 키워드 매칭 0건) → empty 아닌 전체 행위 개요(결정적 집계).
    import clfx.web.api as api
    monkeypatch.setattr(api, "make_llm", lambda *a, **k: None)   # ollama 비의존 → digest
    p = api.query_payload(_engine(), "이 사람 주로 뭐해?")
    assert p["op"] == "search" and p["count"] == 0               # 리터럴 검색은 0건
    assert p["summary"]["mode"] == "digest"                      # empty 아님 — 개요로 답
    assert "전체 행위 개요" in p["summary"]["text"]
    assert p["summary"]["citations"]                             # top files 근거


def test_query_payload_actor_filter(monkeypatch):
    # §3: "사용자" 질의 → on_date actor=user → 결과 전부 user. ollama 무관 결정적.
    import clfx.web.api as api
    monkeypatch.setattr(api, "make_llm", lambda *a, **k: None)
    p = query_payload(_engine(), "2026-06-11 사용자 요약")
    assert p["actor"] == "user"
    assert p["count"] >= 1 and all(e["actor"] == "user" for e in p["events"])


def test_query_payload_secrets_actor_filter(monkeypatch):
    # secrets op도 actor 필터(파일/사용자 secret만). _engine: user paste .env(secret) + agent read id_rsa(secret).
    import clfx.web.api as api
    monkeypatch.setattr(api, "make_llm", lambda *a, **k: None)
    p = query_payload(_engine(), "사용자 secret 요약")
    assert p["op"] == "secrets" and p["actor"] == "user"
    assert p["count"] >= 1 and all(e["actor"] == "user" for e in p["events"])


def test_query_payload_bypass(monkeypatch):
    # [B1] "bypass 모드로 읽은 파일?" → bypass op, bypass-mode 이벤트 매칭(>0). llm=None=digest.
    import clfx.web.api as api
    eng = QueryEngine([
        Event("2026-06-11T01:00:00Z", "claude", "s", "agent", "read", "/x/.env", "x", Source("f", 1), ["bypass-mode"]),
        Event("2026-06-11T02:00:00Z", "claude", "s", "user", "prompt", "", "y", Source("f", 2), []),
    ])
    p = api.query_payload(eng, "bypass 모드로 읽은 파일?", llm=None)
    assert p["op"] == "bypass"
    assert p["count"] > 0
    assert all("bypass-mode" in e["tags"] for e in p["events"])


def test_mcp_payload_has_contract_keys():
    from clfx.web.api import scan_to_engine, mcp_payload
    eng = scan_to_engine(["tests/fixtures/mcp"])
    out = mcp_payload(eng, ["tests/fixtures/mcp"])
    for k in ("configs", "usage", "configured_unused", "used_unconfigured", "errors"):
        assert k in out
    # 픽스처 transcript의 mcp__ 호출이 usage로 잡힘
    servers = {u["server"] for u in out["usage"]}
    assert "playwright" in servers


def test_forensic_scan_includes_retention():
    from clfx.web.api import forensic_scan
    out = forensic_scan([], roots=[], tmp_dirs=[])   # tmp_dirs=[] → 실제 머신 tmp 스캔 안 함(결정성)
    assert "retention" in out
    assert out["retention"] == []


def test_forensic_scan_includes_tmp_hash_index():
    # [#2b] forensic_scan 결과에 tmp_hash_index 키 보존(빈 입력 tmp_dirs=[]서 {}).
    from clfx.web.api import forensic_scan
    out = forensic_scan([], roots=[], tmp_dirs=[])
    assert "tmp_hash_index" in out
    assert out["tmp_hash_index"] == {}


# ── OPT-1: forensic_scan이 공유 인벤토리/해석을 1회만 만들어 위임(무손실 동치) ──
def test_forensic_scan_includes_tmp_inventory(tmp_path, monkeypatch):
    # OPT-1: forensic_scan 결과에 tmp_inventory(list of {path,size,mtime}) 추가 — server lazy 검색용.
    import os
    monkeypatch.setattr(os, "name", "posix")
    from clfx.web.api import forensic_scan
    from clfx.analyze import artifacts as A
    tdir = tmp_path / "tmp"; tdir.mkdir()
    (tdir / "a").write_bytes(b"hello")
    (tdir / "b").write_bytes(b"xy")
    out = forensic_scan([], roots=[], tmp_dirs=[str(tdir)])
    assert "tmp_inventory" in out
    inv = A.build_tmp_inventory([str(tdir)])
    assert out["tmp_inventory"] == inv["files"]


def test_forensic_scan_lossless_with_shared_caches(tmp_path, monkeypatch):
    # OPT-1 무손실: 공유 인벤토리/해석을 거친 forensic_scan 결과가 직접 호출 레퍼런스와 동일.
    import os
    monkeypatch.setattr(os, "name", "posix")
    from clfx.web.api import forensic_scan
    from clfx.analyze import artifacts as A
    from clfx.event import Event, Source
    proj = tmp_path / "proj"; tdir = tmp_path / "tmp"
    proj.mkdir(); tdir.mkdir()
    (proj / "orig.env").write_bytes(b"SECRET=1\n")
    (tdir / "leaked.env").write_bytes(b"SECRET=1\n")
    root = str(tmp_path)
    evs = [(Event("2026-06-16T01:00:00Z", "claude", "s", "user", "paste",
                  str(proj / "orig.env"), "‹secret›", Source("h", 1), ["secret"]), root)]
    out = forensic_scan(evs, roots=[root], tmp_dirs=[str(tdir)])
    # 레퍼런스: 옛 방식대로 개별 호출(공유 캐시 없이).
    ref_hc = A.hash_clusters(evs, roots=[root], tmp_dirs=[str(tdir)])
    ref_attr = A.attribution_join(evs)
    ref_ret = A.tmp_retention([str(tdir)])
    assert out["hashes"] == ref_hc["hashes"]
    assert out["attribution"] == ref_attr
    assert out["retention"] == ref_ret["retention"]
    assert out["tmp_scanned"] == ref_hc["tmp_scanned"]
    assert out["missing"] == ref_hc["missing"]
    assert out["hashed"] == ref_hc["hashed"]
    assert out["stat_verified"] == ref_hc["stat_verified"]
    assert out["content_unread"] == ref_hc["content_unread"]


def test_forensic_scan_staged_progress(tmp_path, monkeypatch):
    # OPT-7: forensic_scan은 on_progress(stage, done, total)로 단계 진행을 보고.
    import os
    monkeypatch.setattr(os, "name", "posix")
    from clfx.web.api import forensic_scan
    from clfx.event import Event, Source
    proj = tmp_path / "proj"; tdir = tmp_path / "tmp"
    proj.mkdir(); tdir.mkdir()
    (proj / "orig.env").write_bytes(b"SECRET=1\n")
    (tdir / "leaked.env").write_bytes(b"SECRET=1\n")
    root = str(tmp_path)
    evs = [(Event("2026-06-16T01:00:00Z", "claude", "s", "user", "paste",
                  str(proj / "orig.env"), "‹secret›", Source("h", 1), ["secret"]), root)]
    seen = []
    forensic_scan(evs, roots=[root], tmp_dirs=[str(tdir)],
                  on_progress=lambda stage, done, total: seen.append((stage, done, total)))
    stages = [s for s, _d, _t in seen]
    # 순서대로 walk-tmp, resolve, hash, attribution, retention 단계가 보고됨.
    for st in ("walk-tmp", "resolve", "hash", "attribution", "retention"):
        assert st in stages
    assert stages.index("walk-tmp") < stages.index("resolve") < stages.index("hash")
    assert stages.index("hash") < stages.index("attribution") < stages.index("retention")
    # hash 단계는 N/M 진행을 보고(dup 2개).
    hash_evts = [(d, t) for s, d, t in seen if s == "hash"]
    assert any(t == 2 for _d, t in hash_evts)
    assert hash_evts[-1][0] == hash_evts[-1][1]


def test_mcp_payload_staged_progress(monkeypatch):
    # OPT-7: mcp_payload는 on_progress로 mcp 단계를 보고.
    from clfx.web.api import scan_to_engine, mcp_payload
    eng = scan_to_engine(["tests/fixtures/mcp"])
    seen = []
    mcp_payload(eng, ["tests/fixtures/mcp"],
                on_progress=lambda stage, done, total: seen.append((stage, done, total)))
    assert any(s == "mcp" for s, _d, _t in seen)


# ── OPT-8: 캐시된 events 바이트(재인코딩 회피, 바이트 동일) ──────────
def test_events_payload_bytes_matches_json(monkeypatch):
    import json
    from clfx.web.api import events_payload, events_payload_bytes
    eng = _engine()
    body = events_payload_bytes(eng)
    assert isinstance(body, (bytes, bytearray))
    # 바이트는 events_payload를 같은 방식으로 직렬화한 것과 동일.
    assert body == json.dumps(events_payload(eng), ensure_ascii=False).encode("utf-8")


def test_events_payload_bytes_memoized():
    from clfx.web.api import events_payload_bytes
    eng = _engine()
    b1 = events_payload_bytes(eng)
    b2 = events_payload_bytes(eng)
    assert b1 is b2            # 메모이즈 — 재인코딩 안 함(같은 객체)


# ── source(origin) 토글: BACKEND 집계 스코핑 (api.py stats/activity/files/keywords) ──
# 단일 진실원천=엔진/API. JS 재집계 금지 — origins 셋만 넘기고 백엔드가 좁혀 재계산.
def _origin_engine():
    """두 origin(wsl/windows)에 걸친 이벤트. 대화(prompt/response)·파일(read/write)·bypass 혼합.
    windows-only 파일 target(win_only.txt)·wsl-only 파일(wsl_only.txt)로 파일 스코핑 검증."""
    def ev(ts, actor, action, target, preview, origin, extra=None, line=1):
        tags = [f"origin:{origin}"] + (extra or [])
        return Event(ts=ts, agent="claude", session="s-" + origin, actor=actor,
                     action=action, target=target, preview=preview,
                     source=Source("h.jsonl", line), tags=tags)
    return QueryEngine([
        ev("2026-06-15T01:00:00Z", "user", "prompt", "", "유출 토큰 password 확인", "wsl", line=1),
        ev("2026-06-15T02:00:00Z", "agent", "read", "wsl_only.txt", "내용", "wsl", line=2),
        ev("2026-06-15T03:00:00Z", "agent", "response", "", "유출 토큰 password 검토", "wsl", line=3),
        ev("2026-06-16T01:00:00Z", "user", "prompt", "", "윈도우 secret 해킹 흔적", "windows", ["bypass-mode"], line=4),
        ev("2026-06-16T02:00:00Z", "agent", "write", "win_only.txt", "기록", "windows", line=5),
        ev("2026-06-16T03:00:00Z", "agent", "response", "", "윈도우 secret 해킹 검토", "windows", line=6),
    ])


def _all_events_engine():
    """_origin_engine과 동일한 이벤트지만, origin 스코핑 레퍼런스용으로 그대로 재사용."""
    return _origin_engine()


# (a) REGRESSION: origins=None == 무인자 == 전체 이벤트 위 계산(바이트 동일).
def test_stats_regression_none_equals_default_and_all():
    eng = _origin_engine()
    base = stats_payload(eng)
    assert stats_payload(eng, origins=None) == base
    # 전체 6건: user 2, agent 4, bypass 1
    assert base == {"total": 6, "user": 2, "agent": 4, "bypass": 1}


def test_files_regression_none_equals_default():
    eng = _origin_engine()
    assert files_payload(eng, origins=None) == files_payload(eng)
    # 전체 파일 2개(wsl_only.txt, win_only.txt)
    targets = {r["target"] for r in files_payload(eng)["files"]}
    assert targets == {"wsl_only.txt", "win_only.txt"}


def test_activity_regression_none_equals_default():
    eng = _origin_engine()
    assert activity_payload(eng, by="day", origins=None) == activity_payload(eng, by="day")
    assert activity_payload(eng, by="month", origins=None) == activity_payload(eng, by="month")


def test_keywords_regression_none_equals_default():
    eng = _origin_engine()
    assert keywords_payload(eng, origins=None) == keywords_payload(eng)


# (a') REGRESSION (memo key identity): origins=None uses CURRENT key — same cached object as no-arg.
def test_none_uses_unchanged_memo_key():
    eng = _origin_engine()
    s1 = stats_payload(eng)
    s2 = stats_payload(eng, origins=None)
    assert s1 is s2                       # 동일 캐시 키("stats") → 같은 객체
    k1 = keywords_payload(eng)
    k2 = keywords_payload(eng, origins=None)
    assert k1 is k2                       # 동일 캐시 키("keywords")


# (b) SCOPING: origins={"wsl"} → wsl 이벤트만 집계.
def test_stats_scoped_to_wsl():
    eng = _origin_engine()
    s = stats_payload(eng, origins={"wsl"})
    # wsl 3건: user 1(prompt), agent 2(read+response), bypass 0
    assert s == {"total": 3, "user": 1, "agent": 2, "bypass": 0}


def test_stats_scoped_to_windows():
    eng = _origin_engine()
    s = stats_payload(eng, origins={"windows"})
    # windows 3건: user 1(prompt+bypass), agent 2(write+response), bypass 1
    assert s == {"total": 3, "user": 1, "agent": 2, "bypass": 1}


def test_files_scoped_excludes_other_origin_target():
    eng = _origin_engine()
    wsl = files_payload(eng, origins={"wsl"})
    targets = {r["target"] for r in wsl["files"]}
    assert targets == {"wsl_only.txt"}            # windows-only 파일 제외
    win = files_payload(eng, origins={"windows"})
    assert {r["target"] for r in win["files"]} == {"win_only.txt"}


def test_activity_scoped_to_wsl():
    eng = _origin_engine()
    a = activity_payload(eng, by="day", origins={"wsl"})
    # wsl은 2026-06-15만(3건). windows의 06-16 버킷은 없어야.
    buckets = {r["bucket"]: r for r in a["rows"]}
    assert set(buckets) == {"2026-06-15"}
    assert buckets["2026-06-15"]["total"] == 3


def test_keywords_scoped_to_windows():
    eng = _origin_engine()
    kw = keywords_payload(eng, origins={"windows"})
    terms = {k["term"] for k in kw["keywords"]}
    # windows 대화에만 등장: "윈도우", "secret", "해킹". wsl-only "password"/"유출" 없어야.
    assert "해킹" in terms
    assert "password" not in terms and "유출" not in terms


# (c) FULL-SET == NONE: 완전 태깅 데이터에서 모든 origin 셋 == None.
def test_stats_full_set_equals_none():
    eng = _origin_engine()
    assert stats_payload(eng, origins={"wsl", "windows"}) == stats_payload(eng, origins=None)


def test_files_full_set_equals_none():
    eng = _origin_engine()
    assert files_payload(eng, origins={"wsl", "windows"}) == files_payload(eng, origins=None)


def test_activity_full_set_equals_none():
    eng = _origin_engine()
    assert (activity_payload(eng, by="day", origins={"wsl", "windows"})
            == activity_payload(eng, by="day", origins=None))


def test_keywords_full_set_equals_none():
    eng = _origin_engine()
    assert (keywords_payload(eng, origins={"wsl", "windows"})
            == keywords_payload(eng, origins=None))


# (d) DETERMINISM: 스코핑된 payload 두 번 호출 → 동일(메모이즈).
def test_scoped_payload_memoized_identical():
    eng = _origin_engine()
    s1 = stats_payload(eng, origins={"wsl"})
    s2 = stats_payload(eng, origins={"wsl"})
    assert s1 is s2                       # 같은 캐시 키 → 같은 객체
    f1 = files_payload(eng, origins={"wsl"})
    f2 = files_payload(eng, origins={"wsl"})
    assert f1 is f2
    a1 = activity_payload(eng, by="day", origins={"wsl"})
    a2 = activity_payload(eng, by="day", origins={"wsl"})
    assert a1 is a2
    k1 = keywords_payload(eng, origins={"wsl"})
    k2 = keywords_payload(eng, origins={"wsl"})
    assert k1 is k2


def test_scoped_set_order_independent_key():
    # 정렬-조인 키 → {"wsl","windows"}와 동일 셋 재호출은 같은 캐시(순서 무관 결정적).
    eng = _origin_engine()
    s1 = stats_payload(eng, origins={"wsl", "windows"})
    s2 = stats_payload(eng, origins={"windows", "wsl"})
    assert s1 is s2


# (e) MEMO KEY SEPARATION: wsl / windows / None 키가 충돌 없이 분리·값 상이.
def test_memo_key_separation_no_collision():
    eng = _origin_engine()
    wsl = stats_payload(eng, origins={"wsl"})
    win = stats_payload(eng, origins={"windows"})
    full = stats_payload(eng)            # None — 키 "stats"
    # 캐시에 구분된 키 3개 존재.
    assert "stats" in eng._cache
    assert "stats:wsl" in eng._cache
    assert "stats:windows" in eng._cache
    # 값은 적절히 상이(스코핑 vs 전체).
    assert wsl != full and win != full
    assert wsl["total"] == 3 and win["total"] == 3 and full["total"] == 6
    # wsl/windows는 bypass에서 갈림(충돌 없음 증명).
    assert wsl["bypass"] == 0 and win["bypass"] == 1


def test_origins_key_helper():
    from clfx.web.api import _origins_key
    assert _origins_key(None) == "all"
    assert _origins_key(set()) == "all"
    assert _origins_key({"wsl"}) == "wsl"
    assert _origins_key({"windows", "wsl"}) == "windows,wsl"   # sorted-joined


def test_empty_set_treated_as_full():
    # origins=빈셋 == None(전체). 무손실.
    eng = _origin_engine()
    assert stats_payload(eng, origins=set()) == stats_payload(eng, origins=None)
    assert files_payload(eng, origins=set()) == files_payload(eng, origins=None)
