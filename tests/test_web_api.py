from clfx.event import Event, Source
from clfx.query.engine import QueryEngine
from clfx.web.api import events_payload, query_payload


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


def test_query_payload_who_read_env():
    p = query_payload(_engine(), "누가 .env 읽었어?")
    assert p["op"] == "who_did"
    assert p["intent"]["action"] == "read"
    assert all(e["action"] == "read" for e in p["events"])
    assert p["count"] == len(p["events"])


def test_query_payload_secrets():
    p = query_payload(_engine(), "유출된 비밀 뭐야?")
    assert p["op"] == "secrets"
    assert p["count"] == 2
    assert all("secret" in e["tags"] or "pii" in e["tags"] for e in p["events"])


def test_query_payload_timeline_and_summary():
    p = query_payload(_engine(), "타임라인 요약해줘")
    assert p["op"] == "timeline"
    assert p["count"] == 3
    assert p["summary"] is not None and p["summary"]["mode"] == "digest"
    assert len(p["summary"]["citations"]) == 3


def test_query_payload_no_summary_when_not_requested():
    p = query_payload(_engine(), "누가 id_rsa 읽었어?")
    assert p["op"] == "who_did" and p["summary"] is None
    assert p["intent"]["target"] == "id_rsa"
