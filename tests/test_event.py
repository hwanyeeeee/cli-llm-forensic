import json
from clfx.event import Event, Source

def _ev(**kw):
    base = dict(ts="2026-06-11T01:00:00Z", agent="claude", session="s1",
               actor="agent", action="read", target="/x/.env",
               preview="STRIPE=...", source=Source("p.jsonl", 42))
    base.update(kw); return Event(**base)

def test_event_roundtrip_jsonl():
    ev = _ev(tags=["secret"])
    line = ev.to_json()
    assert json.loads(line)["source"] == {"file": "p.jsonl", "line": 42}
    back = Event.from_dict(json.loads(line))
    assert back == ev

def test_tags_default_empty():
    assert _ev().tags == []

def test_to_dict_has_all_schema_fields():
    d = _ev().to_dict()
    assert set(d) == {"ts","agent","session","actor","action","target","preview","tags","source"}
