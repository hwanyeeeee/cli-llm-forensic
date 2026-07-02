"""bench.py 순수 함수 단위 테스트 — 실측 실행은 환경 의존이라 CI 밖(스펙 §5)."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("bench", REPO / "scripts" / "bench.py")
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)


def test_median_table_odd_runs():
    runs = [{"hash_s": 1.0, "parse_wall_s": 5.0},
            {"hash_s": 3.0, "parse_wall_s": 4.0},
            {"hash_s": 2.0, "parse_wall_s": 6.0}]
    med = bench.median_table(runs)
    assert med == {"hash_s": 2.0, "parse_wall_s": 5.0}


def test_median_table_missing_key_counts_as_zero():
    runs = [{"hash_s": 2.0}, {"hash_s": 4.0, "mcp_s": 1.0}]
    med = bench.median_table(runs)
    assert med["hash_s"] == 3.0 and med["mcp_s"] == 0.5


def test_fmt_md_orders_stages_and_includes_meta():
    med = {"hash_s": 2.0, "parse_wall_s": 5.0, "zzz_s": 0.1}
    meta = {"events": 10, "scanned": 3, "tmp_scanned": 7, "missing": 0}
    out = bench.fmt_md(med, meta)
    assert out.index("parse_wall_s") < out.index("hash_s") < out.index("zzz_s")  # ORDER 우선, 나머지 정렬
    assert "| 단계 | median(s) |" in out and "events=10" in out
