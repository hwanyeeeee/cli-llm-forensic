from clfx.event import Event, Source
from clfx.analyze.timeline import timeline

def _e(ts): return Event(ts,"claude","s","agent","read","/x","",Source("f",1))

def test_sorts_by_ts_ascending():
    evs = [_e("2026-06-11T03:00:00Z"), _e("2026-06-11T01:00:00Z"), _e(None)]
    out = timeline(evs)
    assert [e.ts for e in out] == [None, "2026-06-11T01:00:00Z", "2026-06-11T03:00:00Z"]

def test_sorts_mixed_ts_types_no_crash():
    # int(epoch-ms)/str(ISO)/None 혼재여도 TypeError 없이 정렬 (None 우선)
    evs = [_e("2026-06-11T03:00:00Z"), _e(1770555950996), _e("2026-06-11T01:00:00Z"), _e(None)]
    out = timeline(evs)               # TypeError 안 나야 함
    assert out[0].ts is None
    assert len(out) == 4
