"""clfx 성능 벤치 — 실데이터 스캔을 N회 반복해 단계별 median 마크다운 표 출력.

사용:  python3 scripts/bench.py <root> [<root>...] [--repeat 3]
       (Windows: py -3 scripts\\bench.py C:\\Users\\<u>\\.claude \\\\wsl.localhost\\Ubuntu\\home\\<u>\\.claude)

테스트 아님(환경 의존 시간값) — CI 밖 수동 실행. 결과는 docs/validation/perf-baseline.md에 붙여넣는다.
read-only: 스캔 대상은 읽기만(roio 가드 유지), 출력은 stdout뿐 — 어디에도 쓰지 않는다."""
import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo 루트

from clfx.web.api import scan_to_engine, forensic_scan, mcp_payload  # noqa: E402

# 표 출력 순서(파이프라인 순). 없는 키는 건너뛰고, ORDER 밖 키는 뒤에 이름순.
ORDER = ["parse_wall_s", "enrich_s", "walk_tmp_s", "resolve_s", "hash_s",
         "attribution_s", "retention_s", "mcp_s", "total_s"]


def run_once(roots):
    """스캔 1회 — (timings dict, 규모 meta dict). 서버 경로(scan_to_engine+forensic_scan+mcp)와 동일 순서."""
    t0 = time.perf_counter()
    eng, ev_root, _by, _man = scan_to_engine(roots, collect_artifacts=True)
    t = dict(getattr(eng, "parse_timings", {}))
    out = forensic_scan(ev_root, roots=roots)
    t.update(out.get("timings") or {})
    _t = time.perf_counter()
    mcp_payload(eng, roots)
    t["mcp_s"] = round(time.perf_counter() - _t, 3)
    t["total_s"] = round(time.perf_counter() - t0, 3)
    meta = {"events": len(eng.events), "scanned": out.get("scanned", 0),
            "tmp_scanned": out.get("tmp_scanned", 0), "missing": out.get("missing", 0)}
    return t, meta


def median_table(runs):
    """단계별 median. 어떤 run에 없는 키는 0.0으로 취급(결정적)."""
    keys = sorted({k for r in runs for k in r})
    return {k: round(statistics.median([r.get(k, 0.0) for r in runs]), 3) for k in keys}


def fmt_md(med, meta):
    """median dict → 마크다운 표(ORDER 순, 나머지 이름순) + 규모 메타 1줄."""
    keys = [k for k in ORDER if k in med] + sorted(k for k in med if k not in ORDER)
    lines = ["| 단계 | median(s) |", "|---|---|"]
    lines += [f"| {k} | {med[k]} |" for k in keys]
    lines.append("")
    lines.append("규모: " + " · ".join(f"{k}={v}" for k, v in sorted(meta.items())))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="clfx 스캔 벤치(단계별 median)")
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args(argv)
    runs, meta = [], {}
    for i in range(args.repeat):
        t, meta = run_once(args.roots)
        runs.append(t)
        print(f"# run {i + 1}/{args.repeat}: total={t.get('total_s')}s", file=sys.stderr)
    print(fmt_md(median_table(runs), meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
