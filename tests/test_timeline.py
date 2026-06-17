from datetime import datetime, timezone
from clfx.event import Event, Source
from clfx.analyze.timeline import timeline

def _e(ts): return Event(ts,"claude","s","agent","read","/x","",Source("f",1))

def test_sorts_by_ts_ascending():
    evs = [_e("2026-06-11T03:00:00Z"), _e("2026-06-11T01:00:00Z"), _e(None)]
    out = timeline(evs)
    assert [e.ts for e in out] == [None, "2026-06-11T01:00:00Z", "2026-06-11T03:00:00Z"]

def test_sorts_mixed_ts_types_chronological():
    # int(epoch-ms)/str(ISO)/None 혼재: 크래시 없음 + 실제 연대순.
    # epoch-ms 1770555950996 == 2026-02-08T13:05:50.996Z → 6/11 ISO들보다 앞.
    # str(epoch-ms)="1770…"가 사전순으론 "2026…"보다 앞이라 단순 str 비교는 연대순 깨짐 → norm_ts 환산 필요.
    epoch = 1770555950996
    evs = [_e("2026-06-11T03:00:00Z"), _e(epoch), _e("2026-06-11T01:00:00Z"), _e(None)]
    out = [e.ts for e in timeline(evs)]    # TypeError 안 나야 함
    assert out == [None, epoch, "2026-06-11T01:00:00Z", "2026-06-11T03:00:00Z"]

def test_same_second_iso_no_ms_vs_epoch_chronological():
    # 같은 초: ISO 밀리초 없음("...00Z") vs epoch-ms(.500). epoch가 더 늦음.
    # 사전순이면 "."(0x2E)<"Z"(0x5A)라 epoch가 앞서 깨짐 → ts_key datetime 비교로 교정.
    iso = "2026-06-11T01:00:00Z"
    epoch = int(datetime(2026, 6, 11, 1, 0, 0, 500000, tzinfo=timezone.utc).timestamp() * 1000)
    out = [e.ts for e in timeline([_e(epoch), _e(iso)])]
    assert out == [iso, epoch]
