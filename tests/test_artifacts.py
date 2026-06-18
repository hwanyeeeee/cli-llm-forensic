import hashlib
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
    # OPT-3: size-prefilter는 unique-size 파일을 해시하지 않으므로, 해시 실패가 errors[]에
    # 표면화되려면 같은 크기 파일이 ≥2여야 한다(해시가 실제로 시도됨). 두 동일크기 파일로 갱신.
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(A, "hash_file", lambda p: (_ for _ in ()).throw(PermissionError("x")))
    (tmp_path / "a").write_bytes(b"z")
    (tmp_path / "b").write_bytes(b"q")          # 같은 크기(1B) → 해시 그룹 형성 → 해시 시도됨
    out = A.hash_clusters([], tmp_dirs=[str(tmp_path)])
    assert any(e["reason"] == "PermissionError" for e in out["errors"])


def test_hash_cluster_unique_size_unreadable_still_counted(tmp_path, monkeypatch):
    # OPT-3 완전성: unique-size 콘텐츠 판독불가 파일은 해시 시도 없이도 stat 커버리지로 COUNT돼야
    # 한다(조용한 누락 금지). 해시 실패가 없어도 stat_verified/content_unread에 반영.
    monkeypatch.setattr(os, "name", "posix")
    # hash_file은 호출되면 실패하지만, unique-size라 호출조차 되지 않아야 한다.
    monkeypatch.setattr(A, "hash_file", lambda p: (_ for _ in ()).throw(PermissionError("x")))
    (tmp_path / "uniq").write_bytes(b"unique-size-content")   # 단독 크기
    out = A.hash_clusters([], tmp_dirs=[str(tmp_path)])
    assert out["tmp_scanned"] == 1                 # stat 커버리지로 전수 집계
    assert out["stat_verified"] == 1
    assert out["hashed"] == 0                      # 해시 시도 안 함
    assert out["content_unread"] == 1              # unique size라 콘텐츠 미판독
    assert out["errors"] == []                     # 해시 시도 없음 → 해시 에러 없음
    # 완전성 검산식: stat_verified == hashed + content_unread + (해시실패 dup-size 파일 수)
    assert out["stat_verified"] == out["hashed"] + out["content_unread"]


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


# ── [#2a] 유출 의심 분류 정합 + [#2b] tmp 해시 인덱스 ───────────────
def test_leak_suspect_true_for_referenced_plus_tmp_copy(tmp_path, monkeypatch):
    # referenced 이벤트 1개 + 동일내용 tmp 파일 1개 = leak_suspect True · tmp_only False.
    monkeypatch.setattr(os, "name", "posix")
    from clfx.event import Event, Source
    proj = tmp_path / "proj"; tdir = tmp_path / "tmp"
    proj.mkdir(); tdir.mkdir()
    (proj / "orig.env").write_bytes(b"SECRET=1\n")
    (tdir / "leaked.env").write_bytes(b"SECRET=1\n")
    ev = (Event("2026-06-16T01:00:00Z", "claude", "s", "user", "paste",
                str(proj / "orig.env"), "‹secret›", Source("h", 1), ["secret"]), str(tmp_path))
    out = A.hash_clusters([ev], tmp_dirs=[str(tdir)])
    cl = [c for c in out["hashes"] if c["count"] >= 2]
    assert len(cl) == 1
    assert cl[0]["leak_suspect"] is True and cl[0]["tmp_only"] is False
    assert cl[0]["secret"] is True
    assert cl[0]["reason"] == "시크릿 참조 파일이 tmp 사본과 동일 해시 — 강한 유출 의심"
    # [#2b] tmp 파일 sha → meta 인덱스 존재.
    idx = out["tmp_hash_index"]
    sha = cl[0]["sha256"]
    assert sha in idx
    metas = idx[sha]
    assert [m["path"] for m in metas] == [str(tdir / "leaked.env")]
    assert metas[0]["size"] == len(b"SECRET=1\n") and metas[0]["mtime"].endswith("Z")


