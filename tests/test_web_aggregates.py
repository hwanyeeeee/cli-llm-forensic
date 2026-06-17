from clfx.event import Event, Source
from clfx.query.engine import QueryEngine
from clfx.web.api import activity_payload, files_payload, keywords_payload, events_payload


def _ev(actor, action, ts, target="x", preview=""):
    return Event(ts=ts, agent="claude", session="s", actor=actor, action=action,
                 target=target, preview=preview, source=Source("h.jsonl", 1), tags=[])


def _eng():
    return QueryEngine([
        _ev("user", "paste", "2026-06-11T01:00:00.000Z", ".env", "비밀번호 유출"),
        _ev("agent", "read", "2026-06-11T02:00:00.000Z", ".env", "점검"),
    ])


def test_activity_payload():
    p = activity_payload(_eng(), by="month")
    assert p["by"] == "month"
    assert p["rows"][0]["bucket"] == "2026-06"
    assert p["rows"][0]["user"] == 1 and p["rows"][0]["agent"] == 1


def test_files_payload():
    p = files_payload(_eng())
    assert p["files"][0]["target"] == ".env" and p["files"][0]["count"] == 2


def test_keywords_payload():
    p = keywords_payload(_eng())
    terms = {k["term"] for k in p["keywords"]}
    assert "비밀번호" in terms
    assert any(k["investigative"] for k in p["keywords"])


def test_payloads_mixed_ts_fixture(mixed_engine):
    # 공용 mixed-ts 픽스처 → 전 payload crash 없음 + events ts 전부 str/None(경계 정규화).
    ep = events_payload(mixed_engine)
    assert all(isinstance(e["ts"], str) or e["ts"] is None for e in ep["events"])
    assert activity_payload(mixed_engine, by="month")["rows"]      # crash 없음
    assert files_payload(mixed_engine)["files"]
    assert keywords_payload(mixed_engine)["keywords"]


def test_events_payload_normalizes_epoch_ms_ts():
    # I1: analyzed.jsonl에 epoch-ms int ts 섞여도 events_payload는 항상 ISO str(또는 None) → JS slice 안전.
    eng = QueryEngine([
        _ev("user", "paste", 1770555950996, ".env"),         # epoch-ms int
        _ev("agent", "read", "2026-06-11T02:00:00.000Z", ".env"),
        _ev("user", "prompt", None),                         # None 유지
    ])
    p = events_payload(eng)
    assert all(isinstance(e["ts"], str) or e["ts"] is None for e in p["events"])
    assert any(e["ts"] == "2026-02-08T13:05:50.996Z" for e in p["events"])   # epoch 환산
