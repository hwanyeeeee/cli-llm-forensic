import os

from clfx.analyze import artifacts as A


# ── Task 1: 경로 변환 ──────────────────────────────────────────────
def test_resolve_mnt_drive_on_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    assert A.resolve_candidates("/mnt/c/Users/best1/x.env", r"\\wsl.localhost\Ubuntu\home\u\.claude") == [r"C:\Users\best1\x.env"]


def test_resolve_windows_abs_on_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    assert A.resolve_candidates(r"C:\Users\best1\.claude\h.jsonl", r"C:\Users\best1\.claude")[0] == r"C:\Users\best1\.claude\h.jsonl"


def test_resolve_posix_to_unc_on_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    got = A.resolve_candidates("/home/u/secret.txt", r"\\wsl.localhost\Ubuntu\home\u\.claude")
    assert got == [r"\\wsl.localhost\Ubuntu\home\u\secret.txt"]


def test_resolve_windows_abs_on_linux(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    assert A.resolve_candidates(r"C:\Users\best1\x", r"C:\Users\best1\.claude") == ["/mnt/c/Users/best1/x"]


def test_resolve_skips_non_files():
    for t in ["", "[Pasted #1]", "[Image #2]", "https://x.com/a", "ls -la", "grep foo"]:
        assert A.resolve_candidates(t, r"C:\x\.claude") == []


# ── Task 2: 해시 + stat ────────────────────────────────────────────
def test_hash_file_sha256(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"hello")
    import hashlib
    assert A.hash_file(str(p)) == hashlib.sha256(b"hello").hexdigest()


def test_hash_same_content_same_hash(tmp_path):
    (tmp_path / "a").write_bytes(b"X" * 100000)
    (tmp_path / "b").write_bytes(b"X" * 100000)
    assert A.hash_file(str(tmp_path / "a")) == A.hash_file(str(tmp_path / "b"))


def test_stat_file_fields(tmp_path):
    p = tmp_path / "a"
    p.write_bytes(b"abc")
    s = A.stat_file(str(p))
    assert s["size"] == 3 and s["mtime"].endswith("Z") and "owner" in s


# ── Task 3: 해시 클러스터 + tmp 전수 스캔 ──────────────────────────
def test_tmp_roots_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    rts = A.tmp_roots([r"C:\Users\best1\.claude", r"\\wsl.localhost\Ubuntu\home\u\.claude"])
    assert r"\\wsl.localhost\Ubuntu\tmp" in rts
    assert r"C:\Users\best1\AppData\Local\Temp" in rts and r"C:\tmp" in rts


def test_tmp_roots_posix(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    assert "/tmp" in A.tmp_roots(["/home/u/.claude"])


def test_hash_cluster_detects_tmp_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    from clfx.event import Event, Source
    proj = tmp_path / "proj"
    tdir = tmp_path / "tmp"
    proj.mkdir()
    tdir.mkdir()
    (proj / "orig.env").write_bytes(b"SECRET=1\n")
    (tdir / "leaked.env").write_bytes(b"SECRET=1\n")
    ev = (Event("2026-06-16T01:00:00Z", "claude", "s", "user", "paste", str(proj / "orig.env"), "‹secret›", Source("h", 1), ["secret"]), str(tmp_path))
    out = A.hash_clusters([ev], tmp_dirs=[str(tdir)])
    assert out["tmp_scanned"] == 1
    cl = [c for c in out["hashes"] if c["count"] >= 2]
    assert len(cl) == 1 and cl[0]["in_tmp"] is True and cl[0]["secret"] is True and cl[0]["leak_suspect"] is True


def test_hash_cluster_reports_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(A, "hash_file", lambda p: (_ for _ in ()).throw(PermissionError("x")))
    (tmp_path / "a").write_bytes(b"z")
    out = A.hash_clusters([], tmp_dirs=[str(tmp_path)])
    assert any(e["reason"] == "PermissionError" for e in out["errors"])


def test_walk_tmp_records_stat_failure_in_errors(tmp_path, monkeypatch):
    # walk가 열거한 정규파일이나 stat(lstat) 자체가 실패하면(접근 거부/레이스 삭제)
    # 흔적 없이 드롭하지 말고 errors[]에 {path, reason}로 기록해야 한다(완전성 불변식).
    monkeypatch.setattr(os, "name", "posix")
    bad = tmp_path / "racy"
    bad.write_bytes(b"x")
    real_lstat = os.lstat

    def fake_lstat(p, *a, **k):
        if str(p) == str(bad):
            raise PermissionError("denied")
        return real_lstat(p, *a, **k)

    monkeypatch.setattr(os, "lstat", fake_lstat)
    files, walk_errors = A._walk_tmp([str(tmp_path)])
    assert str(bad) not in files                      # 해시 대상서 빠짐
    assert {"path": str(bad), "reason": "PermissionError"} in walk_errors


def test_hash_cluster_merges_walk_errors(tmp_path, monkeypatch):
    # _walk_tmp의 접근실패가 hash_clusters의 errors[]로 병합되어야 한다.
    monkeypatch.setattr(os, "name", "posix")
    bad = tmp_path / "racy"
    bad.write_bytes(b"x")
    real_lstat = os.lstat

    def fake_lstat(p, *a, **k):
        if str(p) == str(bad):
            raise OSError("gone")
        return real_lstat(p, *a, **k)

    monkeypatch.setattr(os, "lstat", fake_lstat)
    out = A.hash_clusters([], tmp_dirs=[str(tmp_path)])
    assert any(e["path"] == str(bad) and e["reason"] == "OSError" for e in out["errors"])


def test_walk_tmp_skips_non_regular_without_error(tmp_path, monkeypatch):
    # 비정규파일(fifo/소켓/디바이스/symlink)은 정상 skip — errors 아님.
    monkeypatch.setattr(os, "name", "posix")
    (tmp_path / "regular").write_bytes(b"ok")
    fifo = tmp_path / "myfifo"
    try:
        os.mkfifo(str(fifo))
    except (AttributeError, OSError):
        import pytest
        pytest.skip("mkfifo unavailable on this platform")
    files, walk_errors = A._walk_tmp([str(tmp_path)])
    assert str(tmp_path / "regular") in files
    assert str(fifo) not in files                     # 정규파일 아님 → 미수집
    assert all(e["path"] != str(fifo) for e in walk_errors)   # errors 아님


def test_walk_tmp_skips_symlink_without_error(tmp_path, monkeypatch):
    # symlink는 따라가지 않고 skip(errors 아님). followlinks=False + lstat 보증.
    monkeypatch.setattr(os, "name", "posix")
    target = tmp_path / "target.txt"
    target.write_bytes(b"data")
    link = tmp_path / "link.txt"
    try:
        os.symlink(str(target), str(link))
    except (AttributeError, OSError, NotImplementedError):
        import pytest
        pytest.skip("symlink unavailable on this platform")
    files, walk_errors = A._walk_tmp([str(tmp_path)])
    assert str(target) in files
    assert str(link) not in files                     # symlink는 미수집
    assert all(e["path"] != str(link) for e in walk_errors)


# ── Task 4: 주체왜곡 보정 JOIN ─────────────────────────────────────
def test_attribution_flags_agent_write(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    from clfx.event import Event, Source
    p = tmp_path / "todo.py"
    p.write_bytes(b"print(1)\n")
    ev = Event("2026-06-16T16:04:54Z", "claude", "s", "agent", "write", str(p), "", Source("t.jsonl", 20), [])
    out = A.attribution_join([(ev, str(tmp_path))])
    assert len(out) == 1
    r = out[0]
    assert r["transcript_actor"] == "agent" and r["distortion"] is True
    assert r["source"] == {"file": "t.jsonl", "line": 20} and "에이전트" in r["note"]


# ── Task 5: forensic_scan 통합 + 스캔 연결 ─────────────────────────
def test_forensic_scan_contract():
    from clfx.web.api import forensic_scan
    # (event, root) 리스트는 scan이 조립. 빈 입력서 키/정렬만 확인(tmp_dirs=[] 주입해 머신 tmp 비스캔=테스트 결정성).
    out = forensic_scan([], tmp_dirs=[])
    assert set(out) == {"scanned", "missing", "tmp_scanned", "tmp_roots",
                        "errors", "hashes", "attribution", "retention"}
    assert out["hashes"] == [] and out["attribution"] == [] and out["errors"] == []
    assert out["retention"] == []


def test_scan_to_engine_default_unchanged():
    # collect_artifacts 미지정(기본 False) → 기존과 동일: QueryEngine 반환, events>0(무손실 불변).
    from clfx.web.api import scan_to_engine
    from clfx.query.engine import QueryEngine
    eng = scan_to_engine(["tests/fixtures/dot-claude"])
    assert isinstance(eng, QueryEngine)
    assert len(eng.events) > 0


def test_scan_to_engine_collect_artifacts_returns_pairs():
    # collect_artifacts=True → (engine, list). list 원소는 (Event, str) 튜플(최종 태그 포함 같은 객체).
    from clfx.web.api import scan_to_engine
    from clfx.query.engine import QueryEngine
    from clfx.event import Event
    eng, ev_root = scan_to_engine(["tests/fixtures/dot-claude"], collect_artifacts=True)
    assert isinstance(eng, QueryEngine)
    assert isinstance(ev_root, list) and len(ev_root) == len(eng.events)
    e, root = ev_root[0]
    assert isinstance(e, Event) and isinstance(root, str)
    # ev_root의 Event는 엔진의 Event와 동일 객체(태그 포함 최종 상태) — 입력순 누적.
    assert ev_root[0][0] is eng.events[0]


# ── Task 7: tmp 보존기간(retention) ────────────────────────────────
from clfx.analyze.artifacts import tmp_retention


def test_tmp_retention_reports_age_and_expiry(tmp_path):
    f = tmp_path / "leak.txt"
    f.write_text("secret payload", encoding="utf-8")
    ten_days_ago = f.stat().st_mtime           # 실제 mtime
    now = ten_days_ago + 10 * 86400            # 10일 후를 '현재'로 주입(결정성)
    out = tmp_retention([str(tmp_path)], now_epoch=now)
    rows = out["retention"]
    assert len(rows) == 1                       # 모든 tmp 정규파일(무skip)
    r = rows[0]
    assert r["path"] == str(f)
    assert abs(r["age_days"] - 10.0) < 0.01     # 나이 ≈ 10일
    assert abs(r["expires_in_days"] - 20.0) < 0.01  # 30 - 10 = 20일 잔여
    assert out["errors"] == []


def test_tmp_retention_expired_clamps_to_zero(tmp_path):
    f = tmp_path / "old.txt"
    f.write_text("x", encoding="utf-8")
    now = f.stat().st_mtime + 40 * 86400        # 40일 경과(>30 보존)
    out = tmp_retention([str(tmp_path)], now_epoch=now)
    assert out["retention"][0]["expires_in_days"] == 0   # 만료 → 0 클램프
