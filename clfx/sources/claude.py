import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from clfx import roio


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

    def _iter_jsonl(self, path: Path, sha_out=None):
        # exists() precheck 제거 → 직접 open 시도(slow UNC에서 파일당 syscall 1회 절감).
        # OSError(없는 파일/권한 등)면 yield 없이 종료 — 기존 missing-file 케이스와 동일(무손실).
        # on_file은 open 성공(실제 읽는 파일) 후에만 1회 발화 → 진행률 카운트 의미 보존.
        # B-2: 모든 read는 roio._ro_open 경유(read-only 강제 + in-memory audit 기록).
        # B-1: 바이너리 라인으로 읽어 raw 바이트 SHA-256을 같은 읽기서 누적(추가 읽기 0),
        #      각 라인을 decode+strip 후 json.loads — jsonl(\n-종단) 1-기반 line·파싱 byte-identical.
        #      sha_out(주어지면 호출자 소유 dict)에 끝까지 읽은 뒤 ["sha"]=hex 기록 → src 공유상태
        #      없이 스레드별 분리(32-thread parse 병렬 안전). 못 열면 키 미설정(None 의미).
        try:
            f = roio._ro_open(path, "rb")
        except OSError:
            return
        if self._on_file:
            self._on_file(str(path))     # 실제로 읽는(열린) 파일만 1회 보고
        h = hashlib.sha256()
        with f:
            for i, raw in enumerate(f, start=1):
                h.update(raw)                              # raw 바이트(개행 포함) 연결 == 정확한 파일 바이트
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield RawRecord(str(path), i, obj)
        if sha_out is not None:
            sha_out["sha"] = h.hexdigest()                 # 끝까지 읽은 파일의 raw-바이트 해시 확정

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
