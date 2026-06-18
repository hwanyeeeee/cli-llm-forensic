"""B-2: 공유 read-only open + in-memory audit (clfx.roio)."""
import threading

import pytest

from clfx import roio


def test_ro_open_refuses_write_modes(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("data", encoding="utf-8")   # 테스트 픽스처 준비(분석 대상 FS 아님)
    roio.reset_audit()
    for mode in ("w", "a", "x", "r+", "wb", "ab"):
        with pytest.raises(ValueError) as ei:
            roio._ro_open(p, mode)
        assert "read-only" in str(ei.value)
        assert mode in str(ei.value)


def test_ro_open_allows_read_modes(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("hello", encoding="utf-8")
    roio.reset_audit()
    with roio._ro_open(p, "r", encoding="utf-8") as f:
        assert f.read() == "hello"
    with roio._ro_open(p, "rb") as f:
        assert f.read() == b"hello"
    # default mode = rb
    with roio._ro_open(p) as f:
        assert f.read() == b"hello"


def test_audit_records_every_call_sorted(tmp_path):
    a = tmp_path / "a.txt"; a.write_text("A", encoding="utf-8")
    b = tmp_path / "b.txt"; b.write_text("B", encoding="utf-8")
    roio.reset_audit()
    roio._ro_open(b, "rb").close()
    roio._ro_open(a, "r", encoding="utf-8").close()
    roio._ro_open(a, "rb").close()
    recs = roio.audit_records()
    assert recs == sorted(recs, key=lambda r: (r["path"], r["mode"]))
    assert {"path": str(a), "mode": "r"} in recs
    assert {"path": str(a), "mode": "rb"} in recs
    assert {"path": str(b), "mode": "rb"} in recs
    assert len(recs) == 3


def test_reset_audit_clears(tmp_path):
    p = tmp_path / "x.txt"; p.write_text("x", encoding="utf-8")
    roio.reset_audit()
    roio._ro_open(p, "rb").close()
    assert roio.audit_records()
    roio.reset_audit()
    assert roio.audit_records() == []


def test_modes_seen_subset_of_r_rb(tmp_path):
    p = tmp_path / "x.txt"; p.write_text("x", encoding="utf-8")
    roio.reset_audit()
    roio._ro_open(p, "r", encoding="utf-8").close()
    roio._ro_open(p, "rb").close()
    assert set(roio.modes_seen()) <= {"r", "rb"}
    assert roio.modes_seen() == ["r", "rb"]   # sorted distinct


def test_write_delete_rename_ops_always_zero(tmp_path):
    p = tmp_path / "x.txt"; p.write_text("x", encoding="utf-8")
    roio.reset_audit()
    roio._ro_open(p, "rb").close()
    assert roio.write_delete_rename_ops() == 0


def test_audit_thread_safe(tmp_path):
    files = []
    for i in range(20):
        f = tmp_path / f"f{i}.txt"; f.write_text(str(i), encoding="utf-8")
        files.append(f)
    roio.reset_audit()

    def _open(f):
        roio._ro_open(f, "rb").close()

    threads = [threading.Thread(target=_open, args=(f,)) for f in files for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(roio.audit_records()) == 60   # 20 files * 3 — 락으로 누락 없음
