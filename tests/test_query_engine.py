from datetime import datetime, timezone
from clfx.sources.claude import ClaudeSource
from clfx.parser import parse_source
from clfx.analyze.attribution import enrich
from clfx.query.engine import QueryEngine
from clfx.event import Event, Source

def _engine(root):
    evs = enrich(list(parse_source(ClaudeSource(root))), ClaudeSource(root))
    return QueryEngine(evs)

def test_who_did_read_env_is_agent(built_root):
    res = _engine(built_root).who_did("read", ".env")
    assert res and all(e.actor == "agent" for e in res)
    assert all(e.source.file and e.source.line >= 1 for e in res)   # 인용 실재

def test_secrets_lists_tagged_events(built_root):
    res = _engine(built_root).secrets()
    assert res and all("secret" in e.tags for e in res)

def test_search_keyword(built_root):
    assert _engine(built_root).search("config.py")

def test_on_date_filters(built_root):
    res = _engine(built_root).on_date("2026-06-11")
    assert res and all((e.ts or "").startswith("2026-06-11") for e in res)

def test_timeline_sorted(built_root):
    tl = _engine(built_root).timeline()
    ts = [e.ts for e in tl if e.ts]
    assert ts == sorted(ts)

def _ev(ts): return Event(ts, "claude", "s", "agent", "read", "/x", "", Source("f", 1))

def test_timeline_range_mixed_epoch_ms_no_crash():
    # raw epoch-ms int Event + str start/end range → 옛 (e.ts or "") >= start는 TypeError.
    # ts_key가 양쪽 datetime 통일 → 크래시 없음 + 경계 정확.
    mid = int(datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    before = int(datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    after = int(datetime(2026, 6, 12, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    eng = QueryEngine([_ev(before), _ev(mid), _ev(after), _ev("2026-06-11T18:00:00Z")])
    out = [e.ts for e in eng.timeline(start="2026-06-11", end="2026-06-12")]  # 6/11 하루
    assert out == [mid, "2026-06-11T18:00:00Z"]   # before/after 제외, 연대순


def _aev(actor, action, ts, target="x", preview=""):
    return Event(ts, "claude", "s", actor, action, target, preview, Source("f", 1))


def test_on_date_actor_filter():
    eng = QueryEngine([_aev("user", "paste", "2026-06-11T01:00:00Z"),
                       _aev("agent", "read", "2026-06-11T02:00:00Z")])
    assert [e.actor for e in eng.on_date("2026-06-11", actor="user")] == ["user"]
    assert [e.actor for e in eng.on_date("2026-06-11", actor="agent")] == ["agent"]
    assert len(eng.on_date("2026-06-11")) == 2          # actor=None=전체(기존 보존)


def test_who_did_actor_filter():
    eng = QueryEngine([_aev("user", "read", "2026-06-11T01:00:00Z", "a.py"),
                       _aev("agent", "read", "2026-06-11T02:00:00Z", "a.py")])
    r = eng.who_did("read", "a.py", actor="agent")
    assert len(r) == 1 and r[0].actor == "agent"
    assert len(eng.who_did("read", "a.py")) == 2        # None=전체


def test_search_actor_filter():
    eng = QueryEngine([_aev("user", "prompt", "2026-06-11T01:00:00Z", "x", "find me"),
                       _aev("agent", "response", "2026-06-11T02:00:00Z", "x", "find me")])
    r = eng.search("find", actor="user")
    assert len(r) == 1 and r[0].actor == "user"


def test_timeline_actor_filter():
    eng = QueryEngine([_aev("user", "paste", "2026-06-11T01:00:00Z"),
                       _aev("agent", "read", "2026-06-11T02:00:00Z")])
    assert [e.actor for e in eng.timeline(actor="agent")] == ["agent"]
    assert len(eng.timeline()) == 2                     # None=전체


def test_secrets_actor_filter():
    eng = QueryEngine([
        Event("2026-06-11T01:00:00Z", "claude", "s", "user", "paste", ".env", "x", Source("f", 1), ["secret"]),
        Event("2026-06-11T02:00:00Z", "claude", "s", "agent", "read", ".env", "x", Source("f", 2), ["secret"]),
    ])
    assert [e.actor for e in eng.secrets(actor="user")] == ["user"]
    assert len(eng.secrets()) == 2                      # None=전체


def test_on_date_handles_epoch_ms_no_crash():
    # raw epoch-ms int ts → 옛 e.ts.startswith는 AttributeError. norm_ts로 ISO Z 통일 후 startswith.
    mid = int(datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    other = int(datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    eng = QueryEngine([_ev(mid), _ev(other), _ev("2026-06-11T18:00:00Z")])
    out = [e.ts for e in eng.on_date("2026-06-11")]   # crash 없어야
    assert out == [mid, "2026-06-11T18:00:00Z"]        # 6/11만, 7/1 제외
