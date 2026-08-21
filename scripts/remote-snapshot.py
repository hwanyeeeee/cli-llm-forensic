#!/usr/bin/env python3
"""원격제어 통제 실험용 read-only 스냅샷/차분 도구.

    python3 scripts/remote-snapshot.py snap  <라벨>      # 현 상태 기록
    python3 scripts/remote-snapshot.py diff  <before> <after>

대상 루트: ~/.claude, ~/.codex (존재하는 것만). 원본은 열기만 하고 쓰지 않는다.
SQLite 는 main/-wal/-shm 을 같은 시점에 함께 해시해야 최신 커밋이 빠지지 않는다.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOTS = ["~/.claude", "~/.codex"]
SKIP_DIRS = {"node_modules", "__pycache__", ".git"}
MAX_HASH_BYTES = 64 * 1024 * 1024      # 그보다 크면 크기·mtime 만 (해시 생략 표기)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snap(label, out_dir):
    rows = {}
    for root in ROOTS:
        base = Path(os.path.expanduser(root))
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                p = Path(dirpath) / name
                try:
                    st = p.stat()
                except OSError as e:
                    rows[str(p)] = {"error": type(e).__name__}
                    continue
                row = {"size": st.st_size, "mtime": round(st.st_mtime, 3)}
                if st.st_size <= MAX_HASH_BYTES:
                    try:
                        row["sha256"] = _sha256(p)
                    except OSError as e:
                        row["error"] = type(e).__name__
                else:
                    row["sha256"] = None          # 대용량 — 크기·mtime 으로만 비교
                rows[str(p)] = row
    out = Path(out_dir) / f"snap-{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=1),
                   encoding="utf-8")
    print(f"{out}  파일 {len(rows)}개")


def diff(before, after):
    a = json.loads(Path(before).read_text(encoding="utf-8"))
    b = json.loads(Path(after).read_text(encoding="utf-8"))
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    for title, items in (("신규", added), ("삭제", removed), ("변경", changed)):
        print(f"\n== {title} {len(items)}건")
        for k in items[:200]:
            if title == "변경":
                d = [f for f in ("size", "mtime", "sha256") if a[k].get(f) != b[k].get(f)]
                print(f"  {k}   ({','.join(d)})")
            else:
                print(f"  {k}")
        if len(items) > 200:
            print(f"  … 외 {len(items) - 200}건")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "snap":
        snap(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "artifacts/remote")
    elif len(sys.argv) == 4 and sys.argv[1] == "diff":
        diff(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(2)