def test_tmp_only_true_when_no_referenced(tmp_path, monkeypatch):
    # tmp끼리만 2개(referenced 0) = leak_suspect False · tmp_only True.
    monkeypatch.setattr(os, "name", "posix")
    tdir = tmp_path / "tmp"; tdir.mkdir()
    (tdir / "a.dll").write_bytes(b"DUP-INSTALL\n")
    (tdir / "b.dll").write_bytes(b"DUP-INSTALL\n")
    out = A.hash_clusters([], tmp_dirs=[str(tdir)])
    cl = [c for c in out["hashes"] if c["count"] >= 2]
    assert len(cl) == 1
    assert cl[0]["leak_suspect"] is False and cl[0]["tmp_only"] is True
    assert cl[0]["reason"] == "tmp 내부 중복(설치/캐시 등 — 유출 아님)"
    # 두 tmp 사본 모두 인덱스에 (path 정렬).
    idx = out["tmp_hash_index"]
    sha = cl[0]["sha256"]
    assert [m["path"] for m in idx[sha]] == [str(tdir / "a.dll"), str(tdir / "b.dll")]


# ── [R4] 0B 빈 파일 유출 오탐 차단 ─────────────────────────────────
def test_empty_file_cluster_not_leak_suspect(tmp_path, monkeypatch):
    # 빈 파일(0B) 2개 동일내용(b"") — 하나는 referenced 이벤트로 참조.
    # 빈 파일은 유출할 내용이 없음 → leak_suspect False · tmp_only True · reason "빈 파일".
    monkeypatch.setattr(os, "name", "posix")
    from clfx.event import Event, Source
    proj = tmp_path / "proj"; tdir = tmp_path / "tmp"
    proj.mkdir(); tdir.mkdir()
    (proj / "empty.env").write_bytes(b"")       # referenced, 0B
    (tdir / "empty.tmp").write_bytes(b"")        # tmp 사본, 0B
    ev = (Event("2026-06-16T01:00:00Z", "claude", "s", "user", "paste",
                str(proj / "empty.env"), "", Source("h", 1), ["secret"]), str(tmp_path))
    out = A.hash_clusters([ev], tmp_dirs=[str(tdir)])
    cl = [c for c in out["hashes"] if c["count"] >= 2]
    assert len(cl) == 1
    assert cl[0]["size"] == 0
    assert cl[0]["leak_suspect"] is False        # 오탐 차단
    assert cl[0]["tmp_only"] is True             # 노이즈 섹션으로
    assert "빈 파일" in cl[0]["reason"]
    # 전수 스캔·그룹핑 유지(완전성): 클러스터는 여전히 잡힌다.
    assert cl[0]["count"] == 2


def test_nonempty_referenced_tmp_cluster_still_leak_suspect(tmp_path, monkeypatch):
    # 비교군(회귀 방지): 비어있지 않은 referenced↔tmp 유출 클러스터는 leak_suspect True 유지.
    monkeypatch.setattr(os, "name", "posix")
    from clfx.event import Event, Source
    proj = tmp_path / "proj"; tdir = tmp_path / "tmp"
    proj.mkdir(); tdir.mkdir()
    (proj / "orig.env").write_bytes(b"SECRET=1\n")
    (tdir / "leaked.env").write_bytes(b"SECRET=1\n")
    ev = (Event("2026-06-16T01:00:00Z", "claude", "s", "user", "paste",
                str(proj / "orig.env"), "‹secret›", Source("h", 1), ["secret"]), str(tmp_path))
    out = A.hash_clusters([ev], tmp_dirs=[str(tdir)])
    cl = [c for c in out["hashes"] if c["count"] >= 2]
    assert len(cl) == 1
    assert cl[0]["size"] > 0
    assert cl[0]["leak_suspect"] is True
    assert cl[0]["tmp_only"] is False
    assert "빈 파일" not in cl[0]["reason"]


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
                        "errors", "hashes", "attribution", "retention", "tmp_hash_index",
                        "hashed", "stat_verified", "content_unread",
                        "tmp_inventory",
                        "acquired_hashes", "stat_only"}   # OPT-3 투명 카운터 + OPT-1 lazy-search 인벤토리 + B-1 manifest
    assert out["hashes"] == [] and out["attribution"] == [] and out["errors"] == []
    assert out["retention"] == [] and out["tmp_hash_index"] == {}
    assert out["hashed"] == 0 and out["stat_verified"] == 0 and out["content_unread"] == 0
    assert out["tmp_inventory"] == []
    assert out["acquired_hashes"] == {} and out["stat_only"] == []   # B-1: 빈 입력 → 빈 manifest


