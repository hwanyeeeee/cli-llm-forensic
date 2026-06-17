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
