from clfx.analyze.timeline import timeline as _sort


class QueryEngine:
    """결정적 질의. 모든 반환은 Event 리스트 — 각 Event가 source(file:line)를 보유한다.
    증거 주장은 전적으로 이 엔진이 담당(LLM 없이도 동작·안 흔들림)."""

    def __init__(self, events):
        self.events = list(events)

    def search(self, kw):
        kw = (kw or "").lower()
        return [e for e in self.events
                if kw in (e.target or "").lower() or kw in (e.preview or "").lower()]

    def on_date(self, day):
        return [e for e in self.events if (e.ts or "").startswith(day)]

    def who_did(self, action, target_substr=""):
        t = (target_substr or "").lower()
        return [e for e in self.events
                if e.action == action and t in (e.target or "").lower()]

    def secrets(self):
        return [e for e in self.events if "secret" in e.tags or "pii" in e.tags]

    def timeline(self, start=None, end=None):
        evs = self.events
        if start:
            evs = [e for e in evs if (e.ts or "") >= start]
        if end:
            evs = [e for e in evs if (e.ts or "") <= end]
        return _sort(evs)
