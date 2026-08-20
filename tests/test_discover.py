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


def test_default_candidates_puts_codex_home_first_and_deduplicates_normalized_path(
        tmp_path, monkeypatch):
    import clfx.discover as d
    home = tmp_path / "Evidence" / "User"
    home.mkdir(parents=True)
    codex_home = "~/.CODEX/"

    def expanduser(path):
        if path == "~":
            return str(home)
        if path.startswith("~/"):
            return str(home / path[2:])
        return path

    monkeypatch.setenv("CODEX_HOME", codex_home)
    monkeypatch.setattr(d.os.path, "expanduser", expanduser)
    monkeypatch.setattr(d.os.path, "normcase", lambda path: path.lower())
    monkeypatch.setattr(d.glob, "glob", lambda _pat: [])
    monkeypatch.setattr(d, "_wsl_distros", lambda: [])
    cands = d._default_candidates()
    key = lambda path: d.os.path.normcase(d.os.path.normpath(d.os.path.expanduser(path)))
    assert cands[0] == codex_home
    assert sum(key(path) == key(codex_home) for path in cands) == 1


def test_default_candidates_adds_codex_to_all_four_families(monkeypatch):
    import clfx.discover as d
    monkeypatch.setattr(d.os.path, "expanduser",
                        lambda path: "/home/me" if path == "~" else path)
    monkeypatch.setenv("USERPROFILE", r"C:\Users\me")
    monkeypatch.setattr(d.glob, "glob", lambda pat: [
        "/mnt/c/Users/alice/.codex" if pat.endswith(".codex") else "/mnt/c/Users/alice/.claude"])
    monkeypatch.setattr(d, "_wsl_distros", lambda: ["Ubuntu"])
    monkeypatch.setattr(d, "_listdir_t", lambda _p: (["u"], False))

    cands = d._default_candidates()
    assert "/home/me/.codex" in cands
    assert r"C:\Users\me/.codex" in [p.replace("\\.codex", "/.codex") for p in cands]
    assert "/mnt/c/Users/alice/.codex" in cands
    assert any("wsl.localhost" in p and p.endswith(".codex") for p in cands)


def test_parse_wsl_list_utf16():
    from clfx.discover import _parse_wsl_list
    # wsl.exe -l -q 출력은 UTF-16LE (+ CRLF, 가끔 BOM/널)
    raw = "Ubuntu\r\nDebian\r\n".encode("utf-16-le")
    assert _parse_wsl_list(raw) == ["Ubuntu", "Debian"]


def test_parse_wsl_list_empty():
    from clfx.discover import _parse_wsl_list
    assert _parse_wsl_list(b"") == []