def test_scan_to_engine_default_unchanged():
    # collect_artifacts 미지정(기본 False) → 기존과 동일: QueryEngine 반환, events>0(무손실 불변).
    from clfx.web.api import scan_to_engine
    from clfx.query.engine import QueryEngine
    eng = scan_to_engine(["tests/fixtures/dot-claude"])
    assert isinstance(eng, QueryEngine)
    assert len(eng.events) > 0


def test_scan_to_engine_collect_artifacts_returns_pairs():
    # B-1: collect_artifacts=True → (engine, ev_root, by_origin, acquired_manifest) 4-튜플.
    #   acquired_manifest = jsonl 증거파일 매니페스트(str(path) → 64-hex sha256), parse 단계서 누적(재해시 X).
    from clfx.web.api import scan_to_engine
    from clfx.query.engine import QueryEngine
    from clfx.event import Event
    eng, ev_root, by_origin, acquired_manifest = scan_to_engine(
        ["tests/fixtures/dot-claude"], collect_artifacts=True)
    assert isinstance(eng, QueryEngine)
    assert isinstance(ev_root, list) and len(ev_root) == len(eng.events)
    e, root = ev_root[0]
    assert isinstance(e, Event) and isinstance(root, str)
    # ev_root의 Event는 엔진의 Event와 동일 객체(태그 포함 최종 상태) — 입력순 누적.
    assert ev_root[0][0] is eng.events[0]
    # OPT-8: by_origin는 dict (origin → count). 옛 post-scan 루프 결과와 동일.
    assert isinstance(by_origin, dict)
    ref = {}
    for ev in eng.events:
        for t in ev.tags:
            if t.startswith("origin:"):
                k = t[len("origin:"):]
                ref[k] = ref.get(k, 0) + 1
    assert by_origin == ref
    # B-1: acquired_manifest는 path → 64-hex sha 매니페스트. fixture jsonl이 ≥1개 잡힘.
    assert isinstance(acquired_manifest, dict) and len(acquired_manifest) > 0
    import re as _re
    for p, sha in acquired_manifest.items():
        assert isinstance(p, str)
        assert _re.fullmatch(r"[0-9a-f]{64}", sha)
    # 엔진 부착 evidence_manifest와 동일(단일 진실원천).
    assert acquired_manifest == eng.evidence_manifest


# ── B-1: acquisition manifest (acquired_hashes / stat_only) ────────────
def test_hash_clusters_acquisition_manifest(tmp_path):
    # dup-size 2개(콘텐츠 판독 → acquired_hashes) + unique-size 1개(미판독 → stat_only).
    dup_a = tmp_path / "a.txt"; dup_a.write_text("SAME", encoding="utf-8")     # size 4
    dup_b = tmp_path / "b.txt"; dup_b.write_text("ALSO", encoding="utf-8")     # size 4 (동일 크기, 다른 내용)
    uniq = tmp_path / "c.txt"; uniq.write_text("UNIQUE-SIZE", encoding="utf-8")  # size 11 (유일 크기)
    out = A.hash_clusters([], tmp_dirs=[str(tmp_path)])

    targets = {str(dup_a), str(dup_b), str(uniq)}
    acquired = out["acquired_hashes"]
    stat_only = out["stat_only"]

    # acquired_hashes 키는 targets의 부분집합 + 기존 per-file sha와 정확히 일치(재해시 아님).
    assert set(acquired).issubset(targets)
    assert set(acquired) == {str(dup_a), str(dup_b)}
    assert acquired[str(dup_a)] == hashlib.sha256(dup_a.read_bytes()).hexdigest()
    assert acquired[str(dup_b)] == hashlib.sha256(dup_b.read_bytes()).hexdigest()

    # stat_only = unique-size 파일 정확히(콘텐츠 미판독, 가짜 해시 없음).
    assert stat_only == [str(uniq)]

    # 교집합 0.
    assert set(acquired).isdisjoint(set(stat_only))

    # 길이 검산: targets = acquired + stat_only(+ 해시실패; 여기선 0).
    assert out["stat_verified"] == len(acquired) + len(stat_only)
    assert len(targets) == len(acquired) + len(stat_only)


