from collections import defaultdict

from clfx.analyze.timeline import timeline as _sort
from clfx.event import ts_key, norm_ts


class QueryEngine:
    """결정적 질의. 모든 반환은 Event 리스트 — 각 Event가 source(file:line)를 보유한다.
    증거 주장은 전적으로 이 엔진이 담당(LLM 없이도 동작·안 흔들림)."""

    def __init__(self, events):
        self.events = list(events)        # raw 입력순서 — I2 인용순서 보존(절대 in-place 정렬 금지)
        self._cache = {}                  # 무거운 집계 메모이즈(엔진 불변 → 무효화 불요; 새 스캔=새 엔진=새 캐시)

    def _memo(self, key, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    @property
    def sorted_events(self):
        """timeline 정렬을 1회만(events_payload 등 가장 흔한 경로). self.events(raw)는 불변."""
        return self._memo("sorted", lambda: _sort(self.events))

    def search(self, kw, actor=None):
        # actor=None=전체(기존 동작 보존). set이면 그 주체만(§3 actor 질의).
        kw = (kw or "").lower()
        return [e for e in self.events
                if (kw in (e.target or "").lower() or kw in (e.preview or "").lower())
                and (actor is None or e.actor == actor)]

    def on_date(self, day, actor=None):
        # norm_ts로 epoch-ms int도 ISO Z 문자열로 통일 → raw int.startswith AttributeError 차단.
        return [e for e in self.events
                if (norm_ts(e.ts) or "").startswith(day)
                and (actor is None or e.actor == actor)]

    def who_did(self, action, target_substr="", actor=None):
        t = (target_substr or "").lower()
        return [e for e in self.events
                if e.action == action and t in (e.target or "").lower()
                and (actor is None or e.actor == actor)]

    def secrets(self, actor=None):
        return [e for e in self.events
                if ("secret" in e.tags or "pii" in e.tags)
                and (actor is None or e.actor == actor)]

    def timeline(self, start=None, end=None, actor=None):
        # range 필터도 ts_key로 비교 — raw e.ts가 epoch-ms int면 str start/end와 비교 시
        # TypeError("'>=' not supported between int and str"). ts_key가 양쪽을 datetime으로 통일.
        if start is None and end is None and actor is None:
            return self.sorted_events          # 캐시(events_payload 초기 로드 — 가장 흔한 경로)
        evs = self.events
        if start:
            s = ts_key(start)
            evs = [e for e in evs if ts_key(e.ts) >= s]
        if end:
            en = ts_key(end)
            evs = [e for e in evs if ts_key(e.ts) <= en]
        if actor:
            evs = [e for e in evs if e.actor == actor]
        return _sort(evs)

    def activity(self, by="day"):
        by = "day" if by not in ("day", "month") else by   # 키 정규화(잘못된 by가 캐시 오염 방지)
        return self._memo(f"activity:{by}", lambda: self._activity(by))

    def _activity(self, by):
        """활동량 집계(actor 분리). by=day → ts[:10], month → ts[:7].
        반환: [{"bucket": "2026-06-11", "user": N, "agent": N, "total": N}, ...] (bucket 정렬, unknown 맨뒤)."""
        n = 10 if by == "day" else 7
        buckets = defaultdict(lambda: {"user": 0, "agent": 0})
        for e in self.events:
            # norm_ts로 int epoch-ms도 ISO Z 문자열로 통일 → 슬라이스 균일(raw int 슬라이스 TypeError 방지)
            b = (norm_ts(e.ts) or "")[:n] or "unknown"
            actor = e.actor if e.actor in ("user", "agent") else "user"
            buckets[b][actor] += 1
        known = sorted(b for b in buckets if b != "unknown")
        order = known + (["unknown"] if "unknown" in buckets else [])
        return [{"bucket": b, "user": buckets[b]["user"], "agent": buckets[b]["agent"],
                 "total": buckets[b]["user"] + buckets[b]["agent"]} for b in order]

    _FILE_ACTIONS = ("read", "write", "paste", "upload")

    def files(self):
        return self._memo("files", self._files)

    def _files(self):
        """접근 파일 목록(actor 분리·action별·태그). read/write/paste/upload만.
        반환: [{"target", "count", "by_actor", "actions": {action:n}, "tags": [..]}, ...] (접근 많은 순)."""
        agg = {}
        for e in self.events:
            if e.action not in self._FILE_ACTIONS or not e.target:
                continue
            r = agg.setdefault(e.target, {"target": e.target, "count": 0,
                                          "by_actor": {"user": 0, "agent": 0},
                                          "actions": {}, "tags": set()})
            r["count"] += 1
            actor = e.actor if e.actor in ("user", "agent") else "user"
            r["by_actor"][actor] += 1
            r["actions"][e.action] = r["actions"].get(e.action, 0) + 1
            for t in (e.tags or []):
                r["tags"].add(t)
        rows = sorted(agg.values(), key=lambda r: (-r["count"], r["target"]))
        for r in rows:
            r["tags"] = sorted(r["tags"])
        return rows
