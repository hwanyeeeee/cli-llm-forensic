"""O11: WSL 내부 네이티브 파싱 헬퍼. exe(Windows)가 wsl.exe interop으로 이 모듈을 WSL에서 실행 —
\\wsl.localhost(9P)를 우회해 증거를 네이티브 FS에서 읽는다(신뢰성+속도, docs/perf-baseline.md).

증거 환경 내 발자국(라이브 포렌식 트레이드오프 — 문서화):
  - 실행: python3 -B -E -s (pyc 생성 금지, 환경변수/사이트 격리)
  - 읽기: 증거 root의 jsonl만(roio._ro_open 경유 — read-only 강제)
  - 쓰기: --out(호출자가 지정한 증거 밖 경로, 보통 /mnt/c 임시디렉터리)뿐
출력 계약: out 파일 1행 = meta JSON {"files","events","manifest","timings"}, 이후 행당 Event dict.
stdout: "TOTAL n" 1회 → 파일마다 "PROGRESS i n" (호출자 진행률 포워딩).
파싱·태깅·enrich는 scan_to_engine 직접 경로와 같은 코드·같은 순서 → byte-identical(I1)."""
import argparse
import json
import os
import sys
import time


def run(root, origin_tag, out_path):
    from clfx.sources import remote_control_markers, source_for, source_warnings
    from clfx.parser import parse_file
    from clfx.analyze.attribution import enrich
    if not os.path.isdir(root):
        print(f"root not a directory: {root}", file=sys.stderr)
        return 2
    src = source_for(root)
    files = src.jsonl_files()                       # history 먼저 → sorted transcripts (직접 경로와 동일)
    hist = src.root / "history.jsonl"
    print(f"TOTAL {len(files)}", flush=True)
    events, bypass, manifest = [], set(), {}
    _t = time.perf_counter()
    for i, p in enumerate(files):
        evs, byp, sha = parse_file(src, p, p == hist)
        bypass |= byp
        if sha is not None:
            manifest[str(p)] = sha
        for e in evs:
            if origin_tag and origin_tag not in e.tags:
                e.tags.append(origin_tag)           # 직접 경로 조립 루프와 동일: 태그 먼저 → enrich 나중
        events.extend(evs)
        print(f"PROGRESS {i + 1} {len(files)}", flush=True)
    parse_s = time.perf_counter() - _t
    _t = time.perf_counter()
    enrich(events, src, bypass=bypass)              # 수집된 bypass로 태깅(재읽기 X) — 직접 경로와 동일
    enrich_s = time.perf_counter() - _t
    sqlite_support = {}
    sqlite_warnings = []
    markers = remote_control_markers(src)            # 23단계: 위임 경로도 같은 마커를 낸다
    if src.agent == "codex":
        from clfx.codex_sqlite import (augment_events, collect_sqlite_support,
                                       enrollment_marker)
        support = collect_sqlite_support(src.sqlite_root, files)
        if support["databases"]:
            augment_events(events, support)
            manifest.update(support["manifest"])
            sqlite_warnings = support["warnings"]
            sqlite_support = support
        markers.append(enrollment_marker(support))
    meta = {"files": len(files), "events": len(events),
            "manifest": {k: manifest[k] for k in sorted(manifest)},
            "warnings": source_warnings(src) + sqlite_warnings,
            "sqlite_support": sqlite_support,
            "remote_markers": markers,
            "timings": {"parse_wall_s": round(parse_s, 3), "enrich_s": round(enrich_s, 3)}}
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for e in events:
            f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="clfx WSL-side parse helper (O11)")
    ap.add_argument("root")
    ap.add_argument("--origin-tag", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    return run(a.root, a.origin_tag, a.out)


if __name__ == "__main__":
    sys.exit(main())
