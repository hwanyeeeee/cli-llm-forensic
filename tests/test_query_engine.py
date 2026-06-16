from clfx.sources.claude import ClaudeSource
from clfx.parser import parse_source
from clfx.analyze.attribution import enrich
from clfx.query.engine import QueryEngine

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
