from clfx.query.engine import QueryEngine
from clfx.analyze.timeline import timeline as _sort
from clfx.event import Event, Source


def _evs():
    # ts 뒤섞은 입력순서(정렬 안 됨) → raw순서 보존·정렬뷰 검증용.
    def ev(ts, actor, action, target):
        return Event(ts, "claude", "s", actor, action, target, "", Source("h.jsonl", 1), [])
    return [
        ev("2026-06-12T03:00:00Z", "agent", "read", "b.py"),
        ev("2026-06-11T01:00:00Z", "user", "paste", ".env"),
        ev("2026-06-11T02:00:00Z", "agent", "read", ".env"),
    ]


def test_timeline_cached_same_object():
    eng = QueryEngine(_evs())
    a = eng.timeline(); b = eng.timeline()
    assert a is b                              # 1회 정렬·재사용


def test_timeline_result_unchanged_vs_uncached():
    evs = _evs()
    eng = QueryEngine(evs)
    assert [e.ts for e in eng.timeline()] == [e.ts for e in _sort(list(evs))]   # 캐시가 결과 안 바꿈


def test_raw_order_preserved_for_search():
    # self.events 정렬 금지 확인 — search/who_did 등은 raw 입력순서(I2)
    evs = _evs()
    eng = QueryEngine(evs)
    assert eng.events == list(evs)             # 입력순서 그대로(in-place 정렬 안 함)
    assert eng.timeline() != eng.events        # 정렬뷰는 별개(입력순≠정렬순)


def test_activity_files_cached_and_equal():
    eng = QueryEngine(_evs())
    assert eng.activity("day") is eng.activity("day")
    assert eng.files() is eng.files()
    # 값 정확성: 캐시본 == 새 엔진 1회 계산본
    eng2 = QueryEngine(_evs())
    assert eng.activity("day") == eng2.activity("day")
    assert eng.files() == eng2.files()


def test_activity_bad_by_normalized():
    eng = QueryEngine(_evs())
    assert eng.activity("garbage") is eng.activity("day")   # 잘못된 by → day로 정규화(캐시 키 공유)


def test_fresh_engine_independent_cache():
    # 재스캔 시 옛 집계 carryover 금지(무결성)
    e1 = QueryEngine(_evs()); _ = e1.files()
    e2 = QueryEngine([])                       # 빈 스캔
    assert e2.files() == []                     # e1 캐시와 무관
    assert e2.timeline() == []
