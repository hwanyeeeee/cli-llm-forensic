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

    def __init__(self, root, on_file=None):
        self.root = Path(root)
        self._on_file = on_file          # 파일 1개 읽기 시작 시 호출(진행률 카운트용). None=무동작.

    def _iter_jsonl(self, path: Path):
        if not path.exists():
            return
        if self._on_file:
            self._on_file(str(path))     # 실제로 읽는 파일만(존재) 1회 보고
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

    def jsonl_files(self):
        """parse 대상 jsonl 경로(존재하는 것만): history + projects 전부. 사전 카운트용."""
        files = []
        h = self.root / "history.jsonl"
        if h.exists():
            files.append(h)
        files.extend(sorted((self.root / "projects").rglob("*.jsonl")))
        return files

    def transcript_files(self):
        """transcript jsonl만(enrich/bypass 패스가 재읽는 대상)."""
        return sorted((self.root / "projects").rglob("*.jsonl"))

    def paste_cache_path(self, content_hash: str) -> Path:
        return self.root / "paste-cache" / f"{content_hash}.txt"
