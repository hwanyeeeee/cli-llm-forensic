import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawRecord:
    file: str   # 절대/상대 경로 문자열 (source.file 로 그대로 사용)
    line: int   # 1-기반
    obj: dict


class ClaudeSource:
    """Claude Code 파일 레이아웃 reader. 다른 에이전트는 같은 인터페이스로 추가."""
    agent = "claude"

    def __init__(self, root):
        self.root = Path(root)

    def _iter_jsonl(self, path: Path):
        if not path.exists():
            return
        with path.open(encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield RawRecord(str(path), i, obj)

    def history_records(self):
        yield from self._iter_jsonl(self.root / "history.jsonl")

    def transcript_records(self):
        for p in sorted((self.root / "projects").rglob("*.jsonl")):
            yield from self._iter_jsonl(p)

    def paste_cache_path(self, content_hash: str) -> Path:
        return self.root / "paste-cache" / f"{content_hash}.txt"
