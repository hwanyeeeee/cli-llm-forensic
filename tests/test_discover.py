from clfx.discover import discover_sources


def test_discovers_existing_claude_dirs(tmp_path):
    win = tmp_path / "winhome" / ".claude"; win.mkdir(parents=True)
    wsl = tmp_path / "wslhome" / ".claude"; wsl.mkdir(parents=True)
    # 후보 생성기를 주입(환경 비의존 — I4)
    cands = [str(win), str(wsl), str(tmp_path / "nope" / ".claude")]
    out = discover_sources(candidates=cands)
    paths = {o["path"]: o for o in out}
    assert paths[str(win)]["exists"] is True
    assert paths[str(wsl)]["exists"] is True
    assert paths[str(tmp_path / "nope" / ".claude")]["exists"] is False
    assert all("label" in o for o in out)        # origin 라벨 부여


def test_labels_match_origin_rule():
    # label은 cli._origin_label과 동일 규칙(단일 출처). 경로별 origin 판정 검증.
    cands = [
        r"\\wsl.localhost\Ubuntu\home\u\.claude",   # wsl
        r"C:\Users\u\.claude",                       # windows
        "/home/u/.claude",                           # wsl (posix home)
        "/mnt/c/Users/u/.claude",                    # windows (마운트)
        "relative/.claude",                          # other
    ]
    out = {o["path"]: o["label"] for o in discover_sources(candidates=cands)}
    assert out[r"\\wsl.localhost\Ubuntu\home\u\.claude"] == "wsl"
    assert out[r"C:\Users\u\.claude"] == "windows"
    assert out["/home/u/.claude"] == "wsl"
    assert out["/mnt/c/Users/u/.claude"] == "windows"
    assert out["relative/.claude"] == "other"


def test_preserves_candidate_order_and_count():
    # 주입 후보를 1:1로 순서 보존 매핑(dedup은 _default_candidates 책임).
    cands = ["/a/.claude", "/b/.claude", "/c/.claude"]
    out = discover_sources(candidates=cands)
    assert [o["path"] for o in out] == cands


def test_default_candidates_includes_windows_mount(monkeypatch):
    # WSL에서 실행 시 /mnt/c/Users/*/.claude 후보 포함. 환경무관(glob monkeypatch=I4).
    import clfx.discover as d
    monkeypatch.setattr(d.glob, "glob", lambda pat: ["/mnt/c/Users/alice/.claude"])
    cands = d._default_candidates()
    assert "/mnt/c/Users/alice/.claude" in cands
