from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


def _epoch_to_dt(v):
    """epoch-ms 정수/실수 → tz-aware UTC datetime. norm_ts·ts_key 공유(DRY)."""
    return datetime.fromtimestamp(v / 1000, tz=timezone.utc)


def norm_ts(v):
    """ts 표시/저장용 정규화 → ISO8601 UTC 'Z' 문자열(타입 혼재 방지).
    history.jsonl은 epoch-ms 정수(1770555950996), transcript는 ISO 문자열로 섞여 들어온다.
    int/float(epoch-ms) → ISO 'Z', str → 원본 그대로(포렌식 충실도), None → None.
    정렬 비교는 ts_key를 써라 — 사전순은 동일초 ISO(밀리초無)/epoch(밀리초有) 혼재서 깨진다."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return _epoch_to_dt(v).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return str(v)


_MIN_DT = datetime(1, 1, 1, tzinfo=timezone.utc)


def ts_key(v):
    """정렬용 비교키 → tz-aware UTC datetime(실제 시각 비교, 사전순 아님).
    epoch-ms int/float·ISO str(밀리초 유무·'Z'·'+00:00'·tz없음 모두) 안전.
    None/파싱불가 → 최소시각(맨 앞). norm_ts 사전순의 동일초 혼재 결함을 정렬에서 차단."""
    if v is None:
        return _MIN_DT
    if isinstance(v, (int, float)):
        return _epoch_to_dt(v)
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return _MIN_DT
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@dataclass
class Source:
    file: str
    line: int


@dataclass
class Event:
    ts: Optional[str]
    agent: str          # claude | codex | gemini
    session: str
    actor: str          # user | agent
    action: str         # prompt | read | bash | write | paste | response | mcp
    target: str
    preview: str
    source: Source
    tags: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)              # source -> {"file","line"} 자동
        return d

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        d = dict(d)
        d["source"] = Source(**d["source"])
        if d.get("tags") is None:          # 누락 키 + JSON null 둘 다 정규화
            d["tags"] = []
        return cls(**d)