def test_hash_clusters_acquired_subset_of_targets_real_root(tmp_path):
    # 참조+tmp 혼합: acquired_hashes 키 ⊆ targets, stat_only는 정렬·교집합 0(불변식 회귀).
    a = tmp_path / "x.bin"; a.write_bytes(b"1234567890")
    b = tmp_path / "y.bin"; b.write_bytes(b"0987654321")   # 동일 size 10
    out = A.hash_clusters([], tmp_dirs=[str(tmp_path)])
    assert set(out["acquired_hashes"]) == {str(a), str(b)}
    assert out["stat_only"] == []
    assert out["stat_verified"] == len(out["acquired_hashes"]) + len(out["stat_only"])


# ── B-1/B-2: chain-of-custody attestation payload ──────────────────
_ATTEST_NOTE = ("라이브 제자리 분석(Claude OFF·증거 정적). 취득 시 SHA-256 매니페스트 기록. "
                "비변경은 도구가 쓰기 syscall 0·전 open 읽기전용임으로 보장"
                "(전후 재해싱은 round5 성능 위해 미수행, 필요 시 재검증 옵션).")


def test_attestation_payload_contract_shape():
    from clfx.web.api import attestation_payload
    out = attestation_payload({}, {"acquired_hashes": {}, "stat_only": []})
    assert set(out) == {"acquired", "acquired_count", "stat_only_count",
                        "all_read_only", "modes_seen", "write_delete_rename_ops", "note"}
    assert out["acquired"] == []
    assert out["acquired_count"] == 0
    assert out["stat_only_count"] == 0
    assert out["all_read_only"] is True
    assert out["write_delete_rename_ops"] == 0
    assert out["note"] == _ATTEST_NOTE
    assert isinstance(out["modes_seen"], list)


def test_attestation_payload_merges_and_sorts():
    from clfx.web.api import attestation_payload
    parse_manifest = {"/r/b.jsonl": "b" * 64, "/r/a.jsonl": "a" * 64}
    forensic_out = {"acquired_hashes": {"/t/z.env": "z" * 64, "/t/m.env": "m" * 64},
                    "stat_only": ["/t/uniq1", "/t/uniq2", "/t/uniq3"]}
    out = attestation_payload(parse_manifest, forensic_out)
    paths = [a["path"] for a in out["acquired"]]
    assert paths == sorted(paths)             # 결정성: path 정렬
    assert paths == ["/r/a.jsonl", "/r/b.jsonl", "/t/m.env", "/t/z.env"]
    assert all(set(a) == {"path", "sha256"} for a in out["acquired"])
    d = {a["path"]: a["sha256"] for a in out["acquired"]}
    assert d["/r/a.jsonl"] == "a" * 64 and d["/t/z.env"] == "z" * 64
    assert out["acquired_count"] == 4
    assert out["stat_only_count"] == 3


def test_attestation_payload_dedupes_by_path():
    # 같은 path가 parse_manifest와 acquired_hashes 양쪽에 있어도 1개로 dedupe(path별 1행).
    from clfx.web.api import attestation_payload
    sha = "f" * 64
    out = attestation_payload({"/shared/x": sha}, {"acquired_hashes": {"/shared/x": sha}, "stat_only": []})
    assert out["acquired_count"] == 1
    assert out["acquired"] == [{"path": "/shared/x", "sha256": sha}]


def test_attestation_payload_reuses_existing_hashes_no_rehash(monkeypatch):
    # B-1: attestation은 이미 계산된 해시만 재사용 — 추가 해시(hash_file) 호출 0(경로 커버리지로 증명).
    import clfx.analyze.artifacts as A
    from clfx.web.api import attestation_payload
    monkeypatch.setattr(A, "hash_file", lambda p: (_ for _ in ()).throw(
        AssertionError("attestation은 재해시 금지")))
    parse_manifest = {"/r/a.jsonl": "a" * 64}
    forensic_out = {"acquired_hashes": {"/t/leak.env": "e" * 64}, "stat_only": ["/t/uniq"]}
    out = attestation_payload(parse_manifest, forensic_out)
    # 모든 acquired path가 입력 매니페스트에서 그대로 왔는지(coverage = 재해시 없음).
    got = {a["path"] for a in out["acquired"]}
    assert got == {"/r/a.jsonl", "/t/leak.env"}


