from clfx.event import Event, Source
from clfx.analyze.timeline import timeline

def _e(ts): return Event(ts,"claude","s","agent","read","/x","",Source("f",1))

def test_sorts_by_ts_ascending():
    evs = [_e("2026-06-11T03:00:00Z"), _e("2026-06-11T01:00:00Z"), _e(None)]
    out = timeline(evs)
    assert [e.ts for e in out] == [None, "2026-06-11T01:00:00Z", "2026-06-11T03:00:00Z"]
