from clfx.event import Event, Source
from clfx.query.engine import QueryEngine


def _ev(actor, action, ts, target="x"):
    return Event(ts=ts, agent="claude", session="s", actor=actor, action=action,
                 target=target, preview="", source=Source("h.jsonl", 1), tags=[])


def _eng():
    return QueryEngine([
        _ev("user", "paste", "2026-06-11T01:00:00.000Z"),
        _ev("agent", "read", "2026-06-11T02:00:00.000Z"),
        _ev("agent", "read", "2026-07-02T02:00:00.000Z"),
        _ev("user", "prompt", None),  # ts 없음 → unknown
    ])


def test_activity_by_day_actor_split():
    a = _eng().activity(by="day")
    # day 버킷별 actor 분리
    d = {row["bucket"]: row for row in a}
    assert d["2026-06-11"]["user"] == 1 and d["2026-06-11"]["agent"] == 1
    assert d["2026-07-02"]["agent"] == 1 and d["2026-07-02"]["user"] == 0
    assert d["unknown"]["user"] == 1


def test_activity_by_month():
    a = _eng().activity(by="month")
    d = {row["bucket"]: row for row in a}
    assert d["2026-06"]["user"] == 1 and d["2026-06"]["agent"] == 1
    assert d["2026-07"]["agent"] == 1
    # 버킷은 정렬됨(unknown 맨 뒤)
    buckets = [row["bucket"] for row in a]
    assert buckets == sorted([b for b in buckets if b != "unknown"]) + (["unknown"] if "unknown" in buckets else [])


def test_files_grouping_actor_split():
    eng = QueryEngine([
        _ev("user", "paste", "2026-06-11T01:00:00.000Z", target=".env"),
        _ev("agent", "read", "2026-06-11T02:00:00.000Z", target=".env"),
        _ev("agent", "read", "2026-06-11T03:00:00.000Z", target="app.py"),
    ])
    fs = {row["target"]: row for row in eng.files()}
    assert fs[".env"]["count"] == 2
    assert fs[".env"]["by_actor"] == {"user": 1, "agent": 1}
    assert fs[".env"]["actions"] == {"paste": 1, "read": 1}
    assert fs["app.py"]["by_actor"] == {"user": 0, "agent": 1}
    # 접근 많은 순 정렬
    assert eng.files()[0]["target"] == ".env"


def test_activity_files_mixed_ts_fixture(mixed_engine):
    # 공용 mixed-ts 픽스처(ISO+epoch-ms int+None) → activity/files 집계 crash 없음 + epoch 환산 버킷.
    a = {r["bucket"]: r for r in mixed_engine.activity(by="day")}
    assert "2026-02-08" in a and a["2026-02-08"]["user"] == 1   # epoch-ms → ISO 버킷
    assert "unknown" in a                                       # None ts
    assert mixed_engine.files()                                 # crash 없이 집계


def test_activity_handles_epoch_ms_ts_no_crash():
    # history발 epoch-ms int ts 섞임 → norm_ts 통일, (e.ts or "")[:n] 슬라이스 TypeError 안 남 + 버킷 정상.
    epoch = 1770555950996  # 2026-02-08T13:05:50.996Z
    eng = QueryEngine([_ev("user", "paste", epoch),
                       _ev("agent", "read", "2026-06-11T02:00:00.000Z")])
    d = {r["bucket"]: r for r in eng.activity(by="day")}
    assert d["2026-02-08"]["user"] == 1
    m = {r["bucket"]: r for r in eng.activity(by="month")}
    assert m["2026-02"]["user"] == 1 and m["2026-06"]["agent"] == 1