def test_attestation_payload_reflects_real_audit(tmp_path, monkeypatch):
    # B-2: 실제 read-only audit를 통과한 modes_seen/all_read_only가 계약에 반영.
    import os
    monkeypatch.setattr(os, "name", "posix")
    from clfx import roio
    from clfx.web.api import forensic_scan, attestation_payload
    tdir = tmp_path / "tmp"; tdir.mkdir()
    (tdir / "dup1").write_bytes(b"SAME\n")
    (tdir / "dup2").write_bytes(b"SAME\n")     # dup-size → 콘텐츠 해시(rb open)
    roio.reset_audit()
    full = forensic_scan([], roots=[], tmp_dirs=[str(tdir)])
    out = attestation_payload({}, full)
    assert out["acquired_count"] == 2          # dup1, dup2 콘텐츠 판독
    assert out["all_read_only"] is True
    assert out["write_delete_rename_ops"] == 0
    assert set(out["modes_seen"]).issubset({"r", "rb"})
    assert "rb" in out["modes_seen"]           # 해시 read는 rb


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


# ── [F1] UNC WSL 경로 해석(완전성 갭) ──────────────────────────────
def test_resolve_unc_wsl_on_windows(monkeypatch):
    # Windows: UNC를 직접 접근(역슬래시 정규화), 빈 리스트가 아님(완전성).
    monkeypatch.setattr(os, "name", "nt")
    got = A.resolve_candidates(
        r"\\wsl.localhost\Ubuntu\home\u\x.env",
        r"\\wsl.localhost\Ubuntu\home\u\.claude",
    )
    assert got == [r"\\wsl.localhost\Ubuntu\home\u\x.env"]
    assert got != []


def test_resolve_unc_wsl_on_linux(monkeypatch):
    # posix: UNC → distro 내부 POSIX 경로, 빈 리스트가 아님(완전성).
    monkeypatch.setattr(os, "name", "posix")
    got = A.resolve_candidates(
        r"\\wsl.localhost\Ubuntu\home\u\x.env",
        r"\\wsl.localhost\Ubuntu\home\u\.claude",
    )
    assert got == ["/home/u/x.env"]
    assert got != []


def test_resolve_unc_wsl_dollar_mnt_on_linux(monkeypatch):
    # posix: \\wsl$\<distro>\mnt\c\x → /mnt/c/x.
    monkeypatch.setattr(os, "name", "posix")
    got = A.resolve_candidates(
        r"\\wsl$\Ubuntu\mnt\c\x",
        r"\\wsl$\Ubuntu\home\u\.claude",
    )
    assert got == ["/mnt/c/x"]
    assert got != []


# ── [F2] _walk_tmp onerror 콜백(완전성 직격) ───────────────────────
def test_walk_tmp_records_walk_onerror_in_errors(tmp_path, monkeypatch):
    # os.walk가 목록조회 불가 하위 디렉터리에서 onerror를 호출 → walk_errors로 기록(무skip).
    def fake_walk(d, topdown=True, followlinks=False, onerror=None):
        if onerror:
            onerror(OSError(13, "Permission denied", "/tmp/locked"))
        return iter([])

    monkeypatch.setattr("clfx.analyze.artifacts.os.walk", fake_walk)
    files, errors = A._walk_tmp([str(tmp_path)])   # tmp_path 실재 → isdir 통과
    assert any(e["path"] == "/tmp/locked" for e in errors)


# ── OPT-1: 공유 tmp 인벤토리(단일 walk, 재-stat 금지) ───────────────
def test_build_tmp_inventory_keeps_stat_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    (tmp_path / "a").write_bytes(b"hello")
    (tmp_path / "b").write_bytes(b"xy")
    inv = A.build_tmp_inventory([str(tmp_path)])
    assert set(inv) == {"files", "errors"}
    recs = inv["files"]
    assert [r["path"] for r in recs] == sorted([str(tmp_path / "a"), str(tmp_path / "b")])
    for r in recs:
        assert set(r) >= {"path", "size", "mtime", "atime", "mode"}
        assert r["mtime"].endswith("Z") and r["atime"].endswith("Z")
    a = next(r for r in recs if r["path"] == str(tmp_path / "a"))
    assert a["size"] == 5


