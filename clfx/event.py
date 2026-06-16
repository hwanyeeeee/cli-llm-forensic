from dataclasses import dataclass, field, asdict
from typing import Optional


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
    action: str         # prompt | read | bash | write | paste | response
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