def test_build_tmp_inventory_skips_symlink_and_nonregular(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    (tmp_path / "reg").write_bytes(b"ok")
    link = tmp_path / "link"
    try:
        os.symlink(str(tmp_path / "reg"), str(link))
    except (AttributeError, OSError, NotImplementedError):
        import pytest
        pytest.skip("symlink unavailable")
    inv = A.build_tmp_inventory([str(tmp_path)])
    paths = [r["path"] for r in inv["files"]]
    assert str(tmp_path / "reg") in paths
    assert str(link) not in paths
    assert all(e["path"] != str(link) for e in inv["errors"])


def test_build_tmp_inventory_records_stat_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    bad = tmp_path / "racy"
    bad.write_bytes(b"x")
    real_lstat = os.lstat

    def fake_lstat(p, *a, **k):
        if str(p) == str(bad):
            raise PermissionError("denied")
        return real_lstat(p, *a, **k)

    monkeypatch.setattr(os, "lstat", fake_lstat)
    inv = A.build_tmp_inventory([str(tmp_path)])
    assert all(r["path"] != str(bad) for r in inv["files"])
    assert {"path": str(bad), "reason": "PermissionError"} in inv["errors"]


def test_walk_tmp_derives_from_inventory(tmp_path, monkeypatch):
    # _walk_tmp는 인벤토리에서 파생 — 파일 목록은 인벤토리 path와 동일.
    monkeypatch.setattr(os, "name", "posix")
    (tmp_path / "a").write_bytes(b"a")
    (tmp_path / "b").write_bytes(b"bb")
    files, errors = A._walk_tmp([str(tmp_path)])
    inv = A.build_tmp_inventory([str(tmp_path)])
    assert files == [r["path"] for r in inv["files"]]
    assert errors == inv["errors"]


def test_hash_clusters_uses_given_inventory_no_rewalk(tmp_path, monkeypatch):
    # inventory 주입 시 두 번째 walk 금지 — os.walk가 호출되면 실패시킨다.
    monkeypatch.setattr(os, "name", "posix")
    tdir = tmp_path / "tmp"; tdir.mkdir()
    (tdir / "a").write_bytes(b"DUP\n")
    (tdir / "b").write_bytes(b"DUP\n")
    inv = A.build_tmp_inventory([str(tdir)])

    def boom(*a, **k):
        raise AssertionError("re-walked despite inventory")

    monkeypatch.setattr("clfx.analyze.artifacts.os.walk", boom)
    monkeypatch.setattr("clfx.analyze.artifacts.os.scandir", boom)
    out = A.hash_clusters([], tmp_dirs=[str(tdir)], inventory=inv)
    cl = [c for c in out["hashes"] if c["count"] >= 2]
    assert len(cl) == 1 and cl[0]["count"] == 2


def test_tmp_retention_uses_given_inventory_no_restat(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    f = tmp_path / "leak.txt"
    f.write_text("secret payload", encoding="utf-8")
    inv = A.build_tmp_inventory([str(tmp_path)])
    now = f.stat().st_mtime + 10 * 86400

    def boom(*a, **k):
        raise AssertionError("re-stat despite inventory")

    monkeypatch.setattr("clfx.analyze.artifacts.os.stat", boom)
    monkeypatch.setattr("clfx.analyze.artifacts.os.walk", boom)
    out = A.tmp_retention([str(tmp_path)], now_epoch=now, inventory=inv)
    rows = out["retention"]
    assert len(rows) == 1 and rows[0]["path"] == str(f)
    assert abs(rows[0]["age_days"] - 10.0) < 0.01


def test_tmp_retention_inventory_equivalence(tmp_path, monkeypatch):
    # inventory 유무 결과 동일(무손실).
    monkeypatch.setattr(os, "name", "posix")
    (tmp_path / "a.txt").write_text("aaa")
    (tmp_path / "b.txt").write_text("bbbb")
    f = tmp_path / "a.txt"
    now = f.stat().st_mtime + 5 * 86400
    no_inv = A.tmp_retention([str(tmp_path)], now_epoch=now)
    inv = A.build_tmp_inventory([str(tmp_path)])
    with_inv = A.tmp_retention([str(tmp_path)], now_epoch=now, inventory=inv)
    assert no_inv == with_inv


# ── OPT-2: 공유 참조 해석 캐시 ─────────────────────────────────────
def _mk_ev(ts, action, target, tmp_path, actor="user", tags=None):
    from clfx.event import Event, Source
    return Event(ts, "claude", "s", actor, action, target, "", Source("h", 1), tags or [])


def test_build_reference_resolution_dedupes_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    p = tmp_path / "x.txt"
    p.write_bytes(b"data")
    root = str(tmp_path)
    ev1 = _mk_ev("2026-06-16T01:00:00Z", "read", str(p), tmp_path)
    ev2 = _mk_ev("2026-06-16T02:00:00Z", "write", str(p), tmp_path)  # same (root,target)
    m = A.build_reference_resolution([(ev1, root), (ev2, root)])
    assert (root, str(p)) in m
    entry = m[(root, str(p))]
    assert entry["real"] == str(p)
    assert entry["st"] is not None and entry["st"].st_size == 4


def test_hash_clusters_resolved_equivalence(tmp_path, monkeypatch):
    # 중복 (root,target) 이벤트 fixture에서 resolved 유무 결과 동일.
    monkeypatch.setattr(os, "name", "posix")
    proj = tmp_path / "proj"; tdir = tmp_path / "tmp"
    proj.mkdir(); tdir.mkdir()
    (proj / "orig.env").write_bytes(b"SECRET=1\n")
    (tdir / "leaked.env").write_bytes(b"SECRET=1\n")
    root = str(tmp_path)
    evs = [
        (_mk_ev("2026-06-16T01:00:00Z", "paste", str(proj / "orig.env"), tmp_path, tags=["secret"]), root),
        (_mk_ev("2026-06-16T03:00:00Z", "read", str(proj / "orig.env"), tmp_path, tags=["secret"]), root),  # dup
    ]
    no_res = A.hash_clusters(evs, tmp_dirs=[str(tdir)])
    inv = A.build_tmp_inventory([str(tdir)])
    res = A.build_reference_resolution(evs)
    with_res = A.hash_clusters(evs, tmp_dirs=[str(tdir)], inventory=inv, resolved=res)
    assert no_res["missing"] == with_res["missing"]
    assert no_res["hashes"] == with_res["hashes"]


def test_attribution_join_resolved_equivalence(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    p = tmp_path / "todo.py"
    p.write_bytes(b"print(1)\n")
    root = str(tmp_path)
    evs = [
        (_mk_ev("2026-06-16T16:04:54Z", "write", str(p), tmp_path, actor="agent"), root),
        (_mk_ev("2026-06-16T17:04:54Z", "read", str(p), tmp_path, actor="agent"), root),  # dup path
    ]
    no_res = A.attribution_join(evs)
    res = A.build_reference_resolution(evs)
    with_res = A.attribution_join(evs, resolved=res)
    assert no_res == with_res


# ── OPT-3: size-prefilter 해싱 + 투명 리포팅 ───────────────────────
def test_hash_clusters_size_prefilter_lossless(tmp_path, monkeypatch):
    # dup-content + unique-size 혼합 → hashes[]가 전수 해시 참조와 byte-identical.
    monkeypatch.setattr(os, "name", "posix")
    tdir = tmp_path / "tmp"; tdir.mkdir()
    (tdir / "dup1").write_bytes(b"SAME\n")
    (tdir / "dup2").write_bytes(b"SAME\n")
    (tdir / "uniqA").write_bytes(b"a-different-size-1")
    (tdir / "uniqB").write_bytes(b"bb-different-size-22")
    out = A.hash_clusters([], tmp_dirs=[str(tdir)])
    # 참조: 모든 target을 해시(prefilter 없이)했을 때의 군집.
    import hashlib as _h
    allp = sorted([str(tdir / n) for n in ("dup1", "dup2", "uniqA", "uniqB")])
    groups = {}
    for p in allp:
        d = _h.sha256(open(p, "rb").read()).hexdigest()
        groups.setdefault(d, []).append(p)
    ref_clusters = sorted([d for d, ps in groups.items() if len(ps) >= 2])
    got_clusters = sorted([c["sha256"] for c in out["hashes"]])
    assert got_clusters == ref_clusters
    assert len(out["hashes"]) == 1            # dup만 클러스터
    # 투명 카운터
    assert out["hashed"] == 2                  # dup1, dup2만 콘텐츠 해시
    assert out["stat_verified"] == 4           # 전수 stat 커버
    assert out["content_unread"] == 2          # uniqA, uniqB는 미판독
    assert out["scanned"] == 4                 # scanned == stat_verified
    assert out["tmp_scanned"] == 4
    assert out["stat_verified"] == out["hashed"] + out["content_unread"]


def test_hash_clusters_tmp_hash_index_only_hashed(tmp_path, monkeypatch):
    # OPT-3: tmp_hash_index는 실제 해시된(dup-size) 파일로만 구성.
    monkeypatch.setattr(os, "name", "posix")
    tdir = tmp_path / "tmp"; tdir.mkdir()
    (tdir / "dup1").write_bytes(b"SAME\n")
    (tdir / "dup2").write_bytes(b"SAME\n")
    (tdir / "uniq").write_bytes(b"unique-content-here")
    out = A.hash_clusters([], tmp_dirs=[str(tdir)])
    idx = out["tmp_hash_index"]
    indexed = sorted(p for metas in idx.values() for p in (m["path"] for m in metas))
    assert indexed == sorted([str(tdir / "dup1"), str(tdir / "dup2")])


def test_build_tmp_hash_index_hashes_full_inventory(tmp_path, monkeypatch):
    # 서버 lazy reverse-search용: unique-size 포함 전수 해시.
    monkeypatch.setattr(os, "name", "posix")
    tdir = tmp_path / "tmp"; tdir.mkdir()
    (tdir / "dup1").write_bytes(b"SAME\n")
    (tdir / "dup2").write_bytes(b"SAME\n")
    (tdir / "uniq").write_bytes(b"unique-content-here")
    inv = A.build_tmp_inventory([str(tdir)])
    idx = A.build_tmp_hash_index(inv)
    indexed = sorted(p for metas in idx.values() for p in (m["path"] for m in metas))
    assert indexed == sorted([str(tdir / "dup1"), str(tdir / "dup2"), str(tdir / "uniq")])
    import hashlib as _h
    uniq_sha = _h.sha256(b"unique-content-here").hexdigest()
    assert uniq_sha in idx
    assert idx[uniq_sha][0]["path"] == str(tdir / "uniq")
    assert idx[uniq_sha][0]["mtime"].endswith("Z")
    # dup sha 메타는 path 정렬.
    dup_sha = _h.sha256(b"SAME\n").hexdigest()
    assert [m["path"] for m in idx[dup_sha]] == [str(tdir / "dup1"), str(tdir / "dup2")]


def test_build_tmp_hash_index_skips_hash_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    tdir = tmp_path / "tmp"; tdir.mkdir()
    (tdir / "x").write_bytes(b"abc")
    inv = A.build_tmp_inventory([str(tdir)])
    monkeypatch.setattr(A, "hash_file", lambda p: (_ for _ in ()).throw(PermissionError("x")))
    idx = A.build_tmp_hash_index(inv)
    assert idx == {}            # 해시 실패는 skip(인벤토리 errors에 이미 기록되는 stat 실패와 별개)


# ── OPT-7: 해시 진행 콜백 ──────────────────────────────────────────
def test_hash_clusters_on_hash_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    tdir = tmp_path / "tmp"; tdir.mkdir()
    (tdir / "dup1").write_bytes(b"SAME\n")
    (tdir / "dup2").write_bytes(b"SAME\n")
    (tdir / "uniq").write_bytes(b"unique-content-x")
    seen = []
    A.hash_clusters([], tmp_dirs=[str(tdir)], on_hash_progress=lambda done, total: seen.append((done, total)))
    assert seen                                  # 콜백 호출됨
    assert all(t == 2 for _d, t in seen)         # total = 해시 대상 수(dup 2개)
    assert seen[-1][0] == 2                       # 마지막 done == total
